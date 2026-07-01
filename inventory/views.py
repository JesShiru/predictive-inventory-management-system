from decimal import Decimal

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db.models import Sum
from django.db import transaction
import json
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from .models import Product, Sale, DemandForecast, StockMovement, Category
import os
from django.views.decorators.http import require_POST
from datetime import date, timedelta
from accounts.decorators import permission_required
from accounts.models import User

# a helper function for inventory statistics
# called in the dashboard view and the admin panel view
def get_inventory_stats():
    total_products = Product.objects.count()
    total_sales = Sale.objects.count()
    inventory_value = sum(p.total_value for p in Product.objects.all())
    all_products = Product.objects.all()
    out_of_stock_count = all_products.filter(stock_quantity=0).count()
    low_stock_count = all_products.filter(stock_quantity__gt=0, stock_quantity__lte=F('reorder_level')).count()

    return {
        'total_products': total_products,
        'total_sales': total_sales,
        'inventory_value': inventory_value,
        'out_of_stock_count': out_of_stock_count,
        'low_stock_count': low_stock_count,
    }

# Dashboard view
@permission_required("view_dashboard")
def dashboard(request):
    # call the inventory stats function to get the summary stats
    stats = get_inventory_stats()

    # Recent sales
    recent_sales = Sale.objects.select_related('product').order_by('-date')[:5]

    # Top selling products
    top_products = (
        Sale.objects
        .values('product__name', 'product__category__name', 'product__stock_quantity')
        .annotate(total_sold=Sum('quantity_sold'))
        .order_by('-total_sold')[:5]
    )

    # Expiring soon — Yoghurt products expiring within 7 days
    today = date.today()
    expiry_threshold = today + timedelta(days=7)

    expiring_soon = Product.objects.filter(
        category__name='Yoghurt',
        expiry_date__isnull=False,
        expiry_date__gte=today,           # not already expired
        expiry_date__lte=expiry_threshold # within 7 days
    ).order_by('expiry_date')

    expired = Product.objects.filter(
        category__name='Yoghurt',
        expiry_date__isnull=False,
        expiry_date__lt=today             # already past expiry
    )
    context = {
        'total_products': stats['total_products'],
        'total_sales': stats['total_sales'],
        'inventory_value': stats['inventory_value'],
        'out_of_stock_count': stats['out_of_stock_count'],
        'low_stock_count': stats['low_stock_count'],
        'recent_sales': recent_sales,
        'top_products': top_products,
        'expiring_soon': expiring_soon,
        'expiring_soon_count': expiring_soon.count(),
        'expired':expired,
        'expired_count': expired.count()
    }
    return render(request, 'core/dashboard.html', context)


# Product CRUD Views
from django.db.models import F
@permission_required("manage_products")
def product_list(request):
    products = Product.objects.select_related('category').all()

    category = request.GET.get('category', '')
    location = request.GET.get('location', '')
    status   = request.GET.get('status', '')

    if category:
        products = products.filter(category__name=category)
    if location:
        products = products.filter(stock_location=location)
    if status == 'low':
        products = products.filter(stock_quantity__gt=0, stock_quantity__lte=F('reorder_level'))
    elif status == 'out':
        products = products.filter(stock_quantity=0)

    all_products = Product.objects.all()
    total_products     = all_products.count()
    low_stock_count    = all_products.filter(stock_quantity__gt=0, stock_quantity__lte=F('reorder_level')).count()
    out_of_stock_count = all_products.filter(stock_quantity=0).count()

    category_choices = ['Yoghurt', 'Raw Materials']

    return render(request, 'core/product_list.html', {
        'products': products,
        'total_products': total_products,
        'low_stock_count': low_stock_count,
        'out_of_stock_count': out_of_stock_count,
        'category_options': [
            {'value': c, 'label': c, 'selected': category == c}
            for c in category_choices
        ],
        'location_options': [
            {'value': 'STORE',     'label': 'Store',     'selected': location == 'STORE'},
            {'value': 'COLD ROOM', 'label': 'Cold Room', 'selected': location == 'COLD ROOM'},
        ],
        'status_options': [
            {'value': 'low', 'label': 'Low Stock',    'selected': status == 'low'},
            {'value': 'out', 'label': 'Out of Stock', 'selected': status == 'out'},
        ],
    })

