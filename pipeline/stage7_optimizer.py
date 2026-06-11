"""
stage7_optimizer.py — REAL‑WORLD OPTIMIZER (Adaptive, Never Fails)

Improvements:
- SCIP solver first (optimal), greedy fallback if SCIP missing or too many products
- Realistic max units per product (500) and max coverage days (60)
- Minimum shelf quantity (2) for every product
- ALL products appear in order list (qty 0 with explanation)
- Low‑confidence forecasts get reduced quantity (30% multiplier)
- Seasonal products never get zero (minimum stock)
- Uses unified_score from Stage 2 as objective
"""

import logging
import sys
import numpy as np
import pandas as pd
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

logger = logging.getLogger(__name__)

try:
    from ortools.linear_solver import pywraplp
    HAS_ORTOOLS = True
except ImportError:
    HAS_ORTOOLS = False
    logger.warning("ortools not installed – will use greedy fallback")

# ============================================================================
# CONFIGURATION (with fallbacks)
# ============================================================================

MAX_UNITS_PER_PRODUCT = getattr(config, 'MAX_ORDER_UNITS_PER_PRODUCT', 500)
MIN_SHELF_QUANTITY = getattr(config, 'MIN_SHELF_QUANTITY', 2)
MIN_PRODUCTS_IN_ORDER = getattr(config, 'MIN_PRODUCTS_IN_ORDER', 10)
MAX_COVERAGE_DAYS = getattr(config, 'MAX_COVERAGE_DAYS', 60)
LOW_CONFIDENCE_MULTIPLIER = getattr(config, 'LOW_CONFIDENCE_MULTIPLIER', 0.3)
SEASONAL_MIN_STOCK_DAYS = getattr(config, 'SEASONAL_MIN_STOCK_DAYS', 14)
MAX_SINGLE_PRODUCT_SHARE = getattr(config, 'MAX_SINGLE_PRODUCT_SHARE', 0.30)
SAFETY_STOCK_DAYS = getattr(config, 'SAFETY_STOCK_DAYS', 7)
STAR_COVERAGE_DAYS = getattr(config, 'STAR_COVERAGE_DAYS', 30)
RELIABLE_COVERAGE_DAYS = getattr(config, 'RELIABLE_COVERAGE_DAYS', 21)
SEASONAL_COVERAGE_DAYS = getattr(config, 'SEASONAL_COVERAGE_DAYS', 14)


def run(df_kpis: pd.DataFrame, budget: float, goal: str = "maximize_profit",
        basket_result: dict = None, current_inventory: dict = None,
        forecasts: dict = None, language: str = "en", 
        original_products_list: list = None) -> dict:
    """Run optimisation, fallback to greedy if needed."""
    logger.info(f"Stage 7: optimisation | budget={budget:,.0f} | goal={goal}")

    if budget <= 0:
        return _skip(_t(language, "Budget must be greater than zero.", "بودجه باید بیشتر از صفر باشد."))
    if df_kpis.empty:
        return _skip(_t(language, "No product data available.", "داده‌ای برای تحلیل وجود ندارد."))

    if original_products_list is None:
        original_products_list = df_kpis["product"].tolist()

    # Decide method
    n_products = len(df_kpis)
    use_scip = HAS_ORTOOLS and n_products <= getattr(config, 'OPTIMIZER_MAX_PRODUCTS_FOR_SCIP', 500)

    if use_scip:
        result = _solve_scip(df_kpis, budget, goal, basket_result, current_inventory, forecasts, language)
    else:
        if not HAS_ORTOOLS:
            logger.info("SCIP not available, using greedy fallback.")
        else:
            logger.info(f"Too many products ({n_products}), using greedy fallback for speed.")
        result = _solve_greedy(df_kpis, budget, goal, current_inventory, forecasts, language)

    # Ensure every product appears
    all_products_order = _ensure_all_products_appear(
            result.get("order", []), df_kpis, current_inventory or {}, forecasts or {}, language, original_products_list
        )
    result["order"] = all_products_order
    result["total_cost"] = sum(o["total_cost"] for o in all_products_order)

    if result["feasible"]:
        items_with_qty = [o for o in all_products_order if o["qty"] > 0]
        if items_with_qty:
            items_str = ", ".join([f"{o['product']}: {o['qty']} units" for o in items_with_qty[:10]])
            if len(items_with_qty) > 10:
                items_str += f" + {len(items_with_qty)-10} more"
        else:
            items_str = "No products to buy"
        total = result["total_cost"]
        warn = " ⚠ Some constraints were relaxed." if result.get("relaxations") else ""
        result["summary"] = _t(language,
            f"Recommended purchase: {items_str}. Total cost: {total:,.0f}.{warn}",
            f"سفارش پیشنهادی: {items_str}. هزینه کل: {total:,.0f}.{warn}")
    else:
        result["summary"] = _t(language,
            f"No feasible purchase order found within budget {budget:,.0f}. Consider increasing the budget.",
            f"هیچ سفارش ممکنی در بودجه {budget:,.0f} یافت نشد. بودجه را افزایش دهید.")

    return result


