"""
This file is relevant during deployment of the Django application.

WSGI config for predictive_inventory_management_system project.

It exposes the WSGI callable as a module-level variable named ``application``.

The get_wsgi_application() function is responsible for creating the WSGI application object 
that Django uses to communicate with the web server.
This object is used to handle incoming HTTP requests and return HTTP responses.

The application variable represents your actual, runnable Django application.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'predictive_inventory_management_system.settings')

application = get_wsgi_application()
