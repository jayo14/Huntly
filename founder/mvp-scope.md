<!-- /founder:mvp-scope · 2026-10-22 · input: triage existing code and define the exact list of files to edit, delete, or add. -->
# MVP scope: Huntly (Job Hunter)

## 1. Feature triage

| Feature | Category | Reasoning |
|---|---|---|
| **Master profile builder** | Must have | The AI cannot tailor a resume without a structured source of truth. |
| **Job description paste & keyword extraction** | Must have | Core value driver: extracts role requirements and matches them against candidate skills. |
| **One-click resume bullet tailoring (DOCX export)** | Must have | The primary deliverable candidates use to apply. |
| **Role-specific cover letter generation** | Must have | Saves 30 minutes per application; highest perceived user value after the resume. |
| **Application pipeline Kanban** | Must have | Gives users a reason to return daily to track status from Saved to Offer. |
| **Job posting URL scraper (Greenhouse, Lever)** | Should have | Convenient, but candidates can paste raw job descriptions on day one. |
| **Recruiter email finder & SMTP outreach** | Should have | Strong differentiator, but not strictly needed to submit tailored applications. |
| **Chrome autofill extension (Simplify clone)** | Won't have | Building and maintaining an ATS DOM-injection extension takes months. Cut for MVP. |
| **Selenium Google search scraper** | Won't have | Scraping Google search results for small business websites is useless for job hunting. |
| **Freelance client payment ledger (`Payment` model)** | Won't have | Remnant from freelance resume writing. Has zero value in a self-serve job hunting tool. |
| **Outreach automation rules engine (`AutomationRule`)** | Won't have | Drip automation on personal job applications leads to embarrassing candidate errors. |

## 2. MVP definition

> **"A candidate can paste any job description, generate an ATS-tailored resume (DOCX) and custom cover letter, and track the application in under 2 minutes."**

Features required to achieve this:
1. Master Profile editor (stores all career history and skills).
2. Job Description analyzer (extracts required skills and keywords).
3. Tailored Resume & Cover Letter generator (uses an LLM to rewrite bullet points and draft a 3-paragraph letter).
4. ATS-compliant DOCX resume exporter.
5. 5-stage Application Kanban tracker (Saved, Applied, Interviewing, Offer, Rejected).

## 3. User flow

```
Step 1: User creates an account and fills out their Master Profile (or uploads existing resume text).
Step 2: User clicks "New Application", pastes the target job title, company, and job description.
Step 3: Huntly extracts key keywords, displays matched skills, and generates tailored bullet points + a custom cover letter.
Step 4: User reviews, clicks "Download DOCX", submits application on the job board, and marks status as "Applied".
```

## 4. Codebase triage: exact file changes

### Files to delete
- `resumes/migrations/0003_payment_user_resume_user.py`: remove `Payment` model migrations.
- `leads/scraper_service.py`: delete the local Selenium Google search scraper (saves compute, memory, and headless Chrome binary headaches).
- `leads/templates/leads/scraper*.html`: delete all 4 scraper dashboard and session monitoring templates.
- `leads/templates/leads/automation.html` & `leads/templates/leads/rule_form.html`: delete automation rules templates.
- `leads/templates/leads/partials/scraper*.html`: delete all scraper partials.
- `leads/templates/leads/partials/rule*.html`: delete rule partials.

### Files to edit
1. **`leads/models.py`**:
   - Delete `ScraperJob`, `RawLead`, `AutomationRule`, and `AppSetting`.
   - Rename `Lead` to `JobApplication` (or refactor fields):
     - `business_name` -> `company_name`
     - `contact_name` -> `role_title`
     - `website` -> `job_url`
     - `problem` -> `job_description`
     - `status`: change choices to `saved`, `applied`, `interviewing`, `offer`, `rejected`.
     - Add fields: `tailored_resume_text` (TextField), `cover_letter` (TextField).
2. **`resumes/models.py`**:
   - Delete the `Payment` model and its foreign keys.
   - Keep `Resume` as the user's master candidate profile.
3. **`leads/views.py`**:
   - Refactor `pipeline`: display columns for `Saved`, `Applied`, `Interviewing`, `Offer`, `Rejected`.
   - Refactor `generate_message`: replace the static f-string with an LLM call taking the candidate's `Resume` and the `JobApplication.job_description` to produce the tailored bullet points and cover letter.
   - Refactor `dashboard`: update funnel metrics to show Total Jobs Saved, Applied, Active Interviews, and Offers.
   - Delete all scraper views (`scraper_dashboard`, `scraper_session_detail`, `raw_lead_*`) and rule views (`rule_create`, `toggle_rule`, `rule_delete`).
