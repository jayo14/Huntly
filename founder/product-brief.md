<!-- /founder:product-brief · 2026-10-22 · input: Let's make it Job Hunter; the scraping would still be useful, right? and you know how simplify works, right? So, perhaps something like that, but the resume is automatically tailored for each role,, and auto cover letter generator -->
# Product brief: Huntly (Job Hunter)

## 1. Problem statement

Job seekers in 2026 apply to an average of 150 to 300 jobs before receiving an offer. Applicant Tracking Systems (ATS) filter out over 70% of resumes before a human recruiter reads them because candidates send generic, unaligned resumes. Today, candidates spend 45 minutes per application manually tweaking bullet points, hunting for keywords, and drafting cover letters. Alternatively, they blast 500 identical generic applications through spam bots and get zero interviews.

## 2. Target audience

Active mid-level software engineers, product managers, and knowledge workers who have submitted more than 50 applications in the last 30 days without booking an interview. (Run `/founder:persona-gen` for detailed target buyer personas).

## 3. Value proposition

Huntly helps active tech job seekers double their interview callback rates by instantly matching their master profile against any job posting to generate tailored ATS resumes and cover letters in 30 seconds, unlike Simplify Jobs which charges $39.99/month mainly for form autofill or Teal which charges $29/month but requires heavy manual editing.

## 4. How the scraping fits in

Your current Selenium Google scraper (`leads/scraper_service.py`) searches for local business websites. That specific scraping logic cannot be used as-is, but the scraping architecture can be repurposed for two jobs:

1. **Job Description Extraction (URL Parser)**: Instead of scraping Google results, the scraper takes a job URL (from Greenhouse, Lever, Ashby, or LinkedIn) and extracts the role title, required hard skills, and responsibilities.
2. **Recruiter and Hiring Manager Discovery**: When a user saves a job at Stripe, the scraper runs a targeted search: `site:linkedin.com/in/ ("recruiter" OR "engineering manager") "Stripe"`, finding the hiring lead so the candidate can send a direct outreach email using Huntly's built-in SMTP sender.

Note on browser extensions vs backend scrapers: Simplify works as a Chrome extension because the user's browser already has access to authenticated job boards without triggering Cloudflare blocks. For MVP, allowing users to paste the job text directly or paste a public job URL is 10 times more reliable than running headless Chrome on your server.

## 5. Core features (MVP)

1. **Master profile and resume builder**:
   - Single repository for all career history, projects, metrics, and technical skills.
   - *Why it is essential*: AI cannot tailor bullet points without a comprehensive source of truth.

2. **Job description keyword extractor**:
   - Accepts a pasted job description or job URL; extracts the top 10 required technical keywords and core competencies.
   - *Why it is essential*: Candidates fail ATS screens when their resumes lack exact keyword matches.

3. **Role-tailored resume generator**:
   - Reorders and rewrites bullet points from the master profile to match the target job description while preserving truthfulness. Exports to ATS-compliant DOCX and PDF.
   - *Why it is essential*: This delivers the core value proposition.

4. **Contextual cover letter generator**:
   - Generates a 3-paragraph, role-specific cover letter connecting the candidate's past wins to the specific requirements of the job.
   - *Why it is essential*: Most application portals still have a cover letter field; writing them by hand is the largest time sink in the application process.

5. **Job application Kanban pipeline**:
   - Repurposed from `leads/pipeline.html` with stages: Saved, Applied, Interviewing, Offer, Rejected.
   - *Why it is essential*: Keeps job seekers returning daily to track their pipeline.

6. **Recruiter outreach email composer**:
   - Uses Huntly's existing `Message` model and SMTP integration to draft and send a short, 4-sentence cold note to the hiring manager.
   - *Why it is essential*: Directly pitching the hiring manager bypasses the ATS queue and gives Huntly an edge over pure resume tools.

## 6. Success metrics (First 90 days)

1. **Activation rate**: 60% of signups generate at least 1 tailored resume within 10 minutes of creating an account.
2. **Weekly active applications**: Active users tailor at least 5 resumes and cover letters per week.
3. **Interview conversion rate**: At least 15% of applications sent using Huntly tailored resumes result in a recruiter screen or hiring manager interview (industry benchmark for cold applications is 2% to 4%).
4. **Paid conversion rate**: 4% of free users upgrade to a paid weekly or monthly plan after exporting 3 tailored resumes.

## 7. Risks and assumptions

1. **Assumption: Users will trust AI to rewrite their career history.**
   - *Test for under $200*: Build a landing page with a before-and-after resume comparison. Run $100 in Google Search ads on "ATS resume optimizer" and measure email signup conversion (target: >8%).
2. **Assumption: Job seekers are willing to pay upfront despite being unemployed.**
   - *Test for under $200*: Put a $12/week paywall after the third resume export. If fewer than 2% of active users put in card details, pivot to a freemium model with a referral loop.
3. **Assumption: Server-side scraping of job boards will not get IP blocked.**
   - *Test for under $200*: Test scraping 100 job URLs across Greenhouse, Lever, and Workday using standard HTTP requests. If blocked, provide an instant text paste box or build a lightweight Chrome extension like Simplify.

## 8. Go-to-market snapshot

1. **Channel 1: Reddit career and job search communities (r/jobs, r/cscareerquestions, r/resumes)**
   - *Estimated CAC*: $0 (Organic founder participation).
   - *Tactic*: Post tear-downs of how ATS parsers reject qualified resumes and offer free tailored resumes to the first 50 commenters.
2. **Channel 2: LinkedIn job seeker network**
   - *Estimated CAC*: $15 to $25 per paying subscriber.
   - *Tactic*: Create short comparison videos showing a generic resume scoring 42% on ATS vs Huntly tailored resume scoring 94% in 20 seconds.
3. **Channel 3: TikTok and Instagram Reels (Career tech niche)**
   - *Estimated CAC*: $10 to $20 per paying subscriber.
   - *Tactic*: "Stop spending 1 hour on each application: watch this tool tailor your resume and cover letter in 30 seconds."
