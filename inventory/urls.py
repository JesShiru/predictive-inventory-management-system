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

    # out of stock
    path('out-of-stock/', views.out_of_stock_view, name='out_of_stock'),

    # low stock
    path('low-stock/', views.low_stock_view, name='low_stock'),

    # sales report page
    path('sales-report/', views.sales_report, name='sales_report'),
    
    # dashboard chart data
    path('api/dashboard-chart-data/', views.dashboard_chart_data, name='dashboard_chart_data'),

    # download pdf report
    path('download-pdf-report/', views.download_pdf_report, name='download_pdf_report'),

    #forecast
    path("generate-forecast/", views.generate_forecast, name="generate_forecast"),
    path("forecast-patterns/", views.forecast_patterns, name="forecast_patterns"),
    path("forecast-results/", views.view_forecast_results, name="view_forecast_results"),
]