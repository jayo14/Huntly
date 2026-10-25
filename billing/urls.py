from django.urls import path
from billing import views

app_name = 'billing'

urlpatterns = [
    path('', views.billing_dashboard, name='dashboard'),
    path('checkout/<str:plan_id>/', views.create_checkout, name='checkout'),
    path('success/', views.checkout_success, name='checkout-success'),
    path('cancel/', views.cancel_subscription, name='cancel-subscription'),
    path('webhook/<str:provider_name>/', views.webhook_receiver, name='webhook'),
]
