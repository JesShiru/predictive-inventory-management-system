"""
Shefa Dairies — LSTM Demand Forecasting Engine
===============================================
Trains an LSTM per Yoghurt product and saves predictions
into the DemandForecast model.
"""

import os
import django
import numpy as np
import pandas as pd
from datetime import timedelta
from django.db.models import Sum


os.environ.setdefault(
    'DJANGO_SETTINGS_MODULE',
    'predictive_inventory_management_system.settings'
)
if not django.conf.settings.configured:
    django.setup()

from sklearn.preprocessing import MinMaxScaler
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout, Input
from tensorflow.keras.callbacks import EarlyStopping

from inventory.models import Sale, Product, DemandForecast


# ── CONFIG ────────────────────────────────────────────────────
WINDOW_SIZE   = 30       # days of history per input sequence
EPOCHS        = 50
BATCH_SIZE    = 16
LSTM_UNITS    = 64
HORIZONS      = {
    "3_months":  90,
    "6_months": 180,
    "1_year":   365,
}
SAFETY_FACTOR = 1.5      # multiplier on std dev for safety stock


# load the data
def load_product_sales(product: Product) -> pd.DataFrame:
    qs = (
        Sale.objects
        .filter(product=product)
        .values("date")
        .annotate(qty=Sum("quantity_sold"))
        .order_by("date")
    )

    if not qs.exists():
        return pd.DataFrame()

    df = pd.DataFrame(list(qs))
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").asfreq("D", fill_value=0).reset_index()
    return df


# sequence builder
def make_sequences(scaled: np.ndarray, window: int):
    X, y = [], []
    for i in range(len(scaled) - window):
        X.append(scaled[i : i + window])
        y.append(scaled[i + window])
    return np.array(X), np.array(y)


# build LSTM model
def build_model(window: int) -> Sequential:
    model = Sequential([
        Input(shape=(window, 1)),
        LSTM(LSTM_UNITS, return_sequences=True),
        Dropout(0.2),
        LSTM(LSTM_UNITS // 2, return_sequences=False),
        Dropout(0.2),
        Dense(1),
    ])
    model.compile(optimizer="adam", loss="mse")
    return model


# multi-step forecasting
def forecast_steps(model, last_window: np.ndarray,
                   scaler: MinMaxScaler, steps: int) -> list:
    """
    Iteratively predicts `steps` days into the future.
    Each prediction is fed back as input for the next step.
    """
    predictions = []
    current     = last_window.copy()   # shape: (window, 1)

    for _ in range(steps):
        inp  = current.reshape(1, WINDOW_SIZE, 1)
        pred = model.predict(inp, verbose=0)[0][0]
        predictions.append(pred)
        current = np.append(current[1:], [[pred]], axis=0)

    # Inverse transform
    return scaler.inverse_transform(
        np.array(predictions).reshape(-1, 1)
    ).flatten().tolist()

# check restock
def check_restock(product: Product, forecasted_qty: float,
                  std_dev: float, horizon_days: int) -> str:
    
    safety_stock  = SAFETY_FACTOR * std_dev * (horizon_days ** 0.5)
    current_stock = product.stock_quantity
    
    # Project how long stock lasts at this daily rate
    days_of_stock = current_stock / forecasted_qty if forecasted_qty > 0 else float('inf')
    
    if days_of_stock < horizon_days:
        shortfall = (forecasted_qty * horizon_days) - current_stock
        return (
            f"RESTOCK ALERT: Stock covers only {days_of_stock:.0f} days "
            f"but forecast horizon is {horizon_days} days. "
            f"Estimated shortfall: {shortfall:.0f} units. "
            f"Safety stock: {safety_stock:.0f} units."
        )
    return f"OK: Stock sufficient for {days_of_stock:.0f} days. Safety buffer: {safety_stock:.0f} units."


# save forecasts
def save_forecasts(product: Product, horizon_label: str,
                   predictions: list, start_date, std_dev: float):
    
    horizon_days = len(predictions)  # ← derive from predictions length
    end_date = start_date + timedelta(days=horizon_days)
    
    DemandForecast.objects.filter(
        product=product,
        forecast_date__gte=start_date,
        forecast_date__lte=end_date,
    ).delete()

    records = []
    for i, qty in enumerate(predictions):
        qty        = max(0, round(qty))
        fdate      = start_date + timedelta(days=i + 1)
        alert_note = check_restock(product, qty, std_dev, horizon_days)  # ← pass horizon_days

        records.append(DemandForecast(
            product             = product,
            forecasted_quantity = qty,
            forecast_date       = fdate,
            notes               = f"[{horizon_label}] {alert_note}",
        ))

    DemandForecast.objects.bulk_create(records)
    return len(records)


# run forecast
def run_forecast() -> dict:
    """
    Called by the Django view. Trains LSTM per Yoghurt product
    and saves all forecasts. Returns a summary dict.
    """
    from django.db.models import Sum

    yoghurt_products = Product.objects.filter(
        category__name="Yoghurt"
    )

    summary = {
        "products_processed": 0,
        "total_records":      0,
        "alerts":             [],
        "skipped":            [],
    }

    for product in yoghurt_products:
        df = load_product_sales(product)

        # Need at least WINDOW_SIZE + 1 days of data
        if df.empty or len(df) < WINDOW_SIZE + 1:
            summary["skipped"].append(
                f"{product.name} (insufficient data: {len(df)} days)"
            )
            continue

        # ── Scale ──
        values = df["qty"].values.reshape(-1, 1).astype(float)
        scaler = MinMaxScaler()
        scaled = scaler.fit_transform(values)
        std_dev = float(df["qty"].std())

        # ── Sequences ──
        X, y = make_sequences(scaled, WINDOW_SIZE)
        if len(X) == 0:
            summary["skipped"].append(f"{product.name} (no sequences)")
            continue

        X = X.reshape((X.shape[0], X.shape[1], 1))

        # ── Train ──
        model = build_model(WINDOW_SIZE)
        model.fit(
            X, y,
            epochs    = EPOCHS,
            batch_size= BATCH_SIZE,
            validation_split=0.1,
            verbose   = 0,
            callbacks = [EarlyStopping(patience=5, monitor="val_loss",
                                       restore_best_weights=True)],
        )

        # ── Forecast each horizon ──
        last_window = scaled[-WINDOW_SIZE:].reshape(WINDOW_SIZE, 1)
        last_date   = df["date"].iloc[-1]

        for label, days in HORIZONS.items():
            preds = forecast_steps(model, last_window, scaler, days)
            n     = save_forecasts(
                product, label, preds, last_date, std_dev
            )
            summary["total_records"] += n

            # Collect alerts
            alerts_in_horizon = DemandForecast.objects.filter(
                product      = product,
                notes__icontains = "RESTOCK ALERT",
                forecast_date__gte = last_date,
            ).count()

            if alerts_in_horizon:
                summary["alerts"].append(
                    f"{product.name} ({label}): "
                    f"{alerts_in_horizon} alert days"
                )

        summary["products_processed"] += 1

    return summary