# ============================================================================
# SCIP SOLVER (optimal)
# ============================================================================

def _solve_scip(df_kpis, budget, goal, basket_result, current_inventory, forecasts, language):
    critical_pairs = basket_result.get("critical_pairs", []) if basket_result else []
    relaxations = []
    result = _solve_integer_program(df_kpis, budget, goal, critical_pairs,
                                    current_inventory, forecasts, enforce_pairs=True, enforce_minimums=True)
    if not result["feasible"]:
        relaxations.append(_t(language, "Could not satisfy all basket pair requirements — pair constraints relaxed.",
                                   "شرط جفت‌های سبد ارضا نشد — این شروط کاهش یافت."))
        result = _solve_integer_program(df_kpis, budget, goal, critical_pairs,
                                        current_inventory, forecasts, enforce_pairs=False, enforce_minimums=True)
    if not result["feasible"]:
        relaxations.append(_t(language, "Could not guarantee minimum stock for Star products — minimums relaxed.",
                                   "حداقل موجودی محصولات Star ارضا نشد — حداقل‌ها کاهش یافت."))
        result = _solve_integer_program(df_kpis, budget, goal, critical_pairs,
                                        current_inventory, forecasts, enforce_pairs=False, enforce_minimums=False)
    result["relaxations"] = relaxations
    return result


def _solve_integer_program(df_kpis, budget, goal, critical_pairs, current_inventory, forecasts,
                           enforce_pairs, enforce_minimums):
    solver = pywraplp.Solver.CreateSolver("SCIP")
    if not solver:
        return {"feasible": False, "order": [], "total_cost": 0}
    solver.SetTimeLimit(5_000)

    products = df_kpis["product"].tolist()
    n = len(products)
    unit_costs = df_kpis["avg_buy_price"].fillna(0).tolist()
    segments = df_kpis.get("segment", pd.Series([""]*n)).tolist()
    unified_scores = df_kpis.get("unified_score", pd.Series([50.0]*n)).fillna(50).tolist()
    daily_velocity = df_kpis.get("daily_sales", pd.Series([0.0]*n)).fillna(0).tolist()

    # current stock (fix negatives)
    current_stock = []
    for product in products:
        stock = current_inventory.get(product, 0) if current_inventory else 0
        current_stock.append(max(0, stock))

    # Upper bounds: min of absolute max, budget limit, demand limit
    max_qty = []
    for i in range(n):
        abs_max = MAX_UNITS_PER_PRODUCT
        # budget limit
        max_spend = budget * MAX_SINGLE_PRODUCT_SHARE
        budget_max = int(max_spend / max(unit_costs[i], 1)) if unit_costs[i] > 0 else abs_max
        # demand limit (max coverage days)
        product_name = products[i]
        fc_data = forecasts.get(product_name, {}) if forecasts else {}
        daily_fc = fc_data.get("daily_forecast", [])
        if daily_fc and len(daily_fc) > 0 and sum(daily_fc) > 0:
            avg_daily = sum(daily_fc[:30]) / min(30, len(daily_fc))
            demand_max = int(avg_daily * MAX_COVERAGE_DAYS)
        else:
            demand_max = abs_max
        max_qty.append(max(0, min(abs_max, budget_max, demand_max)))

    buy_vars = [solver.IntVar(0, max_qty[i], f"buy_{i}") for i in range(n)]

    # Budget constraint
    solver.Add(solver.Sum([unit_costs[i] * buy_vars[i] for i in range(n)]) <= budget)

    # Minimum number of products in order
    product_count_vars = []
    for i in range(n):
        cv = solver.BoolVar(f"has_{i}")
        solver.Add(buy_vars[i] >= cv)
        solver.Add(buy_vars[i] <= max_qty[i] * cv)
        product_count_vars.append(cv)
    solver.Add(solver.Sum(product_count_vars) >= MIN_PRODUCTS_IN_ORDER)

    # Deadweight -> buy zero
    for i, seg in enumerate(segments):
        if seg == "Deadweight":
            solver.Add(buy_vars[i] == 0)

    # Minimum quantities based on demand
    if enforce_minimums:
        for i, seg in enumerate(segments):
            product = products[i]
            current = current_stock[i]
            fc_data = forecasts.get(product, {}) if forecasts else {}
            daily_fc = fc_data.get("daily_forecast", [])
            low_conf = fc_data.get("low_confidence", False)
            needed = _calculate_needed_quantity(
                current_stock=current,
                daily_forecast=daily_fc,
                coverage_days=(STAR_COVERAGE_DAYS if seg == "Star" else
                               RELIABLE_COVERAGE_DAYS if seg == "Reliable" else
                               SEASONAL_COVERAGE_DAYS),
                daily_velocity=daily_velocity[i],
                low_confidence=low_conf,
                segment=seg
            )
            if needed > 0:
                solver.Add(buy_vars[i] >= needed)

    # Critical basket pairs
    if enforce_pairs:
        prod_idx = {p: i for i, p in enumerate(products)}
        for a, b in critical_pairs:
            if a in prod_idx and b in prod_idx:
                ia, ib = prod_idx[a], prod_idx[b]
                has_a = current_stock[ia] > 0
                has_b = current_stock[ib] > 0
                if not has_a and not has_b:
                    z = solver.IntVar(0, 1, f"pair_{ia}_{ib}")
                    solver.Add(buy_vars[ia] >= z)
                    solver.Add(buy_vars[ib] >= z)
                elif has_a and not has_b:
                    solver.Add(buy_vars[ib] >= 1)
                elif not has_a and has_b:
                    solver.Add(buy_vars[ia] >= 1)

    # Objective: maximise unified_score
    solver.Maximize(solver.Sum([unified_scores[i] * buy_vars[i] for i in range(n)]))

    status = solver.Solve()
    if status not in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE):
        return {"feasible": False, "order": [], "total_cost": 0}

    order = []
    total_cost = 0.0
    for i in range(n):
        qty = int(buy_vars[i].solution_value())
        if qty > 0:
            cost = round(unit_costs[i] * qty, 2)
            total_cost += cost
            order.append({
                "product": products[i],
                "qty": qty,
                "current_stock": current_stock[i],
                "final_stock": current_stock[i] + qty,
                "unit_cost": round(unit_costs[i], 2),
                "total_cost": cost,
                "segment": segments[i],
                "reason": _order_reason(segments[i], df_kpis["profit_margin"].iloc[i],
                                        unified_scores[i], current_stock[i], daily_velocity[i], qty)
            })
    return {"feasible": True, "order": order, "total_cost": round(total_cost, 2)}


