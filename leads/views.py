import json
from django.conf import settings
from django.core.mail import EmailMessage, get_connection
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.http import HttpResponse, JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db import transaction
from django.db.models import Count, Q

from huntly.security import rate_limit
from .models import JobApplication, Lead, Message, AppSetting, ApplicationActivity
from resumes.models import Resume, ApplicationDocument
from .forms import JobApplicationForm, LeadForm, AppSettingForm, UserProfileForm, OutreachPitchForm, OutreachReplyForm
from .services.llm_tailor import tailor_application
from billing.services import (
    check_and_consume_tailored_application,
    check_tracked_job_limit,
    check_and_consume_outreach_pitch,
    get_user_entitlements,
)
from .services.outreach_service import (
    generate_grounded_pitch,
    create_or_update_draft,
    send_approved_outreach,
    record_manual_reply,
    cancel_reminder_or_draft,
    check_daily_quota,
    OutreachServiceError,
    QuotaExceededError,
    DuplicateSendError,
    InvalidRecipientError,
)


class CountableList(list):
    def count(self, *args):
        if not args:
            return len(self)
        return super().count(*args)


@login_required
def dashboard(request):
    """Candidate mission control dashboard with validated metrics and accurate funnel percentages."""
    user_jobs = JobApplication.objects.filter(user=request.user, is_archived=False)

    status_counts = dict(
        user_jobs.values('status')
        .annotate(count=Count('id'))
        .values_list('status', 'count')
    )
    total_jobs = sum(status_counts.values())

    saved_count = status_counts.get('saved', 0)
    applied_count = status_counts.get('applied', 0)
    interviewing_count = status_counts.get('interviewing', 0)
    offer_count = status_counts.get('offer', 0)
    rejected_count = status_counts.get('rejected', 0)

    # Active evaluated pipeline for callback rate
    evaluated_count = applied_count + interviewing_count + offer_count + rejected_count
    callback_rate = round(
        ((interviewing_count + offer_count) / max(1, evaluated_count) * 100), 1
    ) if evaluated_count > 0 else 0.0

    funnel_stages = [
        {
            'label': label,
            'status': status,
            'count': status_counts.get(status, 0),
            'percentage': round((status_counts.get(status, 0) / total_jobs * 100), 0) if total_jobs > 0 else 0
        }
        for status, label in JobApplication.STATUS_CHOICES
    ]

    recent_jobs = user_jobs.order_by('-updated_at')[:6]
    upcoming_interviews = user_jobs.filter(
        interview_date__isnull=False,
        interview_date__gte=timezone.now()
    ).order_by('interview_date')[:4]
    
    follow_ups_due = user_jobs.filter(
        next_follow_up__isnull=False,
        next_follow_up__lte=timezone.now().date()
    ).order_by('next_follow_up')[:4]

    context = {
        'total_jobs': total_jobs,
        'total_leads': total_jobs,
        'saved_count': saved_count,
        'applied_count': applied_count,
        'interviewing_count': interviewing_count,
        'offer_count': offer_count,
        'rejected_count': rejected_count,
        'callback_rate': callback_rate,
        'funnel_stages': funnel_stages,
        'recent_jobs': recent_jobs,
        'upcoming_interviews': upcoming_interviews,
        'follow_ups_due': follow_ups_due,
        'needs_attention': recent_jobs,
        'status_choices': JobApplication.STATUS_CHOICES,
    }

    if request.headers.get('HX-Request'):
        return render(request, 'leads/partials/dashboard_stats.html', context)

    return render(request, 'leads/dashboard.html', context)


