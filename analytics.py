"""
Shefa Dairies — Sales Analytics Engine
=======================================
Reads from MySQL `sales_records` table and computes:
  - Summary statistics (mean, median, std of daily revenue)
  - Top-selling products by quantity
  - Daily sales trend (revenue per day)
  - 7-day subset analysis

"""
import pandas as pd
from sqlalchemy import create_engine, text
import django
import os
from django.conf import settings as django_settings

os.environ.setdefault(
    'DJANGO_SETTINGS_MODULE',
    'predictive_inventory_management_system.settings'  
)

# Only call setup() if Django isn't already configured
if not django.conf.settings.configured:
    django.setup()



def get_engine():
    from sqlalchemy.engine import URL

    db = django_settings.DATABASES['default']

    url = URL.create(
        drivername="mysql+pymysql",
        username=db['USER'],
        password=db['PASSWORD'],    
        host=db.get('HOST') or 'localhost',
        port=int(db.get('PORT') or 3306),
        database=db['NAME'],
    )
    return create_engine(url)

def load_dataframe(engine=None) -> pd.DataFrame:
    if engine is None:
        engine = get_engine()
    
    query = text("""
        SELECT 
            s.date,
            p.name                          AS product_name,
            s.quantity_sold                 AS quantity,
            s.sale_price                    AS unit_cost,
            s.quantity_sold * s.sale_price  AS total
        FROM inventory_sale s
        JOIN inventory_product p ON s.product_id = p.id
    """)
    
    df = pd.read_sql(query, engine, parse_dates=["date"])
    return df


# ── 1. SUMMARY STATISTICS ─────────────────────────────────────

def summary_statistics(df: pd.DataFrame) -> dict:
    """
    Groups by date first so we get one revenue figure per day.
    """
    daily = df.groupby("date")["total"].sum()

    return {
        "mean":   round(float(daily.mean()),   2),
        "min":    round(float(daily.min()),    2),
        "max":    round(float(daily.max()),    2),
        "total_revenue":    round(float(df["total"].sum()),    2),
        "total_quantity":   int(df["quantity"].sum()),
        "total_days":       int(daily.count()),
        "date_start":       str(df["date"].min().date()),
        "date_end":         str(df["date"].max().date()),
    }


# ── 2. TOP-SELLING PRODUCTS ───────────────────────────────────

def top_products(df: pd.DataFrame, n: int = 10) -> list[dict]:
    """
    Ranked list of products by total quantity sold.
    Returns a list of dicts for easy use in Django templates.
    """
    grouped = (
        df.groupby("product_name")
          .agg(
              total_quantity=("quantity", "sum"),
              total_revenue =("total",    "sum"),
              avg_unit_cost =("unit_cost","mean"),
          )
          .reset_index()
          .sort_values("total_quantity", ascending=False)
          .head(n)
    )
    grouped["rank"] = range(1, len(grouped) + 1)

    return [
        {
            "rank":           int(row["rank"]),
            "product_name":   row["product_name"],
            "total_quantity": int(row["total_quantity"]),
            "total_revenue":  round(float(row["total_revenue"]), 2),
            "avg_unit_cost":  round(float(row["avg_unit_cost"]), 2),
        }
        for _, row in grouped.iterrows()
    ]


# ── 3. DAILY SALES TREND ──────────────────────────────────────

def daily_trend(df: pd.DataFrame) -> list[dict]:
    """
    Time-series of total revenue and quantity per day.
    Returns list of dicts sorted by date ascending.
    """
    daily = (
        df.groupby("date")
          .agg(
              revenue  =("total",    "sum"),
              quantity =("quantity", "sum"),
          )
          .reset_index()
          .sort_values("date")
    )
    return [
        {
            "date":     str(row["date"].date()) if hasattr(row["date"], "date") else str(row["date"]),
            "revenue":  round(float(row["revenue"]),  2),
            "quantity": int(row["quantity"]),
        }
        for _, row in daily.iterrows()
    ]


# ── 4. LAST 7 DAYS ────────────────────────────────────────────

def last_7_days(df: pd.DataFrame) -> dict:
    """
    Isolates the most recent 7 days of data and returns:
      - per-day breakdown
      - summary stats for just that window
      - top products for just that window
    """
    latest_date = df["date"].max()
    cutoff      = latest_date - pd.Timedelta(days=6)   # 7 days inclusive
    subset      = df[df["date"] >= cutoff].copy()

    return {
        "date_start":    str(cutoff.date()),
        "date_end":      str(latest_date.date()),
        "total_revenue": round(float(subset["total"].sum()), 2),
        "total_qty":     int(subset["quantity"].sum()),
        "daily":         daily_trend(subset),
        "top_products":  top_products(subset, n=5),
        "summary":       summary_statistics(subset),
    }


# ── 5. 30-DAY TREND ────────────────────

def last_30_days_trend(df: pd.DataFrame) -> list[dict]:
    """
    Returns daily revenue for the last 30 days.
    """
    latest_date = df["date"].max()
    cutoff      = latest_date - pd.Timedelta(days=29)
    subset      = df[df["date"] >= cutoff]
    return daily_trend(subset)


# FULL REPORT 

