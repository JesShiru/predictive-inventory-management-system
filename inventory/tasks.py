"""
inventory/tasks.py
==================
Celery tasks for the Shefa Dairies forecasting pipeline.

This file is intentionally thin — all the ML logic lives in forecasting.py.
These tasks are just the async wrappers that Django calls.

Quick start
-----------
  # Fire from a view or shell:
  from inventory.tasks import run_forecast_task
  run_forecast_task.delay()                       # all yoghurt SKUs
  run_forecast_task.delay(force_retrain=True)     # force a full retrain

  # Scheduled nightly retrain (add to settings.py):
  CELERY_BEAT_SCHEDULE = {
      'nightly-forecast': {
          'task': 'inventory.tasks.run_forecast_task',
          'schedule': crontab(hour=2, minute=0),
          'kwargs': {'force_retrain': True},
      },
  }
"""

import logging

from celery import shared_task
from inventory.forecasting import run_forecast_for_product
from inventory.models import Product

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="inventory.tasks.run_forecast_task",
             max_retries=3, default_retry_delay=60, acks_late=True)
def run_forecast_task(self, force_retrain: bool = False) -> dict:
    """
    Run the LSTM forecast pipeline for every Yoghurt product.

    Parameters
    ----------
    force_retrain : retrain the model even if a saved version already exists.

    Returns a summary dict the view layer can read from AsyncResult.
    """
    logger.info("run_forecast_task started (force_retrain=%s).", force_retrain)

    summary = {
        "products_processed": 0,
        "total_records":      0,
        "skipped":            [],
        "errors":             [],
        "metrics":            {},
    }

    products = Product.objects.filter(category__name="Yoghurt").select_related("category")

    if not products.exists():
        logger.warning("No Yoghurt products found.")
        return summary

    for product in products:
        try:
            result = run_forecast_for_product(product, force_retrain=force_retrain)

            if result["error"]:
                summary["skipped"].append(f"{product.name}: {result['error']}")
                continue

            summary["products_processed"] += 1
            summary["total_records"]      += result["records"]
            summary["metrics"][product.name] = result["metrics"]

            logger.info(
                "'%s' done — records: %d | RMSE: %.2f | MAE: %.2f | MAPE: %.2f%%",
                product.name, result["records"],
                result["metrics"]["rmse"],
                result["metrics"]["mae"],
                result["metrics"]["mape"],
            )

        except Exception as exc:
            logger.exception("Error processing '%s': %s", product.name, exc)
            summary["errors"].append(f"{product.name}: {exc}")
            try:
                raise self.retry(exc=exc)
            except self.MaxRetriesExceededError:
                pass

    logger.info(
        "run_forecast_task finished — products: %d | records: %d",
        summary["products_processed"], summary["total_records"],
    )
    return summary