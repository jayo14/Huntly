import json
import os
import re
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse, FileResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.conf import settings

from .models import Resume, ApplicationDocument, ResumeImport
from .document_generator import (
    generate_docx,
    generate_pdf,
    generate_cover_letter_docx,
    generate_cover_letter_pdf,
    DocumentGenerationError
)
from .services.importer import process_resume_import_file
from .services.merger import apply_import_to_profile
from .services.extractor import (
    DocumentExtractionError,
    DocumentFormatError,
    DocumentOversizedError,
    get_max_upload_size,
)
from huntly.storage import local_file


@login_required
def resume_list(request):
    """List candidate's career profiles and show Master Profile status."""
    resumes = Resume.objects.filter(user=request.user).order_by('-is_master', '-updated_at')
    return render(request, 'resumes/resume_list.html', {'resumes': resumes})


def save_resume_data(resume, data, files, user=None):
    """Save structured Master Career Profile data from validated dictionary."""
    if user is not None:
        resume.user = user

    resume.full_name = data.get('full_name', '')
    resume.tagline = data.get('tagline', '')
    resume.location = data.get('location', '')
    resume.email = data.get('email', '')
    resume.phone = data.get('phone', '')
    resume.linkedin = data.get('linkedin', '')
    resume.github = data.get('github', '')
    resume.portfolio = data.get('portfolio', '')
    resume.website = data.get('website', '')
    resume.summary = data.get('summary', '')

    resume.target_roles = data.get('target_roles', [])
    resume.work_preferences = data.get('work_preferences', {})
    resume.technical_skills = data.get('technical_skills', [])
    resume.experiences = data.get('experiences', [])
    resume.projects = data.get('projects', [])
    resume.certifications = data.get('certifications', [])
    resume.education = data.get('education', [])
    resume.include_branding = data.get('include_branding', False)
    resume.accent_color = data.get('accent_color', '#102a1f')

    if files.get('passport_photo'):
        from huntly.security import validate_uploaded_image
        photo = files.get('passport_photo')
        validate_uploaded_image(photo, max_size_bytes=5 * 1024 * 1024)
        resume.passport_photo = photo

    resume.save()

    # Consolidate master status if set
    if data.get('is_master', True) or not Resume.objects.filter(user=resume.user, is_master=True).exists():
        resume.consolidate_as_master()

    return resume


@login_required
def resume_create(request):
    """Create a new Master Career Profile with step-by-step guidance."""
    if request.method == 'POST':
        if request.content_type == 'application/json':
            data = json.loads(request.body)
            files = {}
        else:
            data = json.loads(request.POST.get('data', '{}'))
            files = request.FILES

        resume = Resume(user=request.user)
        resume = save_resume_data(resume, data, files, user=request.user)

        # Validate by generating test docx
        try:
            generate_docx(data)
        except DocumentGenerationError as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

        if request.headers.get('HX-Request'):
            return HttpResponse(status=204, headers={'HX-Trigger': 'resumeCreated'})

        if request.content_type == 'application/json':
            return JsonResponse({'status': 'success', 'resume_id': resume.id})
        return redirect('resumes:resume-list')

    return render(request, 'resumes/resume_form.html', {'resume_data': {}, 'resume_data_json': '{}'})


