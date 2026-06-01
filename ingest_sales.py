import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'predictive_inventory_management_system.settings')
django.setup()


import pandas as pd
from django.core.management.base import BaseCommand
from inventory.models import Sale, Product
from datetime import datetime

class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        df = pd.read_csv("sales_data.csv")
        df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

        created_count = 0

        for _, row in df.iterrows():
            # Look up or create the Product by name
            product, _ = Product.objects.get_or_create(
                name=row["product_name"],
            )

            Sale.objects.create(
                product=product,
                quantity_sold=int(row["quantity"]),
                sale_price=float(row["unit_cost"]),
                date=datetime.strptime(row["date"], "%m/%d/%Y").date(),
            )
            created_count += 1

        self.stdout.write(f"Loaded {created_count} sale records.")