# view for creating products
# the form is handled in the template, and the view handles the POST request to save the product
@permission_required("manage_products")
def product_create(request):
    if request.method == 'POST':
        item_no = request.POST.get("item_no")
        name = request.POST.get("name")
        category_id = request.POST.get("category")
        stock_location = request.POST.get("stock_location")
        unit_price = request.POST.get("unit_price")
        stock_quantity = request.POST.get("stock_quantity")
        reorder_level = request.POST.get("reorder_level")
        restock_date = request.POST.get("date_of_last_restocking")
        expiry_date = request.POST.get("expiry_date")

        if not item_no:
            messages.error(request, "Item SKU required.")
            return redirect('core:product_list')
        
        if Decimal(unit_price) < 0:
            messages.error(request, "Unit price can't be negative.")
            return redirect('core:product_list')
        
        if int(stock_quantity) < 0:
            messages.error(request, "Stock quantity cannot be negative.")
            return redirect("core:product_create")

        if int(reorder_level) > int(stock_quantity):
            messages.error(request, "Reorder level cannot exceed stock quantity.")
            return redirect("core:product_create")

        category = get_object_or_404(Category, pk=category_id)
            
        # record the product in the database
        Product.objects.create(
            item_no=item_no,
            name=name,
            category=category,
            stock_location=stock_location,
            unit_price=Decimal(unit_price),
            stock_quantity=int(stock_quantity),
            reorder_level=int(reorder_level),
            date_of_last_restocking=restock_date,
            expiry_date=expiry_date or None,
        )
    return render(request, 'core/product_form.html', 
                  {'categories': Category.objects.all(), 
                    'stock_locations': Product.LOCATION_CHOICES})

# view for updating products
@permission_required("manage_products")
def product_update(request, pk):
    product = get_object_or_404(Product, pk=pk)
    old_quantity = product.stock_quantity  # ← capture the old quantity before save

    # Handle the form submission
    if request.method == 'POST':

        # read data from the HTML
        item_no = request.POST.get("item_no")
        name = request.POST.get("name")
        category_id = request.POST.get("category")
        stock_location = request.POST.get("stock_location")
        unit_price = request.POST.get("unit_price")
        stock_quantity = request.POST.get("stock_quantity")
        reorder_level = request.POST.get("reorder_level")
        restock_date = request.POST.get("date_of_last_restocking")
        expiry_date = request.POST.get("expiry_date")
       
        # validation
        try:
            unit_price = Decimal(unit_price)
            stock_quantity = int(stock_quantity)
            reorder_level = int(reorder_level)
        except ValueError:
            messages.error(request, "Invalid numeric values.")
            return redirect("core:product_update", pk=pk)
        
        if unit_price < 0:
            messages.error(request, "Unit price cannot be negative.")
            return redirect("core:product_update", pk=pk)

        if stock_quantity < 0:
            messages.error(request, "Stock quantity cannot be negative.")
            return redirect("core:product_update", pk=pk)

        if reorder_level < 0:
            messages.error(request, "Reorder level cannot be negative.")
            return redirect("core:product_update", pk=pk)

        if reorder_level > stock_quantity:
            messages.error(
                request,
                "Reorder level cannot exceed stock quantity."
            )
            return redirect("core:product_update", pk=pk)
        
        category = get_object_or_404(Category, pk=category_id)

        # Update the fields
        Product.objects.filter(pk=pk).update(
            item_no=item_no,
            name=name,
            category=category,
            stock_location=stock_location,
            unit_price=unit_price,
            stock_quantity=stock_quantity,
            reorder_level=reorder_level,
            date_of_last_restocking=restock_date,
            expiry_date=expiry_date or None,
        )

        # record stock movement if stock quantity changed
        diff = product.stock_quantity - old_quantity


        # Only log if stock quantity actually changed
        if diff != 0:
            StockMovement.objects.create(
                product=product,
                movement_type='IN' if diff > 0 else 'OUT',
                action='RESTOCK' if diff > 0 else 'ADJUSTMENT',
                quantity=abs(diff),
                user=request.user,
                note=f"Manual stock update: {old_quantity} → {product.stock_quantity}"
            )

        messages.success(request, "Product updated successfully.")
        return redirect('core:product_list')

    return render(request, 'core/product_form.html', {'product': product, 'categories': Category.objects.all()})

