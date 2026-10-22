# Plan 004: Remediate Stored XSS in Outreach Message Generator

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 5e1e430..HEAD -- leads/views.py leads/templates/leads/lead_detail_modal.html`

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: plans/003-implement-user-multi-tenancy-and-data-isolation.md
- **Category**: security
- **Planned at**: commit `5e1e430`, 2026-10-21

## Why this matters

In `leads/views.py:221-225`, the `generate_message` endpoint returns an inline HTML string containing a `<script>` tag populated with Python `json.dumps()` values directly into the browser DOM:
`return HttpResponse(f'<script>document.getElementsByName("subject")[0].value = {subject_js}; document.getElementsByName("body")[0].value = {body_js};</script>')`
`json.dumps()` does not escape `</script>` tags. If a lead's name, problem description, or offer contains `</script><script>...`, the browser prematurely closes the script tag and executes arbitrary injected JavaScript.

## Current state

- `leads/views.py`:
```python
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
```
- In `lead_detail_modal.html`, HTMX calls `hx-post="{% url 'leads:generate-message' lead.pk %}"` and targets an element or swaps the response into the DOM.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Run tests | `python3 manage.py test leads` | All tests pass |

## Scope

**In scope**:
- `leads/views.py` (`generate_message` view)
- `leads/templates/leads/lead_detail_modal.html`
- `leads/tests.py`

**Out of scope**:
- Do not modify `send_message` or other views in this plan.

## Steps

1. In `leads/views.py`:
   - Change `generate_message` to return a `JsonResponse` containing `{'subject': subject, 'body': body}`, OR return an HTML snippet that updates the form values via safe HTMX Out-of-Band (`hx-swap-oob`) elements with auto-escaped template tags:
   ```html
   <input type="text" name="subject" value="{{ subject }}" id="message-subject" hx-swap-oob="true" ...>
   <textarea name="body" id="message-body" hx-swap-oob="true" ...>{{ body }}</textarea>
   ```
   Or return JSON and handle it via client-side Alpine/event dispatch without raw script tag rendering.
2. If using HTMX OOB swap:
   - In `leads/templates/leads/lead_detail_modal.html`, give `id="message-subject"` and `id="message-body"` to the input and textarea fields.
   - Render the partial `leads/partials/generated_message_fields.html` with Django's built-in template auto-escaping enabled.
3. In `leads/tests.py`, add a test case with malicious payload:
   - Create a lead where `problem="</script><script>alert('xss')</script>"`.
   - Call `generate_message` and verify that the response cannot execute unescaped script blocks.
4. Run tests:
   ```bash
   python3 manage.py test leads
   ```

## STOP conditions

- If HTMX version in `base.html` doesn't support OOB swaps, verify with simple test or use JsonResponse with safe event handler.
