# Huntly — The Outbound Career Agent

> Double your interview callbacks with role-tailored resumes in 30 seconds.

Huntly is an AI-powered outbound career platform for modern job seekers. Paste any target job description to instantly generate an ATS-optimized Word DOCX resume, a customized 3-paragraph cover letter, and a direct 4-sentence email pitch to the hiring manager.

---

## Key Features

- **Master Career Profile**: Enter your career achievements, skills, and metrics once.
- **Instant ATS Keyword Alignment**: Extracts target skills and reorders experience bullets to maximize keyword density for ATS screens (Workday, Taleo, Greenhouse).
- **Targeted Cover Letters**: Generated in seconds with real metrics instead of generic fluff.
- **Direct Hiring Manager Outreach**: Draft and send concise cold pitches to skip the 500-applicant queue.
- **Clean ATS DOCX Export**: Outputs formatted single-column Microsoft Word documents.
- **Job Hunt Kanban Pipeline**: Visual board across **Saved &rarr; Applied &rarr; Interviewing &rarr; Offer &rarr; Rejected**.

---

## Local Development

### Prerequisites

- Python 3.10+ (tested through 3.14)
- Node.js 18+ and npm (required for ATS DOCX resume compilation)
- PostgreSQL (or SQLite for local zero-config testing)

### Setup

```bash
# 1. Clone repository
git clone https://github.com/jayo14/Huntly.git
cd Huntly

# 2. Install Node dependencies (for DOCX generation)
npm install

# 3. Create and activate Python virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# 4. Install Python dependencies
pip install -r requirements.txt

# 5. Environment configuration
cp .env.example .env

# 6. Apply database migrations
python3 manage.py migrate

# 7. Start local server
python3 manage.py runserver
```

Open [http://localhost:8000](http://localhost:8000) in your browser.

---

## Production Deployment

### Option 1: Render (Recommended Blueprint)

Huntly includes a [`render.yaml`](render.yaml) Blueprint configured with a web service and a managed PostgreSQL database.

1. Connect your GitHub repository to [Render](https://render.com).
2. Create a new **Blueprint Instance** pointing at `render.yaml`.
3. Render automatically provisions:
   - A Python web service running `./build.sh` and `gunicorn huntly.wsgi:application`.
   - A managed PostgreSQL instance connected via `DATABASE_URL`.
   - Automatic static file compression via WhiteNoise.
4. Add your `GEMINI_API_KEY` (or `OPENAI_API_KEY`) under **Environment Variables**.

### Option 2: Docker / Container Platforms (Fly.io, Railway, AWS, DigitalOcean)

A multi-stage, production-ready [`Dockerfile`](Dockerfile) is provided:

```bash
# Build Docker image
docker build -t huntly:latest .

# Run with Docker Compose (web + postgres)
docker compose up -d
```

### Option 3: Standard PaaS (Procfile & build.sh)

For platforms using buildpacks (Heroku, Railway, Dokku):
- [`Procfile`](Procfile): Runs `gunicorn huntly.wsgi:application --bind 0.0.0.0:$PORT`
- [`build.sh`](build.sh): Handles Node.js dependencies, Python packages, `collectstatic`, and database migrations.

---

## Environment Variables

| Variable | Required in Prod | Description |
|---|:---:|---|
| `SECRET_KEY` | **Yes** | 50+ character random string for cryptographic signing. |
| `ALLOWED_HOSTS` | **Yes** | Comma-separated domains (e.g. `huntly.app,.onrender.com`). |
| `CSRF_TRUSTED_ORIGINS` | **Yes** | Trusted HTTPS origins (e.g. `https://huntly.app`). |
| `DATABASE_URL` | **Yes** | PostgreSQL connection string (`postgres://user:pass@host:5432/db`). |
| `DJANGO_SETTINGS_MODULE` | **Yes** | Set to `huntly.settings.prod`. |
| `SECURE_SSL_REDIRECT` | Optional | Defaults to `True` in production. |
| `GEMINI_API_KEY` | Optional | Google Gemini API key for live LLM tailoring (uses deterministic fallback if omitted). |
| `OPENAI_API_KEY` | Optional | Alternative OpenAI API key. |

---

## Health Check & Verification

Huntly provides an automated health endpoint for uptime monitors:

```bash
curl http://localhost:8000/health/
# {"status": "ok", "app": "huntly"}
```

Run tests and production security check before pushing:

```bash
# Run test suite
python3 manage.py test core leads resumes

# Run Django production security verification
SECRET_KEY="<your-secret-key>" ALLOWED_HOSTS="localhost" python3 manage.py check --deploy --settings=huntly.settings.prod
```
