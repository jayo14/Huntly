<!-- /founder:validate-idea · 2026-10-22 · input: check through this app. What's it actually used for? Wht will people come back for? Why will they even use it? what problem does or could it solve? and what would make people pay? Suggestions to pivot? -->
# Idea validation: Huntly

## 30-second assessment

Huntly currently suffers from product schizophrenia. It bundles an unproxied Google scraper and basic email CRM with an unrelated resume builder and payment log. Nobody will pay for an app that tries to be both Apollo.io and Canva. To survive, you must kill one half immediately and focus entirely on a single customer who has a budget.

## What the app is actually used for today

The codebase contains two completely separate apps under one login:

1. **Local lead scraper and cold email CRM (`leads/`)**:
   - Takes a niche, keywords, and city name (for example: "plumbers in Chicago").
   - Runs a local headless Chrome browser to scrape the first 10 organic Google search results.
   - Parses the text for basic regex email and phone matches.
   - Puts raw leads into an approval queue, then moves them to a status board (New, Contacted, Replied, Proposal, Closed).
   - Generates an email via a hardcoded Python f-string and sends it through a single user-provided SMTP account.

2. **Resume generator and payment logger (`resumes/`)**:
   - Stores work history, skills, education, and passport photos.
   - Runs a Node.js script to output a formatted `.docx` file.
   - Contains a manual ledger to record cash or transfer payments from clients.

The landing page tries to market this frankenstein mix as "The Ultimate Sales Arsenal for Growth". In reality, sales reps do not write resumes, and job seekers do not run cold email pipelines.

## The five fatal questions

### Q1: Who is the customer, and would they pay for this today?
- **Current state**: Nobody will pay for the current bundle.
- **If focused on lead generation**: The customer is a solo agency owner, freelance web designer, or SEO consultant who sells to local brick-and-mortar businesses. They spend 10 to 15 hours a week finding prospects.
- **Willingness to pay**: Solo operators pay $30 to $60/month for working lead tools. But they will pay $0 for Huntly today because the scraper is blocked by Google CAPTCHAs after a dozen searches and lacks email verification.

### Q2: Why hasn't someone built this already?
People have built both sides, and the incumbents have deep moats:
- In local lead scraping: [D7 Lead Finder](https://reachkit.ai) charges $44.99/month for 3,500 leads per day with social links and tech stacks. [Outscraper](https://outscraper.com) sells Google Maps data for $3 per 1,000 records on a pay-as-you-go model.
- In cold outreach: [Instantly.ai](https://instantly.ai) charges $47/month with automated mailbox rotation, inbox warm-up, and deliverability protection.
- In resume building: [Teal](https://tealhq.com) and [Resume.io](https://resume.io) offer specialized AI resume tailoring and job tracking.
- **Why Huntly struggles**: Huntly uses a local headless browser on the server without proxies, CAPTCHA solvers, or multi-inbox rotation. Sending cold emails from a single personal Gmail SMTP will land the user in spam within 48 hours.

### Q3: What is the distribution advantage?
- **Current state**: None. There is no network effect and no viral loop. Every user must be acquired manually through cold outreach, YouTube tutorials, or paid ads.
- **Red flag**: A cold outreach tool that relies on standard content marketing to get users faces high customer acquisition costs against heavily funded competitors like Apollo and Instantly.

### Q4: Can this be a big business, or is it a feature?
- A raw Google scraper is a script, not a SaaS business.
- A local client acquisition system that guarantees deliverability and surfaces high-intent triggers (for example: "this dentist has an outdated HTTP-only website and no Google reviews") can be a $1M ARR business serving 1,000 agencies at $89/month.

### Q5: Can the founder actually build this?
- Scraping Google directly via Selenium at scale is an operational trap: Google changes its DOM constantly and bans IPs aggressively.
- The founder must switch from raw browser scraping to reliable paid APIs (like Google Places API, Outscraper API, or SerpApi) and focus engineering effort on the workflow: enrichment, audit generation, and pitch personalization.

## Idea scorecard

| Dimension | Score (1-5) | Notes |
|---|:---:|---|
| **Problem urgency** | 4/5 | Getting clients is the number one pain point for freelance agencies. |
| **Market size** | 4/5 | Millions of freelancers and boutique agencies globally. |
| **Willingness to pay** | 4/5 | B2B lead generation directly ties to revenue. High willingness to pay. |
| **Moat / Defensibility** | 1/5 | Basic scraping and f-string emails have zero technical moat. |
| **Distribution ease** | 2/5 | Saturated market with dominant venture-backed players. |
| **Unit economics** | 2/5 | High churn if leads fail to generate real client replies. |
| **Technical feasibility** | 2/5 | Direct Selenium scraping breaks quickly in production without proxies. |
| **Total score** | **19/35** | High problem urgency, but broken product architecture and split focus. |

## What will make people come back and pay?

Users churn from lead tools within 30 days if they do not book calls. To make people pay and stay:

1. **Lead accuracy and data enrichment**: Finding a generic `info@business.com` gets a 1% reply rate. Users will pay if you find the actual owner name, verified direct email, mobile phone, and Instagram DM handle.
2. **Built-in problem detection (The Hook)**: Instead of scraping only contact info, check the website for obvious problems:
   - Does the business lack an SSL certificate?
   - Is their Google Maps rating under 4.0?
   - Is their website slow or broken on mobile?
   - Are they running Facebook ads with no landing page?
3. **Evidence-based outreach**: If the software writes: *"Hey John, I saw your dental clinic on Main St has 14 negative reviews mentioning your slow booking system, here is how to fix it"*, the response rate multiplies by 5. Users will gladly pay $79/month for that workflow.

## Three pivot options

### Pivot option 1: The Local Agency Audit and Prospecting Engine (Recommended)
- **Action**: Delete the `resumes/` app completely.
- **Positioning**: "Find local businesses with broken websites and outdated SEO, then pitch them with an instant audit."
- **Customer**: Web designers, local SEO freelancers, marketing agencies.
- **Core feature**: User picks a city and industry. The tool generates a list of 50 local shops, automatically audits their site speed and SEO gaps, and drafts a custom audit email highlighting the exact fix.
- **Pricing**: $49/month for 500 audits, $99/month for 2,000 audits.

### Pivot option 2: The Freelance Client Tracker (Micro-CRM)
- **Action**: Keep the payment log and lead pipeline, drop the scraper and resume builder.
- **Positioning**: "The minimalist CRM for solo freelancers who hate HubSpot."
- **Customer**: Upwork freelancers and independent consultants.
- **Core feature**: Pipeline tracking, invoice logging, client follow-up reminders.
- **Pricing**: $15/month flat fee. (Downside: Low willingness to pay and tough competition from Notion and Bonsai).

### Pivot option 3: The Automated Job Hunter
- **Action**: Delete `leads/`, keep `resumes/`.
- **Positioning**: "Tailor your resume and pitch hiring managers directly for open roles."
- **Customer**: Active tech job seekers and career switchers.
- **Core feature**: Import a job description, tailor the resume DOCX, find the recruiter's email on LinkedIn, and send a cold application.
- **Pricing**: $29/month while job hunting. (Downside: High natural churn once the user lands a job).

## Verdict and next action

**Verdict: PIVOT (Option 1).**

Remove the resume builder. Reposition Huntly strictly as a B2B client acquisition tool for local marketing freelancers. Replace fragile Selenium Google scraping with structured Google Maps API data, and add automated website problem scoring so users send high-converting pitches instead of generic spam.
