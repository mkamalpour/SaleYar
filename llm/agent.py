"""
llm/agent.py

LLM integration for SaleYar.
- talk=False (Gradio): full summary + 4 bullet points.
- talk=True (HTML): micro‑summary + 1‑sentence conversational answer, with tab guidance.
"""

import json
import logging
import urllib.error
import urllib.request

import config

logger = logging.getLogger(__name__)


def enabled() -> bool:
    return config.LLM_ENABLED and bool(config.LLM_ENDPOINT_URL)


def ask_llm(
    report: dict,
    question: str = "",
    language: str = "en",
    talk: bool = False,
    inventory: dict = None,
    forecasts: dict = None,
) -> str | None:
    if not enabled():
        return None
    try:
        prompt = _build_prompt(report, question, language, talk, inventory, forecasts)
        return _query_model(prompt)
    except Exception as e:
        logger.warning(f"LLM integration failed: {e}")
        return None


def _build_prompt(
    report: dict,
    question: str,
    language: str,
    talk: bool,
    inventory: dict,
    forecasts: dict,
) -> str:
    if language == "fa":
        intro = (
            "شما دستیار هوشمند فروشگاه SaleYar هستید. "
            "به سوال کاربر دقت کنید. پاسخ مفید بدهید. "
            ".بر اساس خلاصه داده‌هایی که در اختیار دارید پاسخ دهید"
        )
        question_text = f"سوال: {question}"
    else:
        intro = (
            "You are the SaleYar smart shop assistant. "
            "Pay attention to the user's question. Give helpful answer. "
            "Answer based on the provided data summary."
        )
        question_text = f"Question: {question}"

    if talk:
        summary = _micro_summary(report, language, inventory)
        # Add tab guide
        tab_guide = (
            "Dashboard tabs:\n"
            "- Overview: health, revenue, profit, top 5 products, urgent out-of-stock.\n"
            "- Purchase Orders: recommended purchase quantities with reasons.\n"
            "- Forecast: 30/60/90 day demand forecasts.\n"
            "- Products: ranked list with segment, revenue, margin, risk, last sale.\n"
            "- Segments: Star, Reliable, Deadweight, Risky, Seasonal, Outlier.\n"
            "- Basket Rules: products bought together.\n"
            "- Inventory: current stock levels and status.\n"
            "- Customers & ROI: customer segments and ROI vs bank/gold.\n"
            "- Settings: API and AI mode.\n"
        )
        answer_instruction = (
            "Answer in ONE very short sentence (max 10 words).\n"
            "If the user is just greeting (hi, hello, hey) or thanking (thanks, thank you, cheers), answer politely WITHOUT any numbers.\n"
            "If the user asks about data (sales, stock, revenue, profit, out of stock, top product), include the relevant number from the summary (health %, revenue, out‑of‑stock count, or top seller).\n"
            "If the user asks how to find something (e.g., 'how to see best products?'), tell them the exact dashboard tab name (e.g., 'Products tab').\n"
            "If they ask what you can do, suggest actions like 'reorder, check inventory, find top products'.\n"
            "Never just say 'I can help' – always give a specific example or action when appropriate."
        )
        # Combine summary, tab guide, and instruction
        prompt = f"{intro}\n\n{summary}\n\n{tab_guide}\n\n{question_text}\n{answer_instruction}\n"
    else:
        summary = _full_summary(report, language, inventory, forecasts)
        answer_instruction = "Answer in 4 short bullet points or a short paragraph."
        prompt = f"{intro}\n\n{summary}\n\n{question_text}\n{answer_instruction}\n"

    return prompt

def _micro_summary(report: dict, language: str, inventory: dict = None) -> str:
    """Extremely short summary – only health, revenue, profit, out‑of‑stock count."""
    products = report.get("products", [])
    health = report.get("health_score", 0)
    total_revenue = sum(p.get("total_revenue", 0) for p in products)
    total_profit = sum(p.get("total_profit", 0) for p in products)
    out_count = 0
    if inventory:
        out_count = sum(1 for q in inventory.values() if q == 0)
    top_product = ""
    if products:
        top_product = max(products, key=lambda x: x.get("total_revenue", 0)).get("product", "")
    if language == "fa":
        lines = [
            f"سلامت: {health}% | درآمد: {total_revenue/1e6:.0f}M | سود: {total_profit/1e6:.0f}M",
            f"کالای تمام شده: {out_count}",
            f"پرفروش‌ترین: {top_product}" if top_product else ""
        ]
    else:
        lines = [
            f"Health: {health}% | Revenue: {total_revenue/1e6:.0f}M | Profit: {total_profit/1e6:.0f}M",
            f"Out of stock: {out_count}",
            f"Top seller: {top_product}" if top_product else ""
        ]
    return "\n".join([l for l in lines if l])


