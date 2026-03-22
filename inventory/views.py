from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required 
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from django.contrib import messages
from django.views import View
from django.db.models import Sum
from django.utils import timezone
from datetime import timedelta
from django.db import transaction
import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from .models import Product, Sale, StockMovement, Order
from .forms import ProductForm, SaleForm, RegisterForm

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
        .values('date__date')
        .annotate(total=Sum('quantity_sold'))
        .order_by('date__date')
    )

    
    sales_labels = [str(s['date__date']) for s in daily_sales]
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

    # Filters
    category = request.GET.get('category')
    location = request.GET.get('location')
    status   = request.GET.get('status')

    if category:
        products = products.filter(category__name=category)
    if location:
        products = products.filter(stock_location=location)
    if status == 'low':
        products = products.filter(stock_quantity__gt=0, stock_quantity__lte=F('reorder_level'))
    elif status == 'out':
        products = products.filter(stock_quantity=0)

    # Summary counts (on unfiltered queryset)
    all_products = Product.objects.all()
    total_products   = all_products.count()
    low_stock_count  = all_products.filter(stock_quantity__gt=0, stock_quantity__lte=F('reorder_level')).count()
    out_of_stock_count = all_products.filter(stock_quantity=0).count()

    return render(request, 'core/product_list.html', {
        'products': products,
        'total_products': total_products,
        'low_stock_count': low_stock_count,
        'out_of_stock_count': out_of_stock_count,
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

