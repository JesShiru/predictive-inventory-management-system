"""
This module contains decorators for permission checking based on user roles.

It ensures that users have the required permissions stored in their session
before accessing specific views, redirecting them appropriately if they do not.
"""

from functools import wraps
from django.shortcuts import redirect
from accounts.permissions import ROLE_PERMISSIONS

def permission_required(permission):
    """
    Decorator factory that takes a required permission string and returns a decorator.

    Args:
        permission: The specific permission name required to access the view ie create_users
    """

    # receives the view function as a parameter and wraps it with permission logic
    def decorator(view_func):

        @wraps(view_func) # preserves the original function's metadata, name and docstring
        def wrapper(request, *args, **kwargs): 

            # 1. Authentication Check: Ensure the user has a role assigned in their session
            role = request.session.get("role")

            if not role:
                return redirect("accounts:login")

            # 2. Authorization Check: Fetch permissions mapped to the user's role
            permissions = ROLE_PERMISSIONS.get(role, [])

            # Redirect if the required permission is missing
            if permission not in permissions:
                return redirect("accounts:unauthorized")

            # Execute and return the original view function
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator