from django.conf import settings
from django.db import models


class Resume(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='resumes')
    full_name = models.CharField(max_length=255)
    tagline = models.CharField(max_length=255, blank=True)
    location = models.CharField(max_length=255, blank=True)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True)
    linkedin = models.URLField(blank=True)
    github = models.URLField(blank=True)
    portfolio = models.URLField(blank=True)

    summary = models.TextField(blank=True)

    # JSON arrays for complex lists
    # technical_skills: [{category: 'Frontend', skills: 'React, Next.js'}]
    technical_skills = models.JSONField(default=list, blank=True)
    # experiences: [{role: '', company: '', dates: '', bullets: []}]
    experiences = models.JSONField(default=list, blank=True)
    # projects: [{name: '', link: '', stack: '', bullets: []}]
    projects = models.JSONField(default=list, blank=True)
    # certifications: [{name: '', issuer: '', date: ''}]
    certifications = models.JSONField(default=list, blank=True)
    # education: [{degree: '', institution: '', location: '', dates: ''}]
    education = models.JSONField(default=list, blank=True)

    include_branding = models.BooleanField(default=False)
    accent_color = models.CharField(max_length=7, default="#4F46E5")
    passport_photo = models.ImageField(upload_to="resumes/passports/", null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
        ]

    def __str__(self):
        return self.full_name