@login_required
def lead_list(request):
    """Responsive job tracker list view with search, filtering, sorting, and pagination."""
    search = request.GET.get('search', '').strip()
    status = request.GET.get('status', '').strip()
    show_archived = request.GET.get('archived') == '1'
    sort = request.GET.get('sort', '-updated_at')

    # Allowed sort fields to defend against SQL / field injection
    allowed_sorts = {
        '-updated_at': '-updated_at',
        '-created_at': '-created_at',
        '-score': '-score',
        'company_name': 'company_name',
        'role_title': 'role_title',
        'next_follow_up': 'next_follow_up',
    }
    order_by_field = allowed_sorts.get(sort, '-updated_at')

    jobs_qs = JobApplication.objects.filter(user=request.user, is_archived=show_archived)

    if search:
        jobs_qs = jobs_qs.filter(
            Q(company_name__icontains=search) |
            Q(role_title__icontains=search) |
            Q(location__icontains=search) |
            Q(job_description__icontains=search)
        )

    if status and status in dict(JobApplication.STATUS_CHOICES):
        jobs_qs = jobs_qs.filter(status=status)

    jobs_qs = jobs_qs.order_by(order_by_field)

    # Pagination: 12 jobs per page
    paginator = Paginator(jobs_qs, 12)
    page_number = request.GET.get('page', 1)
    try:
        page_obj = paginator.get_page(page_number)
    except (PageNotAnInteger, EmptyPage):
        page_obj = paginator.get_page(1)

    context = {
        'jobs': page_obj,
        'leads': page_obj,  # Template alias
        'page_obj': page_obj,
        'is_paginated': page_obj.has_other_pages(),
        'status_choices': JobApplication.STATUS_CHOICES,
        'search': search,
        'selected_status': status,
        'current_sort': sort,
        'show_archived': show_archived,
        'total_count': paginator.count,
    }

    if request.headers.get('HX-Request'):
        return render(request, 'leads/partials/lead_list_table.html', context)
    return render(request, 'leads/leads_list.html', context)


@login_required
def lead_list_partial(request):
    return lead_list(request)


@login_required
def lead_create(request):
    """Add a new job application manually without forcing immediate resume tailoring."""
    allowed, limit_msg = check_tracked_job_limit(request.user)
    if not allowed and request.method == 'POST':
        messages.error(request, limit_msg)
        return redirect('leads:lead-list')

    if request.method == 'POST':
        form = JobApplicationForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                job = form.save(commit=False)
                job.user = request.user
                job.save()
                job.record_activity('created', f"Added job: {job.role_title} at {job.company_name}.")

            messages.success(request, f"Added {job.role_title} at {job.company_name}!")
            if request.headers.get('HX-Request'):
                return HttpResponse(status=204, headers={'HX-Trigger': 'leadsChanged'})
            return redirect('leads:lead-list')
    else:
        form = JobApplicationForm()

    return render(request, 'leads/lead_form.html', {'form': form})


@login_required
def lead_update(request, pk):
    """Update job details, interview dates, follow-up schedule, and notes."""
    job = get_object_or_404(JobApplication, pk=pk, user=request.user)
    old_status = job.status

    if request.method == 'POST':
        form = JobApplicationForm(request.POST, instance=job)
        if form.is_valid():
            with transaction.atomic():
                updated_job = form.save()
                if old_status != updated_job.status:
                    updated_job.transition_to_status(updated_job.status, notes="Updated via edit form")
                elif form.cleaned_data.get('notes'):
                    updated_job.record_activity('note_added', "Application details or notes updated.")

            messages.success(request, f"Updated {job.role_title} at {job.company_name}.")
            if request.headers.get('HX-Request'):
                return HttpResponse(status=204, headers={'HX-Trigger': 'leadsChanged'})
            return redirect('leads:lead-list')
    else:
        form = JobApplicationForm(instance=job)

    return render(request, 'leads/lead_form.html', {'form': form, 'lead': job, 'job': job})


@login_required
@require_POST
def lead_delete(request, pk):
    """Delete job application with strict ownership verification."""
    job = get_object_or_404(JobApplication, pk=pk, user=request.user)
    company = job.company_name
    job.delete()
    messages.info(request, f"Removed job application for {company}.")
    if request.headers.get('HX-Request'):
        return HttpResponse(status=204, headers={'HX-Trigger': 'leadsChanged'})
    return redirect('leads:lead-list')


