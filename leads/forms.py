from django import forms
from django.core.exceptions import ValidationError
from urllib.parse import urlparse
from .models import JobApplication, AppSetting


class JobApplicationForm(forms.ModelForm):
    score = forms.IntegerField(required=False, initial=0)
    interview_date = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'w-full px-4 py-2.5 rounded-xl border-2 border-ink text-sm bg-white text-ink'})
    )
    next_follow_up = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'w-full px-4 py-2.5 rounded-xl border-2 border-ink text-sm bg-white text-ink'})
    )

    class Meta:
        model = JobApplication
        fields = [
            'company_name', 'role_title', 'job_url', 'location',
            'salary', 'employment_type', 'job_description',
            'contact_name', 'contact_email', 'status', 'interview_date',
            'next_follow_up', 'notes', 'outcome_details', 'score',
            'tailored_resume_text', 'cover_letter', 'recruiter_pitch'
        ]
        widgets = {
            'company_name': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border-2 border-ink text-sm bg-white text-ink', 'placeholder': 'e.g. Stripe'}),
            'role_title': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border-2 border-ink text-sm bg-white text-ink', 'placeholder': 'e.g. Senior Backend Engineer'}),
            'job_url': forms.URLInput(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border-2 border-ink text-sm bg-white text-ink', 'placeholder': 'https://...'}),
            'location': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border-2 border-ink text-sm bg-white text-ink', 'placeholder': 'e.g. San Francisco, CA / Remote'}),
            'salary': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border-2 border-ink text-sm bg-white text-ink', 'placeholder': 'e.g. $160,000 - $190,000'}),
            'employment_type': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border-2 border-ink text-sm bg-white text-ink', 'placeholder': 'e.g. Full-time, Hybrid'}),
            'contact_name': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border-2 border-ink text-sm bg-white text-ink', 'placeholder': 'Recruiter or Hiring Manager'}),
            'contact_email': forms.EmailInput(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border-2 border-ink text-sm bg-white text-ink', 'placeholder': 'hiring@company.com'}),
            'status': forms.Select(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border-2 border-ink text-sm bg-white text-ink font-semibold'}),
            'job_description': forms.Textarea(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border-2 border-ink text-sm bg-white text-ink leading-relaxed font-sans', 'rows': 6, 'placeholder': 'Paste job posting requirements or key responsibilities here...'}),
            'notes': forms.Textarea(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border-2 border-ink text-sm bg-white text-ink font-sans', 'rows': 3, 'placeholder': 'Personal notes, referral info, interview observations...'}),
            'outcome_details': forms.Textarea(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border-2 border-ink text-sm bg-white text-ink font-sans', 'rows': 2, 'placeholder': 'Offer compensation or rejection feedback details...'}),
            'tailored_resume_text': forms.Textarea(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border-2 border-ink text-sm bg-white text-ink font-mono', 'rows': 5}),
            'cover_letter': forms.Textarea(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border-2 border-ink text-sm bg-white text-ink font-sans', 'rows': 5}),
            'recruiter_pitch': forms.Textarea(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border-2 border-ink text-sm bg-white text-ink font-sans', 'rows': 3}),
        }

    def clean_job_url(self):
        url = self.cleaned_data.get('job_url', '').strip()
        if not url:
            return ''
        parsed = urlparse(url)
        if not parsed.scheme:
            url = 'https://' + url
            parsed = urlparse(url)
        if parsed.scheme not in ('http', 'https') or not parsed.netloc:
            raise ValidationError("Please provide a valid web URL starting with http:// or https://")
        return url


# Alias for backward compatibility
LeadForm = JobApplicationForm


class AppSettingForm(forms.ModelForm):
    class Meta:
        model = AppSetting
        fields = [
            'smtp_host', 'smtp_port', 'email_address', 'email_password',
            'daily_send_limit'
        ]
        widgets = {
            'email_password': forms.PasswordInput(render_value=False),
        }

    def clean_email_password(self):
        password = self.cleaned_data.get('email_password')
        if not password and self.instance and self.instance.pk:
            return self.instance.email_password
        return password


class UserProfileForm(forms.Form):
    first_name = forms.CharField(max_length=150, required=False, label="First Name")
    last_name = forms.CharField(max_length=150, required=False, label="Last Name")
    email = forms.EmailField(required=False, label="Email Address")
    phone = forms.CharField(max_length=20, required=False, label="Phone Number")
    location = forms.CharField(max_length=255, required=False, label="Location")
    tagline = forms.CharField(max_length=255, required=False, label="Professional Tagline")
    passport_photo = forms.ImageField(required=False, label="Profile Avatar / Photo")
    remove_photo = forms.BooleanField(required=False, widget=forms.HiddenInput())

    def clean_passport_photo(self):
        photo = self.cleaned_data.get('passport_photo')
        if photo:
            from huntly.security import validate_uploaded_image
            validate_uploaded_image(photo, max_size_bytes=5 * 1024 * 1024)
        return photo
