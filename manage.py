#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def main():
    """
    The os.environ.setdefault() line sets the default settings module for the Django project.
    It tells Django to use the settings defined in the 'predictive_inventory_management_system.settings' 
    module when running management commands or starting the server.
    
    The try-block attempts to import the 'execute_from_command_line' function from 'django.core.management'.
    If the import fails it raises an ImportError with a message 
    If the import is successful, it calls 'execute_from_command_line(sys.argv)',
    which allows the script to handle command-line arguments 
    and execute the appropriate Django management commands.
    
    """
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'predictive_inventory_management_system.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