# view for deleting products
@permission_required("delete_products")
def product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        product.delete()
        messages.success(request, "Product deleted successfully.")
        return redirect('core:product_list')
    return render(request, 'core/product_confirm_delete.html', {'product': product})


# Sales API Endpoint
@require_http_methods(["POST"])
@permission_required("record_sales")
def sale_create(request):
    """
    API endpoint to record a sale.
    Expects JSON: { "product": <product_id>, "quantity_sold": <int>, "sale_price": <decimal> }
    """
    # Validate JSON input
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    # Validate required fields
    product_id = data.get('product')
    try:
        quantity_sold = int(data.get('quantity_sold'))
    except (TypeError, ValueError):
        return JsonResponse({"error": "Invalid quantity_sold. Must be an integer."}, status=400)
    
    try:
        sale_price = float(data.get('sale_price'))
    except (TypeError, ValueError):
        return JsonResponse({"error": "Invalid sale_price. Must be a number."}, status=400)

    if quantity_sold <= 0:
        return JsonResponse({"error": "Quantity sold must be greater than zero."}, status=400)
    if sale_price < 0:
        return JsonResponse({"error": "Sale price cannot be negative."}, status=400)
    if not product_id:
        return JsonResponse({"error": "Product ID is required."}, status=400)

    # Use a transaction to ensure atomicity
    try:
        with transaction.atomic():
            # Lock the product row for update to prevent race conditions
            product = Product.objects.select_for_update().get(id=product_id)
            
            if product.stock_quantity < quantity_sold:
                return JsonResponse(
                    {"error": f"Insufficient stock. Only {product.stock_quantity} available."},
                    status=400
                )
            
            # Update stock - modifies the stock quantity for the selected column
            new_stock = product.stock_quantity - quantity_sold

            Product.objects.filter(pk=product.pk).update(
            stock_quantity=new_stock
            )

            product.stock_quantity = new_stock
            
            # Create the sale object
            sale = Sale.objects.create(
                product=product,
                quantity_sold=quantity_sold,
                sale_price=sale_price
            )
            
            # Create stock movement audit entry
            StockMovement.objects.create(
                product=product,
                movement_type='OUT',
                action='SALE',
                quantity=quantity_sold,
                user=request.user,
                note=f'Sale ID: {sale.id}'
            )
            
            # Return the detailed response including updated stock level
            response_data = {
                'id': sale.id,
                'product': product.id,
                'quantity_sold': sale.quantity_sold,
                'sale_price': str(sale.sale_price),
                'date': sale.date.isoformat(),
                'total_sale_value': str(sale.total_sale_value),
                'updated_stock_level': product.stock_quantity
            }
            
            return JsonResponse(response_data, status=201)
            
    except Product.DoesNotExist:
        return JsonResponse({"error": "Product not found"}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)

# sales form view
@permission_required("record_sales")
def sale_form_view(request):
    products = Product.objects.select_related('category').filter(category__name='Yoghurt')
    product_options = [
        {
            'val':   str(p.pk),
            'label': f"{p.name} ({p.get_stock_location_display()})",
            'stock': p.stock_quantity,
            'price': str(p.unit_price),
        }
        for p in products
    ]
    return render(request, 'core/sales_form.html', {
        'product_options': product_options,
    })

# out of stock view
@permission_required("view_reports")
def out_of_stock_view(request):
    out_of_stock = Product.objects.select_related('category').filter(stock_quantity=0)
    return render(request, 'core/out_of_stock.html', {'products': out_of_stock, 'count': out_of_stock.count()})

