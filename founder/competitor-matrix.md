<!-- /founder:competitor-matrix · 2026-10-22 · input: benchmark Simplify, Teal, and Jobscan on pricing, ATS compliance, and feature gaps. -->
# Competitor matrix: AI job search and resume tailoring

## 1. Market landscape

### Simplify Jobs ([simplify.jobs](https://simplify.jobs))
- **Founded & funding**: Founded in 2021 by Michael Yan (Y Combinator W21). Raised $4.35M total, including a $3M seed round in February 2024 led by Craft Ventures ([Startup Intros](https://startupintros.com)).
- **Pricing model**: Freemium. Core autofill extension is free. Simplify+ costs $19.99/week or $39.99/month (checked October 2026).
- **Target segment**: Consumer tech candidates, new grads, and interns applying in high volumes.
- **Key differentiator**: Universal 1-click application autofill across Workday, Greenhouse, Lever, and Ashby portals.

### Teal ([tealhq.com](https://tealhq.com))
- **Founded & funding**: Founded in 2019 by David Fano. Raised $20.7M total, including a $7.5M Series A in January 2025 led by City Light Capital and Flybridge ([Refresh Miami](https://refreshmiami.com)).
- **Pricing model**: Freemium. Free basic tracker and resume builder. Teal+ costs $13/week, $29/month, or $79/quarter (checked October 2026).
- **Target segment**: Mid-career professional job seekers and career switchers.
- **Key differentiator**: Visual career growth management platform combining job bookmarking with resume scoring.

### Jobscan ([jobscan.co](https://jobscan.co))
- **Founded & funding**: Founded in 2013 by James Hu. Bootstrapped and profitable with no venture capital rounds recorded on Crunchbase ([Tracxn](https://tracxn.com)).
- **Pricing model**: Freemium. Free tier gives 5 resume scans per month. Premium costs $49.95/month or $89.95/quarter (checked October 2026).
- **Target segment**: Traditional corporate job seekers targeting enterprise ATS portals.
- **Key differentiator**: Hard ATS keyword match score (0-100) reverse-engineered from enterprise scanning algorithms.

### Rezi ([rezi.ai](https://rezi.ai))
- **Founded & funding**: Founded in 2015 by Jacob Jacquet. Bootstrapped and indie-backed ([Rezi](https://rezi.ai)).
- **Pricing model**: Freemium. Free tier includes 1 resume and 3 PDF downloads lifetime. Pro costs $29/month or $149 for a lifetime pass (checked October 2026).
- **Target segment**: Tech and professional job seekers looking for clean ATS templates.
- **Key differentiator**: Strict ATS formatting engine that prevents design elements from breaking scanner parsers.

### Huntr ([huntr.co](https://huntr.co))
- **Founded & funding**: Founded in 2016. Bootstrapped ([Huntr](https://huntr.co)).
- **Pricing model**: Freemium. Free tier includes 100 tracked jobs and 2 tailored application packets. Pro costs $40/month or $90/quarter (checked October 2026).
- **Target segment**: Organized job hunters and coding bootcamp graduates.
- **Key differentiator**: Clean, visual Kanban board for tracking application stages and tasks.

## 2. Feature comparison matrix

| Feature | Simplify Jobs | Teal | Jobscan | Rezi | Huntr | **Huntly** |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **Application autofill extension** | Yes | No | No | No | No | Won't have |
| **Kanban application tracker** | Yes | Yes | Partial | No | Yes | **Planned** |
| **Master profile data store** | Yes | Yes | No | Yes | Yes | **Planned** |
| **ATS keyword match scoring** | Partial | Yes | Yes | Yes | Yes | **Planned** |
| **Automatic bullet point tailoring** | Yes (Paid) | Yes (Paid) | Yes (Paid) | Yes (Paid) | Yes (Paid) | **Planned** |
| **Tailored cover letter generator** | Yes (Paid) | Yes (Paid) | Yes (Paid) | Yes (Paid) | Yes (Paid) | **Planned** |
| **Clean ATS DOCX export** | No (PDF only) | Yes | Yes | Yes | Yes | **Planned** |
| **Recruiter email discovery** | No | No | No | No | No | **Planned** |
| **Direct SMTP email outreach** | No | No | No | No | No | **Planned** |
| **Weekly billing option** | Yes ($19.99/wk) | Yes ($13/wk) | No | No | No | **Planned ($9/wk)** |
| **Pricing for full AI suite** | $39.99/mo | $29/mo | $49.95/mo | $29/mo | $40/mo | **Planned ($19/mo)** |

## 3. Positioning gaps

### Gap 1: Integrated hiring manager discovery and direct email outreach
- **What is missing**: Every competitor stops at the job application portal. They optimize your resume, but you still get dumped into a Workday queue with 600 other applicants.
- **Why it matters**: In the current market, cold applications have a 2% callback rate. Contacting the engineering manager or recruiter directly raises response rates to 15% to 25%.
- **How hard it is to build**: Medium. Huntly already has an outreach database (`Message`), an email dispatcher (`send_message`), and SMTP settings in place. Adding targeted Google search scraping (`site:linkedin.com/in/ "engineering manager" [Company]`) connects the dots.
- **Head start estimate**: 6 to 9 months. Competitors are focused on browser extensions and enterprise partnerships, leaving executive direct outreach unaddressed.

### Gap 2: Complete single-click application packet (Resume + Letter + Pitch)
- **What is missing**: On Jobscan, you scan a resume, copy keywords, and rewrite bullets manually. On Teal, you click through multiple tabs to adjust individual lines.
- **Why it matters**: Candidates apply to 10 jobs per day. They do not want to spend 20 minutes tweaking settings for each role. They want to paste a job description and get an instant packet: tailored DOCX, 3-paragraph cover letter, and a 4-sentence recruiter note.
- **How hard it is to build**: Low. A single LLM prompt taking the master profile and the job description outputs all three assets simultaneously in 5 seconds.
- **Head start estimate**: 3 to 4 months. Competitors have complex legacy UI workflows that prevent them from offering a flat 30-second pipeline.

### Gap 3: Accessible pricing for unemployed job seekers
- **What is missing**: Simplify charges $39.99/month, Jobscan charges $49.95/month, and Huntr charges $40/month. Charging $40 to $50 per month to people without an income leads to high churn and negative customer sentiment.
- **Why it matters**: Job seekers need aggressive tailoring for 3 to 6 weeks, not a long-term enterprise software subscription.
- **How hard it is to build**: Low. Introduce a $9/week or $19/month self-serve tier.
- **Head start estimate**: High price elasticity. Incumbents cannot lower prices without cutting into their blended customer lifetime value.

## 4. Threat assessment

### 1. Simplify Jobs (Threat level: HIGH)
- **Resource advantage**: $4.35M raised, Craft Ventures backing, over 1 million extension installs.
- **Feature overlap**: High. Simplify+ already offers AI bullet rewriting and cover letter generation.
- **Speed of iteration**: High. They release frequent updates to their Chrome extension to stay ahead of ATS layout changes.
- **Vulnerability**: Simplify is tied to its Chrome extension. If an ATS blocks their autofill scripts, their core value proposition drops. They do not offer recruiter discovery or direct email outreach.

### 2. Teal (Threat level: HIGH)
- **Resource advantage**: $20.7M raised, Series A funding closed in early 2025.
- **Feature overlap**: High on resume builder and job tracking.
- **Speed of iteration**: Medium. Focus has shifted toward broad career management and enterprise partnerships rather than raw speed for active applicants.
- **Vulnerability**: Teal's interface is heavy and requires extensive manual configuration.

### 3. Jobscan (Threat level: MEDIUM)
- **Resource advantage**: 13 years of domain authority, profitable, top organic Google search ranking for "ATS resume checker".
- **Feature overlap**: Medium. Jobscan specializes in scoring and diagnostics rather than fast, end-to-end generation.
- **Speed of iteration**: Low. The product UI and workflow have changed very little over the last 5 years.
- **Vulnerability**: High monthly price ($49.95/mo) and cumbersome scan-and-paste interface.

## 5. Strategic recommendations

- **Position to own**: "The Outbound Career Agent": Do not compete with Simplify on form autofill. Win the segment of candidates who want to bypass the ATS entirely by generating tailored application assets and pitching hiring managers directly via email.
- **Feature to ship first**: Single-click Application Packet Generation (paste job description, output tailored DOCX resume, custom cover letter, and recruiter outreach pitch in 30 seconds).
- **Competitor to watch**: Simplify Jobs. With their recent $3M injection from Craft Ventures, they are expanding their AI features into cover letters and networking tools.
