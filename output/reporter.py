"""
reporter.py — OPTIMIZED FINAL REPORT

- Full JSON report (for debugging/API)
- Compact summary (~600‑800 tokens) for LLM and UI
- Health score and alerts
- Handles missing fields gracefully
"""

import json
import logging
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

logger = logging.getLogger(__name__)

REPORT_VERSION = "3.1"


def assemble_and_save(pipeline_result: dict, shop_id: str, save_to_disk: bool = False) -> dict:
    """Build final report, optionally save JSON."""
    report = _enrich(pipeline_result)
    report["summary"] = _build_summary(pipeline_result, report)

    if save_to_disk:
        save_dir = os.path.join("saved_reports", shop_id)
        os.makedirs(save_dir, exist_ok=True)
        date_str = datetime.now().strftime("%Y-%m-%d")
        path_latest = os.path.join(save_dir, "report_latest.json")
        path_dated = os.path.join(save_dir, f"report_{date_str}.json")
        for path in (path_latest, path_dated):
            with open(path, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2, default=str)
        # Also save summary separately for quick access
        summary_path = os.path.join(save_dir, "summary.json")
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(report["summary"], f, ensure_ascii=False, indent=2, default=str)
        logger.info(f"Report saved for shop '{shop_id}'")
    else:
        logger.info(f"Report generated for shop '{shop_id}' (not saved)")

    return report


def _build_summary(r: dict, report: dict) -> dict:
    """Ultra‑compact summary (~600‑800 tokens)."""
    inventory = r.get("inventory", {})
    products = report.get("products", [])

    total_revenue = sum(p.get("total_revenue", 0) for p in products)
    total_profit = sum(p.get("total_profit", 0) for p in products)

    # Top 5 by sales volume
    top_5 = sorted(products, key=lambda x: x.get("total_sold", 0), reverse=True)[:5]
    bottom_5 = sorted(products, key=lambda x: x.get("total_sold", 0))[:5]

    # Inventory issues (limit to 5 each)
    out_of_stock = [p for p, q in inventory.items() if q == 0][:5]
    low_stock = [f"{p}({q})" for p, q in inventory.items() if 0 < q < 20][:5]
    high_risk = [p["product"] for p in products if p.get("risk_score", 0) > 70][:5]

    # Forecast needs (limit to 5)
    forecast_needs = []
    for p in products[:20]:
        fc = p.get("forecast", {})
        h30 = _to_float(fc.get("h30", 0))
        current = inventory.get(p["product"], 0)
        if h30 > current and h30 > 0:
            forecast_needs.append(f"{p['product']}: need {int(h30 - current)}")
    forecast_needs = forecast_needs[:5]

    # Purchase order top 5
    purchase_order = report.get("purchase_order", [])
    to_buy = [f"{o['product']}({o['qty']})" for o in purchase_order if o.get("qty", 0) > 0][:5]

    # Segment breakdown (use segment_breakdown, fallback to segment_summary)
    seg_counts = report.get("segment_breakdown") or report.get("segment_summary", {})
    stars = [p["product"] for p in products if p.get("segment") == "Star"][:3]
    deadweight = [p["product"] for p in products if p.get("segment") == "Deadweight"][:3]

    customers = report.get("customers", {})
    champ_products = customers.get("champion_products", [])[:3]
    shop_roi = report.get("shop_roi", 0)
    vs_bank = report.get("vs_bank", 0)

    # Important alerts (only critical)
    alerts = [a for a in report.get("alerts", []) if "quality" in a.lower() or "stock" in a.lower() or "skip" in a.lower()][:3]
    skipped = [s.get("stage") for s in report.get("skipped_stages", [])]

    return {
        "version": REPORT_VERSION,
        "generated_at": datetime.now().isoformat(),
        "shop": {
            "health": report.get("health_score", 0),
            "revenue": round(total_revenue, 0),
            "profit": round(total_profit, 0),
            "roi": round(shop_roi, 1),
            "vs_bank": round(vs_bank, 1),
        },
        "urgent": {
            "out_of_stock": out_of_stock,
            "low_stock": low_stock,
            "order_now": to_buy,
        },
        "products": {
            "top_5": [{"name": p["product"], "sold": int(p.get("total_sold", 0))} for p in top_5],
            "bottom_5": [{"name": p["product"], "sold": int(p.get("total_sold", 0))} for p in bottom_5],
            "high_risk": high_risk,
            "forecast_needs": forecast_needs,
        },
        "segments": {
            "stars": stars,
            "deadweight": deadweight,
            "counts": seg_counts,
        },
        "customers": {
            "champions": champ_products,
            "segments": customers.get("summary", {}),
        },
        "actions": [a.get("title") for a in report.get("priority_actions", [])[:3]],
        "alerts": alerts,
        "missing": skipped,
    }


