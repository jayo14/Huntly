#!/usr/bin/env bash
# Exit on error
set -o errexit

echo "==> Installing Node.js dependencies for resume generation..."
if command -v npm &> /dev/null; then
  npm ci --omit=dev || npm install --omit=dev
else
  echo "Warning: npm not found in environment. Ensure node/npm are installed if DOCX generation is required."
fi

echo "==> Installing Python dependencies..."
pip install -r requirements.txt

echo "==> Collecting static files..."
python3 manage.py collectstatic --noinput

echo "==> Running database migrations..."
python3 manage.py migrate --noinput

echo "==> Build complete!"
