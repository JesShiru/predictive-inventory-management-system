from django.contrib import admin
from .models import Product, Category, Supplier, Sale, StockMovement, DemandForecast, Order, OrderItem

from django.contrib import admin
from .models import Product, Category, Supplier


# Register the others simply
admin.site.register(Category)
admin.site.register(Supplier)
admin.site.register(Product)
admin.site.register(Sale)
admin.site.register(StockMovement)
admin.site.register(DemandForecast)
admin.site.register(Order)
admin.site.register(OrderItem)
