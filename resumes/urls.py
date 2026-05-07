from django.urls import path
from . import views

app_name = 'resumes'

urlpatterns = [
    path('', views.resume_list, name='resume-list'),
    path('create/', views.resume_create, name='resume-create'),
    path('<int:pk>/update/', views.resume_update, name='resume-update'),
    path('<int:pk>/download/', views.resume_download, name='resume-download'),
    path('payments/', views.payment_list, name='payment-list'),
    path('payments/create/', views.payment_create, name='payment-create'),
]
