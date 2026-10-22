import json
from django.conf import settings
from django.core.mail import EmailMessage, get_connection
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.http import HttpResponse
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Count, Q

from .models import JobApplication, Lead, Message, AppSetting
from resumes.models import Resume
from .forms import JobApplicationForm, LeadForm, AppSettingForm
from .services.llm_tailor import tailor_application


class CountableList(list):
    def count(self, *args):
        if not args:
            return len(self)
        return super().count(*args)


@login_required
def dashboard(request):
    user_jobs = JobApplication.objects.filter(user=request.user)

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

    active_applications = applied_count + interviewing_count + offer_count
    callback_rate = round(
        ((interviewing_count + offer_count) / active_applications * 100), 1
    ) if active_applications > 0 else 0.0

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

    context = {
        'total_jobs': total_jobs,
        'total_leads': total_jobs,  # For backward-compatible templates
        'saved_count': saved_count,
        'applied_count': applied_count,
        'interviewing_count': interviewing_count,
        'offer_count': offer_count,
        'rejected_count': rejected_count,
        'callback_rate': callback_rate,
        'funnel_stages': funnel_stages,
        'recent_jobs': recent_jobs,
        'needs_attention': recent_jobs,
        'status_choices': JobApplication.STATUS_CHOICES,
    }

    if request.headers.get('HX-Request'):
        return render(request, 'leads/partials/dashboard_stats.html', context)

    return render(request, 'leads/dashboard.html', context)


@login_required
def lead_list(request):
    search = request.GET.get('search', '')
    status = request.GET.get('status', '')

    jobs = JobApplication.objects.filter(user=request.user)

    if search:
        jobs = jobs.filter(
            Q(company_name__icontains=search) |
            Q(role_title__icontains=search) |
            Q(job_description__icontains=search)
        )

    if status:
        jobs = jobs.filter(status=status)

    context = {
        'jobs': jobs,
        'leads': jobs,  # Template alias
        'status_choices': JobApplication.STATUS_CHOICES,
        'search': search,
        'selected_status': status,
    }

    if request.headers.get('HX-Request'):
        return render(request, 'leads/partials/lead_list_table.html', context)
    return render(request, 'leads/leads_list.html', context)


@login_required
def lead_list_partial(request):
    return lead_list(request)


@login_required
def lead_create(request):
    if request.method == 'POST':
        form = JobApplicationForm(request.POST)
        if form.is_valid():
            job = form.save(commit=False)
            job.user = request.user
            job.save()
            messages.success(request, f"Added {job.role_title} at {job.company_name}!")
            if request.headers.get('HX-Request'):
                return HttpResponse(status=204, headers={'HX-Trigger': 'leadsChanged'})
            return redirect('leads:lead-list')
    else:
        form = JobApplicationForm()

    return render(request, 'leads/lead_form.html', {'form': form})


@login_required
def lead_update(request, pk):
    job = get_object_or_404(JobApplication, pk=pk, user=request.user)
    if request.method == 'POST':
        form = JobApplicationForm(request.POST, instance=job)
        if form.is_valid():
            form.save()
            messages.success(request, "Job application updated.")
            if request.headers.get('HX-Request'):
                return HttpResponse(status=204, headers={'HX-Trigger': 'leadsChanged'})
            return redirect('leads:lead-list')
    else:
        form = JobApplicationForm(instance=job)

    return render(request, 'leads/lead_form.html', {'form': form, 'lead': job})


@login_required
@require_POST
def lead_delete(request, pk):
    job = get_object_or_404(JobApplication, pk=pk, user=request.user)
    job.delete()
    if request.headers.get('HX-Request'):
        return HttpResponse(status=204, headers={'HX-Trigger': 'leadsChanged'})
    return redirect('leads:lead-list')


@login_required
@require_POST
def update_status(request, pk):
    job = get_object_or_404(JobApplication, pk=pk, user=request.user)
    status = request.POST.get('status')
    if status in dict(JobApplication.STATUS_CHOICES):
        job.status = status
        job.save()

    if request.headers.get('HX-Request'):
        return render(request, 'leads/partials/lead_row.html', {'lead': job})
    return redirect('leads:lead-list')


