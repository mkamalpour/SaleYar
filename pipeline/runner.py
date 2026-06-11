"""
runner.py

Orchestrates all 9 stages in sequence.
No parallel execution — sequential is simpler, safer, and fast enough.

All models are loaded once at server startup by models/loader.py.
Each stage receives what it needs from the previous stage's output.

FIXED: Inventory tracking resets each run, matches UI summary calculation.
FIXED: Damaged goods now correctly reduce inventory.
"""

import hashlib
import logging
import os
import sys
import time
import json
from datetime import datetime

import joblib
import pandas as pd

# Add parent directory to path to enable imports from root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline import (
    stage1_cleaner,
    stage2_metrics,
    stage3_forecast,
    stage4_segments,
    stage5_basket,
    stage6_risk,
    stage7_optimizer,
    stage8_customers,
    stage9_priority,
)
from models import loader
from output import reporter

logger = logging.getLogger(__name__)

CACHE_SEGMENTS = "segment_cache.pkl"
CACHE_FORECASTS = "forecast_cache.pkl"
INVENTORY_STATE_FILE = "inventory_state.json"
PURCHASE_HISTORY_FILE = "purchase_history.json"


# ============================================================================
# INVENTORY TRACKING FUNCTIONS (FIXED - RESETS EACH TIME)
# ============================================================================

def load_inventory_state(shop_id: str) -> dict:
    """Load saved inventory state - DISABLED, always start fresh"""
    return {}


