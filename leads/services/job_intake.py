"""Grounded job posting intake.

Fetches public job postings with SSRF protections, extracts structured fields,
and builds employer research plus a deterministic profile-fit preview. No
fabricated facts: anything absent from the posting is reported as unavailable.
"""

import ipaddress
import json
import logging
import re
import socket
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from django.utils import timezone

from .llm_tailor import (
    extract_job_requirements,
    extract_keywords,
    map_evidence_to_requirements,
    sanitize_untrusted_job_text,
)

logger = logging.getLogger(__name__)

USER_AGENT = 'HuntlyJobIntake/1.0 (+https://huntly.app)'
REQUEST_TIMEOUT = (5, 12)
MAX_RESPONSE_BYTES = 2_000_000
MAX_REDIRECTS = 3
MAX_URL_LENGTH = 2048
ALLOWED_CONTENT_TYPES = {'text/html', 'application/xhtml+xml', 'text/plain'}
REDIRECT_STATUSES = {301, 302, 303, 307, 308}
BLOCKED_HOSTNAMES = {
    'localhost',
    'localhost.localdomain',
    'metadata',
    'metadata.google.internal',
    'instance-data',
}
BLOCKED_HOST_SUFFIXES = ('.local', '.internal', '.localdomain', '.home.arpa')
ATS_HOST_SUFFIXES = (
    'greenhouse.io',
    'lever.co',
    'workday.com',
    'myworkdayjobs.com',
    'ashbyhq.com',
    'smartrecruiters.com',
    'bamboohr.com',
    'recruitee.com',
    'jobvite.com',
    'icims.com',
    'taleo.net',
    'linkedin.com',
    'indeed.com',
    'wellfound.com',
)
EMPLOYMENT_TYPE_MAP = {
    'FULL_TIME': 'Full-time',
    'PART_TIME': 'Part-time',
    'CONTRACTOR': 'Contract',
    'TEMPORARY': 'Temporary',
    'INTERN': 'Internship',
    'VOLUNTEER': 'Volunteer',
    'PER_DIEM': 'Per diem',
    'OTHER': 'Other',
}
SALARY_UNIT_MAP = {
    'HOUR': 'per hour',
    'DAY': 'per day',
    'WEEK': 'per week',
    'MONTH': 'per month',
    'YEAR': 'per year',
}
CURRENCY_SYMBOLS = {'USD': '$', 'EUR': '€', 'GBP': '£', 'CAD': 'CA$', 'AUD': 'A$'}
BENEFIT_KEYWORDS = (
    'health',
    'dental',
    'vision',
    '401k',
    '401(k)',
    'equity',
    'stock',
    'remote',
    'pto',
    'paid time off',
    'parental leave',
    'learning budget',
    'professional development',
    'wellness',
    'stipend',
    'insurance',
    'retirement',
)
GENERIC_HEADINGS = {
    'about us',
    'about the role',
    'about you',
    'job description',
    'responsibilities',
    'requirements',
    'who we are',
    'the role',
    'overview',
    'what you will do',
    "what you'll do",
    'what we offer',
    'benefits',
}


class JobIntakeError(ValueError):
    """User-safe intake failure that can be shown in the UI."""


@dataclass
class FetchedPage:
    url: str
    text: str
    content_type: str


def _normalize_hostname(hostname: str) -> str:
    return (hostname or '').strip().lower().rstrip('.')


def _is_public_ip(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address.split('%')[0])
    except ValueError:
        return False
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    ):
        return False
    return bool(ip.is_global)


def _resolve_public_host(hostname: str, port: int) -> List[str]:
    try:
        infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError, OSError) as exc:
        raise JobIntakeError(
            "Could not resolve the job posting host. Check the URL or paste the description instead."
        ) from exc

    addresses = []
    for info in infos:
        address = str(info[4][0])
        if not _is_public_ip(address):
            raise JobIntakeError(
                "This URL points to a private or internal network address and cannot be fetched."
            )
        addresses.append(address)
    if not addresses:
        raise JobIntakeError("The job posting host did not resolve to a public address.")
    return addresses


