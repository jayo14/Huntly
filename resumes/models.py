from django.db import models

class Resume(models.Model):
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

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.full_name

class Payment(models.Model):
    PAYMENT_METHOD_CHOICES = [
        ('transfer', 'Transfer'),
        ('cash', 'Cash'),
        ('other', 'Other'),
    ]
    customer_name = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    date = models.DateField(auto_now_add=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.customer_name} - {self.amount}"
