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
    path('leads/<int:pk>/archive/', views.lead_archive, name='lead-archive'),
    path('leads/<int:pk>/status/', views.update_status, name='update-status'),
    path('leads/<int:pk>/detail/', views.lead_detail, name='lead-detail'),
    path('pipeline/', views.pipeline, name='pipeline'),
    path('settings/', views.settings_view, name='settings'),
    path('leads/<int:pk>/generate-message/', views.generate_message, name='generate-message'),
    path('leads/<int:pk>/send-message/', views.send_message, name='send-message'),
    path('messages/<int:pk>/reply/', views.record_message_reply, name='message-reply'),
    path('messages/<int:pk>/cancel/', views.cancel_message_reminder, name='message-cancel'),
    path('settings/verify-smtp/', views.verify_smtp_settings, name='verify-smtp'),
    path('profile/', views.profile_view, name='profile'),
    path('profile/edit/', views.profile_edit, name='profile-edit'),
    path('profile/export/', views.profile_export, name='profile-export'),
    path('profile/delete-account/', views.profile_delete_account, name='profile-delete-account'),
]