# low stock view
@permission_required("view_reports")
def low_stock_view(request):
    low_stock = Product.objects.select_related('category').filter(stock_quantity__gt=0, stock_quantity__lte=F('reorder_level'))
    return render(request, 'core/low_stock.html', {'products': low_stock, 'count': low_stock.count()})

# Sales report view
# Import the analytics engine
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

@permission_required("view_reports")
def sales_report(request):
    """
    Renders the full sales report page.
    Supports optional date filtering via GET params: ?start=YYYY-MM-DD&end=YYYY-MM-DD
    """
    from analytics import get_engine
    import pandas as pd

    from analytics import (
        load_dataframe, summary_statistics, top_products,
        daily_trend, last_7_days, stock_turnover
    )

    start_date = request.GET.get("start", "")
    end_date   = request.GET.get("end",   "")
    turnover_days = int(request.GET.get("turnover_days", 90))
    turnover_end = date.today()
    turnover_start = turnover_end - timedelta(days=turnover_days)

    try:
        engine = get_engine()
        df     = load_dataframe(engine)
        turnover = stock_turnover(engine, start_date=turnover_start, end_date=turnover_end)

        if df.empty:
            return render(request, "core/sales_report.html", {"error": True})

        # Apply date filters 
        if start_date:
            df = df[df["date"] >= pd.to_datetime(start_date)]
        if end_date:
            df = df[df["date"] <= pd.to_datetime(end_date)]

        report = {
            "summary":      summary_statistics(df),
            "top_products": top_products(df, n=10),
            "daily_trend":  daily_trend(df),
            "last_7_days":  last_7_days(df),
            "turnover":     turnover,
            "turnover_days": turnover_days,
            "turnover_start": str(turnover_start),
            "turnover_end": str(turnover_end),
            "turnover_options": [
                {"value": 30,  "label": "30 days",           "selected": turnover_days == 30},
                {"value": 60,  "label": "60 days",           "selected": turnover_days == 60},
                {"value": 90,  "label": "90 days",           "selected": turnover_days == 90},
                {"value": 180, "label": "180 days",          "selected": turnover_days == 180},
                {"value": 365, "label": "1 year",            "selected": turnover_days == 365},
                {"value": 730, "label": "Full history (2 years)", "selected": turnover_days == 730},
],
            # Pass as JSON for Chart.js
            "chart_labels":  json.dumps([d["date"]    for d in daily_trend(df)]),
            "chart_revenue": json.dumps([d["revenue"] for d in daily_trend(df)]),
            "start_date":    start_date,
            "end_date":      end_date,
        }

        return render(request, "core/sales_report.html", report)

    except Exception as e:
        return render(request, "core/sales_report.html", {
            "error": True,
            "error_message": str(e),
        })
    

# DASHBOARD CHART DATA (JSON endpoint)
@permission_required("view_reports")
def dashboard_chart_data(request):
    since = date.today() - timedelta(days=90)

    daily_sales = (
        Sale.objects
        .filter(date__gte=since)
        .values('date')
        .annotate(total=Sum('quantity_sold'))
        .order_by('date')
    )
    return JsonResponse({
        "labels": [str(d['date']) for d in daily_sales],
        "data":   [d['total']     for d in daily_sales],
        "label": "Units Sold",
    })