def _enrich(r: dict) -> dict:
    """Add computed fields (health, alerts, etc.) to full report."""
    report = r.get("report", {})
    if not report:
        return r

    products = report.get("products", [])
    language = r.get("language", "en")

    segment_breakdown = {}
    for p in products:
        seg = p.get("segment") or "Unknown"
        segment_breakdown[seg] = segment_breakdown.get(seg, 0) + 1

    to_liquidate = [
        p for p in products
        if p.get("segment") == "Deadweight" and (p.get("days_since_last_sale") or 0) > 60
    ]
    to_watch = [
        p for p in products
        if p.get("segment") in ("Risky", "Outlier")
    ]

    stages = r.get("stages", {})
    skipped = []
    for stage_key, stage_data in stages.items():
        if isinstance(stage_data, dict) and stage_data.get("skipped"):
            reason = stage_data.get("skip_reason") or f"{stage_key} was skipped."
            skipped.append({"stage": stage_key, "reason": reason})

    health_score = _calculate_health_score(report)
    shop_margin = _safe_avg(products, "profit_margin")
    benchmark_delta = round(shop_margin - config.RETAIL_AVG_MARGIN, 2)
    health_status, health_color = _health_label(health_score)
    alerts = _build_alerts(r, report, health_score)

    enriched = {
        **report,
        "segment_breakdown": segment_breakdown,
        "segment_summary": segment_breakdown,      # alias
        "to_liquidate": to_liquidate,
        "to_watch": to_watch,
        "skipped_stages": skipped,
        "health_score": health_score,
        "health_status": health_status,
        "health_color": health_color,
        "alerts": alerts,
        "shop_avg_margin": round(shop_margin, 2),
        "benchmark_margin": config.RETAIL_AVG_MARGIN,
        "benchmark_delta": benchmark_delta,
        "generated_at": datetime.now().isoformat(),
        "pipeline_elapsed": r.get("elapsed_seconds"),
        "shop_id": r.get("shop_id"),
        "language": language,
    }
    return enriched


def _calculate_health_score(report: dict) -> int:
    score = 0
    quality = report.get("data_quality", 0)
    score += quality * 0.25

    vs_bank = report.get("vs_bank", -10)
    if vs_bank >= 20:
        score += 25
    elif vs_bank >= 10:
        score += 20
    elif vs_bank >= 0:
        score += 12
    elif vs_bank >= -10:
        score += 5

    # Use segment_breakdown if available, else segment_summary
    breakdown = report.get("segment_breakdown") or report.get("segment_summary", {})
    total = max(sum(breakdown.values()), 1)
    good_pct = (breakdown.get("Star", 0) + breakdown.get("Reliable", 0)) / total * 100
    score += good_pct * 0.25

    products = report.get("products", [])
    if products:
        fresh = sum(1 for p in products if (p.get("days_since_last_sale") or 999) <= 30)
        fresh_pct = fresh / len(products) * 100
        score += fresh_pct * 0.25

    return int(round(min(100, max(0, score))))


def _health_label(score: int):
    if score >= 70:
        return "Strong", "green"
    if score >= 40:
        return "Moderate", "yellow"
    return "Needs attention", "red"


def _build_alerts(r: dict, report: dict, health_score: int) -> list:
    alerts = []
    if report.get("data_quality", 100) < 60:
        alerts.append("Data quality below 60. Check your file.")
    if health_score < 50:
        alerts.append("Overall shop health weak. Focus on fast‑moving products.")
    if report.get("optimizer_feasible") is False:
        alerts.append("Optimizer could not find a feasible order within budget.")
    if report.get("customers", {}).get("skipped"):
        alerts.append("Customer segmentation skipped (need at least 3 customers).")
    for stage in r.get("stages", {}).values():
        if isinstance(stage, dict) and stage.get("skipped"):
            alerts.append(stage.get("skip_reason", "A stage was skipped."))
    return alerts


def _safe_avg(products: list, key: str) -> float:
    vals = [p[key] for p in products if p.get(key) is not None]
    return float(sum(vals) / len(vals)) if vals else 0.0


def _to_float(value, default=0.0):
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def load_latest(shop_id: str) -> dict | None:
    path = os.path.join("saved_reports", shop_id, "report_latest.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_latest_summary(shop_id: str) -> dict | None:
    path = os.path.join("saved_reports", shop_id, "summary.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)