@login_required
@require_POST
def lead_archive(request, pk):
    """Archive or unarchive a job application without data loss."""
    job = get_object_or_404(JobApplication, pk=pk, user=request.user)
    job.is_archived = not job.is_archived
    job.save(update_fields=['is_archived'])
    action = "archived" if job.is_archived else "restored to active pipeline"
    messages.info(request, f"{job.role_title} at {job.company_name} {action}.")
    if request.headers.get('HX-Request'):
        return HttpResponse(status=204, headers={'HX-Trigger': 'leadsChanged'})
    return redirect('leads:lead-list')


@login_required
@require_POST
def update_status(request, pk):
    """Transition application status with validation and activity history recording."""
    job = get_object_or_404(JobApplication, pk=pk, user=request.user)
    new_status = request.POST.get('status')
    notes = request.POST.get('notes', '')

    if new_status not in dict(JobApplication.STATUS_CHOICES):
        return HttpResponseBadRequest(f"Invalid status: {new_status}")

    job.transition_to_status(new_status, notes=notes)

    if request.headers.get('HX-Request'):
        return render(request, 'leads/partials/lead_row.html', {'lead': job, 'job': job})
    return redirect('leads:lead-list')


@login_required
def pipeline(request):
    """Kanban board visualizer across Saved, Applied, Interviewing, Offer, and Rejected."""
    all_jobs = list(
        JobApplication.objects.filter(user=request.user, is_archived=False)
        .prefetch_related('activities')
        .order_by('-score', '-updated_at')
    )

    jobs_by_status = {status: CountableList() for status, _ in JobApplication.STATUS_CHOICES}
    for job in all_jobs:
        if job.status in jobs_by_status:
            jobs_by_status[job.status].append(job)

    stages = [
        {
            'status': status,
            'label': label,
            'leads': jobs_by_status.get(status, CountableList()),
            'count': len(jobs_by_status.get(status, [])),
        }
        for status, label in JobApplication.STATUS_CHOICES
    ]

    context = {
        'stages': stages,
        'total_active_jobs': len(all_jobs),
        'status_choices': JobApplication.STATUS_CHOICES,
    }
    return render(request, 'leads/pipeline.html', context)


@login_required
def settings_view(request):
    """User outreach settings and SMTP credentials view."""
    setting = AppSetting.objects.filter(user=request.user).first()
    if not setting:
        setting = AppSetting.objects.create(user=request.user)

    if request.method == 'POST':
        form = AppSettingForm(request.POST, instance=setting)
        if form.is_valid():
            s = form.save(commit=False)
            s.user = request.user
            s.save()
            messages.success(request, "Settings updated successfully!")
            if request.headers.get('HX-Request'):
                return HttpResponse(status=204, headers={'HX-Trigger': 'settingsUpdated'})
            return redirect('leads:settings')
    else:
        form = AppSettingForm(instance=setting)

    return render(request, 'leads/settings.html', {'form': form})


@login_required
def lead_detail(request, pk):
    """Application detail view with requirements, documents, outreach, and timeline."""
    job = get_object_or_404(
        JobApplication.objects.prefetch_related('messages', 'activities', 'documents'),
        pk=pk,
        user=request.user
    )
    messages_list = job.messages.all().order_by('-created_at')
    activities_list = job.activities.all().order_by('-created_at')
    documents_list = job.documents.all().order_by('-version')
    resume = Resume.objects.filter(user=request.user, is_master=True).first() or Resume.objects.filter(user=request.user).first()

    # Quota check
    is_quota_allowed, remaining_quota, quota_limit = check_daily_quota(request.user)
    latest_draft = job.messages.filter(status='draft').first()

    context = {
        'lead': job,
        'job': job,
        'messages': messages_list,
        'activities': activities_list,
        'documents': documents_list,
        'resume': resume,
        'remaining_quota': remaining_quota,
        'quota_limit': quota_limit,
        'latest_draft': latest_draft,
    }
    return render(request, 'leads/lead_detail_modal.html', context)


