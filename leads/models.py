from django.conf import settings
from django.db import models
from huntly.security import encrypt_credential, decrypt_credential


class JobApplication(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='job_applications')
    STATUS_CHOICES = [
        ('saved', 'Saved'),
        ('applied', 'Applied'),
        ('interviewing', 'Interviewing'),
        ('offer', 'Offer'),
        ('rejected', 'Rejected'),
    ]

    company_name = models.CharField(max_length=255)
    role_title = models.CharField(max_length=255)
    job_url = models.URLField(blank=True)
    job_description = models.TextField(blank=True)
    contact_name = models.CharField(max_length=255, blank=True)
    contact_email = models.EmailField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='saved', db_index=True)
    score = models.IntegerField(default=0, blank=True, db_index=True)
    tailored_resume_text = models.TextField(blank=True)
    cover_letter = models.TextField(blank=True)
    recruiter_pitch = models.TextField(blank=True)
    matched_keywords = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_contacted = models.DateTimeField(null=True, blank=True)
    next_follow_up = models.DateField(null=True, blank=True, db_index=True)

    def __str__(self):
        return f"{self.role_title} at {self.company_name}"

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['user', '-updated_at']),
            models.Index(fields=['user', '-created_at']),
        ]


# Backward compatibility alias
Lead = JobApplication


class Message(models.Model):
    job_application = models.ForeignKey(JobApplication, on_delete=models.CASCADE, related_name='messages')
    subject = models.CharField(max_length=255)
    body = models.TextField()
    sent_at = models.DateTimeField(auto_now_add=True, db_index=True)
    is_reply = models.BooleanField(default=False, db_index=True)

    @property
    def lead(self):
        return self.job_application

    def __str__(self):
        return f"{'Reply' if self.is_reply else 'Sent'} to {self.job_application.company_name} at {self.sent_at}"


class AppSetting(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='app_settings')
    smtp_host = models.CharField(max_length=255, default='smtp.gmail.com')
    smtp_port = models.IntegerField(default=587)
    email_address = models.EmailField(blank=True)
    email_password = models.CharField(max_length=512, blank=True)
    daily_send_limit = models.IntegerField(default=50)

    def set_email_password(self, raw_password: str):
        self.email_password = encrypt_credential(raw_password)

    def get_decrypted_email_password(self) -> str:
        return decrypt_credential(self.email_password)

    def save(self, *args, **kwargs):
        if self.email_password and not self.email_password.startswith('gAAAAA'):
            self.email_password = encrypt_credential(self.email_password)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Application Settings ({self.user.username if self.user else 'System'})"

    class Meta:
        verbose_name = "Application Setting"
        verbose_name_plural = "Application Settings"
