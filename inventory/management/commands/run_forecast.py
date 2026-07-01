"""
inventory/management/commands/run_forecast.py

Run the forecast pipeline directly from the terminal.
Useful during development.

Usage
-----
  python manage.py run_forecast              # inference only (load saved models)
  python manage.py run_forecast --retrain    # retrain every SKU from scratch
"""

import time
from django.core.management.base import BaseCommand
from inventory.forecast_engine import run_forecast_for_product
from inventory.models import Product


class Command(BaseCommand):
    help = "Run the Shefa Dairies LSTM demand forecasting pipeline."

    def add_arguments(self, parser):
        parser.add_argument(
            "--retrain", action="store_true", default=False,
            help="Force a full retrain instead of loading cached models.",
        )

    def handle(self, *args, **options):
        force_retrain = options["retrain"]
        products      = Product.objects.filter(category__name="Yoghurt")

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\nShefa Dairies — LSTM Forecast "
            f"({'retrain' if force_retrain else 'inference'})\n"
            f"{'─' * 55}"
        ))

        total_records = 0
        start         = time.time()

        for product in products:
            self.stdout.write(f"  {product.name:<40}", ending="")
            result = run_forecast_for_product(product, force_retrain=force_retrain)

            if result["error"]:
                self.stdout.write(self.style.WARNING(f"SKIPPED — {result['error']}"))
                continue

            m = result["metrics"]
            self.stdout.write(self.style.SUCCESS(
                f"OK  RMSE={m['rmse']:.1f}  MAE={m['mae']:.1f}  "
                f"MAPE={m['mape']:.1f}%  rows={result['records']}"
            ))

            total_records += result["records"]

        self.stdout.write(
            f"\n{'─' * 55}\n"
            f"  Done in {time.time() - start:.1f}s — {total_records} forecast rows written.\n"
        )