from django.urls import path
from . import views

app_name = 'resumes'

urlpatterns = [
    path('', views.resume_list, name='resume-list'),
    path('create/', views.resume_create, name='resume-create'),
    path('import/', views.resume_import_upload, name='resume-import'),
    path('import/<int:import_id>/review/', views.resume_import_review, name='resume-import-review'),
    path('import/<int:import_id>/confirm/', views.resume_import_confirm, name='resume-import-confirm'),
    path('import/<int:import_id>/cancel/', views.resume_import_cancel, name='resume-import-cancel'),
    path('import/<int:import_id>/file/', views.resume_import_download, name='resume-import-file'),
    path('<int:pk>/update/', views.resume_update, name='resume-update'),
    path('<int:pk>/delete/', views.resume_delete, name='resume-delete'),
    path('<int:pk>/make-master/', views.make_master_profile, name='make-master'),
    path('<int:pk>/download/', views.resume_download, name='resume-download'),
    path('<int:pk>/preview/', views.resume_preview_partial, name='resume-preview'),
    path('cover-letter/<int:job_id>/download/', views.cover_letter_download, name='cover-letter-download'),
    path('history/<int:job_id>/', views.document_history, name='document-history'),
]
