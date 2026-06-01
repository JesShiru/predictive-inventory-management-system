from django.db import models
from datetime import date

# Category
class Category(models.Model):
    name = models.CharField(max_length=100)  

    class Meta:
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.name
    
# Supplier
class Supplier(models.Model):
    name = models.CharField(max_length=255)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


# Product
class Product(models.Model):
    LOCATION_CHOICES = [
        ('COLD ROOM', 'Cold Room'),
        ('STORE', 'Store'),
    ]

    item_no = models.CharField(max_length=50, unique=True, blank=True, null=True)
    name = models.CharField(max_length=255)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True)
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True)
    stock_location = models.CharField(max_length=20, choices=LOCATION_CHOICES)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    stock_quantity = models.IntegerField(default=0)
    packing_as_per_plan = models.IntegerField(blank=True, null=True)  
    reorder_level = models.IntegerField(default=0)
    date_of_last_restocking = models.DateField(blank=True, null=True)

    @property
    def total_value(self):
        return self.stock_quantity * self.unit_price

    @property
    def reorder_status(self):
        if self.stock_quantity <= self.reorder_level:
            return 'RESTOCK'
        return 'OK'

    def __str__(self):
        return self.name

# Stock movement
class StockMovement(models.Model):
    MOVEMENT_TYPES = [
        ('IN', 'Stock In'),
        ('OUT', 'Stock Out'),
    ]
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    movement_type = models.CharField(max_length=3, choices=MOVEMENT_TYPES)
    quantity = models.IntegerField()
    note = models.TextField(blank=True, null=True)
    date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.movement_type} - {self.product.name} ({self.quantity})"


# Sales
class Sale(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity_sold = models.IntegerField()
    sale_price = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateField(default=date.today)

    @property
    def total_sale_value(self):
        return self.quantity_sold * self.sale_price

    def __str__(self):
        return f"Sale - {self.product.name} x{self.quantity_sold}"


# Orders 
class Order(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('RECEIVED', 'Received'),
        ('CANCELLED', 'Cancelled'),
    ]
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    note = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Order #{self.id} - {self.status}"


# Order items
class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.IntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    @property
    def total_cost(self):
        return self.quantity * self.unit_price

    def __str__(self):
        return f"{self.product.name} x{self.quantity}"


# Demand forecast
class DemandForecast(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    forecasted_quantity = models.IntegerField()
    forecast_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Forecast - {self.product.name} | {self.forecast_date}"
    


