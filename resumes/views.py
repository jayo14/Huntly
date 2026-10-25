import json
import os
import re
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.conf import settings

from .models import Resume, ApplicationDocument
from .document_generator import (
    generate_docx,
    generate_pdf,
    generate_cover_letter_docx,
    generate_cover_letter_pdf,
    DocumentGenerationError
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
        messages.error(request, f"Document generation failed: {e}")
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