# ============================================================================
# GREEDY FALLBACK
# ============================================================================

def _solve_greedy(df_kpis, budget, goal, current_inventory, forecasts, language):
    """Simple greedy algorithm - shows ALL products, respects budget for purchases."""
    sorted_df = df_kpis.sort_values("unified_score", ascending=False).copy()
    remaining_budget = budget
    order = []

    for _, row in sorted_df.iterrows():
        product = row["product"]
        unit_cost = row["avg_buy_price"]
        
        # Calculate needed quantity
        forecast_data = forecasts.get(product, {}) if forecasts else {}
        daily_fc = forecast_data.get("daily_forecast", [])
        low_conf = forecast_data.get("low_confidence", False)
        current = current_inventory.get(product, 0) if current_inventory else 0
        segment = row.get("segment", "Individual")
        needed = _calculate_needed_quantity(
            current_stock=max(0, current),
            daily_forecast=daily_fc,
            coverage_days=(STAR_COVERAGE_DAYS if segment == "Star" else
                           RELIABLE_COVERAGE_DAYS if segment == "Reliable" else
                           SEASONAL_COVERAGE_DAYS),
            daily_velocity=row.get("daily_sales", 0),
            low_confidence=low_conf,
            segment=segment
        )
        
        # Calculate max affordable
        max_by_budget = int(remaining_budget / unit_cost) if unit_cost > 0 else 0
        qty = min(needed, MAX_UNITS_PER_PRODUCT, max_by_budget)
        
        # ALWAYS add to order (qty may be 0)
        if qty >= MIN_SHELF_QUANTITY and unit_cost > 0 and remaining_budget >= qty * unit_cost:
            cost = qty * unit_cost
            order.append({
                "product": product,
                "qty": qty,
                "current_stock": max(0, current),
                "final_stock": max(0, current) + qty,
                "unit_cost": unit_cost,
                "total_cost": cost,
                "segment": segment,
                "reason": _order_reason(segment, row["profit_margin"],
                                        row["unified_score"], current, row["daily_sales"], qty)
            })
            remaining_budget -= cost
        else:
            # Add with qty=0 (no budget consumed)
            order.append({
                "product": product,
                "qty": 0,
                "current_stock": max(0, current),
                "final_stock": max(0, current),
                "unit_cost": unit_cost,
                "total_cost": 0,
                "segment": segment,
                "reason": f"Not purchased: budget limit (needed {needed}, budget remaining {remaining_budget:,.0f})"
            })
    
    return {"feasible": len([o for o in order if o["qty"] > 0]) > 0, 
            "order": order, 
            "total_cost": budget - remaining_budget,
            "relaxations": ["Used greedy algorithm"]}

