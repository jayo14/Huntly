import os
import json
import re


def extract_keywords(job_description):
    """Extract key technical and industry terms from a job description."""
    common_skills = [
        'Python', 'Django', 'React', 'TypeScript', 'JavaScript', 'Node.js',
        'PostgreSQL', 'SQL', 'AWS', 'Docker', 'Kubernetes', 'REST API',
        'GraphQL', 'Tailwind', 'HTML', 'CSS', 'CI/CD', 'Git', 'Agile',
        'Machine Learning', 'Next.js', 'FastAPI', 'Redis', 'Celery',
        'Product Management', 'Data Analysis', 'Scrum', 'Leadership'
    ]
    found = []
    desc_lower = job_description.lower()
    for skill in common_skills:
        pattern = r'\b' + re.escape(skill.lower()) + r'\b'
        if re.search(pattern, desc_lower):
            found.append(skill)
    return found


def _build_prompt(resume, company_name, role_title, job_description):
    return f"""
You are an expert ATS resume strategist and executive career coach.
Tailor this candidate's application for the role of {role_title} at {company_name}.

Candidate Profile:
Name: {getattr(resume, 'full_name', 'Candidate')}
Headline: {getattr(resume, 'tagline', '')}
Skills: {getattr(resume, 'technical_skills', [])}
Experiences: {getattr(resume, 'experiences', [])}
Summary: {getattr(resume, 'summary', '')}

Target Job Description:
{job_description}

Respond with strict JSON with the following keys:
1. "matched_keywords": list of keywords matching this role.
2. "tailored_bullets": list of 3-5 achievement bullet points customized for this role.
3. "cover_letter": a 3-paragraph compelling cover letter.
4. "recruiter_pitch": a 4-sentence cold outreach email for the hiring manager.
"""


def _parse_json_block(text):
    """Pull a JSON object out of a model reply, tolerating ```json fences."""
    text = text.strip()
    if text.startswith('```json'):
        text = text[7:]
    if text.startswith('```'):
        text = text[3:]
    if text.endswith('```'):
        text = text[:-3]
    try:
        return json.loads(text.strip())
    except (ValueError, TypeError):
        return None


def _result_from_parsed(parsed, matched_keywords):
    return {
        'matched_keywords': parsed.get('matched_keywords', matched_keywords),
        'tailored_bullets': parsed.get('tailored_bullets', []),
        'cover_letter': parsed.get('cover_letter', ''),
        'recruiter_pitch': parsed.get('recruiter_pitch', ''),
    }


def _tailor_with_gateway(prompt, matched_keywords):
    """Neon AI Gateway first. Returns None on any failure (incl. Free plan)."""
    try:
        from .ai_gateway import AIGatewayUnavailable, generate_text
    except ImportError:
        return None
    try:
        parsed = _parse_json_block(generate_text(prompt))
    except AIGatewayUnavailable:
        return None
    except Exception:
        return None
    if not parsed:
        return None
    return _result_from_parsed(parsed, matched_keywords)


def _tailor_with_gemini(prompt, matched_keywords):
    """Gemini via google-genai. Returns None when unkeyed or on any failure."""
    gemini_key = os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY')
    if not gemini_key:
        return None
    try:
        from google import genai
        client = genai.Client(api_key=gemini_key)
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        parsed = _parse_json_block(response.text or '')
    except Exception:
        return None
    if not parsed:
        return None
    return _result_from_parsed(parsed, matched_keywords)


def tailor_application(resume, company_name, role_title, job_description):
    """
    Generate role-tailored resume bullets, cover letter, and recruiter pitch.

    Provider order: Neon AI Gateway -> Gemini -> deterministic matcher. Each
    provider returns None on failure so the next one gets a turn.
    """
    matched_keywords = extract_keywords(job_description)
    prompt = _build_prompt(resume, company_name, role_title, job_description)

    for provider in (_tailor_with_gateway, _tailor_with_gemini):
        result = provider(prompt, matched_keywords)
        if result is not None:
            return result

    # Deterministic high-quality fallback generator
    candidate_name = getattr(resume, 'full_name', 'Applicant') or 'Applicant'
    skills_str = ", ".join(matched_keywords) if matched_keywords else "software engineering best practices"

    tailored_bullets = [
        f"Spearheaded technical initiatives directly aligned with {role_title} requirements, incorporating {skills_str}.",
        f"Optimized core systems and workflows at scale, achieving high reliability and measurable performance improvements.",
        f"Collaborated cross-functionally across engineering, product, and operations to deliver mission-critical milestones on schedule.",
        f"Engineered maintainable solutions with rigorous automated testing and modern deployment pipelines for {company_name}'s domain."
    ]

    cover_letter = (
        f"Dear {company_name} Hiring Team,\n\n"
        f"I am writing to express my strong interest in the {role_title} position at {company_name}. "
        f"With a proven background in delivering scalable solutions and a deep focus on {skills_str}, "
        f"I am excited about the opportunity to contribute directly to your team's ambitious goals.\n\n"
        f"Throughout my career, I have focused on solving complex challenges with clean architecture and measurable business impact. "
        f"Your team's mission resonates strongly with my experience, particularly your work in building high-performing, resilient systems.\n\n"
        f"I would welcome the opportunity to discuss how my skill set and enthusiasm can support {company_name}'s continued growth. "
        f"Thank you for your time and consideration.\n\n"
        f"Sincerely,\n{candidate_name}"
    )

    recruiter_pitch = (
        f"Hi there,\n\n"
        f"I recently applied for the {role_title} role at {company_name} and wanted to reach out directly. "
        f"Given my hands-on background in {skills_str}, I am confident I can make an immediate impact on your team. "
        f"I've attached my tailored application and would love to connect for 10 minutes if you're open to it.\n\n"
        f"Best,\n{candidate_name}"
    )

    return {
        'matched_keywords': matched_keywords,
        'tailored_bullets': tailored_bullets,
        'cover_letter': cover_letter,
        'recruiter_pitch': recruiter_pitch,
    }
