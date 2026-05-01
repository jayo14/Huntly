from .base import *

DEBUG = True

DATABASES = {
    'default': env.db('DATABASE_URL', default='postgres://huntly_user:huntly_pass@localhost:5432/huntly_db')
}

ALLOWED_HOSTS = ['*']
