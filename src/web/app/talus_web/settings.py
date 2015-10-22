"""
Django settings for talus_web project.

For more information on this file, see
https://docs.djangoproject.com/en/1.7/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/1.7/ref/settings/
"""

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
import os
BASE_DIR = os.path.dirname(os.path.dirname(__file__))

NO_CONNECT = ("NO_CONNECT" in os.environ)


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/1.7/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = '0tg-fe$rac1mqzp7l#@4!e!)g0zymr-u^4ii$#yo_35ph$gk!w'

base = os.path.dirname("__file__").split(os.path.sep)[0]

if base == "/web":
	print("DEBUG IS FALSE")
	DEBUG = False
else:
	print("DEBUG IS TRUE")
	# SECURITY WARNING: don't run with debug turned on in production!
	DEBUG = True

TEMPLATE_DEBUG = True

ALLOWED_HOSTS = ["*"]


# Application definition

INSTALLED_APPS = (
	'django.contrib.admin',
	'django.contrib.auth',
	'django.contrib.contenttypes',
	'django.contrib.sessions',
	'django.contrib.messages',
	'django.contrib.staticfiles',
	'rest_framework',
	'rest_framework_swagger',
	'mongoengine.django.mongo_auth',
	'api'
)

REST_FRAMEWORK = {
	#'DEFAULT_PERMISSION_CLASSES': ('rest_framework.permissions.IsAdminUser',),
	'PAGE_SIZE': 10
}

MIDDLEWARE_CLASSES = (
	'django.contrib.sessions.middleware.SessionMiddleware',
	'django.middleware.common.CommonMiddleware',
	'django.middleware.csrf.CsrfViewMiddleware',
	'django.contrib.auth.middleware.AuthenticationMiddleware',
	'django.contrib.auth.middleware.SessionAuthenticationMiddleware',
	'django.contrib.messages.middleware.MessageMiddleware',
	'django.middleware.clickjacking.XFrameOptionsMiddleware',
)

ROOT_URLCONF = 'talus_web.urls'

WSGI_APPLICATION = 'talus_web.wsgi.application'


# Database
# https://docs.djangoproject.com/en/1.7/ref/settings/#databases

# as per http://docs.mongoengine.org/django.html, ignoring this. connect()
# will be called in api.models
DATABASES = {
	'default': {
		'ENGINE': 'django.db.backends.dummy'
	}
}

# Internationalization
# https://docs.djangoproject.com/en/1.7/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_L10N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/1.7/howto/static-files/

STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, "static_root")
