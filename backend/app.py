"""
Vercel Python runtime entrypoint: expects a module-level WSGI callable named ``app``.
See https://vercel.com/docs/functions/runtimes/python
"""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = get_wsgi_application()