def _validate_url(url: str) -> Tuple[str, Any, int]:
    candidate = (url or '').strip()
    if not candidate:
        raise JobIntakeError("Enter a job posting URL first.")
    if len(candidate) > MAX_URL_LENGTH:
        raise JobIntakeError("That job posting URL is too long.")

    parsed = urlparse(candidate)
    if parsed.scheme.lower() not in {'http', 'https'}:
        raise JobIntakeError("Only http and https job posting URLs are supported.")
    if parsed.username or parsed.password:
        raise JobIntakeError("Job posting URLs containing credentials are not allowed.")
    if not parsed.hostname:
        raise JobIntakeError("That URL is missing a hostname.")

    hostname = _normalize_hostname(parsed.hostname)
    if hostname in BLOCKED_HOSTNAMES or hostname.endswith(BLOCKED_HOST_SUFFIXES):
        raise JobIntakeError("This host is blocked because it is not a public job posting.")

    try:
        port = parsed.port or (443 if parsed.scheme.lower() == 'https' else 80)
    except ValueError as exc:
        raise JobIntakeError("That URL contains an invalid port.") from exc

    _resolve_public_host(hostname, port)
    return candidate, parsed, port


def _read_limited_body(response: requests.Response) -> bytes:
    declared = response.headers.get('Content-Length')
    if declared:
        try:
            declared_size = int(declared)
        except ValueError:
            declared_size = None
        if declared_size is not None and declared_size > MAX_RESPONSE_BYTES:
            raise JobIntakeError("The job posting is too large to analyze safely.")

    chunks = []
    total = 0
    for chunk in response.iter_content(65536):
        if not chunk:
            continue
        total += len(chunk)
        if total > MAX_RESPONSE_BYTES:
            raise JobIntakeError("The job posting is too large to analyze safely.")
        chunks.append(chunk)
    return b''.join(chunks)


def fetch_job_posting(url: str) -> FetchedPage:
    """Fetch a public job posting with strict SSRF, redirect, size, and type checks."""
    current = (url or '').strip()
    seen = set()

    for attempt in range(MAX_REDIRECTS + 1):
        current, parsed, port = _validate_url(current)
        if current in seen:
            raise JobIntakeError("The job posting URL is in a redirect loop.")
        seen.add(current)

        try:
            with requests.get(
                current,
                headers={
                    'User-Agent': USER_AGENT,
                    'Accept': 'text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.1',
                    'Accept-Language': 'en-US,en;q=0.8',
                },
                timeout=REQUEST_TIMEOUT,
                allow_redirects=False,
                stream=True,
            ) as response:
                if response.status_code in REDIRECT_STATUSES:
                    location = response.headers.get('Location')
                    if not location:
                        raise JobIntakeError("The job page redirected without a destination.")
                    if attempt >= MAX_REDIRECTS:
                        raise JobIntakeError("The job page redirected too many times.")
                    current = urljoin(current, location)
                    continue

                if response.status_code in {401, 403}:
                    raise JobIntakeError(
                        "That job posting blocked automated access. Paste the description instead."
                    )
                if response.status_code != 200:
                    raise JobIntakeError(
                        f"The job page returned HTTP {response.status_code}. Paste the description instead."
                    )

                content_type = (response.headers.get('Content-Type') or '').split(';')[0].strip().lower()
                if content_type and content_type not in ALLOWED_CONTENT_TYPES:
                    raise JobIntakeError(
                        "That URL did not return a readable job posting page. Paste the description instead."
                    )

                body = _read_limited_body(response)
                encoding = response.encoding or 'utf-8'
        except requests.RequestException as exc:
            logger.warning("Job posting fetch failed for %s: %s", current, exc)
            raise JobIntakeError(
                "Could not reach the job posting. Check the URL or paste the description instead."
            ) from exc

        try:
            text = body.decode(encoding, errors='replace')
        except (LookupError, UnicodeError):
            text = body.decode('utf-8', errors='replace')
        return FetchedPage(url=current, text=text, content_type=content_type or 'text/html')

    raise JobIntakeError("The job page redirected too many times.")


def _clean_line(value: str) -> str:
    return re.sub(r'\s+', ' ', value or '').strip()


def _clean_multiline(value: str, max_chars: int = 40000) -> str:
    value = (value or '').replace('\r\n', '\n').replace('\r', '\n')
    lines = []
    for raw in value.split('\n'):
        line = re.sub(r'[ \t\f\v]+', ' ', raw).strip()
        if not line:
            if lines and lines[-1] != '':
                lines.append('')
            continue
        if line in {'•', '-', '*', '·'}:
            continue
        lines.append(line)
    cleaned = '\n'.join(lines).strip()
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned[:max_chars]


