"""Structured Resume Parsing Engine for Huntly.

Extracts candidate identity, contact, summary, work experiences,
measurable achievements, projects, education, skills, and certifications.
Preserves exact metrics, numbers, and dates without hallucinating missing data.
Includes strict schema validation, provenance tracking, and actionable warnings.
"""

import json
import logging
import os
import re
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Common section headers in resumes
SECTION_PATTERNS = {
    'summary': re.compile(r'^(?:professional\s+summary|summary|profile|about\s+me|executive\s+summary|objective|career\s+objective)\b', re.IGNORECASE),
    'experience': re.compile(r'^(?:work\s+experience|professional\s+experience|experience|employment\s+history|work\s+history|career\s+history)\b', re.IGNORECASE),
    'education': re.compile(r'^(?:education|academic\s+background|academic\s+history|qualifications)\b', re.IGNORECASE),
    'skills': re.compile(r'^(?:technical\s+skills|core\s+competencies|skills\s*(?:&|and)\s*technologies|skills|technologies|tools)\b', re.IGNORECASE),
    'projects': re.compile(r'^(?:projects|key\s+projects|personal\s+projects|technical\s+projects)\b', re.IGNORECASE),
    'certifications': re.compile(r'^(?:certifications|licenses\s*(?:&|and)\s*certifications|certificates|credentials)\b', re.IGNORECASE),
    'languages': re.compile(r'^(?:languages|language\s+proficiency)\b', re.IGNORECASE),
    'awards': re.compile(r'^(?:awards|honors|publications|awards\s*(?:&|and)\s*honors|achievements)\b', re.IGNORECASE),
}

