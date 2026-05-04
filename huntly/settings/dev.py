from .base import *

DEBUG = True

DATABASES = {
    'default': env.db('DATABASE_URL', default='sqlite:///sqlite.db3')
}

ALLOWED_HOSTS = ['*']