4. **`resumes/views.py`**:
   - Delete `payment_list` and `payment_create` views.
   - Update `resume_download` to accept an optional `job_application_id` parameter to render either the master resume or a role-tailored resume.
5. **`core/templates/core/landing.html`**:
   - Update headline: "Land 3x More Interviews with Role-Tailored Resumes in 30 Seconds".
   - Replace lead scraper copy with ATS optimization and cover letter generator features.
6. **`huntly/urls.py` & `leads/urls.py` & `resumes/urls.py`**:
   - Clean up dead routes for scraper, rules, and payments.

### Files to add
1. **`leads/services/llm_tailor.py`**:
   - Simple service function: calls an LLM (Gemini or OpenAI API) with a structured prompt containing the master resume and target job description, returning tailored bullet points, matched keywords, and a cover letter.
2. **`leads/templates/leads/job_application_form.html`**:
   - Clean modal or page where the user pastes the job description, reviews generated bullet points and cover letter side-by-side, and clicks Save.

## 5. Technical scope

- **Build vs. buy**:
  - LLM API: Buy (OpenAI `gpt-4o-mini` or Google `gemini-1.5-flash` at under $0.001 per tailored resume).
  - Auth: Built (Django auth already operational).
  - Storage & DOCX: Built (WhiteNoise for static, Node/python-docx for generation).
  - Payments: Buy (Stripe Checkout or LemonSqueezy link when ready).
- **Stack**: Django 6, SQLite / Postgres, Tailwind CSS, HTMX, Alpine.js, LLM API.
- **Hosting**:
  - Web + DB: Render, Fly.io, or Railway ($5 to $10/month).
  - By removing Selenium and headless Chrome, memory footprint drops from 1.5GB to under 256MB.
- **Build time**:
  - Model cleanup and migrations: 2 hours.
  - LLM tailoring service and prompt engineering: 4 hours.
  - Views and template updates: 6 hours.
  - Total time for one full-stack engineer: **12 to 16 working hours (2 days)**.

## 6. What you are not building, and why

1. **Chrome extension for ATS form autofill**:
   - *Why it feels important*: Simplify has one and it looks flashy.
   - *Why it does not matter yet*: Greenhouse, Workday, and Lever constantly change input IDs. Maintaining an extension consumes 80% of engineering time before verifying whether users even like your resumes.
   - *When to revisit*: When 200 users actively tailor at least 5 resumes per week on the web app.
2. **Automated job board crawler**:
   - *Why it feels important*: Users want jobs served to them on a platter.
   - *Why it does not matter yet*: Candidates already find jobs on LinkedIn and Indeed. Your differentiator is tailoring and conversion, not indexing.
   - *When to revisit*: Post-launch, if users request automated alerts for saved searches.
3. **Automated bot application submitter**:
   - *Why it feels important*: Users dream of pressing a button to apply to 1,000 jobs.
   - *Why it does not matter yet*: Auto-apply bots trigger ATS spam filters and get candidate emails blacklisted.
   - *When to revisit*: Never. Keep human-in-the-loop application submission.
4. **Custom visual resume designer / PDF drag-and-drop**:
   - *Why it feels important*: People want pretty resumes.
   - *Why it does not matter yet*: ATS parsers prefer clean, standard single-column text. Fancy multi-column layouts fail ATS scans.
   - *When to revisit*: If expanding to creative fields (design, video).
5. **Multi-user team / enterprise accounts**:
   - *Why it feels important*: B2B university career center sales.
   - *Why it does not matter yet*: You need direct consumer feedback and fast iteration first.
   - *When to revisit*: At $20k MRR.

## 7. Launch criteria

- [ ] User can sign up, log in, and fill their Master Profile.
- [ ] User can paste a job description and receive 3 to 5 tailored bullet points matching target keywords within 10 seconds.
- [ ] User can generate and edit a 3-paragraph cover letter tailored to the job.
- [ ] User can download an ATS-compliant `.docx` resume containing the tailored bullets.
- [ ] User can move applications across the Kanban board (Saved -> Applied -> Interviewing -> Offer).
- [ ] All 67 existing base tests updated and passing.

**What can be ugly at launch:**
- Mobile experience: 95% of candidates tailor resumes on desktop while applying. Mobile can be basic.
- No automated PDF export: Users can open the `.docx` file and save as PDF.
- Copy-paste job descriptions: No need for automated URL scraping on day one.

**First test with 10 users:**
Give 10 active job seekers free access. Have each tailor 3 real job applications and measure their feedback on bullet point accuracy and time saved.
