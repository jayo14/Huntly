import json
import os
import subprocess
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from .models import Resume
from .docx_generator import generate_docx, DocxGenerationError


@login_required
def resume_list(request):
    resumes = Resume.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'resumes/resume_list.html', {'resumes': resumes})


def save_resume_data(resume, data, files, user=None):
    if user is not None:
        resume.user = user
    resume.full_name = data.get('full_name')
    resume.tagline = data.get('tagline', '')
    resume.location = data.get('location', '')
    resume.email = data.get('email')
    resume.phone = data.get('phone', '')
    resume.linkedin = data.get('linkedin', '')
    resume.github = data.get('github', '')
    resume.portfolio = data.get('portfolio', '')
    resume.summary = data.get('summary', '')
    resume.technical_skills = data.get('technical_skills', [])
    resume.experiences = data.get('experiences', [])
    resume.projects = data.get('projects', [])
    resume.certifications = data.get('certifications', [])
    resume.education = data.get('education', [])
    resume.include_branding = data.get('include_branding', False)
    resume.accent_color = data.get('accent_color', '#4F46E5')

    if files.get('passport_photo'):
        resume.passport_photo = files.get('passport_photo')

    resume.save()
    return resume


@login_required
def resume_create(request):
    if request.method == 'POST':
        if request.content_type == 'application/json':
            data = json.loads(request.body)
            files = {}
        else:
            data = json.loads(request.POST.get('data', '{}'))
            files = request.FILES

        resume = Resume(user=request.user)
        resume = save_resume_data(resume, data, files, user=request.user)

        # Generate the docx
        docx_data = data.copy()
        if resume.passport_photo:
            docx_data['passport_photo_path'] = resume.passport_photo.path

        try:
            generate_docx(docx_data)
        except DocxGenerationError as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

        if request.headers.get('HX-Request'):
            return HttpResponse(status=204, headers={'HX-Trigger': 'resumeCreated'})

        if request.content_type == 'application/json':
            return JsonResponse({'status': 'success', 'resume_id': resume.id})
        return redirect('resumes:resume-list')

    return render(request, 'resumes/resume_form.html', {'resume_data_json': '{}'})


@login_required
def resume_update(request, pk):
    resume = get_object_or_404(Resume, pk=pk, user=request.user)

    if request.method == 'POST':
        if request.content_type == 'application/json':
            data = json.loads(request.body)
            files = {}
        else:
            data = json.loads(request.POST.get('data', '{}'))
            files = request.FILES

        resume = save_resume_data(resume, data, files, user=request.user)

        # Generate the docx to verify
        docx_data = data.copy()
        if resume.passport_photo:
            docx_data['passport_photo_path'] = resume.passport_photo.path

        try:
            generate_docx(docx_data)
        except DocxGenerationError as e:
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
        'summary': resume.summary,
        'technical_skills': resume.technical_skills,
        'experiences': resume.experiences,
        'projects': resume.projects,
        'certifications': resume.certifications,
        'education': resume.education,
        'include_branding': resume.include_branding,
        'accent_color': resume.accent_color,
        'passport_photo_url': resume.passport_photo.url if resume.passport_photo else None,
    }
    for exp in resume_data['experiences']:
        exp['bulletsText'] = '\n'.join(exp.get('bullets', []))
    for proj in resume_data['projects']:
        proj['bulletsText'] = '\n'.join(proj.get('bullets', []))

    return render(request, 'resumes/resume_form.html', {'resume_data_json': json.dumps(resume_data)})


@login_required
def resume_preview_partial(request, pk):
    resume = get_object_or_404(Resume, pk=pk, user=request.user)
    return render(request, 'resumes/partials/resume_preview.html', {'resume': resume})


@login_required
def resume_download(request, pk):
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
        'summary': resume.summary,
        'technical_skills': resume.technical_skills,
        'experiences': resume.experiences,
        'projects': resume.projects,
        'certifications': resume.certifications,
        'education': resume.education,
        'include_branding': resume.include_branding,
        'accent_color': resume.accent_color,
    }

    # If downloaded for a specific tailored job application
    job_id = request.GET.get('job_id')
    if job_id:
        from leads.models import JobApplication
        job = JobApplication.objects.filter(pk=job_id, user=request.user).first()
        if job and job.tailored_resume_text:
            # Append tailored summary / focus
            data['summary'] = f"{resume.summary}\n\n[Target Role: {job.role_title} at {job.company_name}]\n{job.tailored_resume_text}"

    if resume.passport_photo:
        data['passport_photo_path'] = resume.passport_photo.path

    try:
        docx_buffer = generate_docx(data)
    except DocxGenerationError:
        messages.error(request, "Failed to generate resume document.")
        return redirect('resumes:resume-list')

    response = HttpResponse(docx_buffer, content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    response['Content-Disposition'] = f'attachment; filename="{resume.full_name.replace(" ", "_")}--_by_Huntly.docx"'
    return response
