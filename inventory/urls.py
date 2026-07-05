from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

app_name = 'core'
urlpatterns = [

    # dashboards
    path('dashboard/',   views.dashboard,   name='dashboard'),
    path('admin-panel/', views.admin_panel,  name='admin_panel'),

    # products
    path('products/',                   views.product_list,   name='product_list'),
    path('products/add/',               views.product_create, name='product_create'),
    path('products/<int:pk>/edit/',     views.product_update, name='product_update'),

    # sales
    path("sales/", views.sale_create, name="sale_create"),

    # stock status
    path('out-of-stock/', views.out_of_stock_view, name='out_of_stock'),
    path('low-stock/',    views.low_stock_view,    name='low_stock'),

    # reports
    path('sales-report/',        views.sales_report,       name='sales_report'),
    path('download-pdf-report/', views.download_pdf_report, name='download_pdf_report'),

    # dashboard chart API
    path('api/dashboard-chart-data/', views.dashboard_chart_data, name='dashboard_chart_data'),

    # ── Forecasting ───────────────────────────────────────────────
    path('forecast/patterns/',              views.forecast_patterns,    name='forecast_patterns'),
    path('forecast/results/',              views.view_forecast_results, name='view_forecast_results'),

    # ── Admin panel ───────────────────────────────────────────────
    path('admin-panel/delete/<int:pk>/',     views.admin_delete_product,   name='admin_delete_product'),
    path('admin-panel/generate-forecast/',   views.generate_forecast, name='generate_forecast'),
    path('admin-panel/users/',               views.admin_users,             name='admin_users'),
    path('admin-panel/users/<int:pk>/update/', views.update_user_role,        name='update_user_role'),
    path('admin-panel/users/<int:pk>/toggle/', views.toggle_user_active,   name='toggle_user_active'),
    path('admin-panel/stock-movements/',     views.stock_movements_view,    name='stock_movements'),
]