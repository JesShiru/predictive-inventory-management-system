import os
import django
import pandas as pd
from datetime import datetime

os.environ.setdefault(
    'DJANGO_SETTINGS_MODULE',
    'predictive_inventory_management_system.settings'
)
django.setup()

from inventory.models import Sale, Product


def import_sales():
    df = pd.read_csv("sales_data.csv")
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    created_count = 0

    for _, row in df.iterrows():
        try:
            product = Product.objects.get(name=row["product_name"])
        except Product.DoesNotExist:
            print(f"Product '{row['product_name']}' not found. Skipping.")
            continue

        Sale.objects.create(
            product=product,
            quantity_sold=int(row["quantity"]),
            sale_price=float(row["unit_cost"]),
            date=datetime.strptime(row["date"], "%m/%d/%Y").date(),
        )

        created_count += 1

    print(f"Loaded {created_count} sale records.")


if __name__ == "__main__":
    import_sales()