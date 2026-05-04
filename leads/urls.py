from django.urls import path
from . import views

app_name = 'leads'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('leads/', views.lead_list, name='lead-list'),
    path('leads/partial/', views.lead_list_partial, name='lead-list-partial'),
    path('leads/create/', views.lead_create, name='lead-create'),
    path('leads/<int:pk>/update/', views.lead_update, name='lead-update'),
    path('leads/<int:pk>/delete/', views.lead_delete, name='lead-delete'),
    path('leads/<int:pk>/status/', views.update_status, name='update-status'),
    path('leads/<int:pk>/detail/', views.lead_detail, name='lead-detail'),
    path('pipeline/', views.pipeline, name='pipeline'),
    path('settings/', views.settings_view, name='settings'),
    path('leads/<int:pk>/generate-message/', views.generate_message, name='generate-message'),
    path('leads/<int:pk>/send-message/', views.send_message, name='send-message'),
    path('automation/', views.automation_dashboard, name='automation-dashboard'),
    path('automation/rules/partial/', views.rule_list_partial, name='rule-list-partial'),
    path('automation/rules/create/', views.rule_create, name='rule-create'),
    path('automation/rules/<int:pk>/update/', views.rule_update, name='rule-update'),
    path('automation/rules/<int:pk>/delete/', views.rule_delete, name='rule-delete'),
    path('automation/rules/<int:pk>/toggle/', views.toggle_rule, name='toggle-rule'),
    path('automation/settings/toggle/', views.toggle_setting, name='toggle-setting'),
    path('scraper/', views.scraper_dashboard, name='scraper-dashboard'),
    path('scraper/jobs/create/', views.scraper_create, name='scraper-create'),
    path('scraper/monitor/partial/', views.scraper_monitor_partial, name='scraper-monitor-partial'),
    path('scraper/raw-leads/partial/', views.raw_lead_list_partial, name='raw-lead-list-partial'),
    path('scraper/raw-leads/<int:pk>/review/', views.raw_lead_review, name='raw-lead-review'),
    path('scraper/raw-leads/<int:pk>/approve/', views.raw_lead_approve, name='raw-lead-approve'),
    path('scraper/raw-leads/<int:pk>/delete/', views.raw_lead_delete, name='raw-lead-delete'),
]
