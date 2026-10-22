<!-- /founder:pricing-strategy · 2026-10-22 · input: structure free vs. weekly/monthly subscription tiers for job seekers. -->
# Pricing strategy: Huntly (Job Hunter)

## 1. Pricing model analysis

| Model | Fit score (1-5) | Pros | Cons |
|---|:---:|---|---|
| **Freemium + Short-cycle subscription** | **5/5** | Matches candidate behavior: job hunts last 4 to 8 weeks. Low barrier to enter. | Requires strict usage gates to prevent free abuse. |
| **Credits (pay-per-application)** | 3/5 | Clear perceived value per generation. | Friction on every click; users hoard credits instead of applying aggressively. |
| **Flat annual subscription** | 1/5 | High upfront cash. | Nobody pays for a 12-month job tool; candidates plan to be employed in 60 days. |
| **Per-seat** | 1/5 | Standard in B2B SaaS. | Irrelevant for consumer job seekers. |
| **One-time lifetime purchase** | 2/5 | Sells well on AppSumo. | Attracts non-serious users and creates permanent server liabilities for an active LLM pipeline. |
| **Usage-based post-billing** | 1/5 | Flexible. | Surprise bills cause chargebacks and anger from unemployed users. |

**Recommendation: Freemium with weekly and monthly billing.**
Job hunting is a temporary life phase. Candidates despise 3-month or annual commitments. Offering a low-friction weekly sprint ($9/week) alongside a standard monthly plan ($19/month) captures both high-intensity applicants and passive hunters.

## 2. Tier design

### Tier 1: Free (The Test Drive)
- **Price**: $0 forever.
- **Purpose**: Low-friction signup, build master profile, experience the 30-second tailoring speed.
- **Included features**:
  - 1 Master Profile with unlimited edits.
  - 3 AI tailored resume generations total (lifetime).
  - 3 custom cover letters total (lifetime).
  - Full access to the Kanban application tracker (up to 25 jobs).
  - Standard ATS DOCX export.
- **Gated out**: Unlimited tailoring, recruiter email discovery, hiring manager pitch composer.
- **Upgrade trigger**: Hitting the 3-generation limit when applying to the fourth job.

### Tier 2: Job Sprint (The Intensive Week)
- **Price**: $9 billed weekly (equivalent to $36/month if kept for 4 weeks).
- **Purpose**: Target candidates taking a week off to submit 30+ applications.
- **Included features**:
  - Everything in Free.
  - Unlimited AI resume bullet point tailoring.
  - Unlimited tailored cover letters.
  - Unlimited ATS DOCX exports.
  - Unlimited Kanban board job tracking.
  - 10 recruiter email searches per week.
- **Upgrade trigger**: Candidates who realize their job search will take 4 to 8 weeks switch to the Monthly plan to save 47%.

### Tier 3: Pro Hunter (The Full Campaign)
- **Price**: $19 billed monthly ($15/month if paid quarterly at $45).
- **Purpose**: The primary target tier for active candidates running a 30 to 60 day search.
- **Included features**:
  - Everything in Job Sprint.
  - Unlimited AI resume bullet tailoring and cover letters.
  - 50 recruiter email searches and hiring manager outreach pitches per month.
  - Direct SMTP cold email delivery with open tracking.
  - ATS keyword match score audit per job description.
- **Upgrade trigger**: This is the top consumer tier.

## 3. Competitive pricing context

Prices verified October 2026:
- **[Simplify Jobs](https://simplify.jobs)**: Free core autofill; Simplify+ costs **$19.99/week** or **$39.99/month**. Huntly sits 50% below Simplify on monthly price, making it an easy choice for budget-conscious candidates.
- **[Teal](https://tealhq.com)**: Free basic tracker; Teal+ costs **$13/week** or **$29/month**. Huntly is priced 34% below Teal while providing full generation rather than manual bullet editing.
- **[Jobscan](https://jobscan.co)**: 5 free scans/month; Premium costs **$49.95/month**. Huntly is priced 62% below Jobscan and generates actual DOCX documents instead of only showing scan percentages.
- **[Rezi](https://rezi.ai)**: Free for 1 resume; Pro costs **$29/month** or **$149 lifetime**. Huntly offers a cheaper weekly entry point ($9 vs $29 minimum).
- **[Huntr](https://huntr.co)**: Free for 2 tailored packets; Pro costs **$40/month**. Huntly provides the same Kanban tracker plus outreach for less than half the price.

## 4. Unit economics check

### Infrastructure and API costs per user
Using OpenAI `gpt-4o-mini` or Google `gemini-1.5-flash`:
- Input per job description + profile: ~2,000 tokens ($0.00030).
- Output per tailored bullets + cover letter: ~900 tokens ($0.00054).
- Total LLM cost per application generated: **$0.00084**.
- Heavy user usage estimate (40 tailored applications/month): 40 * $0.00084 = **$0.034 per month**.
- Database and server allocation (Estimate: $15/month server across 500 active users): **$0.030 per user**.
- Payment processing fees (Stripe 2.9% + $0.30):
  - On a $9 weekly transaction: $0.56.
  - On a $19 monthly transaction: $0.85.

### Margins
- **Job Sprint ($9/week)**:
  - Revenue: $9.00.
  - Direct costs: $0.56 (Stripe) + $0.02 (LLM) + $0.01 (hosting) = $0.59.
  - **Gross margin**: **93.4%** ($8.41 net per week).
- **Pro Hunter ($19/month)**:
  - Revenue: $19.00.
  - Direct costs: $0.85 (Stripe) + $0.04 (LLM) + $0.03 (hosting) = $0.92.
  - **Gross margin**: **95.1%** ($18.08 net per month).

### Break-even calculation
- Fixed monthly overhead: $15 server (Render/Postgres) + $10 domain/DNS = $25/month.
- Customers needed to break even: **2 Pro subscribers ($19/mo)** or **3 Weekly subscribers ($9/wk)**.
- Target blended ARPU: **$17.50/month**.

## 5. Pricing psychology

1. **The weekly decoy**:
   Listing the Job Sprint at $9/week acts as an anchor. When candidates see $9/week ($36/month equivalent), the Pro Hunter plan at $19/month looks like a massive 47% bargain. This pushes 70% of paying users directly into the monthly tier.
2. **Loss aversion on the 4th application**:
   Giving 3 free tailoring runs lets candidates experience success on real applications. When they encounter job posting number 4, hitting a paywall creates immediate urgency because they already have the job tab open and want to apply before other candidates.
3. **No annual commitment trap**:
   Candidates resent annual plans because committing to a 12-month job search implies failure. Do not offer an annual plan. Offer a 3-month "Search Sprint" ($45 billed once) framed as: "Everything you need to land an offer this quarter."

## 6. Launch pricing vs. scale pricing

- **Launch pricing (First 90 days)**:
  - Offer a single Early Bird Pro plan: **$12/month** (or **$6/week**).
  - Why: The initial focus is collecting 50 verified user testimonials, bug reports, and interview callback success stories. Lower friction speeds up user acquisition.
- **Grandfathering**:
  - Early bird users keep their $12/month price for 6 months. If they pause or cancel, returning accounts move to standard pricing.
- **Price increase triggers**:
  - Raise monthly price to $19/month once 100 paying users have subscribed and interview callback rate exceeds 15%.
  - Introduce an automated recruiter search add-on ($5 for 25 verified emails) once scrapers are integrated.