@login_required
@require_POST
@rate_limit('generate_message', limit=20, period=60)
def generate_message(request, pk):
    job = get_object_or_404(JobApplication, pk=pk, user=request.user)
    resume = Resume.objects.filter(user=request.user, is_master=True).first() or Resume.objects.filter(user=request.user).first()

    # Determine version snapshot and check plan entitlements
    last_doc = ApplicationDocument.objects.filter(job_application=job).order_by('-version').first()
    next_version = (last_doc.version + 1) if last_doc else 1

    credit_ok, credit_msg = check_and_consume_tailored_application(request.user, job.pk, next_version)
    if not credit_ok:
        billing_url = reverse('billing:dashboard')
        return HttpResponse(
            f'<div class="p-4 bg-rose-50 border border-rose-300 rounded-2xl text-xs text-rose-900 font-semibold">'
            f'{credit_msg} <a href="{billing_url}" class="underline text-pink font-bold ml-1">Upgrade Plan</a></div>',
            status=403
        )

    tailored = tailor_application(
        resume=resume,
        company_name=job.company_name,
        role_title=job.role_title,
        job_description=job.job_description or f"{job.role_title} at {job.company_name}",
        contact_name=job.contact_name,
    )

    bullets = tailored.get('tailored_bullets', [])
    if isinstance(bullets, list):
        job.tailored_resume_text = "\n\n".join(f"• {b}" for b in bullets)
    else:
        job.tailored_resume_text = str(bullets)

    job.cover_letter = tailored.get('cover_letter', '')
    job.recruiter_pitch = tailored.get('recruiter_pitch', '')
    job.matched_keywords = tailored.get('matched_keywords', [])
    job.score = tailored.get('score', 65)
    job.save()

    # Create immutable application document snapshot with version history
    last_doc = ApplicationDocument.objects.filter(job_application=job).order_by('-version').first()
    next_version = (last_doc.version + 1) if last_doc else 1

    ApplicationDocument.objects.create(
        user=request.user,
        job_application=job,
        version=next_version,
        document_type='full_bundle',
        title=f"Application for {job.role_title} at {job.company_name}",
        tailored_resume_text=job.tailored_resume_text,
        cover_letter_text=job.cover_letter,
        recruiter_pitch_text=job.recruiter_pitch,
        match_score=job.score,
        match_assessment=tailored.get('match_assessment', {}),
        claims_for_verification=tailored.get('claims_for_verification', []),
        profile_snapshot={
            'full_name': getattr(resume, 'full_name', ''),
            'tagline': getattr(resume, 'tagline', ''),
            'skills': getattr(resume, 'technical_skills', []),
            'experiences': getattr(resume, 'experiences', []),
            'summary': getattr(resume, 'summary', ''),
        } if resume else {},
        job_snapshot={
            'company_name': job.company_name,
            'role_title': job.role_title,
            'job_description': job.job_description,
            'job_url': job.job_url,
        }
    )

    candidate_name = (
        getattr(resume, 'full_name', '') or
        request.user.get_full_name() or
        request.user.username
    )
    subject = f"Application: {job.role_title} - {candidate_name}"
    body = job.recruiter_pitch

    # Also generate grounded pitch options through outreach service
    outreach_info = generate_grounded_pitch(
        resume=resume,
        job=job,
        contact_name=job.contact_name,
        contact_role=getattr(job, 'contact_role', '')
    )
    if not body:
        body = outreach_info['body']

    context = {
        'subject': subject,
        'body': body,
        'lead': job,
        'job': job,
        'cover_letter': job.cover_letter,
        'tailored_resume_text': job.tailored_resume_text,
        'matched_keywords': job.matched_keywords,
        'score': job.score,
        'doc_version': next_version,
        'match_assessment': tailored.get('match_assessment', {}),
        'claims_for_verification': tailored.get('claims_for_verification', []),
        'generation_method': tailored.get('generation_method', ''),
        'recipient_email': job.contact_email,
        'recipient_name': job.contact_name,
        'recipient_role': getattr(job, 'contact_role', ''),
    }
    return render(request, 'leads/partials/generated_message_fields.html', context)


