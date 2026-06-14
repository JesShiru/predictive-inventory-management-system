from django.contrib import admin
from .models import Product, Category, Sale, StockMovement, DemandForecast



# Register the others simply
admin.site.register(Category)
admin.site.register(Product)
admin.site.register(Sale)
admin.site.register(StockMovement)
admin.site.register(DemandForecast)

