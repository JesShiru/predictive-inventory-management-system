"""
This module defines the permissions associated with different user roles in the system.
Used to control access to various features and functionalities based on user roles.

"""

ROLE_PERMISSIONS = {
    "ADMIN": [
        "create_user",
        "manage_users",
        "manage_products",
        "view_reports",
        "view_product_status",
        "delete_products",
        "view_admin_dashboard",
        "view_stock_movements",
        "generate_forecast",
        "download_pdf_report",
        "view_dashboard",
        "dashboard_chart",

    ],

    "MANAGER": [
        "manage_products",
        "view_reports",
        "view_product_status",
        "view_dashboard",
        "download_pdf_report",
        "dashboard_chart",
    ],

    "STAFF": [
        "record_sales",
        "view_dashboard",
        "dashboard_chart",
        "view_product_status"
    ],
}