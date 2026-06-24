from django.db import models
from datetime import date
from accounts.models import User

# Category
class Category(models.Model):
    name = models.CharField(max_length=100)  

    class Meta:
        verbose_name_plural = "Categories"

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
    stock_location = models.CharField(max_length=20, choices=LOCATION_CHOICES)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    stock_quantity = models.IntegerField(default=0)
    reorder_level = models.IntegerField(default=0)
    expiry_date = models.DateField(blank=True, null=True)
    date_of_last_restocking = models.DateField(blank=True, null=True)

    @property
    def total_value(self):
        return self.stock_quantity * self.unit_price

    @property
    def reorder_status(self):
        if self.stock_quantity <= self.reorder_level:
            return 'RESTOCK'
        return 'OK'
    
    # models.py
    @property
    def expiry_color(self):
        from datetime import date
        if self.expiry_date and self.expiry_date <= date.today():
            return "#dc2626"  # red — expired today or past
        return "#d97706"      # amber — expiring soon

    def __str__(self):
        return self.name

# Stock movement
class StockMovement(models.Model):
    MOVEMENT_TYPES = [
        ('IN', 'Stock In'),
        ('OUT', 'Stock Out'),
    ]
    ACTION_CHOICES = [
        ('SALE',       'Sale'),
        ('RESTOCK',    'Restock'),
        ('ADJUSTMENT', 'Manual Adjustment'),
        ('DELETE',     'Product Deleted'),
    ]
    
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    movement_type = models.CharField(max_length=3, choices=MOVEMENT_TYPES)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES, default='SALE')
    quantity = models.IntegerField()
    user = models.ForeignKey("accounts.User", on_delete=models.PROTECT)
    note = models.TextField(blank=True, null=True)
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f"{self.movement_type} - {self.product.name} ({self.quantity}) by {self.user or 'System'}"


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


# Demand forecast
class DemandForecast(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    forecasted_quantity = models.IntegerField()
    forecast_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Forecast - {self.product.name} | {self.forecast_date}"
    


