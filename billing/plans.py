from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class PlanDefinition:
    id: str
    name: str
    tagline: str
    price_usd: float
    billing_interval: str  # 'lifetime', 'weekly', 'monthly'
    max_master_profiles: int
    max_tailored_applications: int
    max_tracked_jobs: int
    max_outreach_pitches_per_period: int
    can_export_docx: bool
    can_export_pdf: bool
    has_ats_gap_analysis: bool
    has_recruiter_pitch: bool
    paystack_plan_code: Optional[str] = None
    stripe_price_id: Optional[str] = None


PLANS: Dict[str, PlanDefinition] = {
    'free': PlanDefinition(
        id='free',
        name='Free Test Drive',
        tagline='Build your Master Profile and test drive AI tailoring.',
        price_usd=0.0,
        billing_interval='lifetime',
        max_master_profiles=1,
        max_tailored_applications=3,
        max_tracked_jobs=25,
        max_outreach_pitches_per_period=0,
        can_export_docx=True,
        can_export_pdf=False,
        has_ats_gap_analysis=False,
        has_recruiter_pitch=False,
    ),
    'job_sprint': PlanDefinition(
        id='job_sprint',
        name='Job Sprint',
        tagline='High-intensity weekly sprint for active job seekers.',
        price_usd=9.0,
        billing_interval='weekly',
        max_master_profiles=1,
        max_tailored_applications=50,
        max_tracked_jobs=1000,
        max_outreach_pitches_per_period=10,
        can_export_docx=True,
        can_export_pdf=True,
        has_ats_gap_analysis=False,
        has_recruiter_pitch=True,
        paystack_plan_code='PLN_jobsprint_weekly',
        stripe_price_id='price_jobsprint_weekly',
    ),
    'pro_hunter': PlanDefinition(
        id='pro_hunter',
        name='Pro Hunter',
        tagline='The complete job-search operating system for full campaigns.',
        price_usd=19.0,
        billing_interval='monthly',
        max_master_profiles=3,
        max_tailored_applications=200,
        max_tracked_jobs=5000,
        max_outreach_pitches_per_period=50,
        can_export_docx=True,
        can_export_pdf=True,
        has_ats_gap_analysis=True,
        has_recruiter_pitch=True,
        paystack_plan_code='PLN_prohunter_monthly',
        stripe_price_id='price_prohunter_monthly',
    ),
}


def get_plan(plan_id: str) -> PlanDefinition:
    """Safely return plan definition, defaulting to free tier for unrecognized plans."""
    return PLANS.get(plan_id, PLANS['free'])


def get_all_plans() -> Dict[str, PlanDefinition]:
    return PLANS
