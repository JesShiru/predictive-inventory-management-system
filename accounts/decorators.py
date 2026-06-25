from functools import wraps
from django.shortcuts import redirect
from accounts.permissions import ROLE_PERMISSIONS

def permission_required(permission):

    def decorator(view_func):

        @wraps(view_func)
        def wrapper(request, *args, **kwargs):

            role = request.session.get("role")

            if not role:
                return redirect("accounts:login")

            permissions = ROLE_PERMISSIONS.get(role, [])

            if permission not in permissions:
                return redirect("unauthorized")

            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator