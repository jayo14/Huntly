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
            'contact_name', 'contact_role', 'contact_email',
            'contact_source', 'contact_verification_status',
            'status', 'interview_date', 'next_follow_up', 'notes',
            'outcome_details', 'score', 'tailored_resume_text',
            'cover_letter', 'recruiter_pitch'
        ]
        widgets = {
            'company_name': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border-2 border-ink text-sm bg-white text-ink', 'placeholder': 'e.g. Stripe'}),
            'role_title': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border-2 border-ink text-sm bg-white text-ink', 'placeholder': 'e.g. Senior Backend Engineer'}),
            'job_url': forms.URLInput(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border-2 border-ink text-sm bg-white text-ink', 'placeholder': 'https://...'}),
            'location': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border-2 border-ink text-sm bg-white text-ink', 'placeholder': 'e.g. San Francisco, CA / Remote'}),
            'salary': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border-2 border-ink text-sm bg-white text-ink', 'placeholder': 'e.g. $160,000 - $190,000'}),
            'employment_type': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border-2 border-ink text-sm bg-white text-ink', 'placeholder': 'e.g. Full-time, Hybrid'}),
            'contact_name': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border-2 border-ink text-sm bg-white text-ink', 'placeholder': 'Recruiter or Hiring Manager'}),
            'contact_role': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border-2 border-ink text-sm bg-white text-ink', 'placeholder': 'e.g. Senior Technical Recruiter / Head of Eng'}),
            'contact_email': forms.EmailInput(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border-2 border-ink text-sm bg-white text-ink', 'placeholder': 'hiring@company.com'}),
            'contact_source': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border-2 border-ink text-sm bg-white text-ink', 'placeholder': 'e.g. LinkedIn job post, official career site'}),
            'contact_verification_status': forms.Select(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border-2 border-ink text-sm bg-white text-ink font-semibold'}),
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
            'provider_type', 'sender_name', 'smtp_host', 'smtp_port',
            'email_address', 'email_password', 'daily_send_limit'
        ]
        widgets = {
            'provider_type': forms.Select(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border-2 border-ink text-sm bg-white text-ink font-semibold'}),
            'sender_name': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border-2 border-ink text-sm bg-white text-ink', 'placeholder': 'e.g. Jane Doe'}),
            'smtp_host': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border-2 border-ink text-sm bg-white text-ink', 'placeholder': 'smtp.gmail.com'}),
            'smtp_port': forms.NumberInput(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border-2 border-ink text-sm bg-white text-ink'}),
            'email_address': forms.EmailInput(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border-2 border-ink text-sm bg-white text-ink', 'placeholder': 'me@domain.com'}),
            'email_password': forms.PasswordInput(render_value=False, attrs={'class': 'w-full px-4 py-2.5 rounded-xl border-2 border-ink text-sm bg-white text-ink', 'placeholder': 'App Password or SMTP Secret'}),
            'daily_send_limit': forms.NumberInput(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border-2 border-ink text-sm bg-white text-ink'}),
        }

    def clean_email_password(self):
        password = self.cleaned_data.get('email_password')
        if not password and self.instance and self.instance.pk:
            return self.instance.email_password
        return password


class OutreachPitchForm(forms.Form):
    recipient_email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'w-full px-4 py-2.5 rounded-xl border-2 border-ink text-sm bg-white text-ink font-medium focus:ring-2 focus:ring-pink/40',
            'placeholder': 'verified.recruiter@company.com'
        })
    )
    recipient_name = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2.5 rounded-xl border-2 border-ink text-sm bg-white text-ink',
            'placeholder': 'e.g. Sarah Jenkins'
        })
    )
    recipient_role = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2.5 rounded-xl border-2 border-ink text-sm bg-white text-ink',
            'placeholder': 'e.g. Technical Recruiter / Hiring Lead'
        })
    )
    subject = forms.CharField(
        max_length=255,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2.5 rounded-xl border-2 border-ink text-sm bg-white text-ink font-semibold focus:ring-2 focus:ring-pink/40',
        })
    )
    body = forms.CharField(
        required=True,
        widget=forms.Textarea(attrs={
            'class': 'w-full px-4 py-3 rounded-xl border-2 border-ink text-sm bg-white text-ink leading-relaxed font-sans focus:ring-2 focus:ring-pink/40',
            'rows': 7,
        })
    )
    confirm_send = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'w-4 h-4 rounded border-2 border-ink text-pink focus:ring-pink'})
    )
    schedule_follow_up = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'w-full px-3 py-2 rounded-xl border-2 border-ink text-xs bg-white text-ink'
        })
    )


class OutreachReplyForm(forms.Form):
    reply_notes = forms.CharField(
        required=True,
        widget=forms.Textarea(attrs={
            'class': 'w-full px-4 py-2.5 rounded-xl border-2 border-ink text-sm bg-white text-ink',
            'rows': 3,
            'placeholder': 'Summary of recruiter response, interview invite details, or next steps...'
        })
    )


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