@login_required
def resume_update(request, pk):
    """Update existing career profile with rich experiences, accomplishments, and skills."""
    resume = get_object_or_404(Resume, pk=pk, user=request.user)

    if request.method == 'POST':
        if request.content_type == 'application/json':
            data = json.loads(request.body)
            files = {}
        else:
            data = json.loads(request.POST.get('data', '{}'))
            files = request.FILES

        resume = save_resume_data(resume, data, files, user=request.user)

        try:
            generate_docx(data)
        except DocumentGenerationError as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

        if request.headers.get('HX-Request'):
            return HttpResponse(status=204, headers={'HX-Trigger': 'resumeUpdated'})

        if request.content_type == 'application/json':
            return JsonResponse({'status': 'success', 'resume_id': resume.id})
        return redirect('resumes:resume-list')

    resume_data = {
        'id': resume.id,
        'full_name': resume.full_name,
        'tagline': resume.tagline,
        'location': resume.location,
        'email': resume.email,
        'phone': resume.phone,
        'linkedin': resume.linkedin,
        'github': resume.github,
        'portfolio': resume.portfolio,
        'website': resume.website,
        'summary': resume.summary,
        'target_roles': resume.target_roles,
        'work_preferences': resume.work_preferences,
        'technical_skills': resume.technical_skills,
        'experiences': resume.experiences,
        'projects': resume.projects,
        'certifications': resume.certifications,
        'education': resume.education,
        'include_branding': resume.include_branding,
        'accent_color': resume.accent_color,
        'is_master': resume.is_master,
        'passport_photo_url': resume.passport_photo.url if resume.passport_photo else None,
    }
    for exp in resume_data['experiences']:
        bullets = exp.get('accomplishments') or exp.get('bullets', [])
        exp['bulletsText'] = '\n'.join(bullets) if isinstance(bullets, list) else str(bullets)
    for proj in resume_data['projects']:
        proj_bullets = proj.get('bullets', [])
        proj['bulletsText'] = '\n'.join(proj_bullets) if isinstance(proj_bullets, list) else str(proj_bullets)

    return render(
        request,
        'resumes/resume_form.html',
        {'resume_data': resume_data, 'resume_data_json': json.dumps(resume_data)}
    )


@login_required
@require_POST
def resume_delete(request, pk):
    """Delete a non-master resume with confirmation and ownership enforcement."""
    resume = get_object_or_404(Resume, pk=pk, user=request.user)
    name = resume.full_name
    resume.delete()
    messages.info(request, f"Profile '{name}' deleted.")
    return redirect('resumes:resume-list')


@login_required
@require_POST
def make_master_profile(request, pk):
    """Explicitly designate a profile as the canonical Master Career Profile."""
    resume = get_object_or_404(Resume, pk=pk, user=request.user)
    resume.consolidate_as_master()
    messages.success(request, f"'{resume.full_name}' is now your canonical Master Career Profile.")
    return redirect('resumes:resume-list')


@login_required
def resume_preview_partial(request, pk):
    """Render modal partial preview of resume."""
    resume = get_object_or_404(Resume, pk=pk, user=request.user)
    return render(request, 'resumes/partials/resume_preview.html', {'resume': resume})


