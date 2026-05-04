from django.db import models

class Lead(models.Model):
    TONE_CHOICES = [
        ('professional', 'Professional'),
        ('casual', 'Casual'),
        ('direct', 'Direct'),
        ('empathetic', 'Empathetic'),
    ]

    STATUS_CHOICES = [
        ('new', 'New'),
        ('contacted', 'Contacted'),
        ('replied', 'Replied'),
        ('proposal', 'Proposal Sent'),
        ('closed', 'Closed'),
    ]

    business_name = models.CharField(max_length=255)
    contact_name = models.CharField(max_length=255, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    website = models.URLField(blank=True)
    instagram = models.URLField(blank=True)
    problem = models.TextField(blank=True)
    score = models.IntegerField(default=0)
    tone = models.CharField(max_length=20, choices=TONE_CHOICES, default='professional')
    offer = models.TextField(blank=True)
    evidence_note = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new')
    created_at = models.DateTimeField(auto_now_add=True)
    last_contacted = models.DateTimeField(null=True, blank=True)
    next_follow_up = models.DateField(null=True, blank=True)

    def __str__(self):
        return self.business_name

    class Meta:
        ordering = ['-created_at']

class Message(models.Model):
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='messages')
    subject = models.CharField(max_length=255)
    body = models.TextField()
    sent_at = models.DateTimeField(auto_now_add=True)
    is_reply = models.BooleanField(default=False)

    def __str__(self):
        return f"{'Reply' if self.is_reply else 'Sent'} to {self.lead.business_name} at {self.sent_at}"

class AppSetting(models.Model):
    smtp_host = models.CharField(max_length=255, default='smtp.gmail.com')
    smtp_port = models.IntegerField(default=587)
    email_address = models.EmailField(blank=True)
    email_password = models.CharField(max_length=255, blank=True)
    daily_send_limit = models.IntegerField(default=50)
    default_tone = models.CharField(max_length=20, choices=Lead.TONE_CHOICES, default='professional')
    default_offer = models.TextField(blank=True)
    auto_send_enabled = models.BooleanField(default=False)
    follow_ups_enabled = models.BooleanField(default=True)

    def __str__(self):
        return "Application Settings"

    class Meta:
        verbose_name = "Application Setting"
        verbose_name_plural = "Application Settings"

class AutomationRule(models.Model):
    TRIGGER_CHOICES = [
        ('on_new', 'When Lead is Added'),
        ('on_status_change', 'When Status Changes'),
        ('no_reply', 'If No Reply After X Days'),
    ]

    name = models.CharField(max_length=100)
    trigger_type = models.CharField(max_length=20, choices=TRIGGER_CHOICES, default='on_new')
    target_status = models.CharField(max_length=20, choices=Lead.STATUS_CHOICES, blank=True)
    delay_hours = models.IntegerField(default=24, help_text="Wait time before action")
    ai_prompt_override = models.TextField(blank=True, help_text="Custom AI instructions for this rule")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class ScraperJob(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    name = models.CharField(max_length=255, help_text="Session name for this niche")
    niche = models.CharField(max_length=255)
    keywords = models.CharField(max_length=512)
    region = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    progress = models.IntegerField(default=0)
    leads_found = models.IntegerField(default=0)
    stop_requested = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    logs = models.TextField(default="", blank=True)

    def __str__(self):
        return f"{self.niche} in {self.region} ({self.status})"

    @property
    def logs_list(self):
        if not self.logs:
            return []
        lines = self.logs.strip().split('\n')
        parsed = []
        for line in lines:
            if ']' in line:
                parts = line.split(']', 1)
                parsed.append((parts[0] + ']', parts[1].strip()))
            else:
                parsed.append(('', line))
        return parsed

class RawLead(models.Model):
    job = models.ForeignKey(ScraperJob, on_delete=models.CASCADE, related_name='raw_leads')
    business_name = models.CharField(max_length=255)
    contact_name = models.CharField(max_length=255, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    website = models.URLField(blank=True)
    scraped_data = models.JSONField(default=dict)
    is_approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.business_name
