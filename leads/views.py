from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.http import HttpResponse
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.utils import timezone
from django.db.models import Count, Q
from .models import Lead, Message, AppSetting
from .forms import LeadForm, AppSettingForm
import json

def dashboard(request):
    today = timezone.now().date()
    status_filter = request.GET.get('status', '')

    leads_queryset = Lead.objects.all()
    if status_filter:
        leads_queryset = leads_queryset.filter(status=status_filter)

    total_leads = leads_queryset.count()
    emails_sent_today = Message.objects.filter(sent_at__date=today, is_reply=False).count()
    replies_count = Message.objects.filter(is_reply=True).count()

    conversion_rate = 0
    if Lead.objects.count() > 0:
        closed_leads = Lead.objects.filter(status='closed').count()
        conversion_rate = (closed_leads / Lead.objects.count()) * 100

    # Funnel data (global)
    funnel_stages = []
    global_total = Lead.objects.count()
    for status, label in Lead.STATUS_CHOICES:
        count = Lead.objects.filter(status=status).count()
        percentage = (count / global_total * 100) if global_total > 0 else 0
        funnel_stages.append({
            'label': label,
            'count': count,
            'percentage': round(percentage, 0)
        })

    # Needs Attention
    needs_attention = Lead.objects.filter(
        Q(status='new') | Q(next_follow_up=today)
    ).order_by('-score')[:5]

    context = {
        'total_leads': total_leads,
        'emails_sent_today': emails_sent_today,
        'replies_count': replies_count,
        'conversion_rate': round(conversion_rate, 1),
        'funnel_stages': funnel_stages,
        'needs_attention': needs_attention,
        'status_choices': Lead.STATUS_CHOICES,
        'selected_status': status_filter,
    }

    if request.headers.get('HX-Request'):
        return render(request, 'leads/partials/dashboard_stats.html', context)

    return render(request, 'leads/dashboard.html', context)

def lead_list(request):
    search = request.GET.get('search', '')
    status = request.GET.get('status', '')
    needs_action = request.GET.get('needs_action', '')

    leads = Lead.objects.all()

    if search:
        leads = leads.filter(
            Q(business_name__icontains=search) |
            Q(problem__icontains=search)
        )

    if status:
        leads = leads.filter(status=status)

    if needs_action == 'true':
        today = timezone.now().date()
        leads = leads.filter(
            Q(status='new') | Q(next_follow_up=today)
        )

    context = {
        'leads': leads,
        'status_choices': Lead.STATUS_CHOICES,
        'search': search,
        'selected_status': status,
        'needs_action': needs_action == 'true',
    }

    if request.headers.get('HX-Request'):
        return render(request, 'leads/partials/lead_list_table.html', context)
    return render(request, 'leads/leads_list.html', context)

def lead_create(request):
    if request.method == 'POST':
        form = LeadForm(request.POST)
        if form.is_valid():
            lead = form.save()
            if request.headers.get('HX-Request'):
                return HttpResponse(status=204, headers={'HX-Trigger': 'leadsChanged'})
            return redirect('leads:lead-list')
    else:
        form = LeadForm()

    return render(request, 'leads/lead_form.html', {'form': form})

def lead_update(request, pk):
    lead = get_object_or_404(Lead, pk=pk)
    if request.method == 'POST':
        form = LeadForm(request.POST, instance=lead)
        if form.is_valid():
            form.save()
            if request.headers.get('HX-Request'):
                return HttpResponse(status=204, headers={'HX-Trigger': 'leadsChanged'})
            return redirect('leads:lead-list')
    else:
        form = LeadForm(instance=lead)

    return render(request, 'leads/lead_form.html', {'form': form, 'lead': lead})

@require_POST
def lead_delete(request, pk):
    lead = get_object_or_404(Lead, pk=pk)
    lead.delete()
    if request.headers.get('HX-Request'):
        return HttpResponse(status=204, headers={'HX-Trigger': 'leadsChanged'})
    return redirect('leads:lead-list')

@require_POST
def update_status(request, pk):
    lead = get_object_or_404(Lead, pk=pk)
    status = request.POST.get('status')
    if status in dict(Lead.STATUS_CHOICES):
        lead.status = status
        lead.save()

    if request.headers.get('HX-Request'):
        return render(request, 'leads/partials/lead_row.html', {'lead': lead})
    return redirect('leads:lead-list')

def lead_list_partial(request):
    return lead_list(request)

def pipeline(request):
    stages = []
    for status, label in Lead.STATUS_CHOICES:
        stages.append({
            'status': status,
            'label': label,
            'leads': Lead.objects.filter(status=status).order_by('-score')
        })

    context = {'stages': stages}
    return render(request, 'leads/pipeline.html', context)

def settings_view(request):
    setting = AppSetting.objects.first()
    if not setting:
        setting = AppSetting.objects.create()

    if request.method == 'POST':
        form = AppSettingForm(request.POST, instance=setting)
        if form.is_valid():
            form.save()
            messages.success(request, "Settings updated successfully!")
            if request.headers.get('HX-Request'):
                return HttpResponse(status=204, headers={'HX-Trigger': 'settingsUpdated'})
            return redirect('leads:settings')
    else:
        form = AppSettingForm(instance=setting)

    return render(request, 'leads/settings.html', {'form': form})

def lead_detail(request, pk):
    lead = get_object_or_404(Lead, pk=pk)
    messages_list = lead.messages.all().order_by('-sent_at')

    context = {
        'lead': lead,
        'messages': messages_list,
    }
    return render(request, 'leads/lead_detail_modal.html', context)

@require_POST
def generate_message(request, pk):
    lead = get_object_or_404(Lead, pk=pk)
    subject = f"Inquiry regarding {lead.business_name}"
    body = f"Hello {lead.contact_name or 'Team'},\n\nI saw your website ({lead.website}) and noticed you might need help with {lead.problem}.\n\nOur offer: {lead.offer}\n\nLooking forward to hearing from you."

    # Properly escape for JS
    subject_js = json.dumps(subject)
    body_js = json.dumps(body)

    return HttpResponse(f'<script>document.getElementsByName("subject")[0].value = {subject_js}; document.getElementsByName("body")[0].value = {body_js};</script>')

@require_POST
def send_message(request, pk):
    lead = get_object_or_404(Lead, pk=pk)
    subject = request.POST.get('subject')
    body = request.POST.get('body')

    if subject and body:
        Message.objects.create(
            lead=lead,
            subject=subject,
            body=body
        )

        if lead.status == 'new':
            lead.status = 'contacted'
        lead.last_contacted = timezone.now()
        lead.save()

        messages.success(request, f"Email sent to {lead.business_name}!")
        return HttpResponse(status=204, headers={'HX-Trigger': 'leadsChanged'})

    return HttpResponse("Invalid form", status=400)
