"""
This module contains the url paths for the accounts app, 
mapping specific HTTP requests to their corresponding view 
functions within the accounts app.
"""
from django.urls import path # this 
from . import views

# Application namespace for  reverse url lookup eg: accounts:login
app_name = "accounts"

urlpatterns = [
    # Route: /accounts/
    path("", views.login_view, name="login"),
    #Route: /accounts/login
    path("logout/", views.logout_view, name="logout"),
    # Route: /accouts/create_user
    path("create-user/", views.create_user, name="create_user"),
    path('unauthorized/', views.unauthorized_view, name='unauthorized')
]