from django.db import models
from django.utils import timezone

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

    def __str__(self):
        return self.business_name

    class Meta:
        ordering = ['-created_at']

class Message(models.Model):
    MESSAGE_TYPES = [
        ('initial', 'Initial Message'),
        ('followup1', 'Follow-up 1'),
        ('followup2', 'Follow-up 2'),
    ]

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='messages')
    type = models.CharField(max_length=20, choices=MESSAGE_TYPES)
    subject = models.CharField(max_length=255)
    body = models.TextField()
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.get_type_display()} for {self.lead.business_name}"

class FollowUpSchedule(models.Model):
    MESSAGE_TYPES = [
        ('followup1', 'Follow-up 1'),
        ('followup2', 'Follow-up 2'),
    ]

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='followup_schedules')
    message_type = models.CharField(max_length=20, choices=MESSAGE_TYPES)
    scheduled_date = models.DateField()
    sent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.get_message_type_display()} scheduled for {self.lead.business_name} on {self.scheduled_date}"