def _html_fragment_to_text(fragment: str) -> str:
    if not fragment:
        return ''
    soup = BeautifulSoup(fragment, 'html.parser')
    for tag in soup(['script', 'style', 'noscript', 'svg', 'iframe', 'form']):
        tag.decompose()
    for br in soup.find_all('br'):
        br.replace_with('\n')
    for block in soup.find_all(['p', 'li', 'h1', 'h2', 'h3', 'h4', 'div']):
        block.append('\n')
    return _clean_multiline(soup.get_text('\n'))


def _meta_content(soup: BeautifulSoup, *keys: str) -> str:
    for key in keys:
        tag = soup.find('meta', attrs={'property': key}) or soup.find('meta', attrs={'name': key})
        if tag and tag.get('content'):
            return _clean_line(tag['content'])
    return ''


def _find_job_posting(node: Any) -> Optional[Dict[str, Any]]:
    if isinstance(node, dict):
        node_type = node.get('@type')
        if node_type == 'JobPosting' or (
            isinstance(node_type, list) and 'JobPosting' in node_type
        ):
            return node
        for value in node.values():
            found = _find_job_posting(value)
            if found:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _find_job_posting(item)
            if found:
                return found
    return None


def _parse_json_ld_job_posting(soup: BeautifulSoup) -> Optional[Dict[str, Any]]:
    for script in soup.find_all('script', attrs={'type': 'application/ld+json'}):
        raw = script.string or script.get_text() or ''
        if not raw.strip():
            continue
        try:
            payload = json.loads(raw, strict=False)
        except (json.JSONDecodeError, TypeError):
            continue
        posting = _find_job_posting(payload)
        if posting:
            return posting
    return None


def _format_salary(base_salary: Any) -> str:
    if isinstance(base_salary, str):
        return _clean_line(base_salary)[:100]
    if not isinstance(base_salary, dict):
        return ''

    currency = str(base_salary.get('currency') or '').upper()
    symbol = CURRENCY_SYMBOLS.get(currency, currency)
    amount = base_salary.get('value')
    unit = ''

    if isinstance(amount, dict):
        minimum = amount.get('minValue')
        maximum = amount.get('maxValue')
        single = amount.get('value')
        unit = SALARY_UNIT_MAP.get(str(amount.get('unitText') or '').upper(), '')
    elif isinstance(amount, (int, float)):
        minimum = maximum = None
        single = amount
    else:
        return ''

    def _number(value: Any) -> str:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return ''
        if numeric.is_integer():
            return f"{int(numeric):,}"
        return f"{numeric:,.2f}"

    if minimum is not None or maximum is not None:
        low = _number(minimum)
        high = _number(maximum)
        if low and high:
            return f"{symbol} {low} - {high} {unit}".strip()
        if low or high:
            return f"{symbol} {low or high} {unit}".strip()
        return ''
    if single is not None:
        return f"{symbol} {_number(single)} {unit}".strip()
    return ''


def _normalize_employment_type(value: Any) -> str:
    if isinstance(value, list):
        value = next((item for item in value if item), '')
    raw = str(value or '').strip()
    if not raw:
        return ''
    if raw.upper() in EMPLOYMENT_TYPE_MAP:
        return EMPLOYMENT_TYPE_MAP[raw.upper()]
    lowered = raw.lower().replace('_', ' ')
    aliases = {
        'full time': 'Full-time',
        'part time': 'Part-time',
        'contractor': 'Contract',
        'contract': 'Contract',
        'intern': 'Internship',
        'internship': 'Internship',
        'temporary': 'Temporary',
        'freelance': 'Freelance',
    }
    return aliases.get(lowered, raw[:50])


