from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.http import HttpResponse
from django.views.decorators.http import require_POST
from django.contrib import messages
from .models import Lead
from .forms import LeadForm

def lead_list(request):
    leads = Lead.objects.all()
    return render(request, 'leads/leads_list.html', {'leads': leads})

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
    leads = Lead.objects.all()
    return render(request, 'leads/partials/lead_list_table.html', {'leads': leads})
