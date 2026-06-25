import re
from django.contrib import messages
from .decorators import permission_required
from django.shortcuts import render, redirect
from .models import User

# view for creating a new user
@permission_required("create_user")
def create_user(request):

    if request.method == "POST":

        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()
        password1 = request.POST.get("password1")
        password2 = request.POST.get("password2")
        role = request.POST.get("role")

        errors = {}

        # Username
        if not username:
            errors["username"] = "Username is required."

        elif User.objects.filter(username=username).exists():
            errors["username"] = "Username already exists."

        # Email
        if not email:
            errors["email"] = "Email is required."

        elif User.objects.filter(email=email).exists():
            errors["email"] = "Email already exists."

        # Password
        if not password1:
            errors["password1"] = "Password is required."

        elif len(password1) < 8:
            errors["password1"] = "Password must be at least 8 characters."

        elif not re.search(r"[A-Z]", password1):
            errors["password1"] = "Password must contain an uppercase letter."

        elif not re.search(r"[a-z]", password1):
            errors["password1"] = "Password must contain a lowercase letter."

        elif not re.search(r"\d", password1):
            errors["password1"] = "Password must contain a number."

        elif not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password1):
            errors["password1"] = "Password must contain a special character."

        elif password1 != password2:
            errors["password2"] = "Passwords do not match."

        # Role
        valid_roles = [choice[0] for choice in User.ROLE_CHOICES]

        if role not in valid_roles:
            errors["role"] = "Please select a valid role."

        if not errors:

            user = User(
                username=username,
                email=email,
                role=role
            )

            user.set_password(password1)
            user.save()

            messages.success(
                request,
                f"User '{user.username}' created successfully."
            )

            return redirect("core:admin_users")

        return render(
            request,
            "create_user.html",
            {   
                "roles": User.ROLE_CHOICES,
                "errors": errors,
                "data": request.POST
            }
        )

    return render(
        request,
        "create_user.html",{
            "roles": User.ROLE_CHOICES,
        }
    )

# login view
def login_view(request):

    if request.method == "POST":

        email = request.POST.get("email", "").strip()
        password = request.POST.get("password")

        try:
            user = User.objects.get(email=email)

        except User.DoesNotExist:
            user = None

        # authentication and session management
        if user and user.check_password(password):

            # Store user information in session
            request.session["user_id"] = user.id
            request.session["email"] = user.email
            request.session["role"] = user.role

            messages.success(request, "Login successful.")

            if user.role == "ADMIN":
                return redirect("core:admin_panel")

            elif user.role == "MANAGER":
                return redirect("core:manager_dashboard")

            else:
                return redirect("core:dashboard")

        messages.error(request, "Invalid username or password.")

    return render(request, "login.html")

def home(request):
    return redirect("accounts:login")

# logout view
def logout_view(request):

    request.session.flush()

    return redirect("accounts:login")