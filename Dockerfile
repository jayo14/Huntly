# Multi-language production Dockerfile for Huntly (Python + Node.js for DOCX generation)
FROM python:3.12-slim-bookworm

# System dependencies: curl for health checks, Node.js for Word document generation
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    gnupg \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list \
    && apt-get update && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Environment configuration
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=huntly.settings.prod \
    PORT=8000

# Install Node.js dependencies
COPY package.json package-lock.json ./
RUN npm ci --omit=dev

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Collect static files into /app/staticfiles for WhiteNoise
RUN SECRET_KEY="build-time-secret-key-placeholder" \
    ALLOWED_HOSTS="localhost" \
    python3 manage.py collectstatic --noinput

# Run as non-root user for security
RUN useradd -u 1001 -m huntly && chown -R huntly:huntly /app
USER huntly

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8000/ || exit 1

CMD ["sh", "-c", "python3 manage.py migrate --noinput && gunicorn huntly.wsgi:application --bind 0.0.0.0:${PORT} --workers 3 --timeout 60"]
