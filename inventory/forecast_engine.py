"""
Shefa Dairies — LSTM Demand Forecasting Pipeline

Flow
----
  load_product_sales()        →  raw daily DataFrame from the ORM
  build_features()            →  add calendar + cost columns
  split_and_scale()           →  chronological train/val/test, fit scaler on train only
  make_sequences()            →  sliding-window (X, y) pairs for the LSTM
  build_model()               →  stacked LSTM with Dropout
  train_model()               →  fit with EarlyStopping, return history + metrics
  rollout_forecast()          →  iterative multi-step prediction
  save_forecasts_to_db()      →  bulk-write DemandForecast rows
  run_forecast_for_product()  →  end-to-end for one SKU
"""

from __future__ import annotations

import logging
import pickle
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from django.db.models import Avg, Sum
from sklearn.preprocessing import MinMaxScaler
from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau
from tensorflow.keras.layers import Dense, Dropout, Input, LSTM
from tensorflow.keras.models import Sequential, load_model
from tensorflow.keras.optimizers import Adam

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# CONFIG  — every tunable value in one place
# ─────────────────────────────────────────────────────────────────────────────

WINDOW_SIZE       = 30      # days of history per input sequence
MIN_TRAINING_DAYS = 60      # minimum days of data required to train
TRAIN_RATIO       = 0.70    # chronological split ratios
VAL_RATIO         = 0.15    # test = remaining 0.15
LSTM_UNITS_1      = 64      # first LSTM layer
LSTM_UNITS_2      = 32      # second LSTM layer
DROPOUT_RATE      = 0.2
LEARNING_RATE     = 1e-3
EPOCHS            = 100
BATCH_SIZE        = 16
PATIENCE          = 10      # EarlyStopping patience

# Forecast horizons (label → days)
HORIZONS = {
    "7_days":    7,
    "14_days":  14,
    "30_days":  30,
    "3_months": 90,
}

# Feature columns fed into the LSTM (order matters — scaler uses this order)
FEATURE_COLS = ["qty", "price", "unit_cost", "day_of_week", "month", "is_weekend"]
TARGET_COL   = "qty"        # column we are forecasting

