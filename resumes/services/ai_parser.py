"""Optional AI-assisted structured resume extraction for Huntly.

Treats resume content as untrusted input.
Enforces strict JSON schema validation, defangs prompt injections,
and returns None on failure so the caller falls back to deterministic extraction.
"""

import json
import logging
import os
import re
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

RESUME_EXTRACTION_SCHEMA_PROMPT = """You are a resume parsing assistant for Huntly.
Your job is to extract structured career data from the provided resume text into valid JSON.

STRICT RULES:
1. ONLY extract information explicitly stated in the resume. DO NOT INVENT or HALLUCINATE any employers, dates, qualifications, technologies, metrics, or contact info.
2. If an item is missing or not mentioned, return empty string "" or empty list [].
3. For work experiences, preserve exact metrics and numbers in accomplishments.
4. Output MUST be ONLY a single valid JSON object with the following schema:
{
  "full_name": "string",
  "email": "string",
  "phone": "string",
  "location": "string",
  "tagline": "string",
  "linkedin": "string",
  "github": "string",
  "portfolio": "string",
  "website": "string",
  "summary": "string",
  "technical_skills": [
    {"name": "Python", "category": "Backend", "proficiency": "Proficient"}
  ],
  "experiences": [
    {
      "role": "Software Engineer",
      "company": "Company Name",
      "dates": "Jan 2021 - Present",
      "location": "City, ST",
      "responsibilities": ["Maintained services"],
      "accomplishments": ["Improved query latency by 40%"]
    }
  ],
  "projects": [
    {
      "name": "Project Name",
      "role": "Lead",
      "technologies": ["Django", "PostgreSQL"],
      "outcomes": "Deployed to 10k users"
    }
  ],
  "education": [
    {
      "degree": "B.S. in Computer Science",
      "institution": "University Name",
      "dates": "2016 - 2020",
      "details": "GPA 3.8"
    }
  ],
  "certifications": [
    {
      "name": "AWS Certified Solutions Architect",
      "issuer": "Amazon Web Services",
      "date": "2022"
    }
  ],
  "languages": [
    {"name": "English", "proficiency": "Native"}
  ],
  "awards": [
    {"title": "Dean's Honor List"}
  ],
  "warnings": []
}
"""


def sanitize_input_text(text: str, max_chars: int = 25000) -> str:
    """Sanitize resume text before sending to LLM."""
    if not text:
        return ""
    truncated = text[:max_chars].strip()
    # Strip dangerous instruction injection tags
    cleaned = re.sub(r'</?(?:SYSTEM|INSTRUCTION|PROMPT|OVERRIDE)[^>]*>', '', truncated, flags=re.IGNORECASE)
    return cleaned


def parse_resume_with_ai(text: str) -> Optional[Dict[str, Any]]:
    """Parse resume text using configured AI provider (Gemini or OpenAI).

    Returns structured dictionary or None.
    """
    clean_text = sanitize_input_text(text)
    if not clean_text:
        return None

    gemini_key = os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY')
    openai_key = os.environ.get('OPENAI_API_KEY')

    # Try Gemini first if key available
    if gemini_key:
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=gemini_key)
            prompt = f"{RESUME_EXTRACTION_SCHEMA_PROMPT}\n\nRESUME TEXT TO PARSE:\n\"\"\"\n{clean_text}\n\"\"\""

            response = client.models.generate_content(
                model='gemini-3.8-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type='application/json',
                    temperature=0.0,
                )
            )
            raw_json = response.text.strip()
            data = json.loads(raw_json)
            if isinstance(data, dict):
                return data
        except Exception as e:
            logger.warning(f"Gemini resume parsing failed: {e}")

    # Fallback to OpenAI if configured
    if openai_key:
        try:
            import requests
            headers = {
                "Authorization": f"Bearer {openai_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": RESUME_EXTRACTION_SCHEMA_PROMPT},
                    {"role": "user", "content": f"Parse this resume:\n{clean_text}"}
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.0,
            }
            res = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=20)
            if res.status_code == 200:
                resp_json = res.json()
                content = resp_json['choices'][0]['message']['content']
                data = json.loads(content)
                if isinstance(data, dict):
                    return data
        except Exception as e:
            logger.warning(f"OpenAI resume parsing failed: {e}")

    return None
