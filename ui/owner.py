"""
ui/owner.py — COMPLETE FIXED VERSION

Fixes:
- Most profitable products now show their rank (#1, #2, …)
- Purchase order table includes a "Rank" column (if available)
- All existing functionality preserved
"""

import json
import logging
import os
import shutil
import traceback
import warnings

os.environ["GRADIO_ANALYTICS_ENABLED"] = "False"
os.environ["GRADIO_SHARE"] = "False"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["GRADIO_ALLOW_FLAGGING"] = "never"
warnings.filterwarnings('ignore')

import gradio as gr
import pandas as pd

from models import loader
from output import reporter
from pipeline import runner
from ui.utils import health_tag, build_llm_text

try:
    from llm.agent import ask_llm
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False
    ask_llm = lambda *args, **kwargs: None

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

loader.load_all()


def _clear_shop_models(shop_id: str) -> None:
    shop_dir = os.path.join("models", "shops", shop_id)
    if os.path.exists(shop_dir):
        try:
            shutil.rmtree(shop_dir)
        except Exception as e:
            logger.warning(f"Could not clear models for shop '{shop_id}': {e}")


def _health_tag(score: int) -> str:
    return health_tag(score)


def _build_owner_markdown(report: dict) -> str:
    """Clean markdown dashboard with rank numbers"""
    if not report:
        return "No report available."

    health = report.get("health_score", 0)
    health_tag_text = _health_tag(health)
    quality = report.get("data_quality", 0)
    order_total = report.get("order_total", 0)
    optimizer_summary = report.get("optimizer_summary", "No order recommendation available.")

    # ========== ORDER TABLE (with rank column) ==========
    purchase_order = report.get("purchase_order", [])
    order_items = purchase_order 
    items_to_buy = [o for o in purchase_order if o.get("qty", 0) > 0]
    
    if purchase_order:
        # Build table with optional Rank column
        order_lines = []
        # Check if any order item has a 'rank' field
        has_rank = any(o.get("rank") is not None for o in order_items)
        if has_rank:
            order_lines.append("| Rank | Product | Current Stock | → Buy | Final Stock |")
            order_lines.append("|------|---------|---------------|-------|-------------|")
            for o in order_items[:10]:
                rank = o.get("rank", "?")
                product = o["product"][:25]
                current = o.get("current_stock", 0)
                qty = o.get("qty", 0)
                final = current + qty
                order_lines.append(f"| {rank} | {product} | {current:,} | **{qty}** | {final:,} |")
        else:
            order_lines.append("| Product | Current Stock | → Buy | Final Stock |")
            order_lines.append("|---------|---------------|-------|-------------|")
            for o in order_items[:10]:
                product = o["product"][:25]
                current = o.get("current_stock", 0)
                qty = o.get("qty", 0)
                final = current + qty
                order_lines.append(f"| {product} | {current:,} | **{qty}** | {final:,} |")
        order_table = "\n".join(order_lines)
        order_section = f"""
### Order Recommendation: {order_total:,.0f} budget used

{optimizer_summary}

{order_table}
"""
    else:
        order_section = f"""
### Order Recommendation: {order_total:,.0f} budget used

{optimizer_summary}
"""

    # ========== TOP 3 ACTIONS ==========
    actions = report.get("priority_actions", [])
    if actions:
        actions_text = "\n".join([
            f"{i+1}. {a['urgency']} **{a['title']}**\n   {a['description']}"
            for i, a in enumerate(actions)
        ])
    else:
        actions_text = "No priority actions were generated."

    # ========== FORECAST HIGHLIGHTS (FIXED: handle None values) ==========
    forecasts = report.get("products", [])
    forecast_lines = []
    # Filter products that have valid forecast with h30 value
    valid_forecasts = []
    for p in forecasts:
        fc = p.get("forecast", {})
        if fc and fc.get("h30") is not None and fc.get("h30") > 0:
            if not fc.get("skipped"):
                valid_forecasts.append(p)
    # Sort by h30 (descending)
    sorted_forecasts = sorted(valid_forecasts, key=lambda x: x.get("forecast", {}).get("h30", 0), reverse=True)
    for p in sorted_forecasts[:5]:
        fc = p.get("forecast", {})
        forecast_lines.append(f"- {p['product']}: {fc.get('h30', 0):.0f} units / 30 days")
    forecast_text = "\n".join(forecast_lines) if forecast_lines else "Not enough history to forecast popular products."

    # ========== DEADWEIGHT PRODUCTS ==========
    deadweight = report.get("to_liquidate", [])
    if deadweight:
        deadweight_lines = [f"- 💀 {p.get('product', 'Unknown')}" for p in deadweight[:8]]
        deadweight_text = "\n".join(deadweight_lines)
    else:
        deadweight_text = "No deadweight products."

    # ========== MOST PROFITABLE (WITH RANK) ==========
    products = report.get("products", [])
    # Sort by total profit and add rank numbers
    sorted_profitable = sorted(products, key=lambda x: x.get("total_profit", 0) or 0, reverse=True)
    profitable = sorted_profitable[:5]
    if profitable:
        profit_lines = []
        for i, p in enumerate(profitable, start=1):
            rank_display = f"#{i}"
            profit_millions = (p.get('total_profit', 0) or 0) / 1_000_000
            margin = p.get('profit_margin', 0) or 0
            profit_lines.append(f"- {rank_display} **{p['product']}**: {profit_millions:.1f}M profit ({margin:.0f}% margin)")
        profit_text = "\n".join(profit_lines)
    else:
        profit_text = "No profit data available."

    # ========== ROI COMPARISON ==========
    shop_roi = report.get("shop_roi", 0) or 0
    vs_bank = report.get("vs_bank", 0) or 0
    vs_gold = report.get("vs_gold", 0) or 0
    roi_icon = "✅" if vs_bank > 0 else "⚠️"

    # ========== ALERTS ==========
    alerts = report.get("alerts", [])
    alert_text = "\n".join([f"- {a}" for a in alerts]) if alerts else "No critical alerts."

    return f"""
### 🧠 Shop Health
**Health Score:** {health}/100 — {health_tag_text}
**Data Quality:** {quality}/100

---

{order_section}

---

### 🚨 Top 3 Actions
{actions_text}

---

### 📈 Forecast Highlights
{forecast_text}

---

### 💀 Deadweight Products (Put on Sale)
{deadweight_text}

---

### 🏆 Most Profitable Products
{profit_text}

---

### 💰 Profit vs Benchmarks
**Your Shop ROI:** {shop_roi:.1f}%
- vs Bank (23%): {vs_bank:+.1f}% {roi_icon}
- vs Gold (35%): {vs_gold:+.1f}%

---

### ⚠️ Alerts
{alert_text}

---

### 💡 Quick Tips
- **Out of stock?** Order from the table above
- **Deadweight products?** Run a clearance sale
- **Low profit?** Focus on most profitable products
"""