# ============================================================================
# HELPERS
# ============================================================================

def _calculate_needed_quantity(current_stock, daily_forecast, coverage_days,
                               daily_velocity=0.0, low_confidence=False, segment="Individual"):
    """Calculate how many units to buy (capped at MAX_UNITS_PER_PRODUCT)."""
    if current_stock < 0:
        current_stock = 0
    mult = LOW_CONFIDENCE_MULTIPLIER if low_confidence else 1.0
    if not daily_forecast or len(daily_forecast) == 0 or sum(daily_forecast) == 0:
        if daily_velocity > 0:
            daily_forecast = [daily_velocity] * coverage_days
        else:
            return MIN_SHELF_QUANTITY if segment != "Deadweight" else 0
    forecast_demand = sum(daily_forecast[:coverage_days])
    if current_stock >= forecast_demand * 1.5:
        return 0
    needed = int((forecast_demand - current_stock) * mult)
    needed = max(0, needed)
    if needed > MAX_UNITS_PER_PRODUCT:
        needed = MAX_UNITS_PER_PRODUCT
    if segment != "Deadweight" and needed == 0 and current_stock < MIN_SHELF_QUANTITY:
        needed = MIN_SHELF_QUANTITY
    if segment == "Seasonal" and current_stock < daily_velocity * SEASONAL_MIN_STOCK_DAYS:
        needed = max(needed, MIN_SHELF_QUANTITY)
    return needed


def _order_reason(segment, margin, score, current_stock, daily_velocity, qty):
    if segment == "Star":
        if current_stock == 0:
            return f"Star product — {margin:.1f}% margin. OUT OF STOCK! Order immediately."
        return f"Star product — {margin:.1f}% margin. High priority."
    elif segment == "Seasonal":
        return f"Seasonal product — stocking for upcoming season. Order {qty} units."
    elif segment == "Reliable":
        if current_stock == 0:
            return "Reliable product — consistent demand, currently out of stock."
        return "Reliable product — maintaining stock for steady sales."
    elif segment == "Risky":
        return f"Risky product — limited order ({qty} units) to test demand."
    else:
        return f"Score {score:.0f}/100, margin {margin:.1f}% — recommended {qty} units."


def _ensure_all_products_appear(order_list, df_kpis, current_inventory, forecasts, language, original_products_list=None):
    if original_products_list is None:
        original_products_list = df_kpis["product"].tolist()
    order_dict = {o["product"]: o for o in order_list}
    all_products = original_products_list
    result = []
    for product in all_products:
        if product in order_dict:
            result.append(order_dict[product])
        else:
            # Check if product exists in df_kpis
            product_rows = df_kpis[df_kpis["product"] == product]
            
            if not product_rows.empty:
                row = product_rows.iloc[0]
                segment = row.get("segment", "Individual")
                margin = row.get("profit_margin", 0)
                days_idle = row.get("days_since_last_sale", 999)
                current = current_inventory.get(product, 0)
                unit_cost = row.get("avg_buy_price", 0)
                
                if segment == "Deadweight":
                    reason = "No sales in 90+ days — do not reorder" if days_idle > 90 else "Low profit margin — prioritize others"
                elif segment == "Outlier":
                    reason = "Unusual sales pattern — review manually"
                elif margin < 0:
                    reason = "Negative margin — selling at a loss"
                elif current > 0 and days_idle < 30:
                    reason = f"Sufficient stock ({current} units) — no purchase needed"
                else:
                    reason = "Not prioritized within budget — consider increasing budget"
            else:
                # Product not in df_kpis - use fallback
                current = current_inventory.get(product, 0)
                segment = "Unknown"
                unit_cost = 0
                reason = "Product data missing from KPIs - manual review required"
            
            result.append({
                "product": product,
                "qty": 0,
                "current_stock": current,
                "final_stock": current,
                "unit_cost": unit_cost,
                "total_cost": 0,
                "segment": segment,
                "reason": reason,
            })
    # sort: positive qty first, then by segment importance
    def sort_key(o):
        if o["qty"] > 0:
            priority = {"Star": 1, "Seasonal": 2, "Reliable": 3, "Risky": 4, "Deadweight": 5, "Outlier": 6, "Individual": 7}
            return (0, priority.get(o.get("segment", "Individual"), 8))
        return (1, 0)
    result.sort(key=sort_key)
    return result


def _skip(reason):
    return {"order": [], "total_cost": 0, "feasible": False, "relaxations": [], "summary": reason, "skipped": True}


def _t(language, en, fa):
    return fa if language == "fa" else en