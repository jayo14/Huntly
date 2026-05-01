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

    def __str__(self):
        return self.business_name

    class Meta:
        ordering = ['-created_at']
