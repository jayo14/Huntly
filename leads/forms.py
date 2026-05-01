from django import forms
from .models import Lead

class LeadForm(forms.ModelForm):
    class Meta:
        model = Lead
        fields = [
            'business_name', 'contact_name', 'email', 'phone',
            'website', 'instagram', 'problem', 'score',
            'tone', 'offer', 'evidence_note', 'status'
        ]