@login_required
@require_POST
@rate_limit('send_message', limit=20, period=60)
def send_message(request, pk):
    """
    Handle outreach drafting or explicit confirmed send.
    Distinguishes draft, queued, accepted_by_provider, and failed.
    """
    job = get_object_or_404(JobApplication, pk=pk, user=request.user)
    subject = request.POST.get('subject', '').strip()
    body = request.POST.get('body', '').strip()
    recipient_email = request.POST.get('recipient_email', '').strip() or job.contact_email
    recipient_name = request.POST.get('recipient_name', '').strip() or job.contact_name
    recipient_role = request.POST.get('recipient_role', '').strip() or getattr(job, 'contact_role', '')
    confirmed = request.POST.get('confirm_send') in ['1', 'true', 'on', True]
    is_draft = request.POST.get('is_draft') in ['1', 'true', 'on', True]
    follow_up_str = request.POST.get('schedule_follow_up', '').strip()

    follow_up_date = None
    if follow_up_str:
        try:
            parsed_dt = timezone.datetime.strptime(follow_up_str, '%Y-%m-%d')
            follow_up_date = timezone.make_aware(parsed_dt)
        except ValueError:
            pass

    if not (subject and body):
        return HttpResponseBadRequest("Subject and pitch body are required.")

    # Save as Draft branch
    if is_draft:
        draft = create_or_update_draft(
            user=request.user,
            job=job,
            subject=subject,
            body=body,
            recipient_email=recipient_email,
            recipient_name=recipient_name,
            recipient_role=recipient_role,
            follow_up_reminder_at=follow_up_date
        )
        messages.success(request, f"Pitch draft saved for {job.company_name}.")
        if request.headers.get('HX-Request'):
            return HttpResponse(status=204, headers={'HX-Trigger': 'leadsChanged'})
        return redirect('leads:lead-list')

    # Explicit user confirmation check
    if not confirmed:
        return HttpResponseBadRequest(
            "Explicit user confirmation is required before sending recruiter outreach. "
            "Please check the confirmation box to approve sending."
        )

    # Check subscription entitlement for cold recruiter pitches
    pitch_ok, pitch_msg = check_and_consume_outreach_pitch(request.user, job.pk, recipient_email)
    if not pitch_ok:
        messages.error(request, pitch_msg)
        return HttpResponseBadRequest(pitch_msg)

    # First ensure draft is recorded
    draft = create_or_update_draft(
        user=request.user,
        job=job,
        subject=subject,
        body=body,
        recipient_email=recipient_email,
        recipient_name=recipient_name,
        recipient_role=recipient_role,
        follow_up_reminder_at=follow_up_date
    )

    try:
        success, status_msg, sent_msg = send_approved_outreach(
            message=draft,
            user=request.user,
            confirmed=True
        )

        if success:
            messages.success(request, f"Pitch email accepted by provider for delivery to {job.company_name}!")
            if request.headers.get('HX-Request'):
                return HttpResponse(status=204, headers={'HX-Trigger': 'leadsChanged'})
            return redirect('leads:lead-list')
        else:
            messages.error(request, status_msg)
            return HttpResponse(status_msg, status=502)

    except QuotaExceededError as e:
        messages.error(request, str(e))
        return HttpResponse(str(e), status=429)
    except DuplicateSendError as e:
        messages.warning(request, str(e))
        return HttpResponse(str(e), status=400)
    except InvalidRecipientError as e:
        messages.error(request, str(e))
        return HttpResponse(str(e), status=400)
    except OutreachServiceError as e:
        messages.error(request, str(e))
        return HttpResponse(str(e), status=400)
    except Exception as e:
        messages.error(request, f"Unexpected delivery error: {e}")
        return HttpResponse(f"Unexpected delivery error: {e}", status=500)


