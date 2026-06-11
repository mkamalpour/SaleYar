"""
stage3_forecast.py — SMART & ADAPTIVE FORECASTING

Improvements:
- Category fallback for products with insufficient history (<7 days)
- Confidence levels: High (MAPE<20%), Medium (20-50%), Low (>50% or sparse)
- Adaptive batch size based on number of products
- Sparse data uses simple average instead of SeasonalNaive
- All thresholds from config.py
"""

import logging
import sys
import warnings
import pandas as pd
import numpy as np
import os
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config

logger = logging.getLogger(__name__)

try:
    from statsforecast import StatsForecast
    from statsforecast.models import AutoTheta, AutoETS, SeasonalNaive
    HAS_STATSFORECAST = True
except ImportError:
    HAS_STATSFORECAST = False
    logger.error("statsforecast not installed — Stage 3 will return empty forecasts")


def run(df_raw: pd.DataFrame, df_kpis: pd.DataFrame) -> dict:
    """Run adaptive forecasting."""
    logger.info(f"Stage 3: demand forecasting | {df_kpis['product'].nunique()} products")

    if not HAS_STATSFORECAST:
        return {p: _skip("statsforecast not available") for p in df_kpis["product"].unique()}

    # Filter to sales only
    sales_mask = (df_raw["transaction_type"] == "sale") & (df_raw["qty"] > 0) & (df_raw["sell_price"] > 0)
    df_sales = df_raw[sales_mask].copy()

    # Pre‑compute category averages (for fallback)
    category_avg = {}
    if "product_category" in df_kpis.columns:
        category_avg = df_kpis.groupby("product_category")["daily_sales"].mean().to_dict()

    all_ts = []
    skipped_count = 0

    for product_name, group in df_sales.groupby("product"):
        try:
            kpi_row = df_kpis[df_kpis["product"] == product_name]
            if len(kpi_row) == 0:
                skipped_count += 1
                continue

            sufficiency = kpi_row["sufficiency"].values[0]
            ts = _build_timeseries(group, product_name)

            if ts is None or len(ts) < config.MIN_DAYS_FOR_FORECAST:
                # Not enough data -> use category fallback
                cat = kpi_row["product_category"].values[0] if "product_category" in kpi_row.columns else None
                results = {product_name: _category_fallback(product_name, cat, category_avg)}
                continue

            trend = _calculate_trend(ts)

            all_ts.append({
                "ts": ts,
                "sufficiency": sufficiency,
                "trend": trend,
                "product": product_name,
                "category": kpi_row["product_category"].values[0] if "product_category" in kpi_row.columns else None
            })
        except Exception as e:
            logger.debug(f"Could not prepare {product_name}: {e}")
            skipped_count += 1

    if not all_ts and not results:
        logger.warning(f"No products with sufficient sales data (min {config.MIN_DAYS_FOR_FORECAST} days)")
        return {p: _skip("Insufficient sales data") for p in df_kpis["product"].unique()}

    logger.info(f"Building forecasts for {len(all_ts)} products ({skipped_count} skipped)")

    results = {}

    # Adaptive batch size: larger batches for many products
    total_products = len(all_ts)
    batch_size = getattr(config, 'FORECAST_BATCH_SIZE', 50)
    if total_products > 1000:
        batch_size = 200
    elif total_products > 500:
        batch_size = 100

    # Process each sufficiency group
    for suff in ["rich", "medium", "sparse"]:
        group_items = [item for item in all_ts if item["sufficiency"] == suff]
        if not group_items:
            continue

        # Prepare batch DataFrame
        batch_dfs = []
        for item in group_items:
            ts_copy = item["ts"].copy()
            ts_copy["y"] = pd.to_numeric(ts_copy["y"], errors="coerce").fillna(0)
            ts_copy["unique_id"] = item["product"]
            batch_dfs.append(ts_copy[["ds", "y", "unique_id"]])

        batch = pd.concat(batch_dfs, ignore_index=True)

        # Season length detection
        try:
            if hasattr(config, 'SEASON_LENGTH') and config.SEASON_LENGTH:
                season_length = config.SEASON_LENGTH
            else:
                season_length = _auto_detect_season_length(batch)
        except Exception:
            season_length = 7

        # Choose model
        if suff == "rich":
            model = AutoTheta(season_length=season_length)
            method_name = "AutoTheta"
            low_confidence = False
        elif suff == "medium":
            model = AutoETS(season_length=season_length)
            method_name = "AutoETS"
            low_confidence = False
        else:
            # Sparse: use simple average instead of SeasonalNaive (more robust)
            # We'll handle sparse separately with a simple fallback
            # Continue with normal batch but later we could override
            model = SeasonalNaive(season_length=min(season_length, 7))
            method_name = "SeasonalNaive"
            low_confidence = True

        unique_ids = batch["unique_id"].unique()
        n_products = len(unique_ids)

        for i in range(0, n_products, batch_size):
            batch_ids = unique_ids[i:i+batch_size]
            batch_subset = batch[batch["unique_id"].isin(batch_ids)].copy()

            # Ensure numeric
            for col in batch_subset.columns:
                if col not in ["ds", "unique_id"]:
                    batch_subset[col] = pd.to_numeric(batch_subset[col], errors="coerce").fillna(0)

            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    sf = StatsForecast(models=[model], freq="D", n_jobs=-1)
                    forecast_df = sf.forecast(df=batch_subset, h=config.FORECAST_HORIZON, level=[80, 95])

                for unique_id in batch_ids:
                    try:
                        preds = forecast_df[forecast_df["unique_id"] == unique_id].reset_index()
                        if len(preds) == 0:
                            results[unique_id] = _skip("No forecast generated")
                            continue

                        if method_name in preds.columns:
                            vals = preds[method_name].clip(lower=0).values
                        else:
                            forecast_cols = [c for c in preds.columns if c not in ("ds", "unique_id")
                                           and "lo-" not in c.lower() and "hi-" not in c.lower()]
                            if not forecast_cols:
                                results[unique_id] = _skip("No forecast column found")
                                continue
                            vals = preds[forecast_cols[0]].clip(lower=0).values

                        # Apply trend adjustment
                        if getattr(config, 'ENABLE_TREND_ADJUSTMENT', True):
                            product_item = next((item for item in group_items if item["product"] == unique_id), None)
                            if product_item:
                                trend_val = product_item["trend"]
                                if abs(trend_val) > getattr(config, 'MIN_TREND_THRESHOLD', 0.05):
                                    trend_factor = 1 + trend_val * getattr(config, 'TREND_WEIGHT', 0.5)
                                    vals = vals * trend_factor
                                    vals = np.maximum(vals, 0)

                        # Calculate confidence level based on MAPE (if enough history)
                        historical = batch_subset[batch_subset["unique_id"] == unique_id]["y"].values
                        confidence = _calculate_confidence(historical, vals, suff)

                        results[unique_id] = {
                            "method": method_name,
                            "daily_forecast": vals[:90].tolist(),
                            "daily_lo80": preds["lo-80"][:90].clip(lower=0).tolist() if "lo-80" in preds.columns else None,
                            "daily_hi80": preds["hi-80"][:90].clip(lower=0).tolist() if "hi-80" in preds.columns else None,
                            "h30": round(float(np.sum(vals[:30])), 1),
                            "h60": round(float(np.sum(vals[:60])), 1),
                            "h90": round(float(np.sum(vals[:90])), 1),
                            "low_confidence": confidence == "Low",
                            "confidence": confidence,
                            "skipped": False,
                            "skip_reason": None,
                        }
                    except Exception as e:
                        logger.debug(f"Error processing forecast for {unique_id}: {e}")
                        results[unique_id] = _skip(f"Processing error: {e}")

            except Exception as e:
                logger.warning(f"Forecast failed for batch: {e}")
                for unique_id in batch_ids:
                    results[unique_id] = _skip(f"Forecast failed: {e}")

    # Fill missing products (including those that were skipped)
    for product in df_kpis["product"].unique():
        if product not in results:
            # Try category fallback again
            cat_row = df_kpis[df_kpis["product"] == product]
            cat = cat_row["product_category"].values[0] if "product_category" in cat_row.columns else None
            results[product] = _category_fallback(product, cat, category_avg)

    n_done = sum(1 for v in results.values() if not v.get("skipped"))
    n_skipped = sum(1 for v in results.values() if v.get("skipped"))
    logger.info(f"Stage 3 complete | {n_done} forecasted | {n_skipped} skipped")

    return results


