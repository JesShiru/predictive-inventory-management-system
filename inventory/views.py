from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required 
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from django.contrib import messages
from django.views import View
from django.db.models import Sum, Avg
from django.utils import timezone
from datetime import timedelta
from django.db import transaction
import json
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from .models import Product, Sale, StockMovement, Order, DemandForecast
from .forms import ProductForm, SaleForm, RegisterForm
import subprocess
import os
from django.views.decorators.http import require_POST


# Registration view
class RegisterView(View):
    def get(self, request):
        form = RegisterForm()
        return render(request, 'registration/register.html', {'form': form})

    def post(self, request):
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()  
            messages.success(request, "Account created successfully. Please log in.")
            return redirect('login')
        return render(request, 'registration/register.html', {'form': form})

# Dashboard view
@login_required
def dashboard(request):
    # Stats
    total_products = Product.objects.count()
    total_sales = Sale.objects.count()
    inventory_value = sum(p.total_value for p in Product.objects.all())

    # Alerts
    all_products = Product.objects.all()
    out_of_stock = [p for p in all_products if p.stock_quantity == 0]
    low_stock = [p for p in all_products if 0 < p.stock_quantity <= p.reorder_level]

    # Recent sales
    recent_sales = Sale.objects.select_related('product').order_by('-date')[:5]

    # Top selling products
    top_products = (
        Sale.objects
        .values('product__name', 'product__category__name', 'product__stock_quantity')
        .annotate(total_sold=Sum('quantity_sold'))
        .order_by('-total_sold')[:5]
    )

    # Sales trend (last 30 days)
    thirty_days_ago = timezone.now() - timedelta(days=30)
    daily_sales = (
        Sale.objects
        .filter(date__gte=thirty_days_ago)
        .values('date')
        .annotate(total=Sum('quantity_sold'))
        .order_by('date')
    )

    
    sales_labels = [str(s['date']) for s in daily_sales]
    sales_data = [s['total'] for s in daily_sales]

    context = {
        'total_products': total_products,
        'total_sales': total_sales,
        'inventory_value': inventory_value,
        'out_of_stock': out_of_stock,
        'out_of_stock_count': len(out_of_stock),
        'low_stock': low_stock,
        'low_stock_count': len(low_stock),
        'recent_sales': recent_sales,
        'top_products': top_products,
        'sales_labels': sales_labels,
        'sales_data': sales_data,
    }
    return render(request, 'core/dashboard.html', context)


# Product CRUD Views
from django.db.models import F
@login_required
def product_list(request):
    products = Product.objects.select_related('category', 'supplier').all()

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

@login_required
def product_create(request):
    if request.method == 'POST':
        form = ProductForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Product created successfully.")
            return redirect('core:product_list')
    else:
        form = ProductForm()
    return render(request, 'core/product_form.html', {'form': form})

