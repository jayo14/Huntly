from django import forms
from .models import Lead, AppSetting

class LeadForm(forms.ModelForm):
    class Meta:
        model = Lead
        fields = [
            'business_name', 'contact_name', 'email', 'phone',
            'website', 'instagram', 'problem', 'score',
            'tone', 'offer', 'evidence_note', 'status'
        ]

class AppSettingForm(forms.ModelForm):
    class Meta:
        model = AppSetting
        fields = [
            'smtp_host', 'smtp_port', 'email_address', 'email_password',
            'daily_send_limit', 'default_tone', 'default_offer',
            'auto_send_enabled', 'follow_ups_enabled'
        ]
        widgets = {
            'email_password': forms.PasswordInput(render_value=True),
            'default_offer': forms.Textarea(attrs={'rows': 3}),
        }