def _extract_json_ld_fields(posting: Dict[str, Any]) -> Dict[str, str]:
    fields = {
        'company_name': '',
        'role_title': '',
        'location': '',
        'salary': '',
        'employment_type': '',
        'job_description': '',
    }

    fields['role_title'] = _clean_line(str(posting.get('title') or ''))[:255]

    organization = posting.get('hiringOrganization')
    if isinstance(organization, list):
        organization = organization[0] if organization else None
    if isinstance(organization, dict):
        fields['company_name'] = _clean_line(str(organization.get('name') or ''))[:255]
    elif isinstance(organization, str):
        fields['company_name'] = _clean_line(organization)[:255]

    location = posting.get('jobLocation')
    if isinstance(location, list):
        location = location[0] if location else None
    location_parts: List[str] = []
    if isinstance(location, dict):
        address = location.get('address')
        if isinstance(address, list):
            address = address[0] if address else None
        if isinstance(address, dict):
            for key in ('addressLocality', 'addressRegion', 'addressCountry'):
                value = address.get(key)
                if isinstance(value, dict):
                    value = value.get('name')
                if value:
                    location_parts.append(_clean_line(str(value)))
        place_name = location.get('name')
        if place_name and not location_parts:
            location_parts.append(_clean_line(str(place_name)))
    requirements = posting.get('applicantLocationRequirements')
    if isinstance(requirements, list):
        requirements = requirements[0] if requirements else None
    if isinstance(requirements, dict) and requirements.get('name'):
        location_parts.append(_clean_line(str(requirements['name'])))
    job_location_type = str(posting.get('jobLocationType') or '').upper()
    if 'TELECOMMUTE' in job_location_type:
        location_parts.insert(0, 'Remote')
    fields['location'] = ', '.join(dict.fromkeys(p for p in location_parts if p))[:255]

    fields['salary'] = _format_salary(
        posting.get('baseSalary') or posting.get('estimatedSalary')
    )[:100]
    fields['employment_type'] = _normalize_employment_type(posting.get('employmentType'))
    fields['job_description'] = _html_fragment_to_text(
        str(posting.get('description') or '')
    )
    return fields


def _labeled_value(text: str, labels: Tuple[str, ...]) -> str:
    label_group = '|'.join(re.escape(label) for label in labels)
    pattern = re.compile(
        rf'^\s*(?:{label_group})\s*[:\-–—]\s*(.+)$',
        re.IGNORECASE | re.MULTILINE,
    )
    match = pattern.search(text or '')
    if not match:
        return ''
    return _clean_line(match.group(1))[:255]


def _heuristic_salary(text: str) -> str:
    pattern = re.compile(
        r'(?:(?:USD|EUR|GBP|CAD|AUD)\s?)?[$£€]\s?\d[\d,]*(?:\.\d+)?\s?[kK]?'
        r'(?:\s*(?:-|–|—|to)\s*(?:(?:USD|EUR|GBP|CAD|AUD)\s?)?[$£€]?\s?\d[\d,]*(?:\.\d+)?\s?[kK]?)?'
        r'(?:\s*(?:per|/)\s*(?:year|yr|hour|hr|month|annum))?',
        re.IGNORECASE,
    )
    match = pattern.search(text or '')
    return _clean_line(match.group(0))[:100] if match else ''


def _heuristic_location(text: str) -> str:
    remote = re.search(r'\b(fully remote|remote[- ]first|remote|hybrid|on[- ]site)\b', text or '', re.IGNORECASE)
    labeled = _labeled_value(text, ('location', 'work location', 'based in'))
    if labeled:
        return labeled
    if remote:
        return remote.group(0).title()[:255]
    return ''


def _heuristic_employment_type(text: str) -> str:
    match = re.search(
        r'\b(full[- ]time|part[- ]time|contract(?:or)?|internship|temporary|freelance)\b',
        text or '',
        re.IGNORECASE,
    )
    return _normalize_employment_type(match.group(0)) if match else ''


def _strip_title_noise(title: str) -> str:
    cleaned = re.sub(r'^(?:job application for|apply for|job opening:?)\s+', '', title or '', flags=re.IGNORECASE)
    return _clean_line(cleaned)[:255]


def _is_ats_host(hostname: str) -> bool:
    return any(
        hostname == suffix or hostname.endswith('.' + suffix)
        for suffix in ATS_HOST_SUFFIXES
    )


def _host_label(hostname: str) -> str:
    host = _normalize_hostname(hostname).removeprefix('www.')
    label = host.split('.')[0] if host else ''
    return label.replace('-', ' ').title()[:255]


