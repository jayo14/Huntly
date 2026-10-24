from django import forms
from .models import JobApplication, AppSetting


class JobApplicationForm(forms.ModelForm):
    score = forms.IntegerField(required=False, initial=0)
    class Meta:
        model = JobApplication
        fields = [
            'company_name', 'role_title', 'job_url', 'job_description',
            'contact_name', 'contact_email', 'status', 'score',
            'tailored_resume_text', 'cover_letter', 'recruiter_pitch'
        ]
        widgets = {
            'company_name': forms.TextInput(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-surface-200 dark:border-white/10 bg-surface-50 dark:bg-neutral-800 text-surface-900 dark:text-white', 'placeholder': 'e.g. Stripe'}),
            'role_title': forms.TextInput(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-surface-200 dark:border-white/10 bg-surface-50 dark:bg-neutral-800 text-surface-900 dark:text-white', 'placeholder': 'e.g. Senior Software Engineer'}),
            'job_url': forms.URLInput(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-surface-200 dark:border-white/10 bg-surface-50 dark:bg-neutral-800 text-surface-900 dark:text-white', 'placeholder': 'https://...'}),
            'job_description': forms.Textarea(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-surface-200 dark:border-white/10 bg-surface-50 dark:bg-neutral-800 text-surface-900 dark:text-white', 'rows': 6, 'placeholder': 'Paste full job description requirements and responsibilities here...'}),
            'status': forms.Select(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-surface-200 dark:border-white/10 bg-surface-50 dark:bg-neutral-800 text-surface-900 dark:text-white'}),
            'tailored_resume_text': forms.Textarea(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-surface-200 dark:border-white/10 bg-surface-50 dark:bg-neutral-800 text-surface-900 dark:text-white font-mono text-sm', 'rows': 6}),
            'cover_letter': forms.Textarea(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-surface-200 dark:border-white/10 bg-surface-50 dark:bg-neutral-800 text-surface-900 dark:text-white', 'rows': 6}),
            'recruiter_pitch': forms.Textarea(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-surface-200 dark:border-white/10 bg-surface-50 dark:bg-neutral-800 text-surface-900 dark:text-white', 'rows': 3}),
        }


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
    email = forms.EmailField(required=True, label="Email Address")
    phone = forms.CharField(max_length=30, required=False, label="Phone Number")
    location = forms.CharField(max_length=255, required=False, label="Location (City, Country)")
    tagline = forms.CharField(max_length=255, required=False, label="Professional Headline / Tagline")
    passport_photo = forms.ImageField(required=False, label="Profile Avatar Photo")
    remove_photo = forms.BooleanField(required=False, widget=forms.HiddenInput())