@login_required
@require_POST
def record_message_reply(request, pk):
    """Log a manual reply received from the recruiter or hiring manager."""
    message = get_object_or_404(Message, pk=pk, user=request.user)
    reply_notes = request.POST.get('reply_notes', '').strip()
    if not reply_notes:
        return HttpResponseBadRequest("Reply notes are required.")

    record_manual_reply(message, request.user, reply_notes=reply_notes)
    messages.success(request, f"Recorded reply for {message.job_application.company_name}.")
    if request.headers.get('HX-Request'):
        return HttpResponse(status=204, headers={'HX-Trigger': 'leadsChanged'})
    return redirect('leads:lead-list')


@login_required
@require_POST
def cancel_message_reminder(request, pk):
    """Cancel a pending message draft or clear a follow-up reminder."""
    message = get_object_or_404(Message, pk=pk, user=request.user)
    cancel_reminder_or_draft(message, request.user)
    messages.info(request, "Outreach item cancelled.")
    if request.headers.get('HX-Request'):
        return HttpResponse(status=204, headers={'HX-Trigger': 'leadsChanged'})
    return redirect('leads:lead-list')


@login_required
@require_POST
def verify_smtp_settings(request):
    """Safely verify SMTP credentials without dispatching an email."""
    setting = AppSetting.objects.filter(user=request.user).first()
    if not setting or not setting.email_address or not setting.email_password:
        return JsonResponse({'success': False, 'message': 'Incomplete SMTP credentials configured.'}, status=400)

    try:
        connection = get_connection(
            backend='django.core.mail.backends.smtp.EmailBackend',
            host=setting.smtp_host,
            port=setting.smtp_port,
            username=setting.email_address,
            password=setting.get_decrypted_email_password(),
            use_tls=(setting.smtp_port == 587),
            use_ssl=(setting.smtp_port == 465),
            timeout=8,
        )
        connection.open()
        connection.close()
        setting.is_verified = True
        setting.last_verified_at = timezone.now()
        setting.save(update_fields=['is_verified', 'last_verified_at'])
        return JsonResponse({'success': True, 'message': 'SMTP connection verified successfully!'})
    except Exception as exc:
        setting.is_verified = False
        setting.save(update_fields=['is_verified'])
        return JsonResponse({'success': False, 'message': f'Connection failed: {exc}'}, status=400)


@login_required
def profile_view(request):
    resume = Resume.objects.filter(user=request.user).first()
    return render(request, 'leads/profile.html', {'resume': resume})


@login_required
def profile_edit(request):
    resume = Resume.objects.filter(user=request.user).first()
    if request.method == 'POST':
        form = UserProfileForm(request.POST, request.FILES)
        if form.is_valid():
            user = request.user
            user.first_name = form.cleaned_data['first_name']
            user.last_name = form.cleaned_data['last_name']
            user.email = form.cleaned_data['email']
            user.save()

            if not resume:
                resume = Resume.objects.create(
                    user=user,
                    full_name=user.get_full_name() or user.username,
                    email=user.email,
                )
            resume.email = user.email
            resume.full_name = user.get_full_name() or resume.full_name or user.username
            resume.phone = form.cleaned_data['phone']
            resume.location = form.cleaned_data['location']
            resume.tagline = form.cleaned_data['tagline']

            if form.cleaned_data.get('remove_photo'):
                if resume.passport_photo:
                    resume.passport_photo.delete(save=False)
                    resume.passport_photo = None
            elif 'passport_photo' in request.FILES:
                resume.passport_photo = request.FILES['passport_photo']

            resume.save()
            messages.success(request, "Profile updated successfully!")

            if request.headers.get('HX-Request'):
                response = HttpResponse(status=204)
                response['HX-Redirect'] = reverse('leads:profile')
                return response
            return redirect('leads:profile')
    else:
        initial_data = {
            'first_name': request.user.first_name,
            'last_name': request.user.last_name,
            'email': request.user.email or (resume.email if resume else ''),
            'phone': resume.phone if resume else '',
            'location': resume.location if resume else '',
            'tagline': resume.tagline if resume else '',
        }
        form = UserProfileForm(initial=initial_data)

    return render(request, 'leads/profile_edit_modal.html', {
        'form': form,
        'resume': resume,
    })