def _extract_heuristic_fields(
    text: str,
    source_url: str = '',
    company_name: str = '',
    role_title: str = '',
) -> Dict[str, str]:
    hostname = _normalize_hostname(urlparse(source_url).hostname or '')
    fields = {
        'company_name': _clean_line(company_name)[:255],
        'role_title': _clean_line(role_title)[:255],
        'location': _labeled_value(text, ('location', 'work location')),
        'salary': _labeled_value(text, ('salary', 'compensation', 'pay range')),
        'employment_type': _labeled_value(text, ('employment type', 'job type')),
        'job_description': _clean_multiline(text),
    }
    if not fields['company_name']:
        fields['company_name'] = _labeled_value(text, ('company', 'employer', 'organization'))
    if not fields['role_title']:
        fields['role_title'] = _labeled_value(text, ('job title', 'position', 'role'))
    if not fields['role_title']:
        first_line = next((_clean_line(line) for line in (text or '').split('\n') if _clean_line(line)), '')
        if (
            3 <= len(first_line) <= 100
            and first_line.lower().strip(':') not in GENERIC_HEADINGS
            and not re.search(r'[.!?]$', first_line)
        ):
            fields['role_title'] = first_line
    if not fields['location']:
        fields['location'] = _heuristic_location(text)
    if not fields['salary']:
        fields['salary'] = _heuristic_salary(text)
    if not fields['employment_type']:
        fields['employment_type'] = _heuristic_employment_type(text)
    if not fields['employment_type']:
        fields['employment_type'] = _heuristic_employment_type(fields['role_title'])
    if not fields['company_name'] and hostname and not _is_ats_host(hostname):
        fields['company_name'] = _host_label(hostname)
    return fields


def extract_job_from_html(html: str, source_url: str = '') -> Dict[str, Any]:
    """Extract job fields from a fetched HTML page using JSON-LD first, then heuristics."""
    soup = BeautifulSoup(html or '', 'html.parser')
    posting = _parse_json_ld_job_posting(soup)

    for tag in soup(['script', 'style', 'noscript', 'svg', 'iframe', 'form', 'nav', 'footer', 'aside', 'header']):
        tag.decompose()
    main = (
        soup.find('main')
        or soup.find('article')
        or soup.find(attrs={'role': 'main'})
        or soup.body
        or soup
    )
    visible_text = _clean_multiline(main.get_text('\n') if main else '')
    page_title = _meta_content(soup, 'og:title', 'twitter:title')
    if not page_title and soup.title and soup.title.string:
        page_title = _clean_line(soup.title.string)
    site_name = _meta_content(soup, 'og:site_name')

    fields = {
        'company_name': '',
        'role_title': '',
        'location': '',
        'salary': '',
        'employment_type': '',
        'job_description': '',
    }
    warnings: List[str] = []
    structured = bool(posting)

    if posting:
        fields.update(_extract_json_ld_fields(posting))

    heuristics = _extract_heuristic_fields(visible_text, source_url)
    for key, value in heuristics.items():
        if not fields.get(key) and value:
            fields[key] = value

    if not fields['role_title'] and page_title:
        title = _strip_title_noise(page_title)
        if title.lower().endswith(site_name.lower()) and site_name:
            title = title[: -len(site_name)].rstrip(' |-–—·:')
        fields['role_title'] = title[:255]

    if not fields['company_name'] and site_name:
        fields['company_name'] = site_name[:255]

    if not fields['company_name']:
        hostname = _normalize_hostname(urlparse(source_url).hostname or '')
        if hostname and not _is_ats_host(hostname):
            fields['company_name'] = _host_label(hostname)

    if not fields['company_name'] and page_title:
        match = re.match(r'^(?P<role>.+?)\s+(?:at|@)\s+(?P<company>[A-Z][\w&.\- ]{1,80})$', page_title)
        if match:
            fields['role_title'] = _strip_title_noise(match.group('role'))
            fields['company_name'] = _clean_line(match.group('company'))[:255]

    if not fields['job_description']:
        fields['job_description'] = visible_text
    fields['job_description'] = sanitize_untrusted_job_text(
        fields.get('job_description', ''), max_chars=40000
    )

    if not structured:
        warnings.append(
            "No structured JobPosting data was found. Fields were inferred from page text and should be reviewed."
        )
    if len(visible_text) < 200 and not fields['job_description']:
        warnings.append(
            "This page did not expose readable job text, likely because it requires JavaScript. Paste the description instead."
        )
    if not fields['role_title']:
        warnings.append("Role title could not be identified from the page. Please enter it manually.")
    if not fields['company_name']:
        warnings.append("Company name could not be verified from the page. Please confirm it manually.")
    if not fields['job_description']:
        warnings.append("Job description could not be extracted. Paste the description instead.")

    fields['job_url'] = source_url
    return {
        'fields': fields,
        'warnings': warnings,
        'source_type': 'url',
        'structured_data': structured,
        'fetched': True,
    }