# pdf download
@permission_required("download_pdf_report")
def download_pdf_report(request):
    """
    Generates and streams the PDF sales report as a download.
    """
    import tempfile
    from generate_pdf import generate_pdf

    try:
        with tempfile.NamedTemporaryFile(
            suffix=".pdf", delete=False, prefix="shefa_sales_"
        ) as tmp:
            tmp_path = tmp.name

        generate_pdf(output_path=tmp_path)

        with open(tmp_path, "rb") as f:
            pdf_data = f.read()

        os.unlink(tmp_path)

        from datetime import date
        filename = f"shefa_sales_report_{date.today()}.pdf"
        response = HttpResponse(pdf_data, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    except Exception as e:
        return HttpResponse(f"PDF generation failed: {e}", status=500)

'''# generate_forecast view
@permission_required("generate_forecast")
@require_POST
def generate_forecast(request):
    from inventory.forecast_engine import run_forecast_for_product
    from inventory.models import Product

    total_records = 0
    products_processed = 0

    for product in Product.objects.filter(category__name="Yoghurt"):
        result = run_forecast_for_product(product, force_retrain=True)
        if not result["error"]:
            total_records += result["records"]
            products_processed += 1

    messages.success(
        request,
        f"Forecast complete. {products_processed} products processed, "
        f"{total_records} records saved."
    )
    return redirect("core:view_forecast_results")'''


# forecast_patterns view
@permission_required("view_reports")
def forecast_patterns(request):
    """
    Builds chart data for 7, 14, 30, and 90-day horizons.
    Context keys match the data-island IDs in forecast_patterns.html.
    """
    from django.db.models import Sum
 
    today = date.today()
 
    def chart_for_horizon(days):
        end = today + timedelta(days=days)
        daily = (
            DemandForecast.objects
            .filter(
                product__category__name="Yoghurt",
                forecast_date__gte=today,
                forecast_date__lte=end,
            )
            .values("forecast_date")
            .annotate(total=Sum("forecasted_quantity"))
            .order_by("forecast_date")
        )
        return {
            "labels": [str(d["forecast_date"]) for d in daily],
            "data":   [d["total"]              for d in daily],
        }
 
    context = {
        "chart_7d":      json.dumps(chart_for_horizon(7)),
        "chart_14d":     json.dumps(chart_for_horizon(14)),
        "chart_30d":     json.dumps(chart_for_horizon(30)),
        "chart_90d":     json.dumps(chart_for_horizon(90)),
        "has_forecasts": DemandForecast.objects.filter(
                             forecast_date__gte=today).exists(),
    }
    return render(request, "core/forecast_patterns.html", context)

# forecast_result view
@permission_required("view_reports")
def view_forecast_results(request):
    """
    Shows per-SKU forecast totals and average daily demand for the next 30 days.
    Restock status is handled separately by the stock monitoring dashboard.
    """
    from django.db.models import Avg, Max, Sum

    today        = date.today()
    next_30_days = today + timedelta(days=30)
    products     = Product.objects.filter(category__name="Yoghurt")

    results = []
    for product in products:
        forecasts_30 = DemandForecast.objects.filter(
            product=product,
            forecast_date__gte=today,
            forecast_date__lte=next_30_days,
        )

        if not forecasts_30.exists():
            continue

        total_forecasted = forecasts_30.aggregate(t=Sum("forecasted_quantity"))["t"] or 0
        avg_daily        = forecasts_30.aggregate(a=Avg("forecasted_quantity"))["a"] or 0

        results.append({
            "product":          product,
            "current_stock":    product.stock_quantity,
            "reorder_level":    product.reorder_level,
            "total_forecasted": total_forecasted,
            "avg_daily":        round(avg_daily, 1),
        })

    context = {
        "results":       results,
        "last_forecast": DemandForecast.objects.aggregate(m=Max("forecast_date"))["m"],
    }
    return render(request, "core/view_forecast_results.html", context)
 
    
# ── ADMIN PANEL ───────────────────────────────────────────────
@permission_required("view_admin_dashboard")
def admin_panel(request):
    from django.db.models import Sum, F

    # call the inventory stats function to get the summary stats
    stats = get_inventory_stats()

    # get total users
    total_users = User.objects.count()

    # Recent sales (last 8)
    recent_sales = Sale.objects.select_related('product').order_by('-date')[:8]

    # Top selling products (top 8 by quantity)
    top_products = (
        Sale.objects
        .values(
            'product__name',
            'product__category__name',
            'product__stock_quantity',
        )
        .annotate(total_sold=Sum('quantity_sold'))
        .order_by('-total_sold')[:8]
    )

    context = {
        'total_products':     stats['total_products'],
        'total_users':        total_users,
        'total_sales':        stats['total_sales'],
        'inventory_value':    stats['inventory_value'],
        'low_stock_count':    stats['low_stock_count'],
        'out_of_stock_count': stats['out_of_stock_count'],
        'recent_sales':       recent_sales,
        'top_products':       top_products,
    }
    return render(request, 'core/admin_dashboard.html', context)


# ── ADMIN GENERATE FORECAST ───────────────────────────────────
@permission_required("generate_forecast")
@require_POST
def admin_generate_forecast(request):
    from inventory.forecast_engine import run_forecast_for_product
    from inventory.models import Product

    products_processed = 0

    for product in Product.objects.filter(category__name="Yoghurt"):
        result = run_forecast_for_product(product, force_retrain=True)
        if not result["error"]:
            products_processed += 1

    messages.success(request, f"Forecast complete. {products_processed} products processed.")
    return redirect("core:admin_panel")


# ── ADMIN DELETE PRODUCT ──────────────────────────────────────
@permission_required("delete_products")
def admin_delete_product(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == "POST":
        name = product.name
        # Log remaining stock going out
        if product.stock_quantity > 0:
            StockMovement.objects.create(
                product=product,
                movement_type='OUT',
                action='DELETE',
                quantity=product.stock_quantity,
                user=request.user,
                note=f"Product deleted: {name}"
            )
        product.delete()
        messages.success(request, f"{name} deleted successfully.")
        return redirect("core:admin_panel")
    return render(request, "core/admin_confirm_delete.html", {"product": product})

@permission_required("manage_users")
def admin_users(request):
    from accounts.models import User

    users = User.objects.all().order_by('-date_joined')

    return render(request, 'core/admin_users.html', {
        'users':       users,
        'total_users': users.count(),
        'admin_count': users.filter(role='ADMIN').count(),
        'active_count': users.filter(is_active=True).count(),
    })


@permission_required("manage_users")
def toggle_user_active(request, pk):
    """Activate or deactivate a user account."""
    from accounts.models import User
    if request.method == 'POST':
        user = get_object_or_404(User, pk=pk)
        if user != request.user:  # prevent self-deactivation
            user.is_active = not user.is_active
            user.save()
            status = "activated" if user.is_active else "deactivated"
            messages.success(request, f"{user.username} {status} successfully.")
        else:
            messages.warning(request, "You cannot deactivate your own account.")
    return redirect('core:admin_users')


# ── STOCK MOVEMENTS AUDIT LOG ──────────────────────────────────
from django.core.paginator import Paginator

@permission_required("view_stock_movements")
def stock_movements_view(request):
    movements = StockMovement.objects.select_related('product', 'user').order_by('-date')

    # Filters
    action     = request.GET.get('action', '')
    product_id = request.GET.get('product', '')
    start_date = request.GET.get('start_date', '')
    end_date   = request.GET.get('end_date', '')

    if action:
        movements = movements.filter(action=action)
    if product_id:
        movements = movements.filter(product_id=product_id)
    if start_date:
        movements = movements.filter(date__date__gte=start_date)
    if end_date:
        movements = movements.filter(date__date__lte=end_date)

    # Stats — always from full table, not filtered
    total_movements = StockMovement.objects.count()
    sales_count     = StockMovement.objects.filter(action='SALE').count()
    restock_count   = StockMovement.objects.filter(action='RESTOCK').count()

    # Pagination — 20 rows per page
    paginator = Paginator(movements, 20)
    page      = request.GET.get('page', 1)
    movements = paginator.get_page(page)

    context = {
        'movements':        movements,        
        'total_movements':  total_movements,
        'sales_count':      sales_count,
        'restock_count':    restock_count,
        'action_choices':   StockMovement.ACTION_CHOICES,
        'product_choices':  Product.objects.all().order_by('name'),
        'current_action':     action,
        'current_product':    product_id,
        'current_start_date': start_date,
        'current_end_date':   end_date,
    }
    return render(request, 'core/stock_movements.html', context)