"""
stage2_metrics.py — IMPROVED VERSION (Smart & Adaptive)

Improvements:
- Outlier clipping (percentile) for normalization
- Category fallback for products with no sales or missing KPIs
- Unified score uses only available metrics (risk is added later in Stage 6)
- Configurable weights from config.py
- Handles edge cases (zero division, single product, etc.)
"""

import logging
import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

logger = logging.getLogger(__name__)


def run(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate KPIs per product, unified score, and rank."""
    logger.info("Stage 2: calculating KPIs")

    # ========== SHOP‑WIDE METRICS ==========
    sales_mask = (df["qty"] > 0) & (df["sell_price"] > 0)
    shop_sales_df = df[sales_mask]
    shop_total_revenue = (shop_sales_df["qty"] * shop_sales_df["sell_price"]).sum()
    shop_total_cost = (shop_sales_df["qty"] * shop_sales_df["buy_price"]).sum()
    shop_avg_margin = ((shop_total_revenue - shop_total_cost) / shop_total_cost * 100) if shop_total_cost > 0 else 0.0

    max_date = df["date"].max() if not df.empty else pd.Timestamp.now()

    # ========== PRODUCT‑LEVEL KPIS ==========
    products = []
    for product_name, group in df.groupby("product"):
        kpi = _calc_product_kpis(product_name, group, df, shop_avg_margin, max_date)
        products.append(kpi)

    result = pd.DataFrame(products)

    # ========== FILL MISSING VALUES WITH CATEGORY DEFAULTS ==========
    if getattr(config, 'CATEGORY_FALLBACK_ENABLED', True):
        for col in ["profit_margin", "daily_sales", "liquidity_rate"]:
            if col in result.columns and result[col].isna().any():
                # Use median of same product_category if available
                if "product_category" in result.columns:
                    category_median = result.groupby("product_category")[col].transform("median")
                    result[col] = result[col].fillna(category_median)
                # Final fallback to 0
                result[col] = result[col].fillna(0)

    # ========== OUTLIER CLIPPING (percentile) ==========
    clip_low, clip_high = getattr(config, 'OUTLIER_PERCENTILE_CLIP', (1, 99))
    for col in ["profit_margin", "daily_sales", "liquidity_rate"]:
        if col in result.columns:
            low = result[col].quantile(clip_low / 100)
            high = result[col].quantile(clip_high / 100)
            result[col] = result[col].clip(low, high)

    # ========== UNIFIED SCORE (without risk – risk added later) ==========
    # Normalize each metric to 0‑100 using robust scaling (min‑max after clipping)
    metrics_to_normalize = ["profit_margin", "daily_sales", "liquidity_rate"]
    for metric in metrics_to_normalize:
        if metric in result.columns:
            min_val = result[metric].min()
            max_val = result[metric].max()
            if max_val > min_val:
                result[f"{metric}_norm"] = (result[metric] - min_val) / (max_val - min_val) * 100
            else:
                result[f"{metric}_norm"] = 50.0
        else:
            result[f"{metric}_norm"] = 50.0

    # Use weights from config (risk weight will be applied later in Stage 7)
    weights = config.UNIFIED_SCORE_WEIGHTS
    # Note: inverse_risk is not available yet; we ignore it here
    # For ranking, use only profit_margin, sales_velocity, liquidity_rate, customer_demand
    result["unified_score"] = (
        weights.get("profit_margin", 0.25) * result["profit_margin_norm"] +
        weights.get("sales_velocity", 0.25) * result["daily_sales_norm"] +
        weights.get("liquidity_rate", 0.20) * result["liquidity_rate_norm"] +
        weights.get("customer_demand", 0.15) * result["daily_sales_norm"]   # demand = sales velocity
        # No inverse_risk here (will be added in Stage 7 optimizer)
    )

    # Add ranking (1 = best)
    result["rank"] = result["unified_score"].rank(ascending=False, method="min").astype(int)

    logger.info(f"Stage 2 complete | {len(result)} products")
    return result


def _calc_product_kpis(product_name, group, df_all, shop_avg_margin, max_date) -> dict:
    group = group.sort_values("date")
    sales_group = group[(group["qty"] > 0) & (group["sell_price"] > 0)]

    total_sold = sales_group["qty"].sum()
    total_revenue = (sales_group["qty"] * sales_group["sell_price"]).sum()
    total_cost = (sales_group["qty"] * sales_group["buy_price"]).sum()
    total_profit = total_revenue - total_cost

    avg_buy = group["buy_price"].mean() if not group.empty else 0
    avg_sell = group["sell_price"].mean() if not group.empty else 0
    profit_margin = ((avg_sell - avg_buy) / avg_buy * 100) if avg_buy > 0 else 0.0

    # Liquidity rate (stock turnover scaled 0‑100)
    if len(sales_group) > 0:
        date_range = (sales_group["date"].max() - sales_group["date"].min()).days
        date_range = max(date_range, 1)
        if date_range >= 7:
            avg_daily_sales = total_sold / date_range
            monthly_demand = avg_daily_sales * 30
            estimated_stock = max(1, monthly_demand * 0.5)
            monthly_turnover = monthly_demand / estimated_stock
        else:
            avg_daily_sales = total_sold / date_range
            monthly_turnover = 1.0
        liquidity_rate = min(100.0, monthly_turnover * 10)
    else:
        avg_daily_sales = 0.0
        liquidity_rate = 0.0

    # Price volatility
    if len(sales_group) > 1:
        price_volatility = float(sales_group["sell_price"].std())
        price_change_count = int((sales_group["sell_price"].diff().abs() > 0).sum())
    else:
        price_volatility = 0.0
        price_change_count = 0

    # Hope rate (potential margin improvement)
    if len(sales_group) > 0:
        max_sell = sales_group["sell_price"].max()
        min_buy = sales_group["buy_price"].min()
        if min_buy > 0:
            max_possible_margin = ((max_sell - min_buy) / min_buy) * 100
        else:
            max_possible_margin = 0
        actual_margin = profit_margin
        hope_rate = (actual_margin / max_possible_margin * 100) if max_possible_margin > 0 else 0.0
    else:
        hope_rate = 0.0

    # Portfolio weight (share of total revenue)
    shop_total_revenue = (df_all[(df_all["qty"] > 0) & (df_all["sell_price"] > 0)]["qty"] *
                          df_all[(df_all["qty"] > 0) & (df_all["sell_price"] > 0)]["sell_price"]).sum()
    portfolio_weight = (total_revenue / shop_total_revenue * 100) if shop_total_revenue > 0 else 0.0

    # Days since last sale
    if len(sales_group) > 0:
        last_sale = sales_group["date"].max()
        days_since_last_sale = (max_date - last_sale).days if pd.notna(last_sale) else 999
    else:
        days_since_last_sale = 999

    # Best selling season (quarter)
    if len(sales_group) > 0 and "date" in sales_group.columns:
        temp = sales_group.copy()
        temp["quarter"] = temp["date"].dt.quarter
        best_quarter = temp.groupby("quarter")["qty"].sum().idxmax()
        quarter_names = {1: "Q1 (Jan-Mar)", 2: "Q2 (Apr-Jun)", 3: "Q3 (Jul-Sep)", 4: "Q4 (Oct-Dec)"}
        best_season = quarter_names.get(int(best_quarter), "Unknown")
    else:
        best_season = "Unknown"

    # Date range (based on sales)
    if len(sales_group) > 0:
        date_range_days = (sales_group["date"].max() - sales_group["date"].min()).days + 1
    else:
        date_range_days = 0

    # Unique customers
    if "customer_id" in sales_group.columns:
        unique_customers = sales_group["customer_id"].nunique()
    else:
        unique_customers = None

    # Conversion rate (invoices containing this product)
    total_invoices = df_all["invoice_id"].nunique()
    product_invoices = sales_group["invoice_id"].nunique()
    conversion_rate = (product_invoices / total_invoices * 100) if total_invoices > 0 else 0.0

    # Annual ROI (only if enough history)
    if date_range_days >= 30 and total_cost > 0:
        annual_roi = (total_profit / total_cost) * (365 / date_range_days) * 100
    else:
        annual_roi = 0.0

    margin_vs_avg = profit_margin - shop_avg_margin
    sufficiency = _data_sufficiency(total_sold, date_range_days)

    return {
        "product": product_name,
        "total_sold": float(total_sold),
        "total_revenue": round(total_revenue, 2),
        "total_cost": round(total_cost, 2),
        "total_profit": round(total_profit, 2),
        "avg_buy_price": round(avg_buy, 2),
        "avg_sell_price": round(avg_sell, 2),
        "profit_margin": round(profit_margin, 2),
        "liquidity_rate": round(liquidity_rate, 2),
        "daily_sales": round(avg_daily_sales, 2),
        "price_volatility": round(price_volatility, 2),
        "price_change_count": price_change_count,
        "hope_rate": round(hope_rate, 2),
        "portfolio_weight": round(portfolio_weight, 2),
        "days_since_last_sale": days_since_last_sale,
        "best_season": best_season,
        "conversion_rate": round(conversion_rate, 2),
        "annual_roi": round(annual_roi, 2),
        "date_range_days": date_range_days,
        "invoice_count": int(product_invoices),
        "unique_customers": unique_customers,
        "margin_vs_avg": round(margin_vs_avg, 2),
        "sufficiency": sufficiency,
    }


def _data_sufficiency(total_sold: float, date_range_days: int) -> str:
    if total_sold >= config.MIN_SALES_RICH and date_range_days >= 90:
        return "rich"
    elif total_sold >= config.MIN_SALES_MEDIUM:
        return "medium"
    else:
        return "sparse"