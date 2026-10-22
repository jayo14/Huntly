web: gunicorn huntly.wsgi:application --bind 0.0.0.0:$PORT
release: python3 manage.py migrate --noinput
