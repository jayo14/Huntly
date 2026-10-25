"""Career Profile Merge and Consolidation Engine.

Merges user-approved import draft data into the canonical Master Career Profile.
Performs smart deduplication, preserves existing verified facts,
and sets provenance tracking on approved entries.
"""

from typing import Dict, Any, List, Optional
from django.db import transaction
from resumes.models import Resume, ResumeImport


def merge_skills(existing_skills: List[Dict[str, Any]], imported_skills: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge and deduplicate skills by case-insensitive name."""
    merged = list(existing_skills)
    existing_names = {s.get('name', '').strip().lower() for s in existing_skills if isinstance(s, dict)}

    for s in imported_skills:
        if not isinstance(s, dict):
            continue
        name = s.get('name', '').strip()
        if not name:
            continue
        if name.lower() not in existing_names:
            s_copy = dict(s)
            s_copy['provenance'] = 'confirmed_by_user'
            merged.append(s_copy)
            existing_names.add(name.lower())

    return merged


def merge_experiences(existing_exps: List[Dict[str, Any]], imported_exps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge work experiences, matching on company and role to avoid duplicates."""
    merged = list(existing_exps)

    def exp_key(e):
        c = (e.get('company') or '').strip().lower()
        r = (e.get('role') or '').strip().lower()
        return f"{c}::{r}"

    existing_keys = {exp_key(e) for e in existing_exps if isinstance(e, dict)}

    for e in imported_exps:
        if not isinstance(e, dict):
            continue
        k = exp_key(e)
        if k in existing_keys:
            # Entry already exists; find matching experience and add any novel accomplishments
            for existing in merged:
                if exp_key(existing) == k:
                    existing_acc = set(existing.get('accomplishments', []))
                    for acc in e.get('accomplishments', []):
                        if acc not in existing_acc:
                            existing.setdefault('accomplishments', []).append(acc)
                            existing_acc.add(acc)
                    break
        else:
            e_copy = dict(e)
            e_copy['provenance'] = 'confirmed_by_user'
            merged.append(e_copy)
            existing_keys.add(k)

    return merged


def merge_projects(existing_projects: List[Dict[str, Any]], imported_projects: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge projects, matching on case-insensitive project name."""
    merged = list(existing_projects)
    existing_names = {p.get('name', '').strip().lower() for p in existing_projects if isinstance(p, dict)}

    for p in imported_projects:
        if not isinstance(p, dict):
            continue
        name = p.get('name', '').strip()
        if not name:
            continue
        if name.lower() not in existing_names:
            p_copy = dict(p)
            p_copy['provenance'] = 'confirmed_by_user'
            merged.append(p_copy)
            existing_names.add(name.lower())

    return merged


def merge_education(existing_edu: List[Dict[str, Any]], imported_edu: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge education entries matching institution and degree."""
    merged = list(existing_edu)

    def edu_key(ed):
        inst = (ed.get('institution') or '').strip().lower()
        deg = (ed.get('degree') or '').strip().lower()
        return f"{inst}::{deg}"

    existing_keys = {edu_key(ed) for ed in existing_edu if isinstance(ed, dict)}

    for ed in imported_edu:
        if not isinstance(ed, dict):
            continue
        k = edu_key(ed)
        if k not in existing_keys:
            ed_copy = dict(ed)
            ed_copy['provenance'] = 'confirmed_by_user'
            merged.append(ed_copy)
            existing_keys.add(k)

    return merged


def merge_certifications(existing_certs: List[Dict[str, Any]], imported_certs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge certifications matching on certification name."""
    merged = list(existing_certs)
    existing_names = {c.get('name', '').strip().lower() for c in existing_certs if isinstance(c, dict)}

    for c in imported_certs:
        if not isinstance(c, dict):
            continue
        name = c.get('name', '').strip()
        if not name:
            continue
        if name.lower() not in existing_names:
            c_copy = dict(c)
            c_copy['provenance'] = 'confirmed_by_user'
            merged.append(c_copy)
            existing_names.add(name.lower())

    return merged


@transaction.atomic
def apply_import_to_profile(
    user,
    import_obj: ResumeImport,
    approved_data: Dict[str, Any],
    merge_strategy: str = 'merge'
) -> Resume:
    """Save user-approved information into the user's canonical Career Profile.

    :param user: The authenticated user.
    :param import_obj: The ResumeImport instance.
    :param approved_data: The dictionary of confirmed, reviewed candidate fields.
    :param merge_strategy: 'merge' (add to existing Master Profile) or 'new' (create separate profile).
    :return: The updated or newly created Resume instance.
    """
    master_resume = Resume.objects.filter(user=user, is_master=True).first()

    if merge_strategy == 'new' or not master_resume:
        # Create new profile
        resume = Resume(user=user)
        resume.full_name = approved_data.get('full_name', '') or user.get_full_name() or user.username
        resume.tagline = approved_data.get('tagline', '')
        resume.email = approved_data.get('email', '') or user.email
        resume.phone = approved_data.get('phone', '')
        resume.location = approved_data.get('location', '')
        resume.linkedin = approved_data.get('linkedin', '')
        resume.github = approved_data.get('github', '')
        resume.portfolio = approved_data.get('portfolio', '')
        resume.website = approved_data.get('website', '')
        resume.summary = approved_data.get('summary', '')

        # Set verified provenance on all imported arrays
        exps = approved_data.get('experiences', [])
        for e in exps:
            e['provenance'] = 'confirmed_by_user'
        skills = approved_data.get('technical_skills', [])
        for s in skills:
            s['provenance'] = 'confirmed_by_user'
        projs = approved_data.get('projects', [])
        for p in projs:
            p['provenance'] = 'confirmed_by_user'
        edus = approved_data.get('education', [])
        for ed in edus:
            ed['provenance'] = 'confirmed_by_user'
        certs = approved_data.get('certifications', [])
        for c in certs:
            c['provenance'] = 'confirmed_by_user'

        resume.experiences = exps
        resume.technical_skills = skills
        resume.projects = projs
        resume.education = edus
        resume.certifications = certs
        resume.languages = approved_data.get('languages', [])
        resume.awards = approved_data.get('awards', [])

        resume.save()
        if not master_resume:
            resume.consolidate_as_master()
    else:
        # Merge into existing Master Profile
        resume = master_resume

        # Only update scalar fields if existing is empty or user explicitly updated
        if not resume.full_name and approved_data.get('full_name'):
            resume.full_name = approved_data['full_name']
        if not resume.tagline and approved_data.get('tagline'):
            resume.tagline = approved_data['tagline']
        if not resume.email and approved_data.get('email'):
            resume.email = approved_data['email']
        if not resume.phone and approved_data.get('phone'):
            resume.phone = approved_data['phone']
        if not resume.location and approved_data.get('location'):
            resume.location = approved_data['location']
        if not resume.summary and approved_data.get('summary'):
            resume.summary = approved_data['summary']

        # Social & web links
        if not resume.linkedin and approved_data.get('linkedin'):
            resume.linkedin = approved_data['linkedin']
        if not resume.github and approved_data.get('github'):
            resume.github = approved_data['github']
        if not resume.portfolio and approved_data.get('portfolio'):
            resume.portfolio = approved_data['portfolio']

        # Merge collection fields cleanly without duplicate data
        resume.technical_skills = merge_skills(resume.technical_skills, approved_data.get('technical_skills', []))
        resume.experiences = merge_experiences(resume.experiences, approved_data.get('experiences', []))
        resume.projects = merge_projects(resume.projects, approved_data.get('projects', []))
        resume.education = merge_education(resume.education, approved_data.get('education', []))
        resume.certifications = merge_certifications(resume.certifications, approved_data.get('certifications', []))

        # Languages and awards
        existing_langs = {l.get('name', '').lower() for l in (resume.languages or []) if isinstance(l, dict)}
        for lang in approved_data.get('languages', []):
            if isinstance(lang, dict) and lang.get('name', '').lower() not in existing_langs:
                resume.languages.append(lang)
                existing_langs.add(lang['name'].lower())

        resume.save()

    # Link import record to resulting profile and mark completed
    import_obj.status = 'completed'
    import_obj.target_resume = resume
    import_obj.save(update_fields=['status', 'target_resume', 'updated_at'])

    return resume