@login_required
def pipeline(request):
    all_jobs = list(JobApplication.objects.filter(user=request.user).order_by('-score', '-updated_at'))

    jobs_by_status = {status: CountableList() for status, _ in JobApplication.STATUS_CHOICES}
    for job in all_jobs:
        if job.status in jobs_by_status:
            jobs_by_status[job.status].append(job)

    stages = [
        {
            'status': status,
            'label': label,
            'leads': jobs_by_status.get(status, CountableList()),
        }
        for status, label in JobApplication.STATUS_CHOICES
    ]

    context = {'stages': stages}
    return render(request, 'leads/pipeline.html', context)


@login_required
def settings_view(request):
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
    job = get_object_or_404(JobApplication, pk=pk, user=request.user)
    messages_list = job.messages.all().order_by('-sent_at')
    resume = Resume.objects.filter(user=request.user).first()

    context = {
        'lead': job,
        'job': job,
        'messages': messages_list,
        'resume': resume,
    }
    return render(request, 'leads/lead_detail_modal.html', context)


@login_required
@require_POST
def generate_message(request, pk):
    job = get_object_or_404(JobApplication, pk=pk, user=request.user)
    resume = Resume.objects.filter(user=request.user).first()

    tailored = tailor_application(
        resume=resume,
        company_name=job.company_name,
        role_title=job.role_title,
        job_description=job.job_description or f"{job.role_title} at {job.company_name}",
    )

    bullets = tailored.get('tailored_bullets', [])
    if isinstance(bullets, list):
        job.tailored_resume_text = "\n\n".join(f"• {b}" for b in bullets)
    else:
        job.tailored_resume_text = str(bullets)

    job.cover_letter = tailored.get('cover_letter', '')
    job.recruiter_pitch = tailored.get('recruiter_pitch', '')
    job.matched_keywords = tailored.get('matched_keywords', [])

    keyword_bonus = min(50, len(job.matched_keywords) * 10)
    job.score = 50 + keyword_bonus
    job.save()

    candidate_name = (
        getattr(resume, 'full_name', '') or
        request.user.get_full_name() or
        request.user.username
    )
    subject = f"Application: {job.role_title} - {candidate_name}"
    body = job.recruiter_pitch

    context = {
        'subject': subject,
        'body': body,
        'lead': job,
        'job': job,
        'cover_letter': job.cover_letter,
        'tailored_resume_text': job.tailored_resume_text,
        'matched_keywords': job.matched_keywords,
        'score': job.score,
    }
    return render(request, 'leads/partials/generated_message_fields.html', context)


@login_required
@require_POST
def send_message(request, pk):
    job = get_object_or_404(JobApplication, pk=pk, user=request.user)
    subject = request.POST.get('subject')
    body = request.POST.get('body')

    if not (subject and body):
        return HttpResponse("Invalid form: subject and body are required", status=400)

    recipient = job.contact_email
    if not recipient:
        return HttpResponse("No contact email specified for this job application", status=400)

    setting = AppSetting.objects.filter(user=request.user).first()

    try:
        if setting and setting.smtp_host and setting.email_address and setting.email_password:
            connection = get_connection(
                backend='django.core.mail.backends.smtp.EmailBackend',
                host=setting.smtp_host,
                port=setting.smtp_port,
                username=setting.email_address,
                password=setting.email_password,
                use_tls=True,
            )
            email = EmailMessage(
                subject=subject,
                body=body,
                from_email=setting.email_address,
                to=[recipient],
                connection=connection,
            )
            email.send()
        elif getattr(settings, 'EMAIL_BACKEND', None):
            email = EmailMessage(
                subject=subject,
                body=body,
                from_email='noreply@huntly.local',
                to=[recipient],
            )
            email.send()
        else:
            raise ValueError("No email configuration found.")

        Message.objects.create(
            job_application=job,
            subject=subject,
            body=body
        )

        if job.status == 'saved':
            job.status = 'applied'
        job.last_contacted = timezone.now()
        job.save()

        messages.success(request, f"Pitch email sent to {job.company_name}!")
        return HttpResponse(status=204, headers={'HX-Trigger': 'leadsChanged'})

    except Exception as e:
        messages.error(request, f"Failed to send email: {e}")
        return HttpResponse(f"Failed to send email: {e}", status=500)


@login_required
def profile_view(request):
    resume = Resume.objects.filter(user=request.user).first()
    return render(request, 'leads/profile.html', {'resume': resume})
