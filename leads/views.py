from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.http import HttpResponse
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.contrib.auth.decorators import login_required

from django.utils import timezone
from django.db.models import Count, Q
from .models import Lead, Message, AppSetting, AutomationRule, ScraperJob, RawLead
from .forms import LeadForm, AppSettingForm, AutomationRuleForm, ScraperJobForm, RawLeadForm
import json

@login_required
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

@login_required
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

@login_required
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

@login_required
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

@login_required
@require_POST
def lead_delete(request, pk):

    lead = get_object_or_404(Lead, pk=pk)
    lead.delete()
    if request.headers.get('HX-Request'):
        return HttpResponse(status=204, headers={'HX-Trigger': 'leadsChanged'})
    return redirect('leads:lead-list')

@login_required
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

@login_required
def lead_list_partial(request):

    return lead_list(request)

@login_required
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

@login_required
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

@login_required
def lead_detail(request, pk):

    lead = get_object_or_404(Lead, pk=pk)
    messages_list = lead.messages.all().order_by('-sent_at')

    context = {
        'lead': lead,
        'messages': messages_list,
    }
    return render(request, 'leads/lead_detail_modal.html', context)

@login_required
@require_POST
def generate_message(request, pk):

    lead = get_object_or_404(Lead, pk=pk)
    subject = f"Inquiry regarding {lead.business_name}"
    body = f"Hello {lead.contact_name or 'Team'},\n\nI saw your website ({lead.website}) and noticed you might need help with {lead.problem}.\n\nOur offer: {lead.offer}\n\nLooking forward to hearing from you."

    # Properly escape for JS
    subject_js = json.dumps(subject)
    body_js = json.dumps(body)

    return HttpResponse(f'<script>document.getElementsByName("subject")[0].value = {subject_js}; document.getElementsByName("body")[0].value = {body_js};</script>')

@login_required
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

@login_required
def automation_dashboard(request):
    rules = AutomationRule.objects.all()
    settings = AppSetting.objects.first()
    if not settings:
        settings = AppSetting.objects.create()
    
    context = {
        'rules': rules,
        'settings': settings,
    }
    return render(request, 'leads/automation.html', context)

@login_required
def rule_create(request):
    if request.method == 'POST':
        form = AutomationRuleForm(request.POST)
        if form.is_valid():
            form.save()
            if request.headers.get('HX-Request'):
                return HttpResponse(status=204, headers={'HX-Trigger': 'rulesChanged'})
            return redirect('leads:automation-dashboard')
    else:
        form = AutomationRuleForm()
    return render(request, 'leads/rule_form.html', {'form': form})

@login_required
def rule_update(request, pk):
    rule = get_object_or_404(AutomationRule, pk=pk)
    if request.method == 'POST':
        form = AutomationRuleForm(request.POST, instance=rule)
        if form.is_valid():
            form.save()
            if request.headers.get('HX-Request'):
                return HttpResponse(status=204, headers={'HX-Trigger': 'rulesChanged'})
            return redirect('leads:automation-dashboard')
    else:
        form = AutomationRuleForm(instance=rule)
    return render(request, 'leads/rule_form.html', {'form': form, 'rule': rule})

@login_required
@require_POST
def rule_delete(request, pk):
    rule = get_object_or_404(AutomationRule, pk=pk)
    rule.delete()
    if request.headers.get('HX-Request'):
        return HttpResponse(status=204, headers={'HX-Trigger': 'rulesChanged'})
    return redirect('leads:automation-dashboard')

@login_required
@require_POST
def toggle_rule(request, pk):
    rule = get_object_or_404(AutomationRule, pk=pk)
    rule.is_active = not rule.is_active
    rule.save()
    if request.headers.get('HX-Request'):
        return render(request, 'leads/partials/rule_row.html', {'rule': rule})
    return redirect('leads:automation-dashboard')

@login_required
def rule_list_partial(request):
    rules = AutomationRule.objects.all()
    return render(request, 'leads/partials/rule_list.html', {'rules': rules})

@login_required
@require_POST
def toggle_setting(request):
    setting = AppSetting.objects.first()
    if not setting:
        setting = AppSetting.objects.create()
    
    field = request.POST.get('field')
    if field in ['auto_send_enabled', 'follow_ups_enabled']:
        current_val = getattr(setting, field)
        setattr(setting, field, not current_val)
        setting.save()
    
    return HttpResponse(status=204)

@login_required
def scraper_dashboard(request):
    jobs = ScraperJob.objects.all().order_by('-created_at')
    raw_leads = RawLead.objects.filter(is_approved=False).order_by('-created_at')
    
    context = {
        'jobs': jobs,
        'raw_leads': raw_leads,
    }
    return render(request, 'leads/scraper.html', context)

@login_required
def scraper_create(request):
    if request.method == 'POST':
        form = ScraperJobForm(request.POST)
        if form.is_valid():
            job = form.save()
            # In a real app, you'd trigger a background task here
            # For this demo, we'll simulate a job starting
            job.status = 'running'
            job.save()
            
            if request.headers.get('HX-Request'):
                return HttpResponse(status=204, headers={'HX-Trigger': 'jobsChanged'})
            return redirect('leads:scraper-dashboard')
    else:
        form = ScraperJobForm()
    return render(request, 'leads/scraper_job_form.html', {'form': form})

@login_required
def scraper_monitor_partial(request):
    jobs = ScraperJob.objects.exclude(status='completed').exclude(status='failed')
    return render(request, 'leads/partials/scraper_monitor.html', {'jobs': jobs})

@login_required
def raw_lead_list_partial(request):
    raw_leads = RawLead.objects.filter(is_approved=False).order_by('-created_at')
    return render(request, 'leads/partials/raw_lead_list.html', {'raw_leads': raw_leads})

@login_required
def raw_lead_review(request, pk):
    raw_lead = get_object_or_404(RawLead, pk=pk)
    if request.method == 'POST':
        form = RawLeadForm(request.POST, instance=raw_lead)
        if form.is_valid():
            form.save()
            if request.headers.get('HX-Request'):
                return HttpResponse(status=204, headers={'HX-Trigger': 'rawLeadsChanged'})
            return redirect('leads:scraper-dashboard')
    else:
        form = RawLeadForm(instance=raw_lead)
    return render(request, 'leads/raw_lead_review_form.html', {'form': form, 'raw_lead': raw_lead})

@login_required
@require_POST
def raw_lead_approve(request, pk):
    raw_lead = get_object_or_404(RawLead, pk=pk)
    
    # Move to Lead model
    Lead.objects.create(
        business_name=raw_lead.business_name,
        contact_name=raw_lead.contact_name,
        email=raw_lead.email,
        phone=raw_lead.phone,
        website=raw_lead.website,
        status='new'
    )
    
    raw_lead.is_approved = True
    raw_lead.save()
    
    if request.headers.get('HX-Request'):
        return HttpResponse(status=204, headers={'HX-Trigger': 'rawLeadsChanged'})
    return redirect('leads:scraper-dashboard')

@login_required
@require_POST
def raw_lead_delete(request, pk):
    raw_lead = get_object_or_404(RawLead, pk=pk)
    raw_lead.delete()
    if request.headers.get('HX-Request'):
        return HttpResponse(status=204, headers={'HX-Trigger': 'rawLeadsChanged'})
    return redirect('leads:scraper-dashboard')