@login_required
def resume_download(request, pk):
    """Download an ATS-friendly resume in verified DOCX or PDF format."""
    resume = get_object_or_404(Resume, pk=pk, user=request.user)
    data = {
        'full_name': resume.full_name,
        'tagline': resume.tagline,
        'location': resume.location,
        'email': resume.email,
        'phone': resume.phone,
        'linkedin': resume.linkedin,
        'github': resume.github,
        'portfolio': resume.portfolio,
        'website': resume.website,
        'summary': resume.summary,
        'technical_skills': resume.technical_skills,
        'experiences': resume.experiences,
        'projects': resume.projects,
        'certifications': resume.certifications,
        'education': resume.education,
        'include_branding': resume.include_branding,
        'accent_color': resume.accent_color,
    }

    job = None
    job_id = request.GET.get('job_id')
    if job_id:
        from leads.models import JobApplication
        job = JobApplication.objects.filter(pk=job_id, user=request.user).first()
        if job and job.tailored_resume_text:
            data['summary'] = f"{resume.summary}\n\n[Tailored Target: {job.role_title} at {job.company_name}]\n{job.tailored_resume_text}"

    clean_name = re.sub(r'[^a-zA-Z0-9_-]', '_', resume.full_name or 'Candidate').strip('_')
    company_suffix = f"_{re.sub(r'[^a-zA-Z0-9_-]', '_', job.company_name)}" if job else ""

    fmt = request.GET.get('format', 'docx').lower()
    if fmt == 'pdf':
        from billing.services import get_or_create_subscription
        sub = get_or_create_subscription(request.user)
        if not sub.can_access_feature('can_export_pdf'):
            fmt = 'docx'
            messages.info(request, "PDF export is a premium feature on Job Sprint & Pro Hunter. Downloaded your ATS-friendly DOCX resume instead.")

    try:
        if fmt == 'pdf':
            pdf_bytes = generate_pdf(data)
            response = HttpResponse(pdf_bytes, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="Huntly_Resume_{clean_name}{company_suffix}.pdf"'
            return response
        else:
            docx_bytes = generate_docx(data)
            response = HttpResponse(
                docx_bytes,
                content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            )
            response['Content-Disposition'] = f'attachment; filename="Huntly_Resume_{clean_name}{company_suffix}.docx"'
            return response
    except Exception as e:
        messages.error(request, f"Failed to generate resume document. {e}")
        return redirect('resumes:resume-list')


@login_required
def cover_letter_download(request, job_id):
    """Download a tailored, role-specific cover letter in DOCX or PDF format."""
    from leads.models import JobApplication
    job = get_object_or_404(JobApplication, pk=job_id, user=request.user)
    resume = Resume.objects.filter(user=request.user, is_master=True).first() or Resume.objects.filter(user=request.user).first()

    candidate_name = getattr(resume, 'full_name', '') or request.user.get_full_name() or request.user.username
    candidate_email = getattr(resume, 'email', '') or request.user.email
    clean_name = re.sub(r'[^a-zA-Z0-9_-]', '_', candidate_name).strip('_')
    company_suffix = re.sub(r'[^a-zA-Z0-9_-]', '_', job.company_name).strip('_')

    fmt = request.GET.get('format', 'pdf').lower()
    letter_text = job.cover_letter or f"Application for {job.role_title} at {job.company_name}."

    try:
        if fmt == 'docx':
            docx_bytes = generate_cover_letter_docx(
                candidate_name=candidate_name,
                candidate_contact=candidate_email,
                company_name=job.company_name,
                role_title=job.role_title,
                letter_body=letter_text
            )
            response = HttpResponse(
                docx_bytes,
                content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            )
            response['Content-Disposition'] = f'attachment; filename="Huntly_Cover_Letter_{clean_name}_{company_suffix}.docx"'
            return response
        else:
            pdf_bytes = generate_cover_letter_pdf(
                candidate_name=candidate_name,
                candidate_contact=candidate_email,
                company_name=job.company_name,
                role_title=job.role_title,
                letter_body=letter_text
            )
            response = HttpResponse(pdf_bytes, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="Huntly_Cover_Letter_{clean_name}_{company_suffix}.pdf"'
            return response
    except Exception as e:
        messages.error(request, f"Cover letter generation failed: {e}")
        return redirect('leads:lead-list')


@login_required
def document_history(request, job_id):
    """View application document snapshot versions for a specific job."""
    from leads.models import JobApplication
    job = get_object_or_404(JobApplication, pk=job_id, user=request.user)
    docs = ApplicationDocument.objects.filter(job_application=job, user=request.user).order_by('-version')
    return render(request, 'resumes/partials/document_history_modal.html', {
        'job': job,
        'documents': docs,
    })


@login_required
def resume_import_upload(request):
    """Upload an existing resume (PDF/DOCX) and launch the extraction pipeline."""
    max_size_mb = get_max_upload_size() // (1024 * 1024)

    if request.method == 'POST':
        uploaded_file = request.FILES.get('resume_file')
        if not uploaded_file:
            messages.error(request, "Please choose a PDF or DOCX resume file to upload.")
            return render(request, 'resumes/import_upload.html', {'max_size_mb': max_size_mb})

        # Pre-check size
        if uploaded_file.size > get_max_upload_size():
            messages.error(
                request,
                f"The uploaded file ({uploaded_file.size / (1024 * 1024):.1f} MB) exceeds the {max_size_mb} MB limit."
            )
            return render(request, 'resumes/import_upload.html', {'max_size_mb': max_size_mb})

        # Pre-check extension
        ext = os.path.splitext(uploaded_file.name)[1].lower()
        if ext not in ('.pdf', '.docx'):
            messages.error(request, f"Unsupported file type '{ext}'. Please upload a PDF or Microsoft Word (.docx) file.")
            return render(request, 'resumes/import_upload.html', {'max_size_mb': max_size_mb})

        # Sanitize filename (prevent path traversal or malformed names)
        safe_filename = re.sub(r'[^a-zA-Z0-9_.-]', '_', os.path.basename(uploaded_file.name))

        # Create unconfirmed import draft
        import_obj = ResumeImport.objects.create(
            user=request.user,
            file=uploaded_file,
            file_name=safe_filename,
            file_type='pdf' if ext == '.pdf' else 'docx',
            file_size=uploaded_file.size,
            status='uploaded',
        )

        # Process through extraction and parsing pipeline
        import_obj = process_resume_import_file(import_obj)

        if import_obj.status == 'failed':
            messages.error(request, import_obj.error_message or "Failed to extract information from resume.")
            return render(request, 'resumes/import_upload.html', {
                'max_size_mb': max_size_mb,
                'import_error': import_obj.error_message,
                'is_scanned': import_obj.is_scanned,
            })

        return redirect('resumes:resume-import-review', import_id=import_obj.pk)

    return render(request, 'resumes/import_upload.html', {'max_size_mb': max_size_mb})


@login_required
def resume_import_review(request, import_id):
    """Interactive review interface for extracted resume candidate information."""
    import_obj = get_object_or_404(ResumeImport, pk=import_id, user=request.user)

    if import_obj.status == 'completed':
        messages.info(request, "This resume import has already been reviewed and saved to your Career Profile.")
        return redirect('resumes:resume-list')

    existing_master = Resume.objects.filter(user=request.user, is_master=True).first()
    parsed_data = import_obj.parsed_data or {}

    return render(request, 'resumes/import_review.html', {
        'import_obj': import_obj,
        'parsed_data': parsed_data,
        'parsed_data_json': json.dumps(parsed_data),
        'existing_master': existing_master,
        'warnings': import_obj.warnings or [],
    })


@login_required
@require_POST
def resume_import_confirm(request, import_id):
    """Save user-approved information into canonical Career Profile."""
    import_obj = get_object_or_404(ResumeImport, pk=import_id, user=request.user)

    if import_obj.status == 'completed':
        messages.info(request, "This import draft was already applied.")
        return redirect('resumes:resume-list')

    # Read submitted approved data
    approved_json = request.POST.get('approved_data')
    if approved_json:
        try:
            approved_data = json.loads(approved_json)
        except Exception:
            approved_data = import_obj.parsed_data
    elif request.content_type == 'application/json':
        try:
            approved_data = json.loads(request.body)
        except Exception:
            approved_data = import_obj.parsed_data
    else:
        # Fallback to current parsed data
        approved_data = import_obj.parsed_data

    merge_strategy = request.POST.get('merge_strategy', 'merge')

    # Apply approved data to user's Career Profile
    saved_profile = apply_import_to_profile(
        user=request.user,
        import_obj=import_obj,
        approved_data=approved_data,
        merge_strategy=merge_strategy
    )

    messages.success(
        request,
        f"Verified resume data saved! '{saved_profile.full_name}' is ready for tailoring."
    )
    return redirect('resumes:resume-update', pk=saved_profile.pk)


@login_required
@require_POST
def resume_import_cancel(request, import_id):
    """Cancel and delete an unconfirmed resume import draft and its private file."""
    import_obj = get_object_or_404(ResumeImport, pk=import_id, user=request.user)
    import_obj.delete()
    messages.info(request, "Resume import cancelled.")
    return redirect('resumes:resume-list')


@login_required
def resume_import_download(request, import_id):
    """Privately stream original uploaded resume document with ownership enforcement."""
    import_obj = get_object_or_404(ResumeImport, pk=import_id, user=request.user)
    if not import_obj.file:
        messages.error(request, "Original document file is no longer available.")
        return redirect('resumes:resume-list')

    # Stream file securely with generic octet-stream and attachment header
    response = FileResponse(import_obj.file.open('rb'), content_type='application/octet-stream')
    response['Content-Disposition'] = f'attachment; filename="{import_obj.file_name}"'
    return response