# Where to save trained models and scalers
MODELS_DIR = Path("saved_models")
MODELS_DIR.mkdir(exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — Load sales data from Django ORM
# ─────────────────────────────────────────────────────────────────────────────

def load_product_sales(product) -> pd.DataFrame:
    """
    Query Sale records for one product and return a gap-free daily DataFrame.

    Columns returned: date, qty, price, unit_cost

    Missing dates (days with no sales) are filled:
      qty       → 0        (no sales that day)
      price     → forward-fill from last known sale price
      unit_cost → constant from Product.unit_price
    """
    qs = (
        product.sale_set
        .values("date")
        .annotate(qty=Sum("quantity_sold"), price=Avg("sale_price"))
        .order_by("date")
    )

    if not qs.exists():
        return pd.DataFrame()

    df = pd.DataFrame(list(qs))
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")

    # Fill the date gaps so the time series is continuous
    full_range = pd.date_range(df.index.min(), df.index.max(), freq="D")
    df = df.reindex(full_range)
    df.index.name = "date"

    df["qty"]       = df["qty"].fillna(0).astype(float)
    df["price"]     = df["price"].ffill().bfill()
    df["unit_cost"] = float(product.unit_price)

    return df.reset_index()


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — Feature engineering
# ─────────────────────────────────────────────────────────────────────────────

def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add calendar features to the DataFrame, then return only FEATURE_COLS.

    """
    df = df.copy()
    df["day_of_week"] = df["date"].dt.dayofweek.astype(float)   # 0=Mon … 6=Sun
    df["month"]       = df["date"].dt.month.astype(float)        # 1–12
    df["is_weekend"]  = (df["date"].dt.dayofweek >= 5).astype(float)
    return df[FEATURE_COLS].copy()


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — Chronological train / val / test split + scaling
# ─────────────────────────────────────────────────────────────────────────────

def split_and_scale(feature_df: pd.DataFrame):
    """
    Split the feature matrix chronologically (no shuffle, no leakage) and
    fit a MinMaxScaler on the training portion only.

    Returns: train_scaled, val_scaled, test_scaled, scaler
    """
    n         = len(feature_df)
    train_end = int(n * TRAIN_RATIO)
    val_end   = int(n * (TRAIN_RATIO + VAL_RATIO))

    train = feature_df.iloc[:train_end].values
    val   = feature_df.iloc[train_end:val_end].values
    test  = feature_df.iloc[val_end:].values

    # Fit ONLY on training data — applying the same scaler to val/test
    # without refitting is the key guard against data leakage.
    scaler        = MinMaxScaler()
    train_scaled  = scaler.fit_transform(train)
    val_scaled    = scaler.transform(val)
    test_scaled   = scaler.transform(test)

    logger.info("Split — train: %d | val: %d | test: %d rows", len(train), len(val), len(test))
    return train_scaled, val_scaled, test_scaled, scaler


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 — Sliding-window sequence builder
# ─────────────────────────────────────────────────────────────────────────────

def make_sequences(scaled: np.ndarray):
    """
    Slide a window of WINDOW_SIZE over the scaled array to create (X, y) pairs.

    X shape: (samples, WINDOW_SIZE, n_features)
    y shape: (samples,)  — the scaled qty value one step ahead
    """
    qty_idx = FEATURE_COLS.index(TARGET_COL)
    X, y = [], []

    for i in range(len(scaled) - WINDOW_SIZE):
        X.append(scaled[i : i + WINDOW_SIZE, :])       # all features as input
        y.append(scaled[i + WINDOW_SIZE, qty_idx])      # predict qty only

    return np.array(X, dtype=np.float32), np.array(y, dtype=np.float32)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 5 — LSTM model
# ─────────────────────────────────────────────────────────────────────────────

def build_model() -> Sequential:
    """
    Stacked LSTM with Dropout regularisation.

    Layer 1: LSTM(64, return_sequences=True)  — passes sequences to layer 2
    Layer 2: LSTM(32)                         — collapses to a single vector
    Output:  Dense(1)                         — one-step-ahead qty prediction
    """
    model = Sequential([
        Input(shape=(WINDOW_SIZE, len(FEATURE_COLS))),
        LSTM(LSTM_UNITS_1, return_sequences=True),
        Dropout(DROPOUT_RATE),
        LSTM(LSTM_UNITS_2, return_sequences=False),
        Dropout(DROPOUT_RATE),
        Dense(1),
    ], name="shefa_lstm")

    model.compile(optimizer=Adam(LEARNING_RATE), loss="mse", metrics=["mae"])
    return model


# ─────────────────────────────────────────────────────────────────────────────
# STEP 6 — Training
# ─────────────────────────────────────────────────────────────────────────────

def train_model(model, X_train, y_train, X_val, y_val):
    """
    Fit the model with EarlyStopping and ReduceLROnPlateau callbacks.

    EarlyStopping monitors val_loss and restores the best weights — the model
    never overfits past its optimal point even if EPOCHS is set high.
    """
    callbacks = [
        EarlyStopping(
            monitor="val_loss",
            patience=PATIENCE,
            min_delta=1e-4,
            restore_best_weights=True,
            verbose=1,
        ),
        ReduceLROnPlateau(
            monitor="val_loss",
            factor=0.5,
            patience=5,
            min_lr=1e-6,
            verbose=1,
        ),
    ]

    history = model.fit(
        X_train, y_train,
        validation_data=(X_val, y_val),
        epochs=EPOCHS,
        batch_size=BATCH_SIZE,
        callbacks=callbacks,
        verbose=0,
    )

    logger.info(
        "Training complete. Epochs run: %d. Best val_loss: %.6f",
        len(history.history["val_loss"]),
        min(history.history["val_loss"]),
    )
    return history


# ─────────────────────────────────────────────────────────────────────────────
# STEP 7 — Evaluation metrics
# ─────────────────────────────────────────────────────────────────────────────

def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    """
    Compute RMSE, MAE, and MAPE on raw (un-scaled) values.

    All three metrics are in the same units as qty (units of yoghurt),
    except MAPE which is a percentage.
    """
    y_true = y_true.flatten()
    y_pred = np.clip(y_pred.flatten(), 0, None)

    rmse = float(np.sqrt(np.mean((y_true - y_pred) ** 2)))
    mae  = float(np.mean(np.abs(y_true - y_pred)))
    mape = float(np.mean(np.abs((y_true - y_pred) / (np.abs(y_true) + 1e-8))) * 100)

    return {"rmse": rmse, "mae": mae, "mape": mape}


def evaluate_on_test(model, X_test, y_test, scaler) -> dict:
    """Predict on the held-out test set and return metrics in original units."""
    if len(X_test) == 0:
        return {"rmse": 0.0, "mae": 0.0, "mape": 0.0}

    qty_idx       = FEATURE_COLS.index(TARGET_COL)
    y_pred_scaled = model.predict(X_test, verbose=0).flatten()

    # Inverse-scale: reconstruct a full-width dummy array, insert qty, invert
    def inverse_qty(scaled_vals):
        dummy = np.zeros((len(scaled_vals), len(FEATURE_COLS)))
        dummy[:, qty_idx] = scaled_vals
        return scaler.inverse_transform(dummy)[:, qty_idx]

    y_true = inverse_qty(y_test)
    y_pred = inverse_qty(y_pred_scaled)

    return compute_metrics(y_true, y_pred)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 8 — Multi-step forecast rollout
# ─────────────────────────────────────────────────────────────────────────────

def rollout_forecast(model, seed_window: np.ndarray, scaler, steps: int,
                     last_date: pd.Timestamp) -> list[float]:
    """
    Iteratively predict `steps` days into the future.

    Each predicted qty is fed back as the qty input for the next step.
    Calendar features are computed from the actual future date (safe — deterministic).
    Price, unit_cost are held constant at their last known values.

    Returns a list of raw (un-scaled) daily demand predictions.
    """
    qty_idx     = FEATURE_COLS.index(TARGET_COL)
    current_win = seed_window.copy()    # shape: (WINDOW_SIZE, n_features)
    scaled_preds = []

    for step in range(steps):
        inp  = current_win.reshape(1, WINDOW_SIZE, len(FEATURE_COLS))
        pred = float(model.predict(inp, verbose=0)[0, 0])
        scaled_preds.append(pred)

        # Build the next row: update qty prediction + recalculate calendar features
        next_row          = current_win[-1].copy()
        next_row[qty_idx] = pred

        future_date = last_date + timedelta(days=step + 1)
        for col, val in [
            ("day_of_week", float(future_date.dayofweek)),
            ("month",       float(future_date.month)),
            ("is_weekend",  float(future_date.dayofweek >= 5)),
        ]:
            if col in FEATURE_COLS:
                idx     = FEATURE_COLS.index(col)
                col_min = scaler.data_min_[idx]
                col_max = scaler.data_max_[idx]
                denom   = col_max - col_min if col_max != col_min else 1.0
                next_row[idx] = (val - col_min) / denom

        current_win = np.vstack([current_win[1:], next_row])

    # Inverse-scale the predicted qty values back to real units
    qty_idx    = FEATURE_COLS.index(TARGET_COL)
    dummy      = np.zeros((len(scaled_preds), len(FEATURE_COLS)))
    dummy[:, qty_idx] = scaled_preds
    raw_preds  = scaler.inverse_transform(dummy)[:, qty_idx]

    return np.clip(raw_preds, 0, None).tolist()


# ─────────────────────────────────────────────────────────────────────────────
# STEP 9 — Save forecasts to DemandForecast model
# ─────────────────────────────────────────────────────────────────────────────

def save_forecasts_to_db(product, predictions: list, start_date) -> int:
    """
    Save a full forecast to the database.

    Deletes all existing future forecasts for the product, then inserts one
    row per predicted day. The notes field indicates the shortest forecast
    horizon the day belongs to.

    Returns the number of rows written.
    """
    from inventory.models import DemandForecast

    # Delete all existing future forecasts
    DemandForecast.objects.filter(
        product=product,
        forecast_date__gt=start_date,
    ).delete()

    records = []

    for i, qty in enumerate(predictions):
        day_number = i + 1

        if day_number <= 7:
            label = "7_days"
        elif day_number <= 14:
            label = "14_days"
        elif day_number <= 30:
            label = "30_days"
        else:
            label = "3_months"

        records.append(
            DemandForecast(
                product=product,
                forecasted_quantity=max(0, round(qty)),
                forecast_date=start_date + timedelta(days=day_number),
                notes=label,
            )
        )

    DemandForecast.objects.bulk_create(records)

    return len(records)

# ─────────────────────────────────────────────────────────────────────────────
# STEP 11 — Model + scaler persistence
# ─────────────────────────────────────────────────────────────────────────────

def _model_dir(product_name: str) -> Path:
    slug = product_name.lower().replace(" ", "_").replace("/", "-")
    d    = MODELS_DIR / slug
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_model_artifacts(model, scaler, product_name: str):
    d = _model_dir(product_name)
    model.save(d / "model.keras")
    with open(d / "scaler.pkl", "wb") as f:
        pickle.dump(scaler, f)
    logger.info("Saved model and scaler for '%s'.", product_name)


def load_model_artifacts(product_name: str):
    d           = _model_dir(product_name)
    model_path  = d / "model.keras"
    scaler_path = d / "scaler.pkl"
    if not model_path.exists():
        raise FileNotFoundError(f"No saved model for '{product_name}'. Train first.")
    model = load_model(model_path)
    with open(scaler_path, "rb") as f:
        scaler = pickle.load(f)
    return model, scaler


# ─────────────────────────────────────────────────────────────────────────────
# MAIN ENTRY POINT — full pipeline for one product
# ─────────────────────────────────────────────────────────────────────────────

def run_forecast_for_product(product, force_retrain: bool = False) -> dict:
    """
    End-to-end pipeline for a single yoghurt SKU.

    Steps:  load → features → split+scale → sequences →
            train → evaluate → forecast → save to DB

    Returns a summary dict with metrics, record count, and any alerts.
    """
    result = {"product": product.name, "records": 0, "metrics": {}, "error": None}

    # ── Load raw data ─────────────────────────────────────────────────────────
    raw_df = load_product_sales(product)

    if raw_df.empty or len(raw_df) < MIN_TRAINING_DAYS:
        result["error"] = f"Only {len(raw_df)} days of data (need {MIN_TRAINING_DAYS})."
        logger.warning("Skipping '%s': %s", product.name, result["error"])
        return result

    last_date  = pd.Timestamp(raw_df["date"].iloc[-1])

    # ── Features, split, scale ────────────────────────────────────────────────
    feature_df                              = build_features(raw_df)
    train_sc, val_sc, test_sc, scaler       = split_and_scale(feature_df)
    X_train, y_train                        = make_sequences(train_sc)
    X_val,   y_val                          = make_sequences(val_sc)
    X_test,  y_test                         = make_sequences(test_sc)

    if len(X_train) == 0:
        result["error"] = "Not enough rows to form training sequences."
        return result

    # ── Train (or reload cached model) ────────────────────────────────────────
    if not force_retrain:
        try:
            model, scaler = load_model_artifacts(product.name)
            logger.info("Loaded cached model for '%s'.", product.name)
        except FileNotFoundError:
            force_retrain = True   # no cache — fall through to training

    if force_retrain:
        model = build_model()
        train_model(model, X_train, y_train, X_val, y_val)
        save_model_artifacts(model, scaler, product.name)

    # ── Evaluate on held-out test set ─────────────────────────────────────────
    result["metrics"] = evaluate_on_test(model, X_test, y_test, scaler)
    logger.info(
        "'%s' — RMSE: %.2f | MAE: %.2f | MAPE: %.2f%%",
        product.name, result["metrics"]["rmse"],
        result["metrics"]["mae"], result["metrics"]["mape"],
    )

    # ── Build seed window from most recent WINDOW_SIZE days ───────────────────
    seed_window = scaler.transform(feature_df.iloc[-WINDOW_SIZE:].values)

    # ── Forecast each horizon and save to DB ──────────────────────────────────
    MAX_DAYS = 90
    predictions = rollout_forecast(model, seed_window, scaler, MAX_DAYS, last_date)

    MAX_DAYS = max(HORIZONS.values())

    predictions = rollout_forecast(
        model=model,
        seed_window=seed_window,
        scaler=scaler,
        steps=MAX_DAYS,
        last_date=last_date,
    )

    result["records"] = save_forecasts_to_db(
        product=product,
        predictions=predictions,
        start_date=last_date,
    )

    return result