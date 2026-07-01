import pandas as pd
import os
import django
from decimal import Decimal
from datetime import datetime

# 1. Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'predictive_inventory_management_system.settings')
django.setup()

from inventory.models import Product, Category 

import re

def clean_decimal(value):
    if pd.isna(value) or value == "" or str(value).strip() == "-":
        return Decimal('0.00')
    
    clean_str = re.sub(r'[^\d.]', '', str(value))
    
    try:
        return Decimal(clean_str)
    except Exception as e:
        print(f"Skipping price for value '{value}': {e}")
        return Decimal('0.00')

def clean_int(value):
    if pd.isna(value) or value == "":
        return 0
    try:
        return int(float(value))
    except:
        return 0

def clean_date(value):
    if pd.isna(value) or value == "":
        return None
    try:
        
        return datetime.strptime(str(value), '%d/%m/%Y').date()
    except ValueError:
        return None

def import_inventory(file_path, category_name):
    df = pd.read_csv(file_path)
    
    # Ensure the Category exists
    category_obj, _ = Category.objects.get_or_create(name=category_name)
    
    for _, row in df.iterrows():
        raw_item_no = row.get('ITEM NO.')
        item_name = row.get('ITEM NAME')

        # check to ensure item_name isn't empty/NaN
        if pd.isna(item_name):
            print("Skipping a row with a missing Item Name.")
            continue 


        item_name = str(item_name).strip()

        if not raw_item_no:
            raw_item_no = item_name.replace(" ", "-")[:50]

        # Stock Location normalization
        raw_location = str(row.get('STOCK LOCATION', '')).upper()
        location = 'COLD ROOM' if 'COLD' in raw_location else 'STORE'

        Product.objects.update_or_create(
            item_no=raw_item_no,
            defaults={
                'name': item_name,
                'category': category_obj,
                'stock_location': location,
                'unit_price': clean_decimal(row.get('COST PER ITEM(EX-FACTORY)') or row.get('UNIT PRICE')),
        
                'stock_quantity': clean_int(row.get('STOCK QUANTITY')),
                'reorder_level': clean_int(row.get('REORDER LEVEL')),
            
                'date_of_last_restocking': clean_date(row.get('DATE OF LAST RESTOCKING') or row.get('DATE OF LAST STOCK TAKING')),
            }
        )
    print(f"Successfully imported {category_name} items.")

if __name__ == "__main__":
    import_inventory('yoghurt.csv', 'Yoghurt')
    import_inventory('raw_materials.csv', 'Raw Materials')