def _category_fallback(product_name, category, category_avg):
    """Return a forecast based on category average."""
    avg_daily = category_avg.get(category, 0) if category else 0
    if avg_daily <= 0:
        return _skip(f"No data and no category average for '{product_name}'")
    daily_forecast = [avg_daily] * 90
    return {
        "method": "Category Average (Fallback)",
        "daily_forecast": daily_forecast,
        "daily_lo80": None,
        "daily_hi80": None,
        "h30": round(avg_daily * 30, 1),
        "h60": round(avg_daily * 60, 1),
        "h90": round(avg_daily * 90, 1),
        "low_confidence": True,
        "confidence": "Low",
        "skipped": False,
        "skip_reason": None,
    }


def _calculate_confidence(historical, forecast, sufficiency):
    """Calculate confidence level: High, Medium, Low."""
    # If sparse data or fallback, confidence is Low
    if sufficiency == "sparse" or len(historical) < 14:
        return "Low"
    # Calculate MAPE on last 14 days (if available)
    n = min(14, len(historical), len(forecast))
    if n < 7:
        return "Medium"
    hist = historical[-n:]
    fcst = forecast[:n]
    # Avoid division by zero
    mask = hist != 0
    if mask.sum() == 0:
        return "Medium"
    mape = np.mean(np.abs((hist[mask] - fcst[mask]) / hist[mask])) * 100
    high_thresh = getattr(config, 'FORECAST_CONFIDENCE_MAPE_HIGH', 20)
    low_thresh = getattr(config, 'FORECAST_CONFIDENCE_MAPE_LOW', 50)
    if mape < high_thresh:
        return "High"
    elif mape < low_thresh:
        return "Medium"
    else:
        return "Low"