def full_report(engine=None) -> dict:
    """
    Single function that returns everything needed for the
    sales report page and dashboard. Import this in your Django view.
    """
    df = load_dataframe(engine)
    if df.empty:
        return {"error": "No sales data found in the database."}

    return {
        "summary":      summary_statistics(df),
        "top_products": top_products(df),
        "daily_trend":  daily_trend(df),
        "last_7_days":  last_7_days(df),
        "last_30_days": last_30_days_trend(df),
    }


# ── 6. STOCK TURNOVER ─────────────────────────────────────────────
def stock_turnover(engine=None, start_date=None, end_date=None) -> list[dict]:
    if engine is None:
        engine = get_engine()

    # Build WHERE clause for the subquery
    date_conditions = ["1=1"]
    params = {}
    if start_date:
        date_conditions.append("date >= :start")
        params["start"] = str(start_date)
    if end_date:
        date_conditions.append("date <= :end")
        params["end"] = str(end_date)

    date_where = " AND ".join(date_conditions)

    query = text(f"""
        SELECT 
            p.name                              AS product_name,
            p.stock_quantity                    AS current_stock,
            COALESCE(sq.total_sold, 0)          AS total_sold,
            sq.first_sale                       AS first_sale,
            sq.last_sale                        AS last_sale
        FROM inventory_product p
        JOIN inventory_category c ON p.category_id = c.id
        LEFT JOIN (
            SELECT 
                product_id,
                SUM(quantity_sold)  AS total_sold,
                MIN(date)           AS first_sale,
                MAX(date)           AS last_sale
            FROM inventory_sale
            WHERE {date_where}
            GROUP BY product_id
        ) sq ON sq.product_id = p.id
        WHERE c.name = 'Yoghurt'
        ORDER BY total_sold DESC
    """)

    df = pd.read_sql(query, engine, params=params, parse_dates=["first_sale", "last_sale"])

    results = []
    for _, row in df.iterrows():
        current_stock = int(row["current_stock"])
        total_sold    = int(row["total_sold"])

        avg_stock     = (current_stock + total_sold) / 2
        turnover_rate = round(total_sold / avg_stock, 2) if avg_stock > 0 else 0

        if pd.notna(row["first_sale"]) and pd.notna(row["last_sale"]):
            total_days = (row["last_sale"] - row["first_sale"]).days or 1
            avg_daily  = round(total_sold / total_days, 2)
        else:
            avg_daily  = 0

        days_remaining = round(current_stock / avg_daily, 1) if avg_daily > 0 else None

        results.append({
            "product_name":    row["product_name"],
            "current_stock":   current_stock,
            "total_sold":      total_sold,
            "turnover_rate":   turnover_rate,
            "avg_daily_sales": avg_daily,
            "days_remaining":  days_remaining,
            "status":          _stock_status(days_remaining),
        })

    return results


def _stock_status(days_remaining) -> str:
    """Classify inventory health."""
    if days_remaining is None:
        return "no_sales"
    if days_remaining <= 3:
        return "critical"
    if days_remaining <= 7:
        return "low"
    if days_remaining <= 14:
        return "moderate"
    return "healthy"


# ── STANDALONE TERMINAL OUTPUT ────────────────────────────────

def print_report():
    print("\n" + "=" * 60)
    print("  SHEFA DAIRIES — SALES ANALYTICS REPORT")
    print("=" * 60)

    report = full_report()

    if "error" in report:
        print(f"\nERROR: {report['error']}")
        return

    s = report["summary"]
    print(f"\n📅 Period : {s['date_start']}  →  {s['date_end']}  ({s['total_days']} days)")
    print(f"   Total Revenue  : KES {s['total_revenue']:>12,.2f}")
    print(f"   Total Quantity : {s['total_quantity']:>12,} units")

    print("\n── DAILY REVENUE STATISTICS ──────────────────────────")
    print(f"   Mean   : KES {s['mean']:>10,.2f}")
    print(f"   Min    : KES {s['min']:>10,.2f}")
    print(f"   Max    : KES {s['max']:>10,.2f}")

    print("\n── TOP-SELLING PRODUCTS (by quantity) ───────────────")
    print(f"  {'#':<4} {'Product':<25} {'Qty':>8} {'Revenue':>14}")
    print(f"  {'-'*4} {'-'*25} {'-'*8} {'-'*14}")
    for p in report["top_products"]:
        print(f"  {p['rank']:<4} {p['product_name']:<25} {p['total_quantity']:>8,} KES {p['total_revenue']:>10,.2f}")

    print("\n── LAST 7 DAYS ───────────────────────────────────────")
    w = report["last_7_days"]
    print(f"   Period  : {w['date_start']} → {w['date_end']}")
    print(f"   Revenue : KES {w['total_revenue']:,.2f}")
    print(f"   Quantity: {w['total_qty']:,} units")
    print(f"\n   {'Date':<12} {'Revenue':>12} {'Qty':>8}")
    print(f"   {'-'*12} {'-'*12} {'-'*8}")
    for d in w["daily"]:
        print(f"   {d['date']:<12} KES {d['revenue']:>8,.2f} {d['quantity']:>8,}")

    print("\n" + "=" * 60)
    print("  END OF REPORT")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    print_report()