def _build_llm_text(report: dict, question: str, language: str) -> str:
    return build_llm_text(report, question, language, ask_llm)


def analyse_owner(file, budget, goal, language, shop_id, use_llm, question):
    if file is None:
        return "Please upload a sales file first.", "", ""

    try:
        with open(file.name, "rb") as f:
            file_bytes = f.read()

        filename = os.path.basename(file.name)
        budget_float = float(budget) if budget else 1_000_000.0
        sid = shop_id.strip() or "demo"
        result = runner.run_pipeline(file_bytes, filename, budget_float, sid, goal, language)
        
        if not result.get("passed"):
            return f"❌ {result.get('stop_reason', 'Pipeline failed — check your file.')}", "", ""

        report = reporter.assemble_and_save(result, sid)
        owner_text = _build_owner_markdown(report)
        llm_text = _build_llm_text(report, question or "", language) if use_llm and LLM_AVAILABLE else "LLM advisor is disabled or not available."
        cache_text = (
            "Reused cached shop models for the same CSV." if report.get("cache_status") == "reused"
            else "New CSV uploaded — shop models were reset and recomputed."
        )
        return owner_text, llm_text, f"✅ Analysis complete | Shop: {sid} | {cache_text}"

    except Exception as e:
        logger.error(f"Owner app error: {e}", exc_info=True)
        err = f"❌ Error: {e}\n\n{traceback.format_exc()}"
        return err, "", err


with gr.Blocks(title="SaleYar — Shop Advisor") as demo:
    gr.Markdown("# 🛍️ SaleYar — Shop Advisor\nA simple dashboard for shop owners. Upload your sales file and get the top actions.")

    with gr.Row():
        file_input = gr.File(label="Upload CSV / Excel", file_types=[".csv", ".xlsx", ".xls"])
        budget_input = gr.Number(label="Budget", value=100_000_000, precision=0)
        goal_input = gr.Dropdown(
            label="Optimization Goal",
            choices=["maximize_profit", "cover_customers", "reduce_risk"],
            value="maximize_profit",
        )
        lang_input = gr.Dropdown(label="Language", choices=["en", "fa"], value="en")
        shop_input = gr.Textbox(label="Shop ID", value="demo", placeholder="e.g. demo")
        llm_checkbox = gr.Checkbox(label="Use LLM advisor (optional)", value=True)
        llm_question = gr.Textbox(label="Ask the advisor", placeholder="What should I do next?", lines=1)
        run_btn = gr.Button("🚀 Analyze", variant="primary")

    owner_out = gr.Markdown()
    llm_out = gr.Markdown()
    status_out = gr.Textbox(label="Status", interactive=False)

    run_btn.click(
        fn=analyse_owner,
        inputs=[file_input, budget_input, goal_input, lang_input, shop_input, llm_checkbox, llm_question],
        outputs=[owner_out, llm_out, status_out],
    )


def run():
    demo.launch(server_name="0.0.0.0", server_port=7860, share=False)


if __name__ == "__main__":
    run()