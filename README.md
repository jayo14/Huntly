# Huntly

A Django-based lead management CRM for tracking prospects, sending outreach emails, and managing your sales pipeline.

## Features

- Dashboard with funnel stats and conversion tracking
- Lead list with search and status filtering
- Kanban-style pipeline view
- Outreach message generation and sending
- App settings (SMTP, tone, offers)

---

## Local Development

### Prerequisites

- Python 3.10+
- A PostgreSQL database (or use SQLite by omitting `DATABASE_URL` in dev)

### Setup

```bash
# 1. Clone the repository
git clone <your-repo-url>
cd Huntly

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy the example env file and fill in your values
cp .env.example .env

# 5. Run migrations
python manage.py migrate

# 6. Start the development server
python manage.py runserver
```

By default the dev settings (`huntly.settings.dev`) use PostgreSQL via `DATABASE_URL`.  
You can point `DATABASE_URL` at a local Postgres instance or a hosted one (see `.env.example`).

---

## Environment Variables

Copy `.env.example` to `.env` and set the following variables:

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | Yes | Django secret key (generate with `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`) |
| `DEBUG` | No | `True` for local dev, `False` in production (default: `False`) |
| `ALLOWED_HOSTS` | Yes (prod) | Comma-separated list of allowed hostnames, e.g. `yourdomain.com,.vercel.app` |
| `DATABASE_URL` | Yes | PostgreSQL connection string — `postgres://USER:PASSWORD@HOST:PORT/DBNAME` |
| `DJANGO_SETTINGS_MODULE` | Yes (prod) | `huntly.settings.prod` for production, `huntly.settings.dev` for local |

---

## Deployment on Vercel

1. Push the repository to GitHub and import it in [Vercel](https://vercel.com).
2. In your Vercel project **Settings → Environment Variables**, add:
   - `SECRET_KEY` — a strong random secret key
   - `ALLOWED_HOSTS` — your Vercel domain, e.g. `huntly-ai-alpha.vercel.app`
   - `DATABASE_URL` — a hosted PostgreSQL connection string (e.g. [Neon](https://neon.tech), [Supabase](https://supabase.com), [Railway](https://railway.app))
   - `DJANGO_SETTINGS_MODULE` — `huntly.settings.prod`
3. Run database migrations from your local machine (or a CI step) targeting the production database:
   ```bash
   DATABASE_URL=<your-prod-db-url> DJANGO_SETTINGS_MODULE=huntly.settings.prod python manage.py migrate
   ```
4. Deploy — Vercel will use `vercel.json` to route requests through the Django WSGI app.

> **Why the "Connection refused" error?**  
> The production settings require `DATABASE_URL` to be set to a reachable PostgreSQL server.  
> Without it (or with the wrong settings module), Django falls back to trying `localhost:5432`,  
> which does not exist in Vercel's serverless environment.
