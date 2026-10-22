from .base import *

DEBUG = True

DATABASES = {
    'default': env.db('DATABASE_URL', default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}")
}
if DATABASES['default']['ENGINE'] == 'django.db.backends.postgresql':
    DATABASES['default']['CONN_MAX_AGE'] = env.int('CONN_MAX_AGE', default=0)

ALLOWED_HOSTS = ['*']
