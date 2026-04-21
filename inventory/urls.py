from django.urls import path
from . import views

app_name = 'core'
urlpatterns = [
    # dashboard
    path('', views.dashboard, name='dashboard'),

    # products
    path('products/', views.product_list, name='product_list'),
    path('products/add/', views.product_create, name='product_create'),
    path('products/<int:pk>/edit/', views.product_update, name='product_update'),
    path('products/<int:pk>/delete/', views.product_delete, name='product_delete'),

    # sales API endpoint
    path('sales/new/', views.sale_form_view, name='sales_form'),
    path('sales/create/', views.sale_create, name='sale_create'),
]