def extract_job_from_text(
    text: str,
    job_url: str = '',
    company_name: str = '',
    role_title: str = '',
) -> Dict[str, Any]:
    """Extract job fields from pasted description text without inventing facts."""
    cleaned = sanitize_untrusted_job_text(text or '', max_chars=40000)
    if not cleaned.strip():
        raise JobIntakeError("Paste a job description or enter a posting URL first.")

    fields = _extract_heuristic_fields(cleaned, job_url, company_name, role_title)
    fields['job_url'] = _clean_line(job_url)[:500]
    warnings = []
    if not fields['role_title']:
        warnings.append("Role title could not be identified from the pasted text. Please enter it manually.")
    if not fields['company_name']:
        warnings.append("Company name could not be identified from the pasted text. Please enter it manually.")

    return {
        'fields': fields,
        'warnings': warnings,
        'source_type': 'pasted',
        'structured_data': False,
        'fetched': False,
    }


def build_employer_research(fields: Dict[str, Any]) -> Dict[str, Any]:
    """Build employer notes strictly from the posting text, marking gaps unavailable."""
    description = fields.get('job_description') or ''
    text_lower = description.lower()

    paragraphs = [
        _clean_line(paragraph)
        for paragraph in re.split(r'\n\s*\n', description)
        if _clean_line(paragraph)
    ]
    summary_source = next(
        (
            paragraph for paragraph in paragraphs
            if paragraph.lower().strip(':') not in GENERIC_HEADINGS and len(paragraph) > 60
        ),
        '',
    )

    benefits = []
    for line in description.split('\n'):
        cleaned = _clean_line(line)
        lowered = cleaned.lower()
        if not cleaned or len(cleaned) > 200:
            continue
        if any(keyword in lowered for keyword in BENEFIT_KEYWORDS):
            if cleaned not in benefits:
                benefits.append(cleaned)
        if len(benefits) >= 5:
            break

    work_arrangement = []
    for label, pattern in (
        ('Remote', r'\bremote\b'),
        ('Hybrid', r'\bhybrid\b'),
        ('On-site', r'\b(?:on[- ]site|in[- ]office)\b'),
    ):
        if re.search(pattern, text_lower):
            work_arrangement.append(label)

    red_flags = []
    suspicious_patterns = (
        (r'\bunpaid\b', "Posting mentions unpaid work."),
        (r'\bcommission[- ]only\b', "Posting mentions commission-only compensation."),
        (r'\b(?:application|training|onboarding) fee\b', "Posting mentions an upfront fee."),
        (r'\bno experience (?:required|necessary)\b', "Posting requires no experience."),
        (r'\bearn up to\b', "Posting uses an 'earn up to' pay claim."),
        (r'\b(?:contact|apply) (?:us )?(?:on|via) telegram\b', "Posting directs applicants to Telegram."),
    )
    for pattern, note in suspicious_patterns:
        if re.search(pattern, text_lower):
            red_flags.append(note)

    unavailable = [
        'Company size',
        'Funding stage',
        'Leadership team',
        'Employee reviews',
        'Interview process details',
    ]

    return {
        'company_name': fields.get('company_name', ''),
        'role_title': fields.get('role_title', ''),
        'summary': summary_source[:600],
        'tech_stack': extract_keywords(description)[:12],
        'benefits': benefits,
        'work_arrangement': work_arrangement,
        'salary_transparency': bool(fields.get('salary')),
        'compensation_note': (
            fields.get('salary') if fields.get('salary')
            else 'Not disclosed in the posting.'
        ),
        'red_flags': red_flags,
        'unavailable': unavailable,
        'sources': [fields['job_url']] if fields.get('job_url') else [],
        'grounding_note': (
            'Derived only from the submitted posting text. Facts not present in the posting are marked unavailable.'
        ),
        'analyzed_at': timezone.now().isoformat(),
    }


