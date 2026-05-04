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

from .models import AutomationRule

class AutomationRuleForm(forms.ModelForm):
    class Meta:
        model = AutomationRule
        fields = ['name', 'trigger_type', 'target_status', 'delay_hours', 'ai_prompt_override', 'is_active']
        widgets = {
            'ai_prompt_override': forms.Textarea(attrs={'rows': 4, 'placeholder': 'e.g. Focus on their specific pain point mentioned in the problem field...'}),
        }

from .models import ScraperJob, RawLead

class ScraperJobForm(forms.ModelForm):
    class Meta:
        model = ScraperJob
        fields = ['name', 'niche', 'keywords', 'region']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'e.g. Miami Real Estate Search'}),
            'keywords': forms.TextInput(attrs={'placeholder': 'e.g. restaurant, cafe, bistro'}),
            'niche': forms.TextInput(attrs={'placeholder': 'e.g. Hospitality'}),
            'region': forms.TextInput(attrs={'placeholder': 'e.g. London, UK'}),
        }

class RawLeadForm(forms.ModelForm):
    class Meta:
        model = RawLead
        fields = ['business_name', 'contact_name', 'email', 'phone', 'website']
