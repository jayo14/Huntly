import json
import subprocess
import os
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.contrib.auth.decorators import login_required
from django.conf import settings
from .models import Resume, Payment

@login_required
def resume_list(request):
    resumes = Resume.objects.all().order_by('-created_at')
    return render(request, 'resumes/resume_list.html', {'resumes': resumes})

def save_resume_data(resume, data, files):
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

        resume = Resume()
        resume = save_resume_data(resume, data, files)

        # Generate the docx
        docx_data = data.copy()
        if resume.passport_photo:
            docx_data['passport_photo_path'] = resume.passport_photo.path

        docx_buffer = generate_docx(docx_data)
        response = HttpResponse(docx_buffer, content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        response['Content-Disposition'] = f'attachment; filename="{resume.full_name.replace(" ", "_")}--_by_Huntly.docx"'
        return response

    return render(request, 'resumes/resume_form.html')

@login_required
def resume_update(request, pk):
    resume = get_object_or_404(Resume, pk=pk)
    if request.method == 'POST':
        if request.content_type == 'application/json':
            data = json.loads(request.body)
            files = {}
        else:
            data = json.loads(request.POST.get('data', '{}'))
            files = request.FILES

        resume = save_resume_data(resume, data, files)

        # Generate the docx
        docx_data = data.copy()
        if resume.passport_photo:
            docx_data['passport_photo_path'] = resume.passport_photo.path

        docx_buffer = generate_docx(docx_data)
        response = HttpResponse(docx_buffer, content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        response['Content-Disposition'] = f'attachment; filename="{resume.full_name.replace(" ", "_")}--_by_Huntly.docx"'
        return response

    # Convert model to JSON for Alpine.js
    resume_data = {
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
    # Add bulletsText to experiences and projects for the UI
    for exp in resume_data['experiences']:
        exp['bulletsText'] = '\n'.join(exp.get('bullets', []))
    for proj in resume_data['projects']:
        proj['bulletsText'] = '\n'.join(proj.get('bullets', []))

    return render(request, 'resumes/resume_form.html', {'resume_data_json': json.dumps(resume_data)})

@login_required
def resume_preview_partial(request, pk):
    resume = get_object_or_404(Resume, pk=pk)
    return render(request, 'resumes/partials/resume_preview.html', {'resume': resume})

@login_required
def resume_download(request, pk):
    resume = get_object_or_404(Resume, pk=pk)
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
    if resume.passport_photo:
        data['passport_photo_path'] = resume.passport_photo.path

    docx_buffer = generate_docx(data)
    response = HttpResponse(docx_buffer, content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    response['Content-Disposition'] = f'attachment; filename="{resume.full_name.replace(" ", "_")}--_by_Huntly.docx"'
    return response

@login_required
def payment_list(request):
    payments = Payment.objects.all().order_by('-date')
    return render(request, 'resumes/payment_list.html', {'payments': payments})

@login_required
def payment_create(request):
    if request.method == 'POST':
        Payment.objects.create(
            customer_name=request.POST.get('customer_name'),
            amount=request.POST.get('amount'),
            method=request.POST.get('method'),
            notes=request.POST.get('notes', '')
        )
    return redirect('resumes:payment-list')

def generate_docx(data):
    # Call node script
    process = subprocess.Popen(
        ['node', 'scripts/resume_generator.js', json.dumps(data)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    stdout, stderr = process.communicate()
    if stderr:
        print(f"Error in node script: {stderr.decode()}")
    return stdout
