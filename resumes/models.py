from django.conf import settings
from django.db import models


from django.conf import settings
from django.db import models, transaction


class Resume(models.Model):
    """Master Career Profile and customizable resume models.

    Acts as the candidate's authoritative career source-of-truth.
    Tailored resumes, cover letters, and pitches are derived from this
    data without overwriting original verified career facts.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='resumes')
    is_master = models.BooleanField(default=True, db_index=True)
    full_name = models.CharField(max_length=255)
    tagline = models.CharField(max_length=255, blank=True)
    location = models.CharField(max_length=255, blank=True)
    email = models.EmailField()
    phone = models.CharField(max_length=50, blank=True)
    linkedin = models.URLField(blank=True)
    github = models.URLField(blank=True)
    portfolio = models.URLField(blank=True)
    website = models.URLField(blank=True)

    summary = models.TextField(blank=True)

    # Work preferences & target roles
    target_roles = models.JSONField(default=list, blank=True)
    work_preferences = models.JSONField(default=dict, blank=True)

    # Structured Career Profile data
    # technical_skills: [{name: '', category: '', proficiency: '', evidence: '', provenance: 'user_entered'}]
    technical_skills = models.JSONField(default=list, blank=True)
    # experiences: [{role: '', company: '', dates: '', location: '', description: '', responsibilities: [], accomplishments: [], technologies: [], provenance: 'user_entered'}]
    experiences = models.JSONField(default=list, blank=True)
    # projects: [{name: '', role: '', contribution: '', link: '', technologies: [], outcomes: '', provenance: 'user_entered'}]
    projects = models.JSONField(default=list, blank=True)
    # certifications: [{name: '', issuer: '', date: '', verification_url: '', provenance: 'user_entered'}]
    certifications = models.JSONField(default=list, blank=True)
    # education: [{degree: '', institution: '', location: '', dates: '', details: '', provenance: 'user_entered'}]
    education = models.JSONField(default=list, blank=True)

    include_branding = models.BooleanField(default=False)
    accent_color = models.CharField(max_length=7, default="#4F46E5")
    passport_photo = models.ImageField(upload_to="resumes/passports/", null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_master', '-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['user', 'is_master']),
        ]

    def __str__(self):
        master_flag = " [Master]" if self.is_master else ""
        return f"{self.full_name}{master_flag}"

    def consolidate_as_master(self):
        """Designate this resume as the candidate's canonical Master Career Profile."""
        with transaction.atomic():
            Resume.objects.filter(user=self.user).exclude(pk=self.pk).update(is_master=False)
            self.is_master = True
            self.save(update_fields=['is_master'])

    def get_completeness_report(self):
        """Calculate profile completeness percentage, missing sections, and actionable suggestions."""
        score = 0
        missing = []
        suggestions = []

        # 1. Identity & Contact (20 points)
        if self.full_name and self.email:
            score += 10
            if self.phone or self.location:
                score += 5
            if self.tagline:
                score += 5
        else:
            missing.append("Name & Email")
            suggestions.append("Add your full name and primary email address.")

        # 2. Professional Summary (15 points)
        if self.summary and len(self.summary.strip()) >= 50:
            score += 15
        elif self.summary:
            score += 8
            suggestions.append("Expand your summary to 2-3 sentences highlighting your core value.")
        else:
            missing.append("Professional Summary")
            suggestions.append("Add a concise professional summary.")

        # 3. Work Experience & Accomplishments (30 points)
        if self.experiences and len(self.experiences) > 0:
            score += 15
            has_accomplishments = any(
                (exp.get('accomplishments') and len(exp['accomplishments']) > 0) or
                (exp.get('bullets') and len(exp['bullets']) > 0)
                for exp in self.experiences if isinstance(exp, dict)
            )
            if has_accomplishments:
                score += 15
            else:
                suggestions.append("Add quantifiable accomplishments with outcomes to your work history.")
        else:
            missing.append("Work Experience")
            suggestions.append("List at least one professional work experience.")

        # 4. Technical Skills & Evidence (15 points)
        if self.technical_skills and len(self.technical_skills) > 0:
            score += 10
            has_skills = any(
                isinstance(s, dict) and s.get('name')
                for s in self.technical_skills
            ) or any(isinstance(s, str) for s in self.technical_skills)
            if has_skills:
                score += 5
        else:
            missing.append("Skills")
            suggestions.append("Add your primary skills and competencies.")

        # 5. Projects or Portfolio (10 points)
        if (self.projects and len(self.projects) > 0) or self.portfolio or self.github:
            score += 10
        else:
            suggestions.append("Add key projects or links to your GitHub/Portfolio.")

        # 6. Education or Certifications (10 points)
        if (self.education and len(self.education) > 0) or (self.certifications and len(self.certifications) > 0):
            score += 10
        else:
            suggestions.append("Add your educational background or professional certifications.")

        return {
            'score': min(100, score),
            'missing': missing,
            'suggestions': suggestions,
            'is_ready_for_tailoring': score >= 40,
        }


class ApplicationDocument(models.Model):
    """Snapshot and version history of generated application documents tied to a specific job."""
    DOCUMENT_TYPES = [
        ('resume', 'Tailored Resume'),
        ('cover_letter', 'Cover Letter'),
        ('recruiter_pitch', 'Recruiter Outreach Pitch'),
        ('full_bundle', 'Application Bundle'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='application_documents')
    job_application = models.ForeignKey('leads.JobApplication', on_delete=models.CASCADE, related_name='documents')
    version = models.PositiveIntegerField(default=1)
    document_type = models.CharField(max_length=30, choices=DOCUMENT_TYPES, default='full_bundle')
    title = models.CharField(max_length=255)

    # Content snapshots
    tailored_resume_text = models.TextField(blank=True)
    tailored_resume_data = models.JSONField(default=dict, blank=True)
    cover_letter_text = models.TextField(blank=True)
    recruiter_pitch_text = models.TextField(blank=True)

    # Match Assessment & Evidence
    match_score = models.IntegerField(default=0)
    match_assessment = models.JSONField(default=dict, blank=True)
    claims_for_verification = models.JSONField(default=list, blank=True)

    # Audit provenance snapshots
    profile_snapshot = models.JSONField(default=dict, blank=True)
    job_snapshot = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['job_application', '-version', '-created_at']
        unique_together = [('job_application', 'version', 'document_type')]
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['job_application', '-version']),
        ]

    def __str__(self):
        return f"{self.title} (v{self.version}) for {self.job_application.company_name}"