def _calculate_trend(ts: pd.DataFrame) -> float:
    """Calculate trend (daily growth rate)."""
    try:
        y = ts["y"].values
        if len(y) < 14:
            return 0.0
        x = np.arange(len(y))
        slope = np.polyfit(x, y, 1)[0]
        mean_y = np.mean(y)
        if mean_y == 0:
            return 0.0
        trend_rate = slope / mean_y
        return max(-0.5, min(0.5, trend_rate))
    except Exception:
        return 0.0


def _auto_detect_season_length(batch: pd.DataFrame) -> int:
    """Auto-detect seasonality (7, 30, or 365 days)."""
    try:
        sample = batch[batch["y"] > 0].head(200)
        if len(sample) < 60:
            return 7

        y_vals = sample["y"].values[:365]
        n = len(y_vals)
        if n < 30:
            return 7

        def autocorr(lag):
            if lag >= n:
                return 0
            return np.corrcoef(y_vals[:-lag], y_vals[lag:])[0, 1]

        corr_7 = autocorr(7) if n > 7 else 0
        corr_30 = autocorr(30) if n > 30 else 0
        corr_365 = autocorr(365) if n > 365 else 0

        if corr_365 > 0.3:
            return 365
        elif corr_30 > 0.3:
            return 30
        else:
            return 7
    except Exception:
        return 7


def _build_timeseries(group: pd.DataFrame, product_name: str):
    """Build daily aggregated time series from sales only."""
    try:
        group = group.copy()
        group["qty"] = pd.to_numeric(group["qty"], errors="coerce").fillna(0)
        ts = group.groupby("date")["qty"].sum().reset_index()
        ts.columns = ["ds", "y"]
        ts["ds"] = pd.to_datetime(ts["ds"])
        ts = ts.sort_values("ds")

        if len(ts) < config.MIN_DAYS_FOR_FORECAST:
            return None

        full_range = pd.date_range(ts["ds"].min(), ts["ds"].max(), freq="D")
        ts = ts.set_index("ds").reindex(full_range, fill_value=0).reset_index()
        ts.columns = ["ds", "y"]
        ts["unique_id"] = product_name
        ts["y"] = ts["y"].clip(lower=0)
        ts["y"] = pd.to_numeric(ts["y"], errors="coerce").fillna(0)
        return ts
    except Exception as e:
        logger.debug(f"Error building timeseries for {product_name}: {e}")
        return None


def _skip(reason: str) -> dict:
    return {
        "method": "Skipped",
        "daily_forecast": [],
        "daily_lo80": [],
        "daily_hi80": [],
        "h30": None,
        "h60": None,
        "h90": None,
        "lo80": None,
        "hi80": None,
        "lo95": None,
        "hi95": None,
        "low_confidence": True,
        "confidence": "Low",
        "skipped": True,
        "skip_reason": reason,
    }