def _full_summary(report: dict, language: str, inventory: dict, forecasts: dict) -> str:
    """Detailed summary for bullet‑point mode (Gradio)."""
    lines = []
    products = report.get("products", [])

    health = report.get("health_score", 0)
    data_quality = report.get("data_quality", 0)
    lines.append(f"Shop health: {health}/100 | Data quality: {data_quality}/100")

    total_revenue = sum(p.get("total_revenue", 0) for p in products)
    total_profit = sum(p.get("total_profit", 0) for p in products)
    lines.append(f"Total revenue: {total_revenue:,.0f} Toman | Profit: {total_profit:,.0f} Toman")

    # Top 5 by revenue
    top_rev = sorted(products, key=lambda x: x.get("total_revenue", 0), reverse=True)[:5]
    if top_rev:
        lines.append("Top products (revenue, margin%):")
        for p in top_rev:
            rev_m = p.get("total_revenue", 0) / 1_000_000
            margin = p.get("profit_margin", 0)
            lines.append(f"  - {p.get('product')}: {rev_m:.1f}M Toman, {margin:.1f}% margin")

    # Bottom 5 by sales
    bottom_sales = sorted(products, key=lambda x: x.get("total_sold", 0))[:5]
    if bottom_sales and len(products) > 5:
        lines.append("Worst selling products (units):")
        for p in bottom_sales:
            lines.append(f"  - {p.get('product')}: {p.get('total_sold', 0)} units")

    # Segments
    seg_counts = report.get("segment_breakdown") or report.get("segment_summary", {})
    if seg_counts:
        lines.append("Product segments:")
        for seg, cnt in seg_counts.items():
            lines.append(f"  - {seg}: {cnt}")

    # Inventory
    if inventory:
        out_stock = [p for p, q in inventory.items() if q == 0][:5]
        low_stock = [f"{p}({q})" for p, q in inventory.items() if 0 < q < 20][:5]
        over_stock = [f"{p}({q})" for p, q in inventory.items() if q > 200][:3]
        if out_stock:
            lines.append(f"Out of stock: {', '.join(out_stock)}")
        if low_stock:
            lines.append(f"Low stock (<20): {', '.join(low_stock)}")
        if over_stock:
            lines.append(f"Overstock (>200): {', '.join(over_stock)}")

        # Forecast needs
        if forecasts:
            needs = []
            for prod, fc in forecasts.items():
                h30 = fc.get("h30")
                if h30 is None:
                    continue
                h30 = float(h30)
                stock = inventory.get(prod, 0)
                if h30 > stock and h30 > 0:
                    needs.append(f"{prod}: need {int(h30 - stock)}")
            if needs:
                lines.append(f"Forecast needs (30d): {', '.join(needs[:5])}")

    # Basket rules
    basket_rules = report.get("basket_rules", [])
    if basket_rules:
        lines.append("Frequent product pairs:")
        for r in basket_rules[:3]:
            antecedent = " + ".join(r.get("antecedent", []))
            consequent = " + ".join(r.get("consequent", []))
            conf = r.get("confidence", 0) * 100
            lines.append(f"  - {antecedent} → also {consequent} ({conf:.0f}% confidence)")

    # Customer segments
    customers = report.get("customers", {})
    cust_summary = customers.get("summary", {})
    if cust_summary:
        lines.append("Customer segments:")
        for seg, cnt in cust_summary.items():
            lines.append(f"  - {seg}: {cnt}")

    # Priority actions
    actions = report.get("priority_actions", [])
    if actions:
        lines.append("Priority actions:")
        for a in actions[:3]:
            urgency = a.get("urgency", "")
            title = a.get("title", "")
            lines.append(f"  - {urgency} {title}")

    # Order total & alerts
    order_total = report.get("order_total")
    if order_total:
        lines.append(f"Recommended order total: {order_total:,.0f} Toman")
    alerts = report.get("alerts", [])
    if alerts:
        lines.append(f"Alerts: {', '.join(alerts[:3])}")

    # High risk products
    top_risk = sorted(
        [p for p in products if p.get("risk_score") is not None],
        key=lambda p: p.get("risk_score", 0),
        reverse=True
    )[:3]
    if top_risk:
        lines.append("High risk products (score>70):")
        for p in top_risk:
            lines.append(f"  - {p.get('product')}: risk {p.get('risk_score', 0):.0f}")

    return "\n".join(lines)


def _query_model(prompt: str) -> str | None:
    """Query LM Studio API at /api/v1/chat endpoint (also works with Ollama)."""
    try:
        data = {
            "input": prompt,
            "temperature": 0.7
        }
        if config.LLM_MODEL_NAME and config.LLM_MODEL_NAME.strip():
            data["model"] = config.LLM_MODEL_NAME

        json_data = json.dumps(data).encode('utf-8')
        request = urllib.request.Request(
            config.LLM_ENDPOINT_URL,
            data=json_data,
            headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
            method='POST'
        )

        with urllib.request.urlopen(request, timeout=config.LLM_TIMEOUT_SECONDS) as response:
            response_data = json.loads(response.read().decode('utf-8'))

        # Parse common response formats
        if 'choices' in response_data and len(response_data['choices']) > 0:
            choice = response_data['choices'][0]
            if 'message' in choice and 'content' in choice['message']:
                return choice['message']['content'].strip()
            elif 'text' in choice:
                return choice['text'].strip()
        elif 'output' in response_data:
            out = response_data['output']
            if isinstance(out, list):
                for item in out:
                    if isinstance(item, dict) and item.get('type') == 'message' and 'content' in item:
                        return item['content'].strip()
                if out and isinstance(out[-1], dict) and 'content' in out[-1]:
                    return out[-1]['content'].strip()
                return str(out)
            else:
                return out.strip() if isinstance(out, str) else str(out)
        elif 'response' in response_data:
            resp = response_data['response']
            if isinstance(resp, list):
                for item in resp:
                    if isinstance(item, dict) and item.get('type') == 'message' and 'content' in item:
                        return item['content'].strip()
                if resp and isinstance(resp[-1], dict) and 'content' in resp[-1]:
                    return resp[-1]['content'].strip()
                return str(resp)
            else:
                return resp.strip() if isinstance(resp, str) else str(resp)

        logger.error(f"Unexpected LLM response format: {response_data}")
        return None
    except Exception as e:
        logger.error(f"LLM query error: {e}")
        return None