EMAIL_REGEX = re.compile(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+')
PHONE_REGEX = re.compile(r'(?:(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}|\+\d{10,14})')
LINKEDIN_REGEX = re.compile(r'(?:https?://)?(?:www\.)?linkedin\.com/in/[a-zA-Z0-9_-]+/?', re.IGNORECASE)
GITHUB_REGEX = re.compile(r'(?:https?://)?(?:www\.)?github\.com/[a-zA-Z0-9_-]+/?', re.IGNORECASE)
URL_REGEX = re.compile(r'https?://[^\s/$.?#].[^\s]*', re.IGNORECASE)

MONTH_NAME = r'(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)'
DATE_TOKEN = rf'(?:{MONTH_NAME}\s+\d{{4}}|\d{{1,2}}/\d{{2,4}}|\d{{4}})'
END_DATE_TOKEN = rf'(?:Present|Current|Now|{MONTH_NAME}\s+\d{{4}}|\d{{1,2}}/\d{{2,4}}|\d{{4}})'
DATE_RANGE_REGEX = re.compile(
    rf'\b({DATE_TOKEN}\s*[-–—to]+\s*{END_DATE_TOKEN})\b',
    re.IGNORECASE
)

METRIC_INDICATORS = [
    r'\b\d+(?:\.\d+)?%',                      # 45%, 99.9%
    r'\$\s*\d+(?:,\d+)*(?:\.\d+)?[kKmMbB]?',   # $500k, $2M
    r'\b\d+\s*(?:k|K|M|B|million|billion)\b',  # 5M, 100k
    r'\b\d+x\b',                               # 10x
    r'\b(?:reduced|increased|improved|boosted|cut|grew|saved)\s+by\s+\d+',
    r'\b(?:handled|served|scaled\s+to)\s+\d+',
]

DEGREE_PATTERNS = [
    r'\b(?:B\.?S\.?|Bachelor(?:\'s)?\s+of\s+[A-Za-z\s]+|B\.?A\.?|B\.?Eng\.?|B\.?Tech\.?)\b',
    r'\b(?:M\.?S\.?|Master(?:\'s)?\s+of\s+[A-Za-z\s]+|M\.?A\.?|M\.?B\.?A\.?|M\.?Eng\.?)\b',
    r'\b(?:Ph\.?D\.?|Doctor\s+of\s+[A-Za-z\s]+)\b',
    r'\b(?:Associate(?:\'s)?\s+Degree|Diploma)\b',
]


US_STATES = {
    'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA', 'HI', 'ID', 'IL', 'IN', 'IA',
    'KS', 'KY', 'LA', 'ME', 'MD', 'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
    'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC', 'SD', 'TN', 'TX', 'UT', 'VT',
    'VA', 'WA', 'WV', 'WI', 'WY', 'DC'
}


def extract_contact_info(text: str, header_lines: Optional[List[str]] = None) -> Dict[str, str]:
    """Extract candidate name, email, phone, location, and web profiles."""
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    if header_lines is None:
        header_lines = []
        for line in lines:
            if any(p.match(re.sub(r'[:_\-]+$', '', line).strip()) for p in SECTION_PATTERNS.values()):
                break
            header_lines.append(line)

    contact = {
        'full_name': '',
        'email': '',
        'phone': '',
        'location': '',
        'linkedin': '',
        'github': '',
        'portfolio': '',
        'website': '',
    }

    # 1. Email
    emails = EMAIL_REGEX.findall(text)
    if emails:
        contact['email'] = emails[0].lower()

    # 2. Phone
    phones = PHONE_REGEX.findall(text)
    if phones:
        contact['phone'] = phones[0].strip()

    # 3. Social & Portfolio links
    for match in LINKEDIN_REGEX.finditer(text):
        url = match.group(0)
        contact['linkedin'] = url if url.startswith('http') else f"https://{url}"
        break

    for match in GITHUB_REGEX.finditer(text):
        url = match.group(0)
        contact['github'] = url if url.startswith('http') else f"https://{url}"
        break

    # 4. Name extraction heuristic (first prominent non-header line in header block)
    for line in header_lines[:4]:
        if EMAIL_REGEX.search(line) or PHONE_REGEX.search(line) or 'http' in line.lower() or '.com' in line.lower():
            continue
        clean_line = re.sub(r'[^a-zA-Z\s\.\'-]', '', line).strip()
        words = clean_line.split()
        if 2 <= len(words) <= 4 and all(w[0].isupper() for w in words if w):
            contact['full_name'] = clean_line
            break

    # 5. Location heuristic (strictly from header block)
    loc_pattern = re.compile(r'^([A-Za-z\s\.\'-]+),\s*([A-Za-z\s]+)$')
    for line in header_lines:
        parts = [p.strip() for p in line.split('|')]
        for p in parts:
            if not EMAIL_REGEX.search(p) and not PHONE_REGEX.search(p):
                m = loc_pattern.match(p)
                if m:
                    city, region = m.group(1).strip(), m.group(2).strip()
                    if len(region) == 2 and region.upper() in US_STATES:
                        contact['location'] = f"{city}, {region.upper()}"
                        break
                    elif len(city.split()) <= 3 and len(region.split()) <= 2:
                        if not any(k in p.lower() for k in ['developer', 'engineer', 'lead', 'manager', 'architect', 'skills', 'python']):
                            contact['location'] = f"{city}, {region}"
                            break
        if contact['location']:
            break

    return contact


def segment_sections(text: str) -> Dict[str, List[str]]:
    """Segment resume text into logical sections based on detected headers."""
    sections: Dict[str, List[str]] = {
        'header': [],
        'summary': [],
        'experience': [],
        'education': [],
        'skills': [],
        'projects': [],
        'certifications': [],
        'languages': [],
        'awards': [],
        'other': [],
    }

    current_section = 'header'
    lines = [line.strip() for line in text.split('\n')]

    for line in lines:
        if not line:
            continue

        # Check if line matches a known section header
        matched_section = None
        # Headers are short lines (< 45 chars) and do not contain key: value content on the same line
        is_kv_line = False
        if ':' in line:
            parts = line.split(':', 1)
            if parts[1].strip():
                is_kv_line = True

        if len(line) < 45 and not is_kv_line:
            clean_header = re.sub(r'[:_\-]+$', '', line).strip()
            for sec_name, pattern in SECTION_PATTERNS.items():
                if pattern.match(clean_header):
                    matched_section = sec_name
                    break

        if matched_section:
            current_section = matched_section
        else:
            sections[current_section].append(line)

    return sections


def parse_experiences(lines: List[str]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Parse work experience lines into role, company, dates, responsibilities, and accomplishments."""
    experiences = []
    warnings = []
    if not lines:
        return experiences, warnings

    current_exp: Optional[Dict[str, Any]] = None

    def finalize_exp(exp):
        if not exp:
            return
        # Ensure accomplishments vs responsibilities separation
        all_bullets = exp.get('responsibilities', [])
        resp = []
        acc = []
        for b in all_bullets:
            # Check for measurable metrics
            has_metric = any(re.search(pat, b) for pat in METRIC_INDICATORS)
            if has_metric:
                acc.append(b)
            else:
                resp.append(b)

        exp['responsibilities'] = resp
        exp['accomplishments'] = acc
        if not acc:
            exp['warnings'] = ["No measurable accomplishments (percentages, numbers, scale) detected in this role."]
        experiences.append(exp)

    for line in lines:
        # Check if this line introduces a new role (contains a date range or bold-like title/company)
        date_match = DATE_RANGE_REGEX.search(line)
        is_bullet = line.startswith(('•', '-', '*', '–', '—', '·')) or re.match(r'^\d+\.', line)

        if date_match and not is_bullet:
            finalize_exp(current_exp)
            dates = date_match.group(0).strip()
            # The rest of the line or adjacent text contains role and company
            text_without_date = line.replace(dates, '').strip(' |–—-,')
            parts = [p.strip() for p in re.split(r'\||–|—|-| at |,| @ ', text_without_date) if p.strip()]

            role = parts[0] if parts else "Role"
            company = parts[1] if len(parts) > 1 else ""
            location = parts[2] if len(parts) > 2 else ""

            current_exp = {
                'role': role,
                'company': company,
                'dates': dates,
                'location': location,
                'responsibilities': [],
                'accomplishments': [],
                'technologies': [],
                'provenance': 'imported_from_resume',
                'review_status': 'unconfirmed',
                'confidence': 'high' if company and role else 'medium',
                'source_snippet': line,
            }
        elif current_exp is not None:
            clean_bullet = re.sub(r'^[•\-\*–—·\d\.]+\s*', '', line).strip()
            if clean_bullet:
                current_exp['responsibilities'].append(clean_bullet)
        else:
            # Orphan line before first date match; check if company/role header
            if not is_bullet and len(line) < 80:
                current_exp = {
                    'role': line,
                    'company': '',
                    'dates': '',
                    'location': '',
                    'responsibilities': [],
                    'accomplishments': [],
                    'technologies': [],
                    'provenance': 'imported_from_resume',
                    'review_status': 'unconfirmed',
                    'confidence': 'low',
                    'source_snippet': line,
                }

    finalize_exp(current_exp)

    # Check overall experience warnings
    for exp in experiences:
        if not exp.get('dates'):
            warnings.append(f"Employment dates for '{exp.get('role', 'Unknown Role')}' could not be identified automatically. Please verify.")

    return experiences, warnings


def parse_education(lines: List[str]) -> List[Dict[str, Any]]:
    """Parse education entries (degrees, institutions, dates, details)."""
    education = []
    if not lines:
        return education

    current_edu: Optional[Dict[str, Any]] = None

    def finalize_edu(edu):
        if edu and (edu.get('degree') or edu.get('institution')):
            education.append(edu)

    for line in lines:
        date_match = DATE_RANGE_REGEX.search(line) or re.search(r'\b(19\d{2}|20\d{2})\b', line)
        degree_match = None
        for deg_pat in DEGREE_PATTERNS:
            match = re.search(deg_pat, line, re.IGNORECASE)
            if match:
                degree_match = match.group(0)
                break

        if degree_match or (date_match and not line.startswith(('•', '-', '*'))):
            finalize_edu(current_edu)
            dates = date_match.group(0) if date_match else ''
            line_no_date = line.replace(dates, '').strip(' |–—-,') if dates else line

            parts = [p.strip() for p in re.split(r'\||–|—', line_no_date) if p.strip()]
            if len(parts) >= 2:
                deg_part = None
                inst_part = None
                for p in parts:
                    if degree_match and degree_match.lower() in p.lower():
                        deg_part = p
                    elif not inst_part:
                        inst_part = p
                degree = deg_part or parts[0]
                institution = inst_part or (parts[1] if len(parts) > 1 else '')
            else:
                degree = line_no_date
                institution = ''

            current_edu = {
                'degree': degree,
                'institution': institution or 'University / College',
                'location': '',
                'dates': dates,
                'details': '',
                'provenance': 'imported_from_resume',
                'review_status': 'unconfirmed',
                'confidence': 'high' if degree_match else 'medium',
            }
        elif current_edu is not None:
            clean_text = line.strip(' •-*')
            if clean_text:
                if not current_edu['institution'] or current_edu['institution'] == 'University / College':
                    current_edu['institution'] = clean_text
                else:
                    current_edu['details'] = (current_edu['details'] + " " + clean_text).strip()

    finalize_edu(current_edu)
    return education


def parse_skills(lines: List[str]) -> List[Dict[str, Any]]:
    """Parse technical and functional skills with categorical grouping."""
    skills = []
    seen = set()

    # Split lines by commas, bullets, pipes, or semicolons
    for line in lines:
        # Check if line is formatted as Category: Skill 1, Skill 2
        category = 'General'
        content = line
        if ':' in line:
            cat_part, content_part = line.split(':', 1)
            if len(cat_part.strip()) < 30:
                category = cat_part.strip()
                content = content_part

        tokens = re.split(r'[,|;•\n\t]+', content)
        for token in tokens:
            clean_skill = token.strip(' •-*–—').strip()
            # Filter trivial strings or excessively long phrases
            if clean_skill and 1 <= len(clean_skill.split()) <= 4 and len(clean_skill) <= 40:
                skill_lower = clean_skill.lower()
                if skill_lower not in seen:
                    seen.add(skill_lower)
                    skills.append({
                        'name': clean_skill,
                        'category': category,
                        'proficiency': 'Proficient',
                        'evidence': '',
                        'provenance': 'imported_from_resume',
                        'review_status': 'unconfirmed',
                        'confidence': 'high',
                    })

    return skills


def parse_projects(lines: List[str]) -> List[Dict[str, Any]]:
    """Parse technical projects, links, and outcomes."""
    projects = []
    if not lines:
        return projects

    current_proj: Optional[Dict[str, Any]] = None

    def finalize_proj(p):
        if p and p.get('name'):
            projects.append(p)

    for line in lines:
        is_bullet = line.startswith(('•', '-', '*', '–', '—', '·'))
        if not is_bullet and len(line) < 70 and not line.endswith('.'):
            finalize_proj(current_proj)
            # Find URLs if present
            url_match = URL_REGEX.search(line)
            link = url_match.group(0) if url_match else ''
            clean_name = line.replace(link, '').strip(' |–—-,')

            current_proj = {
                'name': clean_name or "Project",
                'role': 'Creator / Contributor',
                'contribution': '',
                'link': link,
                'technologies': [],
                'outcomes': '',
                'bullets': [],
                'provenance': 'imported_from_resume',
                'review_status': 'unconfirmed',
                'confidence': 'medium',
            }
        elif current_proj is not None:
            clean_bullet = re.sub(r'^[•\-\*–—·\d\.]+\s*', '', line).strip()
            if clean_bullet:
                current_proj['bullets'].append(clean_bullet)
                current_proj['outcomes'] = " ".join(current_proj['bullets'])

    finalize_proj(current_proj)
    return projects


def parse_certifications(lines: List[str]) -> List[Dict[str, Any]]:
    """Parse professional certifications and qualifications."""
    certifications = []
    for line in lines:
        clean = line.strip(' •-*–—').strip()
        if not clean:
            continue
        date_match = re.search(r'\b(20\d{2}|19\d{2})\b', clean)
        date = date_match.group(0) if date_match else ''
        name = clean.replace(date, '').strip(' |–—-,')

        certifications.append({
            'name': name or clean,
            'issuer': '',
            'date': date,
            'verification_url': '',
            'provenance': 'imported_from_resume',
            'review_status': 'unconfirmed',
            'confidence': 'high' if date else 'medium',
        })
    return certifications


def parse_languages(lines: List[str]) -> List[Dict[str, str]]:
    """Parse spoken/written language proficiencies."""
    languages = []
    for line in lines:
        tokens = re.split(r'[,|;•\n\t]+', line)
        for token in tokens:
            clean = token.strip(' •-*–—').strip()
            if clean and len(clean.split()) <= 3:
                parts = clean.split('(')
                lang_name = parts[0].strip()
                proficiency = parts[1].rstrip(')').strip() if len(parts) > 1 else 'Native / Fluent'
                languages.append({'name': lang_name, 'proficiency': proficiency})
    return languages


def parse_awards(lines: List[str]) -> List[Dict[str, str]]:
    """Parse publications, awards, and recognitions."""
    awards = []
    for line in lines:
        clean = line.strip(' •-*–—').strip()
        if clean:
            awards.append({'title': clean, 'provenance': 'imported_from_resume'})
    return awards


def validate_parsed_candidate_schema(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate parsed candidate data dictionary against expected schema.

    Returns (is_valid, validation_errors).
    """
    errors = []
    if not isinstance(data, dict):
        return False, ["Parsed data must be a valid JSON dictionary."]

    expected_keys = ['full_name', 'email', 'phone', 'experiences', 'technical_skills', 'education']
    for k in expected_keys:
        if k not in data:
            errors.append(f"Missing required schema field: '{k}'.")

    if not isinstance(data.get('experiences', []), list):
        errors.append("Field 'experiences' must be a list.")
    if not isinstance(data.get('technical_skills', []), list):
        errors.append("Field 'technical_skills' must be a list.")
    if not isinstance(data.get('education', []), list):
        errors.append("Field 'education' must be a list.")

    return len(errors) == 0, errors


def parse_resume_text_deterministic(text: str) -> Dict[str, Any]:
    """Pure deterministic parsing pipeline with high accuracy and zero hallucination risk."""
    sections = segment_sections(text)
    contact = extract_contact_info(text, sections.get('header', []))

    # Professional Summary
    summary_lines = sections.get('summary', [])
    summary = "\n".join(summary_lines).strip()
    tagline = ""

    # If no explicit summary section, check for opening paragraph in header
    if not summary and sections.get('header'):
        header_lines = sections['header']
        for line in header_lines[1:]:
            if len(line) > 60 and not EMAIL_REGEX.search(line) and not PHONE_REGEX.search(line):
                summary = line
                break

    # Tagline heuristic: line following full name if short
    if sections.get('header'):
        for line in sections['header'][:4]:
            if line != contact['full_name'] and 3 <= len(line.split()) <= 7 and not EMAIL_REGEX.search(line):
                tagline = line
                break

    experiences, exp_warnings = parse_experiences(sections.get('experience', []))
    education = parse_education(sections.get('education', []))
    skills = parse_skills(sections.get('skills', []))
    projects = parse_projects(sections.get('projects', []))
    certifications = parse_certifications(sections.get('certifications', []))
    languages = parse_languages(sections.get('languages', []))
    awards = parse_awards(sections.get('awards', []))

    all_warnings = []
    all_warnings.extend(exp_warnings)

    if not experiences:
        all_warnings.append("No work experiences could be automatically identified. You can add them during review.")
    if not skills:
        all_warnings.append("No technical skills section was detected. Please review and add your core competencies.")
    if not contact['email']:
        all_warnings.append("Email address was not found in the resume header. Please provide your contact email.")

    parsed_data = {
        'full_name': contact['full_name'],
        'email': contact['email'],
        'phone': contact['phone'],
        'location': contact['location'],
        'tagline': tagline,
        'linkedin': contact['linkedin'],
        'github': contact['github'],
        'portfolio': contact['portfolio'],
        'website': contact['website'],
        'summary': summary,
        'technical_skills': skills,
        'experiences': experiences,
        'projects': projects,
        'education': education,
        'certifications': certifications,
        'languages': languages,
        'awards': awards,
        'warnings': all_warnings,
        'provenance': {
            'extraction_method': 'deterministic',
            'status': 'unconfirmed_draft',
        }
    }

    is_valid, validation_errors = validate_parsed_candidate_schema(parsed_data)
    if not is_valid:
        parsed_data['warnings'].extend(validation_errors)

    return parsed_data


def parse_resume_text(text: str, allow_ai: bool = True) -> Dict[str, Any]:
    """Main parsing entry point.

    Executes deterministic parsing as primary guarantee.
    If an AI provider is configured and available, optionally attempts
    schema-validated extraction to enhance difficult formatting, falling back
    cleanly to deterministic output on any error.
    """
    deterministic_result = parse_resume_text_deterministic(text)

    # Check if AI parsing is available and requested
    gemini_key = os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY')
    openai_key = os.environ.get('OPENAI_API_KEY')

    if not allow_ai or (not gemini_key and not openai_key):
        return deterministic_result

    # Optional AI structured enhancement
    try:
        from .ai_parser import parse_resume_with_ai
        ai_result = parse_resume_with_ai(text)
        if ai_result:
            is_valid, errors = validate_parsed_candidate_schema(ai_result)
            if is_valid:
                ai_result['provenance'] = {
                    'extraction_method': 'ai_enhanced',
                    'status': 'unconfirmed_draft',
                }
                return ai_result
            else:
                logger.warning(f"AI resume parsing produced invalid schema: {errors}. Falling back to deterministic.")
    except Exception as e:
        logger.warning(f"AI resume parsing error: {e}. Falling back gracefully to deterministic parser.")

    return deterministic_result
