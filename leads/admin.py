from django.contrib import admin
from .models import Lead

@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ('business_name', 'email', 'status', 'score', 'created_at')
    list_filter = ('status', 'tone', 'created_at')
    search_fields = ('business_name', 'contact_name', 'email', 'website')
    ordering = ('-created_at',)
