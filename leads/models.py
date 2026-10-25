from django.conf import settings
from django.db import models, transaction
from django.utils import timezone
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
    job_url = models.URLField(max_length=500, blank=True)
    location = models.CharField(max_length=255, blank=True)
    salary = models.CharField(max_length=100, blank=True)
    employment_type = models.CharField(max_length=50, blank=True)
    job_description = models.TextField(blank=True)
    contact_name = models.CharField(max_length=255, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_role = models.CharField(max_length=150, blank=True)
    contact_source = models.CharField(max_length=255, blank=True)
    contact_verification_status = models.CharField(
        max_length=50,
        choices=[
            ('unverified', 'Unverified'),
            ('user_verified', 'Verified by Candidate'),
            ('authorized_source', 'Direct Job Listing / Official Source'),
        ],
        default='unverified',
        blank=True,
        db_index=True
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='saved', db_index=True)
    score = models.IntegerField(default=0, blank=True, db_index=True)
    notes = models.TextField(blank=True)

    # Timeline & key dates
    applied_at = models.DateTimeField(null=True, blank=True, db_index=True)
    interview_date = models.DateTimeField(null=True, blank=True, db_index=True)
    outcome_details = models.TextField(blank=True)
    last_contacted = models.DateTimeField(null=True, blank=True)
    next_follow_up = models.DateField(null=True, blank=True, db_index=True)
    is_archived = models.BooleanField(default=False, db_index=True)

    tailored_resume_text = models.TextField(blank=True)
    cover_letter = models.TextField(blank=True)
    recruiter_pitch = models.TextField(blank=True)
    matched_keywords = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.role_title} at {self.company_name}"

    def record_activity(self, activity_type: str, description: str, from_status: str = '', to_status: str = ''):
        """Record an immutable timeline event for this job application."""
        return ApplicationActivity.objects.create(
            job_application=self,
            activity_type=activity_type,
            from_status=from_status,
            to_status=to_status,
            description=description
        )

    def transition_to_status(self, new_status: str, notes: str = ""):
        """Safely transition application status and record timeline history."""
        valid_statuses = dict(self.STATUS_CHOICES)
        if new_status not in valid_statuses:
            raise ValueError(f"Invalid status '{new_status}'. Allowed choices: {list(valid_statuses.keys())}")

        old_status = self.status
        if old_status == new_status and not notes:
            return

        with transaction.atomic():
            self.status = new_status
            if new_status == 'applied' and not self.applied_at:
                self.applied_at = timezone.now()

            self.save(update_fields=['status', 'applied_at', 'updated_at'])

            desc = f"Stage changed from {valid_statuses.get(old_status, old_status)} to {valid_statuses.get(new_status, new_status)}."
            if notes:
                desc += f" Note: {notes}"
            self.record_activity('status_change', desc, from_status=old_status, to_status=new_status)

    class Meta:
        ordering = ['-updated_at', '-created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['user', 'is_archived']),
            models.Index(fields=['user', '-updated_at']),
            models.Index(fields=['user', '-created_at']),
        ]


# Backward compatibility alias
Lead = JobApplication


class ApplicationActivity(models.Model):
    """Timeline event and audit history for job applications."""
    ACTIVITY_TYPES = [
        ('created', 'Application Created'),
        ('status_change', 'Status Change'),
        ('interview_scheduled', 'Interview Scheduled'),
        ('note_added', 'Note Added'),
        ('email_sent', 'Email Outreach Sent'),
        ('document_generated', 'Tailored Document Generated'),
    ]

    job_application = models.ForeignKey(JobApplication, on_delete=models.CASCADE, related_name='activities')
    activity_type = models.CharField(max_length=50, choices=ACTIVITY_TYPES, default='status_change', db_index=True)
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20, blank=True)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['job_application', '-created_at']),
        ]

    def __str__(self):
        return f"{self.activity_type} on {self.job_application.company_name} at {self.created_at}"


class Message(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('queued', 'Queued'),
        ('accepted_by_provider', 'Accepted by Provider'),
        ('delivered', 'Delivered (Confirmed)'),
        ('bounced', 'Bounced'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='outreach_messages', null=True, blank=True)
    job_application = models.ForeignKey(JobApplication, on_delete=models.CASCADE, related_name='messages')

    recipient_email = models.EmailField(blank=True)
    recipient_name = models.CharField(max_length=255, blank=True)
    recipient_role = models.CharField(max_length=150, blank=True)

    subject = models.CharField(max_length=255)
    body = models.TextField()
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='draft', db_index=True)
    provider_message_id = models.CharField(max_length=255, blank=True)
    error_message = models.TextField(blank=True)

    sent_at = models.DateTimeField(null=True, blank=True, db_index=True)
    follow_up_reminder_at = models.DateTimeField(null=True, blank=True, db_index=True)
    reply_received_at = models.DateTimeField(null=True, blank=True)
    reply_notes = models.TextField(blank=True)
    is_reply = models.BooleanField(default=False, db_index=True)

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def lead(self):
        return self.job_application

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['job_application', '-created_at']),
            models.Index(fields=['follow_up_reminder_at']),
        ]

    def save(self, *args, **kwargs):
        if not self.user and self.job_application and self.job_application.user:
            self.user = self.job_application.user
        if not self.recipient_email and self.job_application:
            self.recipient_email = self.job_application.contact_email
        if not self.recipient_name and self.job_application:
            self.recipient_name = self.job_application.contact_name
        if not self.recipient_role and self.job_application:
            self.recipient_role = getattr(self.job_application, 'contact_role', '')
        if self.status in ['accepted_by_provider', 'delivered'] and not self.sent_at:
            self.sent_at = timezone.now()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_status_display()}: {self.subject} to {self.recipient_email or 'No recipient'}"


class AppSetting(models.Model):
    PROVIDER_CHOICES = [
        ('smtp', 'Custom SMTP Server'),
        ('system', 'System Default / Platform Service'),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='app_settings')
    provider_type = models.CharField(max_length=50, choices=PROVIDER_CHOICES, default='smtp', blank=True)
    sender_name = models.CharField(max_length=150, blank=True)
    smtp_host = models.CharField(max_length=255, default='smtp.gmail.com')
    smtp_port = models.IntegerField(default=587)
    email_address = models.EmailField(blank=True)
    email_password = models.CharField(max_length=512, blank=True)
    daily_send_limit = models.IntegerField(default=50)
    is_verified = models.BooleanField(default=False)
    last_verified_at = models.DateTimeField(null=True, blank=True)

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