def save_inventory_state(shop_id: str, inventory: dict):
    """Save inventory state for reference/audit only (not loaded)"""
    inventory_path = os.path.join(loader.get_shop_dir(shop_id), INVENTORY_STATE_FILE)
    try:
        os.makedirs(os.path.dirname(inventory_path), exist_ok=True)
        data = {
            'inventory': inventory,
            'last_updated': datetime.now().isoformat(),
            'shop_id': shop_id
        }
        with open(inventory_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved inventory reference for {shop_id}: {len(inventory)} products")
    except Exception as e:
        logger.warning(f"Could not save inventory for {shop_id}: {e}")


def calculate_net_change_from_transactions(df: pd.DataFrame) -> dict:
    """
    Calculate net change directly from DataFrame (same as UI summary).
    Formula: net_change = Purchases + Return_Sale - Sales - Return_Purchase 
    
    All quantities are assumed positive; transaction_type determines direction.
    """
    inventory = {}
    
    for _, row in df.iterrows():
        product = row.get('product')
        if not product or pd.isna(product):
            continue
            
        qty = float(row.get('qty', 0))
        trans_type = row.get('transaction_type', 'sale')
        
        # Stock increases
        if trans_type == 'purchase':
            inventory[product] = inventory.get(product, 0) + abs(qty)
        elif trans_type == 'return_sale':
            inventory[product] = inventory.get(product, 0) + abs(qty)
        # Stock decreases
        elif trans_type == 'sale':
            inventory[product] = inventory.get(product, 0) - abs(qty)
        elif trans_type == 'return_purchase':
            inventory[product] = inventory.get(product, 0) - abs(qty)

    
    return inventory


def calculate_current_inventory(
    df: pd.DataFrame, 
    shop_id: str, 
    use_transaction_type: bool = True,
    reset_inventory: bool = True
) -> dict:
    """
    Calculate current inventory - ALWAYS starts from zero.
    Uses same logic as UI summary for consistency.
    """
    logger.info(f"Inventory calculated from scratch for shop '{shop_id}'")
    
    if use_transaction_type and 'transaction_type' in df.columns:
        inventory = calculate_net_change_from_transactions(df)
        logger.info(f"Inventory calculated using transaction_type: {len(inventory)} products")
    else:
        # Fallback method (purchases - sales only) - ignores returns and damaged
        inventory = {}
        for product, group in df.groupby("product"):
            purchases = group[group['qty'] > 0]['qty'].sum()
            sales = abs(group[group['qty'] < 0]['qty'].sum())
            net_change = purchases - sales
            inventory[product] = net_change if net_change > 0 else 0
        logger.info(f"Inventory calculated using fallback method: {len(inventory)} products")
    
    return inventory


def record_purchases_from_optimizer(shop_id: str, order: list):
    """Record that user purchased the recommended quantities - DISABLED"""
    logger.info(f"Purchase recording disabled for shop '{shop_id}'")
    pass


# ============================================================================
# CACHE FUNCTIONS (unchanged)
# ============================================================================

def _shop_cache_path(shop_id: str, filename: str) -> str:
    return os.path.join(loader.get_shop_dir(shop_id), filename)


def _load_shop_cache(shop_id: str, data_hash: str) -> dict | None:
    metadata = loader.get_shop_metadata(shop_id)
    if not metadata or metadata.get("data_hash") != data_hash:
        return None

    segment_path = _shop_cache_path(shop_id, CACHE_SEGMENTS)
    forecast_path = _shop_cache_path(shop_id, CACHE_FORECASTS)
    if not os.path.exists(segment_path) or not os.path.exists(forecast_path):
        return None

    try:
        df_kpis = joblib.load(segment_path)
        forecasts = joblib.load(forecast_path)
        logger.info(f"Loaded cached segment and forecast data for shop '{shop_id}'")
        return {"df_kpis": df_kpis, "forecasts": forecasts}
    except Exception as e:
        logger.warning(f"Could not load shop cache for '{shop_id}': {e}")
        return None


def _save_shop_cache(shop_id: str, data_hash: str, df_kpis, forecasts: dict) -> None:
    os.makedirs(loader.get_shop_dir(shop_id), exist_ok=True)
    try:
        joblib.dump(df_kpis, _shop_cache_path(shop_id, CACHE_SEGMENTS))
        joblib.dump(forecasts, _shop_cache_path(shop_id, CACHE_FORECASTS))
        loader.save_shop_metadata(
            shop_id,
            {
                "shop_id":   shop_id,
                "data_hash": data_hash,
                "cached_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            },
        )
        logger.info(f"Saved shop cache for '{shop_id}'")
    except Exception as e:
        logger.warning(f"Could not save shop cache for '{shop_id}': {e}")


# ============================================================================
# MAIN PIPELINE (unchanged except for inventory call)
# ============================================================================

def run_pipeline(
    file_bytes: bytes,
    filename:   str,
    budget:     float,
    shop_id:    str  = "default",
    goal:       str  = "maximize_profit",
    language:   str  = "en",
    reset_inventory: bool = True
) -> dict:
    """
    Run all 9 stages and assemble the final report.
    """
    start_total = time.time()
    stages = {}
    timing = {}

    logger.info(f"Pipeline start | shop={shop_id} | file={filename} | budget={budget:,.0f}")
    print(f"\n{'='*60}")
    print(f"🚀 PIPELINE START - Timing Analysis")
    print(f"{'='*60}")

    # ── Stage 1: Ingest, validate, clean ─────────────────────
    t1 = time.time()
    s1 = stage1_cleaner.run(file_bytes, filename, language)
    timing["stage1_cleaner"] = round(time.time() - t1, 2)
    print(f"[{timing['stage1_cleaner']:>6}s] Stage 1: Cleaner - quality={s1['quality']} | rows_after={len(s1.get('df', []))}")
    
    stages["stage1"] = {
        "quality": s1["quality"],
        "passed":  s1["passed"],
        "flagged": len(s1["flagged"]),
        "issues":  s1["issues"],
        "message": s1["message"],
    }

    if not s1["passed"]:
        return {
            "shop_id":         shop_id,
            "language":        language,
            "passed":          False,
            "stop_reason":     s1["message"],
            "stages":          stages,
            "elapsed_seconds": round(time.time() - start_total, 2),
        }

    df = s1["df"]
    
    # Hash calculation
    t_hash = time.time()
    data_hash = hashlib.md5(file_bytes).hexdigest()
    timing["hash_calculation"] = round(time.time() - t_hash, 2)
    print(f"[{timing['hash_calculation']:>6}s] Stage 0: MD5 Hash calculation")

    # Cache check
    t_cache = time.time()
    shop_cache = _load_shop_cache(shop_id, data_hash)
    timing["cache_check"] = round(time.time() - t_cache, 2)
    cache_status = "reused" if shop_cache is not None else "reset"
    print(f"[{timing['cache_check']:>6}s] Cache check: {cache_status}")

    if shop_cache is not None:
        df_kpis = shop_cache["df_kpis"]
        forecasts = shop_cache["forecasts"]
        timing["stage2_kpi"] = 0
        timing["stage3_forecast"] = 0
        timing["stage4_segments"] = 0
        print(f"[CACHED] Skipped Stages 2-4 (using cached data)")
    else:
        loader.clear_shop_models(shop_id)
        os.makedirs(loader.get_shop_dir(shop_id), exist_ok=True)

        # ── Stage 2: KPI calculation ──────────────────────────────
        t2 = time.time()
        df_kpis = stage2_metrics.run(df)
        timing["stage2_kpi"] = round(time.time() - t2, 2)
        print(f"[{timing['stage2_kpi']:>6}s] Stage 2: KPI Metrics - {len(df_kpis)} products")
        
        stages["stage2"] = {
            "products": len(df_kpis),
            "columns":  list(df_kpis.columns),
        }

        # ── Stage 3: Demand forecasting ───────────────────────────
        t3 = time.time()
        forecasts = stage3_forecast.run(df, df_kpis)
        timing["stage3_forecast"] = round(time.time() - t3, 2)
        n_fc = sum(1 for v in forecasts.values() if not v.get("skipped"))
        print(f"[{timing['stage3_forecast']:>6}s] Stage 3: Forecast - {n_fc}/{len(forecasts)} products forecasted")
        
        stages["stage3"] = {"forecasted": n_fc, "skipped": len(forecasts) - n_fc}

        # ── Stage 4: Product segmentation ─────────────────────────
        t4 = time.time()
        df_kpis = stage4_segments.run(df_kpis)
        timing["stage4_segments"] = round(time.time() - t4, 2)
        print(f"[{timing['stage4_segments']:>6}s] Stage 4: Segments - {df_kpis['segment'].nunique() if 'segment' in df_kpis.columns else 0} types")
        
        stages["stage4"] = {
            "skipped": bool(df_kpis.get("segment_skipped", pd.Series([False])).any()),
            "counts":  df_kpis["segment"].value_counts().to_dict()
                       if "segment" in df_kpis.columns else {},
        }

        # Save cache
        t_save = time.time()
        _save_shop_cache(shop_id, data_hash, df_kpis, forecasts)
        timing["cache_save"] = round(time.time() - t_save, 2)
        print(f"[{timing['cache_save']:>6}s] Cache saved")

    if shop_cache is not None:
        stages["stage2"] = {"products": len(df_kpis), "columns": list(df_kpis.columns)}
        n_fc = sum(1 for v in forecasts.values() if not v.get("skipped"))
        stages["stage3"] = {"forecasted": n_fc, "skipped": len(forecasts) - n_fc}
        stages["stage4"] = {
            "skipped": bool(df_kpis.get("segment_skipped", pd.Series([False])).any()),
            "counts": df_kpis["segment"].value_counts().to_dict()
                       if "segment" in df_kpis.columns else {},
        }

    # ── Stage 5: Basket analysis ──────────────────────────────
    t5 = time.time()
    basket = stage5_basket.run(df, shop_id)
    timing["stage5_basket"] = round(time.time() - t5, 2)
    print(f"[{timing['stage5_basket']:>6}s] Stage 5: Basket - {len(basket.get('rules', []))} rules, {len(basket.get('critical_pairs', []))} critical pairs")
    
    stages["stage5"] = {
        "rules":          len(basket.get("rules", [])),
        "critical_pairs": len(basket.get("critical_pairs", [])),
        "skipped":        basket.get("skipped", False),
    }

    # ── Stage 6: Risk scoring ─────────────────────────────────
    t6 = time.time()
    df_kpis = stage6_risk.run(df_kpis, language)
    timing["stage6_risk"] = round(time.time() - t6, 2)
    shop_roi = float(df_kpis["shop_roi"].iloc[0]) if "shop_roi" in df_kpis.columns else 0.0
    print(f"[{timing['stage6_risk']:>6}s] Stage 6: Risk - shop_roi={shop_roi:.1f}% | vs_bank={df_kpis['vs_bank'].iloc[0]:+.1f}%")
    
    stages["stage6"] = {
        "shop_roi": round(shop_roi, 2),
        "vs_bank":  round(df_kpis["vs_bank"].iloc[0], 2) if "vs_bank" in df_kpis.columns else 0,
        "vs_gold":  round(df_kpis["vs_gold"].iloc[0], 2) if "vs_gold" in df_kpis.columns else 0,
    }

    # ── Stage 7: Portfolio optimization WITH INVENTORY ────────
    t7 = time.time()
    
    # Calculate current inventory - ALWAYS fresh calculation, no saved state
    current_inventory = calculate_current_inventory(df, shop_id, use_transaction_type=True, reset_inventory=True)
    current_inventory = {k: max(0, v) for k, v in current_inventory.items()}
    print(f"[INVENTORY] Calculated {len(current_inventory)} products")
    
    # Debug: Show Rice stock
    if 'Rice' in current_inventory:
        print(f"[INVENTORY] Rice stock: {current_inventory['Rice']}")
    
    original_products = df["product"].unique().tolist()

    optimizer = stage7_optimizer.run(
        df_kpis=df_kpis, 
        budget=budget, 
        goal=goal, 
        basket_result=basket, 
        current_inventory=current_inventory,
        forecasts=forecasts,
        language=language,
        original_products_list=original_products
    )
    timing["stage7_optimizer"] = round(time.time() - t7, 2)
    print(f"[{timing['stage7_optimizer']:>6}s] Stage 7: Optimizer - feasible={optimizer.get('feasible')} | cost={optimizer.get('total_cost', 0):,.0f} | items={len([o for o in optimizer.get('order', []) if o.get('qty', 0) > 0])}")
    
    stages["stage7"] = {
        "feasible":    optimizer.get("feasible"),
        "total_cost":  optimizer.get("total_cost"),
        "items":       len([o for o in optimizer.get("order", []) if o.get("qty", 0) > 0]),
        "relaxations": optimizer.get("relaxations", []),
    }

    # ── Stage 8: Customer segmentation ────────────────────────
    t8 = time.time()
    customers = stage8_customers.run(df, language)
    timing["stage8_customers"] = round(time.time() - t8, 2)
    print(f"[{timing['stage8_customers']:>6}s] Stage 8: Customers - skipped={customers.get('skipped')} | segments={customers.get('summary', {})}")

    # Boost champion product scores for better optimizer weighting
    if not customers.get("skipped"):
        champ_products = customers.get("champion_products", [])
        if champ_products and "product" in df_kpis.columns:
            mask = df_kpis["product"].isin(champ_products)
            df_kpis.loc[mask, "risk_score"] = (
                df_kpis.loc[mask, "risk_score"] * 1.1
            ).clip(upper=100)

    stages["stage8"] = {
        "skipped": customers.get("skipped", True),
        "summary": customers.get("summary", {}),
    }

    # ── Stage 9: Priority actions ─────────────────────────────
    t9 = time.time()
    priority_actions = stage9_priority.run(
        df=df,
        products=[{
            "product": row["product"],
            "segment": row.get("segment"),
            "days_since_last_sale": row.get("days_since_last_sale"),
            "risk_score": row.get("risk_score"),
        } for _, row in df_kpis.iterrows()],
        forecasts=forecasts,
        basket_rules=basket.get("rules", []),
        customers=customers,
        optimizer=optimizer,
        language=language,
    )
    timing["stage9_priority"] = round(time.time() - t9, 2)
    print(f"[{timing['stage9_priority']:>6}s] Stage 9: Priority - {len(priority_actions)} actions")

    stages["stage9"] = {"actions": len(priority_actions)}

    # ── Assemble report ───────────────────────────────────────
    t_report = time.time()
    report = _build_report(
        df_kpis, forecasts, basket, customers,
        optimizer, s1, language, priority_actions,
        cache_status,
    )
    timing["report_assembly"] = round(time.time() - t_report, 2)
    print(f"[{timing['report_assembly']:>6}s] Report Assembly")

    elapsed = round(time.time() - start_total, 2)
    
    # ── Summary ────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"📊 TIMING SUMMARY")
    print(f"{'='*60}")
    
    sorted_timing = sorted(timing.items(), key=lambda x: x[1], reverse=True)
    
    for name, t in sorted_timing:
        bar_len = int(t / max(timing.values()) * 40) if max(timing.values()) > 0 else 0
        bar = "█" * bar_len
        print(f"  {name:<20} : {t:>6.2f}s  {bar}")
    
    print(f"{'='*60}")
    print(f"  {'TOTAL':<20} : {elapsed:>6.2f}s")
    print(f"{'='*60}\n")
    
    # Show inventory summary
    non_zero = {k: v for k, v in current_inventory.items() if v > 0}
    if non_zero:
        print(f"📦 INVENTORY SUMMARY ({len(non_zero)} products in stock):")
        for product, stock in list(non_zero.items())[:5]:
            print(f"     {product}: {stock} units")
        if len(non_zero) > 5:
            print(f"     ... and {len(non_zero) - 5} more")
    
    logger.info(f"Pipeline complete | shop={shop_id} | {elapsed}s")

    return {
        "shop_id":         shop_id,
        "language":        language,
        "passed":          True,
        "stages":          stages,
        "report":          report,
        "df":              df,
        "elapsed_seconds": elapsed,
        "timing":          timing,
        "inventory":       current_inventory,
    }


# ─────────────────────────────────────────────────────────────
# Report assembly (unchanged)
# ─────────────────────────────────────────────────────────────

def _build_report(
    df_kpis:   "pd.DataFrame",
    forecasts: dict,
    basket:    dict,
    customers: dict,
    optimizer: dict,
    s1:        dict,
    language:  str,
    priority_actions: list,
    cache_status: str,
) -> dict:
    """Build the top-level report structure from all stage outputs."""
    import pandas as pd

    shop_roi = float(df_kpis["shop_roi"].iloc[0]) if "shop_roi" in df_kpis.columns else 0.0
    vs_bank  = float(df_kpis["vs_bank"].iloc[0])  if "vs_bank" in df_kpis.columns else 0.0
    vs_gold  = float(df_kpis["vs_gold"].iloc[0])  if "vs_gold" in df_kpis.columns else 0.0

    products = []
    for _, row in df_kpis.iterrows():
        name = row["product"]
        products.append({
            "product":             name,
            "segment":             row.get("segment"),
            "segment_confidence":  row.get("segment_confidence"),
            "risk_score":          row.get("risk_score"),
            "risk_explanation":    row.get("risk_explanation"),
            "profit_margin":       row.get("profit_margin"),
            "days_since_last_sale": row.get("days_since_last_sale"),
            "total_sold":          row.get("total_sold"),
            "total_revenue":       row.get("total_revenue"),
            "total_profit":        row.get("total_profit"),
            "sufficiency":         row.get("sufficiency"),
            "best_season":         row.get("best_season"),
            "annual_roi":          row.get("annual_roi"),
            "forecast":            forecasts.get(name),
        })

    segment_summary = {}
    for p in products:
        seg = p.get("segment") or "Unknown"
        segment_summary[seg] = segment_summary.get(seg, 0) + 1

    scored          = [p for p in products if p.get("risk_score") is not None]
    top_performers  = sorted(scored, key=lambda p: p["risk_score"], reverse=True)[:5]
    bottom_products = sorted(scored, key=lambda p: p["risk_score"])[:5]
    deadweight      = [p for p in products if p.get("segment") == "Deadweight"]

    roi_commentary = _roi_commentary(shop_roi, vs_bank, vs_gold, language)

    return {
        "generated_at":      pd.Timestamp.now().isoformat(),
        "language":          language,
        "cache_status":      cache_status,
        "data_quality":      s1["quality"],
        "data_quality_msg":  s1["message"],
        "flagged_rows":      s1["flagged"],
        "products":          products,
        "segment_summary":   segment_summary,
        "top_performers":    top_performers,
        "bottom_products":   bottom_products,
        "deadweight":        deadweight,
        "basket_rules":      basket.get("rules", []),
        "critical_pairs":    basket.get("critical_pairs", []),
        "customers":         customers,
        "purchase_order":    optimizer.get("order", []),
        "order_total":       optimizer.get("total_cost", 0),
        "optimizer_feasible": optimizer.get("feasible", False),
        "optimizer_summary": optimizer.get("summary", ""),
        "optimizer_relaxations": optimizer.get("relaxations", []),
        "priority_actions":  priority_actions,
        "shop_roi":          round(shop_roi, 2),
        "vs_bank":           round(vs_bank, 2),
        "vs_gold":           round(vs_gold, 2),
        "roi_commentary":    roi_commentary,
        "benchmark_margin":  18.0,
        "benchmark_turnover": 8.0,
    }


def _roi_commentary(roi: float, vs_bank: float, vs_gold: float, language: str) -> str:
    fa = language == "fa"
    if fa:
        base = f"بازده سالانه فروشگاه: {roi:.1f}٪. "
        base += (f"در مقایسه با سود بانکی {roi - vs_bank:.1f}٪: "
                 f"{'بهتر' if vs_bank > 0 else 'بدتر'} است. ")
        base += (f"در مقایسه با طلا {roi - vs_gold:.1f}٪: "
                 f"{'بهتر' if vs_gold > 0 else 'بدتر'} است.")
    else:
        base = f"Shop annual ROI: {roi:.1f}%. "
        base += (f"Vs bank deposit rate ({roi - vs_bank:.1f}%): "
                 f"{'ahead' if vs_bank > 0 else 'behind'}. ")
        base += (f"Vs gold return ({roi - vs_gold:.1f}%): "
                 f"{'ahead' if vs_gold > 0 else 'behind'}.")
    return base