@login_required
def profile_export(request):
    """Export all personal and career data belonging to the authenticated user in standard JSON format."""
    user = request.user
    resume = Resume.objects.filter(user=user).first()
    jobs = JobApplication.objects.filter(user=user).prefetch_related('messages')
    setting = AppSetting.objects.filter(user=user).first()

    data = {
        'export_metadata': {
            'generated_at': timezone.now().isoformat(),
            'platform': 'Huntly Job-Search Operating System',
            'version': '1.0',
        },
        'user': {
            'id': user.pk,
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'date_joined': user.date_joined.isoformat() if user.date_joined else None,
        },
        'career_profile': {
            'full_name': getattr(resume, 'full_name', ''),
            'email': getattr(resume, 'email', ''),
            'phone': getattr(resume, 'phone', ''),
            'location': getattr(resume, 'location', ''),
            'tagline': getattr(resume, 'tagline', ''),
            'linkedin': getattr(resume, 'linkedin', ''),
            'github': getattr(resume, 'github', ''),
            'portfolio': getattr(resume, 'portfolio', ''),
            'summary': getattr(resume, 'summary', ''),
            'technical_skills': getattr(resume, 'technical_skills', []),
            'experiences': getattr(resume, 'experiences', []),
            'projects': getattr(resume, 'projects', []),
            'education': getattr(resume, 'education', []),
            'certifications': getattr(resume, 'certifications', []),
        } if resume else None,
        'job_applications': [
            {
                'id': job.pk,
                'company_name': job.company_name,
                'role_title': job.role_title,
                'job_url': job.job_url,
                'job_description': job.job_description,
                'status': job.status,
                'score': job.score,
                'contact_name': job.contact_name,
                'contact_email': job.contact_email,
                'matched_keywords': job.matched_keywords,
                'cover_letter': job.cover_letter,
                'recruiter_pitch': job.recruiter_pitch,
                'tailored_resume_text': job.tailored_resume_text,
                'created_at': job.created_at.isoformat() if job.created_at else None,
                'updated_at': job.updated_at.isoformat() if job.updated_at else None,
                'messages': [
                    {
                        'id': msg.pk,
                        'subject': msg.subject,
                        'body': msg.body,
                        'sent_at': msg.sent_at.isoformat() if msg.sent_at else None,
                    }
                    for msg in job.messages.all()
                ]
            }
            for job in jobs
        ],
        'app_settings': {
            'daily_send_limit': setting.daily_send_limit if setting else 20,
            'default_tone': setting.default_tone if setting else 'professional',
            'auto_send': setting.auto_send if setting else False,
            'email_address': setting.email_address if setting else '',
            'smtp_host': setting.smtp_host if setting else '',
            'smtp_port': setting.smtp_port if setting else 587,
        } if setting else None,
    }

    response = JsonResponse(data, json_dumps_params={'indent': 2})
    response['Content-Disposition'] = f'attachment; filename="huntly_data_export_{user.username}_{timezone.now().strftime("%Y%m%d")}.json"'
    return response


@login_required
@require_POST
def profile_delete_account(request):
    """Permanently delete authenticated user and all associated career records upon password verification."""
    password = request.POST.get('password', '')
    user = request.user

    if not user.check_password(password):
        messages.error(request, "Incorrect password. Account deletion aborted.")
        return redirect('leads:profile')

    # Remove resume passport photo asset if present
    resumes = Resume.objects.filter(user=user)
    for res in resumes:
        if res.passport_photo:
            res.passport_photo.delete(save=False)

    username = user.username
    user.delete()
    logout(request)

    messages.info(request, f"Account '{username}' and all associated personal data have been permanently deleted.")
    return redirect('core:landing')
