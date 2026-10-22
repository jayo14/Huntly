from django.contrib import admin
from .models import JobApplication, Message, AppSetting


@admin.register(JobApplication)
class JobApplicationAdmin(admin.ModelAdmin):
    list_display = ('role_title', 'company_name', 'user', 'status', 'score', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('role_title', 'company_name', 'contact_name', 'contact_email')


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('subject', 'job_application', 'sent_at', 'is_reply')
    list_filter = ('sent_at', 'is_reply')


@admin.register(AppSetting)
class AppSettingAdmin(admin.ModelAdmin):
    list_display = ('user', 'email_address', 'smtp_host', 'smtp_port', 'daily_send_limit')