def build_fit_analysis(resume: Any, job_description: str) -> Dict[str, Any]:
    """Compare the posting against the Career Profile with a deterministic, free heuristic."""
    if not resume or not (job_description or '').strip():
        return {}

    requirements = extract_job_requirements(job_description)
    evidence = map_evidence_to_requirements(resume, requirements)
    fit = {
        'fit_heuristic_score': evidence.get('fit_heuristic_score', 0),
        'strengths': evidence.get('strengths', [])[:8],
        'gaps': evidence.get('gaps', [])[:8],
        'evidence_items': evidence.get('evidence_items', [])[:20],
        'matched_keywords': requirements.get('matched_keywords', [])[:15],
        'seniority': requirements.get('seniority', ''),
        'score_disclaimer': evidence.get('score_disclaimer', ''),
        'score_source': 'deterministic_profile_overlap',
        'analyzed_at': timezone.now().isoformat(),
    }
    return fit


def analyze_job_intake(
    job_url: str = '',
    job_description: str = '',
    company_name: str = '',
    role_title: str = '',
    resume: Any = None,
) -> Dict[str, Any]:
    """Analyze a URL or pasted description without writing to the database or using AI credits."""
    job_url = _clean_line(job_url)[:500]
    description = (job_description or '').strip()
    warnings: List[str] = []

    if not job_url and not description:
        raise JobIntakeError("Paste a job description or enter a posting URL first.")

    analysis: Dict[str, Any] = {
        'fields': {
            'company_name': _clean_line(company_name)[:255],
            'role_title': _clean_line(role_title)[:255],
            'job_url': job_url,
            'location': '',
            'salary': '',
            'employment_type': '',
            'job_description': '',
        },
        'warnings': warnings,
        'source_type': 'manual',
        'structured_data': False,
        'fetched': False,
    }

    if job_url and not description:
        try:
            page = fetch_job_posting(job_url)
            extracted = extract_job_from_html(page.text, page.url)
            analysis.update(extracted)
            warnings.extend(extracted['warnings'])
        except JobIntakeError as exc:
            warnings.append(str(exc))
            analysis['extraction_status'] = 'failed'
            analysis['source_type'] = 'url'
    elif description:
        extracted = extract_job_from_text(
            description,
            job_url=job_url,
            company_name=company_name,
            role_title=role_title,
        )
        analysis.update(extracted)
        warnings.extend(extracted['warnings'])
        if job_url:
            warnings.append("Pasted description used. The URL was saved without fetching the page.")

    fields = analysis['fields']
    if company_name:
        fields['company_name'] = _clean_line(company_name)[:255]
    if role_title:
        fields['role_title'] = _clean_line(role_title)[:255]
    if job_url:
        fields['job_url'] = job_url

    fields['job_description'] = sanitize_untrusted_job_text(
        fields.get('job_description', ''), max_chars=40000
    )

    analysis['employer_research'] = build_employer_research(fields)
    analysis['fit_analysis'] = build_fit_analysis(resume, fields.get('job_description', ''))

    if analysis.get('extraction_status') != 'failed':
        if fields.get('role_title') and fields.get('job_description'):
            analysis['extraction_status'] = 'extracted'
        elif any(fields.get(key) for key in ('role_title', 'company_name', 'job_description')):
            analysis['extraction_status'] = 'partial'
        else:
            analysis['extraction_status'] = 'failed'
    return analysis


def apply_intake_analysis(job: Any, analysis: Dict[str, Any], fill_blank_fields: bool = True) -> Any:
    """Persist analysis on an existing job without overwriting user-edited text."""
    fields = analysis.get('fields', {})
    update_fields = ['employer_research', 'fit_analysis', 'analyzed_at', 'extraction_status']

    if fill_blank_fields:
        for field_name in ('location', 'salary', 'employment_type'):
            if not getattr(job, field_name, '') and fields.get(field_name):
                setattr(job, field_name, fields[field_name])
                update_fields.append(field_name)
        if not (job.job_description or '').strip() and fields.get('job_description'):
            job.job_description = fields['job_description']
            update_fields.append('job_description')

    job.employer_research = analysis.get('employer_research', {})
    job.fit_analysis = analysis.get('fit_analysis', {})
    job.analyzed_at = timezone.now()
    job.extraction_status = analysis.get('extraction_status', 'partial')

    fit = analysis.get('fit_analysis') or {}
    if not job.score and fit.get('fit_heuristic_score'):
        job.score = fit['fit_heuristic_score']
        update_fields.append('score')

    job.save(update_fields=list(dict.fromkeys(update_fields)))
    return job
