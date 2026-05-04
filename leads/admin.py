from django.contrib import admin
from .models import Lead, Message, AppSetting, AutomationRule, ScraperJob, RawLead

@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ('business_name', 'contact_name', 'email', 'status', 'score', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('business_name', 'contact_name', 'email')

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('lead', 'subject', 'sent_at', 'is_reply')
    list_filter = ('sent_at', 'is_reply')

@admin.register(AppSetting)
class AppSettingAdmin(admin.ModelAdmin):
    list_display = ('id', 'auto_send_enabled', 'follow_ups_enabled')

@admin.register(AutomationRule)
class AutomationRuleAdmin(admin.ModelAdmin):
    list_display = ('name', 'trigger_type', 'target_status', 'is_active')
    list_filter = ('trigger_type', 'target_status', 'is_active')

@admin.register(ScraperJob)
class ScraperJobAdmin(admin.ModelAdmin):
    list_display = ('name', 'niche', 'region', 'status', 'leads_found', 'created_at')
    list_filter = ('status', 'created_at')

@admin.register(RawLead)
class RawLeadAdmin(admin.ModelAdmin):
    list_display = ('business_name', 'email', 'job', 'is_approved', 'created_at')
    list_filter = ('is_approved', 'created_at')