@login_required
def product_update(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        form = ProductForm(request.POST, instance=product)
        if form.is_valid():
            form.save()
            messages.success(request, "Product updated successfully.")
            return redirect('core:product_list')
    else:
        form = ProductForm(instance=product)
    return render(request, 'core/product_form.html', {'form': form, 'product': product})

@login_required
def product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        product.delete()
        messages.success(request, "Product deleted successfully.")
        return redirect('core:product_list')
    return render(request, 'core/product_confirm_delete.html', {'product': product})


# Sales API Endpoint
@require_http_methods(["POST"])
@login_required
def sale_create(request):
    """
    API endpoint to record a sale.
    Expects JSON: { "product": <product_id>, "quantity_sold": <int>, "sale_price": <decimal> }
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

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

    try:
        with transaction.atomic():
            # Lock the product row for update to prevent race conditions
            product = Product.objects.select_for_update().get(id=product_id)
            
            if product.stock_quantity < quantity_sold:
                return JsonResponse(
                    {"error": f"Insufficient stock. Only {product.stock_quantity} available."},
                    status=400
                )
            
            # Update stock
            product.stock_quantity -= quantity_sold
            product.save()
            
            # Save the sale
            sale = Sale.objects.create(
                product=product,
                quantity_sold=quantity_sold,
                sale_price=sale_price
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
@login_required
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
@login_required
def out_of_stock_view(request):
    out_of_stock = Product.objects.select_related('category', 'supplier').filter(stock_quantity=0)
    return render(request, 'core/out_of_stock.html', {'products': out_of_stock, 'count': out_of_stock.count()})

# low stock view
@login_required
def low_stock_view(request):
    low_stock = Product.objects.select_related('category', 'supplier').filter(stock_quantity__gt=0, stock_quantity__lte=F('reorder_level'))
    return render(request, 'core/low_stock.html', {'products': low_stock, 'count': low_stock.count()})

# Sales report view
# Import your analytics engine
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

@login_required
def sales_report(request):
    """
    Renders the full sales report page.
    Supports optional date filtering via GET params: ?start=YYYY-MM-DD&end=YYYY-MM-DD
    """
    from analytics import full_report, get_engine
    import pandas as pd
    from datetime import date, timedelta

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

@login_required
def dashboard_chart_data(request):
    from analytics import load_dataframe, last_30_days_trend, get_engine 
    try:
        engine = get_engine()
        df     = load_dataframe(engine)

        if df.empty:
            return JsonResponse({"labels": [], "data": []})

        trend = last_30_days_trend(df)
        return JsonResponse({
            "labels": [d["date"]    for d in trend],
            "data":   [d["revenue"] for d in trend],
        })

    except Exception as e:
        import traceback
        print("DASHBOARD CHART ERROR:", traceback.format_exc())
        return JsonResponse({"error": str(e)}, status=500)


# pdf download
@login_required
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

# generate_forecast view
@login_required
@require_POST
def generate_forecast(request):
    """
    Triggers LSTM training and forecast generation.
    Redirects to forecast results on completion.
    """
    import sys
    sys.path.insert(0, os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    ))

    try:
        from forecast_engine import run_forecast
        summary = run_forecast()

        request.session["forecast_summary"] = summary
        messages.success(
            request,
            f"Forecast complete. "
            f"{summary['products_processed']} products processed, "
            f"{summary['total_records']} records saved."
        )
    except Exception as e:
        messages.error(request, f"Forecast failed: {e}")

    return redirect("core:view_forecast_results")

# forecast_patterns view
@login_required
def forecast_patterns(request):
    from datetime import date
    from django.db.models import Sum

    today = date.today()

    chart_data = {
        "90_days": {
            "end": today + timedelta(days=90)
        },
        "6_months": {
            "end": today + timedelta(days=180)
        },
        "1_year": {
            "end": today + timedelta(days=365)
        },
    }

    for label, meta in chart_data.items():
        daily = (
            DemandForecast.objects
            .filter(
                product__category__name="Yoghurt",
                forecast_date__gte=today,
                forecast_date__lte=meta["end"],  # ← date range only, no notes filter
            )
            .values("forecast_date")
            .annotate(total=Sum("forecasted_quantity"))
            .order_by("forecast_date")
        )
        chart_data[label] = {
            "labels": [str(d["forecast_date"]) for d in daily],
            "data":   [d["total"]              for d in daily],
        }

    context = {
        "chart_90":      json.dumps(chart_data["90_days"]),
        "chart_6m":      json.dumps(chart_data["6_months"]),
        "chart_1y":      json.dumps(chart_data["1_year"]),
        "has_forecasts": DemandForecast.objects.exists(),
    }

    return render(request, "core/forecast_patterns.html", context)

# forecast_result view
@login_required
def view_forecast_results(request):
    try:
        from datetime import date
        from django.db.models import Max, Sum, Avg

        today = date.today()
        products = Product.objects.filter(category__name="Yoghurt")

        results = []
        for product in products:
            forecasts = DemandForecast.objects.filter(
                product=product,
                forecast_date__gte=today,
            )

            if not forecasts.exists():
                continue

            total_forecasted = forecasts.aggregate(t=Sum("forecasted_quantity"))["t"] or 0
            avg_daily = forecasts.aggregate(a=Avg("forecasted_quantity"))["a"] or 0
            alert_count = forecasts.filter(notes__icontains="RESTOCK ALERT").count()
            latest_alert = (
                forecasts
                .filter(notes__icontains="RESTOCK ALERT")
                .order_by("-forecast_date")
                .values_list("notes", flat=True)
                .first()
            )

            results.append({
                "product":          product,
                "current_stock":    product.stock_quantity,
                "total_forecasted": total_forecasted,
                "avg_daily":        round(avg_daily, 1),
                "alert_count":      alert_count,
                "latest_alert":     latest_alert,
                "has_alerts":       alert_count > 0,
                "row_class":        "alert-row" if alert_count > 0 else "",
            })

        results.sort(key=lambda x: x["has_alerts"], reverse=True)
        forecast_summary = request.session.pop("forecast_summary", None)

        context = {
            "results":          results,
            "forecast_summary": forecast_summary,
            "total_alerts":     sum(r["alert_count"] for r in results),
            "last_forecast":    DemandForecast.objects.aggregate(
                                    m=Max("forecast_date"))["m"],
        }

        return render(request, "core/view_forecast_results.html", context)

    except Exception as e:
        # Log the actual error
        import traceback
        print("FORECAST RESULTS ERROR:", traceback.format_exc())
        return render(request, "core/view_forecast_results.html", {
            "error": True,
            "error_message": str(e),
            "results": [],
            "total_alerts": 0,
        })