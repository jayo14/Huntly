from .models import Message, Lead, FollowUpSchedule
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from datetime import timedelta

def generate_messages_for_lead(lead):
    """
    Generates 3 messages (initial, followup1, followup2) for a lead based on its tone and other details.
    """
    templates = {
        'professional': {
            'initial': {
                'subject': "Regarding your challenges with {problem} at {business_name}",
                'body': "Dear {contact_name},\n\nI noticed that {business_name} might be facing some difficulties with {problem}. We have a proven solution: {offer}.\n\nWould you be open to a brief professional discussion about how we can help?\n\nBest regards,\nThe team"
            },
            'followup1': {
                'subject': "Following up on our solution for {problem}",
                'body': "Dear {contact_name},\n\nI'm following up on my previous message regarding {problem}. I believe {offer} could significantly benefit {business_name}.\n\nPlease let me know if you have a moment to talk this week.\n\nBest regards,\nThe team"
            },
            'followup2': {
                'subject': "Final follow-up: Streamlining {business_name}'s operations",
                'body': "Dear {contact_name},\n\nI haven't heard back from you regarding {problem}. I'll assume now isn't the right time, but I remain confident that {offer} is a great fit for {business_name}.\n\nFeel free to reach out whenever you're ready.\n\nBest regards,\nThe team"
            }
        },
        'casual': {
            'initial': {
                'subject': "Quick question about {business_name}",
                'body': "Hi {contact_name},\n\nI was checking out {business_name} and noticed you guys might be struggling with {problem}. We've been working on {offer} and thought it'd be right up your alley.\n\nDown to chat about it?\n\nCheers,\nJules"
            },
            'followup1': {
                'subject': "Just circling back!",
                'body': "Hey {contact_name},\n\nJust wanted to make sure you saw my last note about {problem}. Really think {offer} could help you out.\n\nLet me know what you think!\n\nBest,\nJules"
            },
            'followup2': {
                'subject': "One last try :)",
                'body': "Hi {contact_name},\n\nI'll stop bugging you after this, but I really wanted to help with {problem} via {offer}.\n\nHope to hear from you eventually!\n\nTake care,\nJules"
            }
        },
        'direct': {
            'initial': {
                'subject': "Fixing {problem} at {business_name}",
                'body': "{contact_name},\n\n{business_name} has a problem with {problem}. Our offer, {offer}, fixes this directly.\n\nAre you available for a 5-minute call tomorrow?\n\nRegards"
            },
            'followup1': {
                'subject': "Re: Fixing {problem}",
                'body': "{contact_name},\n\nChecking in on my previous message. {offer} is the best way to solve {problem} for {business_name}.\n\nWhen can we talk?"
            },
            'followup2': {
                'subject': "Last attempt: {problem}",
                'body': "{contact_name},\n\nThis is my final follow-up. If you want to solve {problem} with {offer}, let me know.\n\nOtherwise, I'll move on."
            }
        },
        'empathetic': {
            'initial': {
                'subject': "I understand the struggle with {problem}",
                'body': "Hi {contact_name},\n\nI know how frustrating it can be to deal with {problem} at {business_name}. It's a common challenge, and we've developed {offer} specifically to help ease that burden.\n\nI'd love to hear about your experience and see if we can support you.\n\nWarmly"
            },
            'followup1': {
                'subject': "Thinking of {business_name} and {problem}",
                'body': "Hi {contact_name},\n\nI was just thinking about the {problem} you're facing. I truly believe {offer} can make things easier for you and your team.\n\nIs there anything I can do to help right now?"
            },
            'followup2': {
                'subject': "Always here to help with {problem}",
                'body': "Hi {contact_name},\n\nI understand you're busy. I'll leave you be for now, but please know that {offer} is always here when you're ready to tackle {problem}.\n\nWishing you the best"
            }
        }
    }

    tone = lead.tone if lead.tone in templates else 'professional'
    context = {
        'business_name': lead.business_name,
        'contact_name': lead.contact_name or "there",
        'problem': lead.problem or "your current processes",
        'offer': lead.offer or "our specialized services"
    }

    generated_messages = []
    for msg_type in ['initial', 'followup1', 'followup2']:
        template = templates[tone][msg_type]
        message, created = Message.objects.update_or_create(
            lead=lead,
            type=msg_type,
            defaults={
                'subject': template['subject'].format(**context),
                'body': template['body'].format(**context)
            }
        )
        generated_messages.append(message)

    return generated_messages

def send_lead_email(message_obj):
    """
    Sends an email for a given Message object with rate limiting (20/day).
    """
    today = timezone.now().date()
    sent_today_count = Message.objects.filter(sent_at__date=today).count()

    if sent_today_count >= 20:
        return False, "Rate limit reached: Max 20 emails per day."

    lead = message_obj.lead
    if not lead.email:
        return False, f"Lead {lead.business_name} has no email address."

    try:
        send_mail(
            subject=message_obj.subject,
            message=message_obj.body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[lead.email],
            fail_silently=False,
        )

        message_obj.sent_at = timezone.now()
        message_obj.save()

        # Update lead status if initial
        if message_obj.type == 'initial':
            lead.status = 'contacted'
            lead.save()

            # Schedule follow-ups
            FollowUpSchedule.objects.get_or_create(
                lead=lead,
                message_type='followup1',
                defaults={'scheduled_date': timezone.now().date() + timedelta(days=4)}
            )
            FollowUpSchedule.objects.get_or_create(
                lead=lead,
                message_type='followup2',
                defaults={'scheduled_date': timezone.now().date() + timedelta(days=9)}
            )

        return True, "Email sent successfully."
    except Exception as e:
        return False, f"Failed to send email: {str(e)}"

def process_followups_task():
    """
    Task to check for due follow-ups and send them.
    Called by cron job.
    """
    today = timezone.now().date()
    due_schedules = FollowUpSchedule.objects.filter(
        scheduled_date__lte=today,
        sent=False,
        lead__status='contacted' # Only send if they haven't replied
    )

    count = 0
    for schedule in due_schedules:
        lead = schedule.lead
        # Double check if lead has replied in the meantime (though status filter should handle it)
        if lead.status == 'replied':
            continue

        message_obj = lead.messages.filter(type=schedule.message_type).first()
        if message_obj and not message_obj.sent_at:
            success, msg = send_lead_email(message_obj)
            if success:
                schedule.sent = True
                schedule.save()
                count += 1

    return f"Processed {count} follow-up emails."
