"""
ui/developer.py — FULLY FIXED with working search & rank column
"""

import json
import logging
import os
import shutil
import subprocess
import sys
import traceback
import warnings

# ============================================================================
# ENVIRONMENT SETUP
# ============================================================================

os.environ["GRADIO_ANALYTICS_ENABLED"] = "False"
os.environ["GRADIO_SHARE"] = "False"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["GRADIO_ALLOW_FLAGGING"] = "never"
warnings.filterwarnings('ignore')

# ============================================================================
# IMPORTS
# ============================================================================

import gradio as gr
import pandas as pd
import matplotlib.pyplot as plt
from io import BytesIO
import base64
import numpy as np

from models import loader
from output import reporter
from pipeline import runner
from ui.utils import health_tag, build_llm_text
import config

try:
    from llm.agent import ask_llm
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False
    ask_llm = lambda *args, **kwargs: None

# ============================================================================
# GLOBALS
# ============================================================================

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

loader.load_all()

_cleaned_df = None
_cleaned_stats = None

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def _clear_shop_models(shop_id: str) -> None:
    shop_dir = os.path.join("models", "shops", shop_id)
    if os.path.exists(shop_dir):
        try:
            shutil.rmtree(shop_dir)
        except Exception as e:
            logger.warning(f"Could not clear models for shop '{shop_id}': {e}")

def _health_tag(score: int) -> str:
    return health_tag(score)

def _build_llm_text(report: dict, question: str, language: str) -> str:
    return build_llm_text(report, question, language, ask_llm)

def to_finglish(text: str) -> str:
    """Convert Persian/Arabic text to Finglish (Latin script)"""
    if not text or not isinstance(text, str):
        return text
    digits = {'۰':'0','۱':'1','۲':'2','۳':'3','۴':'4',
              '۵':'5','۶':'6','۷':'7','۸':'8','۹':'9'}
    mapping = {
        'ا':'a','آ':'a','أ':'a','إ':'e','ب':'b','پ':'p','ت':'t','ث':'s',
        'ج':'j','چ':'ch','ح':'h','خ':'kh','ي':'i','د':'d','ذ':'z','ر':'r',
        'ز':'z','ژ':'zh','س':'s','ش':'sh','ص':'s','ض':'z','ط':'t','ظ':'z',
        'ع':'a','غ':'gh','ف':'f','ق':'gh','ک':'k','گ':'g','ل':'l','م':'m',
        'ن':'n','و':'o','ه':'h','ی':'y','ى':'y','ئ':'e','ؤ':'o','ء':'',
        ' ': ' ', ',':',', '.':'.', '-':'-', '/':'/', '_':'_',
        '(':'(', ')':')', '!':'!', '?':'?', ':':':', ';':';',
    }
    text = ''.join(digits.get(c,c) for c in text)
    result = []
    for char in text:
        if char in mapping:
            converted = mapping[char]
            if converted:
                result.append(converted)
        else:
            result.append(char)
    output = ''.join(result)
    output = ' '.join(output.split())
    return output

# ============================================================================
# DATA ANALYSIS FUNCTIONS (Health & Quality Tab)
# ============================================================================

def get_column_stats(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or len(df) == 0:
        return pd.DataFrame()
    stats = []
    for col in df.columns:
        stats.append({
            'Column': col,
            'Type': str(df[col].dtype),
            'Non-Null': df[col].count(),
            'Null %': round((df[col].isnull().sum() / len(df)) * 100, 1),
            'Unique': df[col].nunique(),
            'Sample Value': str(df[col].iloc[0])[:50] if len(df) > 0 else ''
        })
    return pd.DataFrame(stats)

def get_product_quantity_summary(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or len(df) == 0:
        return pd.DataFrame()
    df = df.copy()
    product_col = 'product' if 'product' in df.columns else 'نام کالا'
    qty_col = 'qty' if 'qty' in df.columns else 'تعداد'
    date_col = 'date' if 'date' in df.columns else 'تاریخ'
    price_col = 'sell_price' if 'sell_price' in df.columns else 'قیمت فروش'
    if product_col not in df.columns or qty_col not in df.columns:
        return pd.DataFrame()
    df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
    is_sale = df['transaction_type'] == 'sale'
    is_purchase = df['transaction_type'] == 'purchase'
    is_return_sale = df['transaction_type'] == 'return_sale'
    is_return_purchase = df['transaction_type'] == 'return_purchase'
    all_products = df[product_col].unique()
    sales = df[is_sale].groupby(product_col)[qty_col].sum().reindex(all_products, fill_value=0)
    purchases = df[is_purchase].groupby(product_col)[qty_col].sum().reindex(all_products, fill_value=0)
    returns_customer_data = df[is_return_sale].copy()
    if len(returns_customer_data) > 0:
        returns_customer_data[qty_col] = returns_customer_data[qty_col].abs()
        returns_customer = returns_customer_data.groupby(product_col)[qty_col].sum().reindex(all_products, fill_value=0)
    else:
        returns_customer = pd.Series(0, index=all_products)
    returns_supplier_data = df[is_return_purchase].copy()
    if len(returns_supplier_data) > 0:
        returns_supplier_data[qty_col] = returns_supplier_data[qty_col].abs()
        returns_supplier = returns_supplier_data.groupby(product_col)[qty_col].sum().reindex(all_products, fill_value=0)
    else:
        returns_supplier = pd.Series(0, index=all_products)
    net_change = (purchases + returns_customer - sales - returns_supplier).fillna(0)
    logger.debug(f"Calculated net change for {len(net_change)} products")
    df['month'] = df[date_col].dt.month
    monthly_sales = df[is_sale].groupby([product_col, 'month'])[qty_col].sum().reset_index()
    peak_idx = monthly_sales.groupby(product_col)[qty_col].idxmax()
    peak_month = monthly_sales.loc[peak_idx].set_index(product_col)['month'].to_dict()
    persian_months = {1:'فروردین',2:'اردیبهشت',3:'خرداد',4:'تیر',5:'مرداد',6:'شهریور',7:'مهر',8:'آبان',9:'آذر',10:'دی',11:'بهمن',12:'اسفند'}
    df['total_value'] = df[is_sale][qty_col] * df[is_sale][price_col]
    total_value = df[is_sale].groupby(product_col)['total_value'].sum().fillna(0)
    avg_price = (total_value / sales).fillna(0).replace([np.inf, -np.inf], 0)
    all_products_set = set(sales.index) | set(purchases.index) | set(returns_customer.index) | set(returns_supplier.index)
    result = pd.DataFrame(index=list(all_products_set))
    result['Product'] = result.index
    result['Sales'] = sales
    result['Purchases'] = purchases
    result['Returns (Customer)'] = returns_customer
    result['Returns (Supplier)'] = returns_supplier
    result['net_change'] = net_change
    result['Peak Month'] = pd.Series(peak_month).reindex(result.index).map(persian_months).fillna('نامشخص')
    result['avg price'] = avg_price
    result = result.fillna(0)
    result['net_change'] = pd.to_numeric(result['net_change'], errors='coerce').fillna(0)
    result['avg price'] = pd.to_numeric(result['avg price'], errors='coerce').fillna(0)
    result = result.sort_values('net_change', ascending=False).reset_index(drop=True)
    columns = ['Product','Sales','Purchases','Returns (Customer)','Returns (Supplier)','net_change','Peak Month','avg price']
    result = result[columns]
    return result.head(50)

def create_sales_trend_chart(df: pd.DataFrame) -> str:
    if df is None or len(df) == 0:
        return ""
    try:
        date_col = 'date' if 'date' in df.columns else 'تاریخ'
        qty_col = 'qty' if 'qty' in df.columns else 'تعداد'
        if date_col not in df.columns or qty_col not in df.columns:
            return ""
        df_copy = df.copy()
        df_copy = df_copy[df_copy['transaction_type'] == 'sale']
        df_copy[date_col] = pd.to_datetime(df_copy[date_col], errors='coerce')
        daily_sales = df_copy.groupby(date_col)[qty_col].sum().reset_index()
        daily_sales.columns = ['date','sales']
        daily_sales = daily_sales.sort_values('date')
        if len(daily_sales) == 0:
            return "No sales data available"
        cap = daily_sales['sales'].quantile(0.99)
        daily_sales['sales_capped'] = daily_sales['sales'].clip(upper=cap)
        daily_sales['ma7'] = daily_sales['sales_capped'].rolling(window=7, min_periods=1).mean()
        fig, ax = plt.subplots(figsize=(12,5))
        ax.bar(daily_sales['date'], daily_sales['sales_capped'], alpha=0.3, color='steelblue', label='Daily Sales', width=0.8)
        ax.plot(daily_sales['date'], daily_sales['ma7'], color='red', linewidth=2.5, label='7-day Trend', marker='o', markersize=2)
        ax.set_xlabel('Date')
        ax.set_ylabel('Quantity Sold')
        ax.set_title('Sales Trend (Customer Demand)')
        ax.legend()
        ax.grid(True, alpha=0.3)
        plt.xticks(rotation=45)
        plt.tight_layout()
        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
        buf.seek(0)
        img_base64 = base64.b64encode(buf.read()).decode('utf-8')
        plt.close()
        return f'<img src="data:image/png;base64,{img_base64}" style="width:100%"/>'
    except Exception as e:
        return f"Could not generate chart: {str(e)[:50]}"

def create_top_products_chart(df: pd.DataFrame) -> str:
    if df is None or len(df) == 0:
        return ""
    try:
        product_col = 'product' if 'product' in df.columns else 'نام کالا'
        qty_col = 'qty' if 'qty' in df.columns else 'تعداد'
        if product_col not in df.columns or qty_col not in df.columns:
            return "Missing required columns"
        df_copy = df.copy()
        df_copy[qty_col] = pd.to_numeric(df_copy[qty_col], errors='coerce').fillna(0)
        df_copy = df_copy[df_copy['transaction_type'] == 'sale']
        if len(df_copy) == 0:
            return "No sales data available"
        top_products = df_copy.groupby(product_col)[qty_col].sum().nlargest(10).reset_index()
        if len(top_products) == 0:
            return "No data to display"
        top_products['display_name'] = top_products[product_col].apply(to_finglish)
        fig, ax = plt.subplots(figsize=(10,6))
        colors = plt.cm.Blues(np.linspace(0.4,0.9,len(top_products)))
        ax.barh(top_products['display_name'], top_products[qty_col], color=colors)
        ax.set_xlabel(to_finglish('Total Quantity Sold'))
        ax.set_title(to_finglish('Top 10 Products by Sales'))
        ax.invert_yaxis()
        for i,v in enumerate(top_products[qty_col]):
            ax.text(v+max(top_products[qty_col])*0.01, i, f'{v:,.0f}', va='center', fontsize=9)
        plt.tight_layout()
        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
        buf.seek(0)
        img_base64 = base64.b64encode(buf.read()).decode('utf-8')
        plt.close()
        return f'<img src="data:image/png;base64,{img_base64}" style="width:100%"/>'
    except Exception as e:
        return f"Could not generate chart: {str(e)[:50]}"

def create_data_quality_report(df: pd.DataFrame, original_rows: int = None) -> str:
    if df is None or len(df) == 0:
        return "No data available"
    issues = []
    for col in df.columns:
        null_pct = (df[col].isnull().sum() / len(df)) * 100
        if null_pct > 0:
            issues.append(f"- Column '{col}': {null_pct:.1f}% missing values")
    price_col = 'sell_price' if 'sell_price' in df.columns else 'قیمت فروش'
    if price_col in df.columns:
        zero_prices = len(df[df[price_col] <= 0])
        if zero_prices > 0:
            issues.append(f"- {zero_prices} rows with zero/negative selling price")
    qty_col = 'qty' if 'qty' in df.columns else 'تعداد'
    if qty_col in df.columns:
        zero_qty = len(df[df[qty_col] <= 0])
        if zero_qty > 0:
            issues.append(f"- {zero_qty} rows with zero/negative quantity")
    duplicates = df.duplicated().sum()
    if duplicates > 0:
        issues.append(f"- {duplicates} duplicate rows found")
    if not issues:
        issues.append("✅ No data quality issues detected")
    report = "### 📋 Data Quality Report\n\n"
    report += "#### Issues Found & Fixed:\n" + "\n".join(issues) + "\n\n"
    if original_rows:
        report += f"#### Data Shape:\n"
        report += f"- Original rows: {original_rows:,}\n"
        report += f"- After cleaning: {len(df):,}\n"
        report += f"- Rows removed: {original_rows - len(df):,} ({(1 - len(df)/original_rows)*100:.1f}%)\n"
    return report

def render_inventory(report_data: dict, inventory: dict) -> str:
    if not inventory:
        return "No inventory data. Upload a file or enter current stock manually."
    products = report_data.get("products", [])
    rows = []
    for p in products:
        product_name = p["product"]
        current = inventory.get(product_name, 0)
        forecast = p.get("forecast", {})
        h30 = forecast.get("h30", 0)
        low_conf = forecast.get("low_confidence", False)
        if h30 is None:
            h30 = 0
        daily_avg = h30 / 30 if h30 > 0 else 0
        days_left = int(current / daily_avg) if daily_avg > 0 and current > 0 else 999 if current > 0 else 0
        if current == 0 and h30 > 0:
            action = "🔴 ORDER NOW"
        elif days_left < 7 and days_left > 0:
            action = "🟡 ORDER THIS WEEK"
        elif 7 <= days_left < 14:
            action = "📦 ORDER SOON"
        elif days_left > 60 and current > 0:
            action = "🛑 RUN SALE"
        elif low_conf and current > 0:
            action = "❓ CHECK MANUALLY"
        elif current > 0:
            action = "✅ OK"
        else:
            action = "⚪ NO SALES"
        days_display = f"{days_left}d" if days_left > 0 and days_left < 999 else "∞" if current > 0 else "0"
        rows.append({
            "Product": product_name[:25],
            "Stock": f"{current:,}",
            "Daily Sale": f"{daily_avg:.1f}" if daily_avg > 0 else "0",
            "Days Left": days_display,
            "Action": action,
        })
    urgency_order = {"🔴 ORDER NOW":1,"🟡 ORDER THIS WEEK":2,"📦 ORDER SOON":3,"🛑 RUN SALE":4,"❓ CHECK MANUALLY":5,"✅ OK":6,"⚪ NO SALES":7}
    rows.sort(key=lambda x: urgency_order.get(x["Action"],99))
    df = pd.DataFrame(rows)
    out_of_stock = sum(1 for r in rows if r["Action"] == "🔴 ORDER NOW")
    low_stock = sum(1 for r in rows if r["Action"] in ["🟡 ORDER THIS WEEK","📦 ORDER SOON"])
    overstock = sum(1 for r in rows if r["Action"] == "🛑 RUN SALE")
    healthy = sum(1 for r in rows if r["Action"] == "✅ OK")
    output = f"""
## 📦 Inventory Status

### 📊 Summary
| Status | Count |
|--------|-------|
| 🔴 Out of Stock / Order Now | {out_of_stock} |
| 🟡 Low Stock (Order Soon) | {low_stock} |
| 🟢 Healthy Stock | {healthy} |
| 🛑 Overstock (Run Sale) | {overstock} |

---

### 📋 Detailed Inventory

{df.to_markdown(index=False)}

---
### 🎯 What Each Action Means

| Action | What To Do |
|--------|------------|
| 🔴 ORDER NOW | Out of stock — you're losing sales |
| 🟡 ORDER THIS WEEK | Less than 7 days of stock left |
| 📦 ORDER SOON | 7-14 days of stock left |
| 🛑 RUN SALE | Too much stock (60+ days) — put on discount |
| ❓ CHECK MANUALLY | Not enough sales data — use your judgment |
| ✅ OK | Stock level is good |
| ⚪ NO SALES | Product never sells — consider removing |

---
*Calculated using 30-day sales forecast | Days Left = Stock ÷ Daily Average Sale*
"""
    return output


def filter_products_table(products_list, inventory_dict, search_term):
    """Filter products by search term and generate HTML table (identical to original)"""
    if not products_list:
        return "No products analyzed."
    
    segment_icons = {"Star":"⭐","Reliable":"✅","Deadweight":"💀",
                     "Risky":"⚠️","Seasonal":"📅","Outlier":"❓","Individual":"📌"}
    segment_colors = {"Star":"#f1c40f","Reliable":"#2ecc71","Deadweight":"#e74c3c",
                      "Risky":"#e67e22","Seasonal":"#3498db","Outlier":"#95a5a6","Individual":"#9b59b6"}
    
    # Filter by search term
    search_lower = search_term.lower().strip() if search_term else ""
    filtered = []
    for p in products_list:
        if search_lower == "" or search_lower in p["product"].lower():
            filtered.append(p)
    
    if not filtered:
        return f"❌ No products found matching '{search_term}'"
    
    # Sort by profit (same as original)
    sorted_products = sorted(filtered, key=lambda x: x.get("unified_score", 0), reverse=True)
    
    def color_risk(val):
        if val < 30: return f'🟢 {val:.2f}'
        elif val < 70: return f'🟡 {val:.2f}'
        else: return f'🔴 {val:.2f}'
    
    # Build HTML table (IDENTICAL to original, no extra text)
    html = '<div style="overflow-x: auto; max-height: 500px;">'
    html += '<table style="width: 100%; border-collapse: collapse; font-size: 13px;">'
    html += '<thead style="position: sticky; top: 0; background: #2c3e50;">'
    html += '<tr>'
    html += '<th style="padding: 10px 8px; color: white; text-align: center; width: 60px;">Rank</th>'
    html += '<th style="padding: 10px 8px; color: white; text-align: left;">Product</th>'
    html += '<th style="padding: 10px 8px; color: white; text-align: center;">Segment</th>'
    html += '<th style="padding: 10px 8px; color: white; text-align: center;">Stock</th>'
    html += '<th style="padding: 10px 8px; color: white; text-align: center;">Rev(M)</th>'
    html += '<th style="padding: 10px 8px; color: white; text-align: center;">Profit(M)</th>'
    html += '<th style="padding: 10px 8px; color: white; text-align: center;">Margin%</th>'
    html += '<th style="padding: 10px 8px; color: white; text-align: center;">Risk</th>'
    html += '<th style="padding: 10px 8px; color: white; text-align: center;">Last Sale</th>'
    html += '<th style="padding: 10px 8px; color: white; text-align: left;">Why</th>'
    html += '</tr>'
    html += '</thead><tbody>'
    
    for i, p in enumerate(sorted_products[:100], 1):
        margin = p.get("profit_margin", 0)
        margin_color = 'green' if margin > 20 else 'orange' if margin > 10 else 'red'
        stock = int(inventory_dict.get(p["product"], 0))
        stock_display = f"{stock:,}" if stock > 0 else "0"
        segment = p.get("segment", "Individual")
        segment_icon = segment_icons.get(segment, "📦")
        segment_color = segment_colors.get(segment, "#ffffff")
        risk_val = p.get("risk_score", 0)
        if risk_val < 30:
            risk_display = f'🟢 {risk_val:.2f}'
        elif risk_val < 70:
            risk_display = f'🟡 {risk_val:.2f}'
        else:
            risk_display = f'🔴 {risk_val:.2f}'
        # Keep full "Why" text (no truncation)
        why = p.get("risk_explanation", "?")
        
        html += '<tr style="border-bottom: 1px solid #e2e8f0;">'
        html += f'<td style="padding: 8px 8px; text-align: center; font-weight: bold; background-color: #f0f0f0;">{i}</td>'
        html += f'<td style="padding: 8px 8px; text-align: left; max-width: 150px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="{p["product"]}">{p["product"]}</td>'
        html += f'<td style="padding: 8px 8px; text-align: center;"><span style="background: {segment_color}20; color: {segment_color}; padding: 2px 8px; border-radius: 12px; font-size: 11px;">{segment_icon} {segment}</span></td>'
        html += f'<td style="padding: 8px 8px; text-align: center;">{stock_display}</td>'
        html += f'<td style="padding: 8px 8px; text-align: center;">{round(p.get("total_revenue", 0) / 1_000_000, 1):,.1f}</td>'
        html += f'<td style="padding: 8px 8px; text-align: center;">{round(p.get("total_profit", 0) / 1_000_000, 1):,.1f}</td>'
        html += f'<td style="padding: 8px 8px; text-align: center; color: {margin_color}; font-weight: 500;">{margin:.1f}%</td>'
        html += f'<td style="padding: 8px 8px; text-align: center;">{risk_display}</td>'
        html += f'<td style="padding: 8px 8px; text-align: center;">{p.get("days_since_last_sale", 0)}d</td>'
        html += f'<td style="padding: 8px 8px; text-align: left; max-width: 200px;">{why}</td>'
        html += '</tr>'
    html += '</tbody>\\table</div>'
    html += '<br><small>⭐ Star | ✅ Reliable | 💀 Deadweight | ⚠️ Risky | 📅 Seasonal | ❓ Outlier | Stock = current inventory | 🟢 Safe | 🟡 Caution | 🔴 High Risk</small>'
    
    return html

# ============================================================================
# MAIN ANALYSIS FUNCTION
# ============================================================================

def analyse(file, budget, goal, language, shop_id, use_llm, question):
    global _cleaned_df, _cleaned_stats
    
    if file is None:
        empty = [None] * 12
        return empty + ["❌ Please upload a file first."]
    
    try:
        with open(file.name, "rb") as f:
            file_bytes = f.read()
        filename = os.path.basename(file.name)
        budget_float = float(budget) if budget else 1_000_000.0
        sid = shop_id.strip() or "demo"
        result = runner.run_pipeline(file_bytes, filename, budget_float, sid, goal, language)
        
        if not result.get("passed"):
            msg = f"❌ {result.get('stop_reason', 'Pipeline failed — check your data.')}"
            return [None] * 12 + [msg]
        
        report_data = reporter.assemble_and_save(result, sid)
        
        _cleaned_df = result.get('df')
        _cleaned_stats = {
            'original_rows': result.get('original_rows', len(_cleaned_df) if _cleaned_df is not None else 0),
            'quality_score': report_data.get('data_quality', 0)
        }
        
        data_quality = report_data.get('data_quality', 0)
        health = report_data.get('health_score', 0)
        inventory = result.get('inventory', {})
        products = report_data.get("products", [])
        
        # ========== STAGE 9: PRIORITY ACTIONS ==========
        products_kpis = report_data.get('products', [])
        forecasts_dict = {p['product']: p.get('forecast', {}) for p in products_kpis if p.get('forecast')}
        basket_rules = report_data.get('basket_rules', [])
        customers_data = report_data.get('customers', {})
        optimizer_data = report_data.get('purchase_order_info', {})
        priority_actions = []
        try:
            from pipeline.stage9_priority import run as priority_run
            priority_actions = priority_run(
                df=_cleaned_df,
                products=products_kpis,
                forecasts=forecasts_dict,
                basket_rules=basket_rules,
                customers=customers_data,
                optimizer=optimizer_data,
                language=language
            )
        except Exception as e:
            logger.warning(f"Stage 9 priority actions failed: {e}")
            priority_actions = [{"urgency":"⚠️","title":"Priority actions not available","description":str(e),"product":None}]
        
        # ========== TAB 1: HEALTH & QUALITY ==========
        quality_report = create_data_quality_report(_cleaned_df, _cleaned_stats.get('original_rows'))
        if _cleaned_df is not None and len(_cleaned_df) > 0:
            qty_col = 'qty' if 'qty' in _cleaned_df.columns else 'تعداد'
            price_col = 'sell_price' if 'sell_price' in _cleaned_df.columns else 'قیمت فروش'
            invoice_col = 'invoice_id' if 'invoice_id' in _cleaned_df.columns else 'شماره فاکتور'
            customer_col = 'customer_id' if 'customer_id' in _cleaned_df.columns else 'کد مشتری'
            total_qty = _cleaned_df[qty_col].sum() if qty_col in _cleaned_df.columns else 0
            total_revenue = (_cleaned_df[qty_col] * _cleaned_df[price_col]).sum() if qty_col in _cleaned_df.columns and price_col in _cleaned_df.columns else 0
            unique_invoices = _cleaned_df[invoice_col].nunique() if invoice_col in _cleaned_df.columns else 0
            unique_customers = _cleaned_df[customer_col].nunique() if customer_col in _cleaned_df.columns else 0
            date_col = 'date' if 'date' in _cleaned_df.columns else 'تاریخ'
            if date_col in _cleaned_df.columns:
                _cleaned_df[date_col] = pd.to_datetime(_cleaned_df[date_col], errors='coerce')
                min_date = _cleaned_df[date_col].min()
                max_date = _cleaned_df[date_col].max()
                date_range = f"{min_date.strftime('%Y-%m-%d')} to {max_date.strftime('%Y-%m-%d')}" if pd.notna(min_date) and pd.notna(max_date) else "Unknown"
            else:
                date_range = "Unknown"
            stats_cards = f"""
### 📊 Dataset Overview

| Metric | Value |
|--------|-------|
| **Total Rows (after cleaning)** | {len(_cleaned_df):,} |
| **Total Columns** | {len(_cleaned_df.columns)} |
| **Total Quantity Sold** | {total_qty:,} units |
| **Total Revenue** | {total_revenue:,.0f} تومان |
| **Unique Invoices** | {unique_invoices:,} |
| **Unique Customers** | {unique_customers:,} |
| **Date Range** | {date_range} |
| **Data Quality Score** | {data_quality}/100 |
| **Health Score** | {health}/100 |
"""
        else:
            stats_cards = "No data available"
        col_stats_df = get_column_stats(_cleaned_df)
        col_stats_md = col_stats_df.to_markdown(index=False) if len(col_stats_df) > 0 else "No column data available"
        product_summary_df = get_product_quantity_summary(_cleaned_df)
        product_summary_md = product_summary_df.to_markdown(index=False) if len(product_summary_df) > 0 else "No product data available"
        sales_chart = create_sales_trend_chart(_cleaned_df)
        top_products_chart = create_top_products_chart(_cleaned_df)
        if _cleaned_df is not None and len(_cleaned_df) > 0:
            preview_df = _cleaned_df.head(100).copy()
            cleaned_data_table = preview_df.to_markdown(index=False)
        else:
            cleaned_data_table = "No data available"
        health_quality_content = f"""
## 🏥 Data Quality Report

{quality_report}

---

{stats_cards}

---

## 📈 Charts

### Sales Trend Over Time
{sales_chart if sales_chart else 'No chart available'}

### Top 10 Products by Quantity
{top_products_chart if top_products_chart else 'No chart available'}

---

## 📊 Column Statistics

{col_stats_md}

---

## 📦 Per-Product Quantity Summary (Top 50)

{product_summary_md}

---

## 📋 Cleaned Data Preview (First 100 rows)

{cleaned_data_table}
"""
        
# ========== TAB 2: PRODUCT RANKINGS (HTML table) ==========
        if products:
            segment_icons = {"Star":"⭐","Reliable":"✅","Deadweight":"💀",
                            "Risky":"⚠️","Seasonal":"📅","Outlier":"❓","Individual":"📌"}
            segment_colors = {"Star":"#f1c40f","Reliable":"#2ecc71","Deadweight":"#e74c3c",
                            "Risky":"#e67e22","Seasonal":"#3498db","Outlier":"#95a5a6","Individual":"#9b59b6"}
            
            # Sort by profit for initial display
            sorted_products = sorted(products, key=lambda x: x.get("unified_score", 0), reverse=True)
            
            def color_risk(val):
                if val < 30: return f'🟢 {val:.2f}'
                elif val < 70: return f'🟡 {val:.2f}'
                else: return f'🔴 {val:.2f}'
            
            products_text = '<div style="overflow-x: auto; max-height: 500px;">'
            products_text += '<table style="width: 100%; border-collapse: collapse; font-size: 13px;">'
            products_text += '<thead style="position: sticky; top: 0; background: #2c3e50;">'
            products_text += '<tr>'
            products_text += '<th style="padding: 10px 8px; color: white; text-align: center; width: 60px;">Rank</th>'
            products_text += '<th style="padding: 10px 8px; color: white; text-align: left;">Product</th>'
            products_text += '<th style="padding: 10px 8px; color: white; text-align: center;">Segment</th>'
            products_text += '<th style="padding: 10px 8px; color: white; text-align: center;">Stock</th>'
            products_text += '<th style="padding: 10px 8px; color: white; text-align: center;">Rev(M)</th>'
            products_text += '<th style="padding: 10px 8px; color: white; text-align: center;">Profit(M)</th>'
            products_text += '<th style="padding: 10px 8px; color: white; text-align: center;">Margin%</th>'
            products_text += '<th style="padding: 10px 8px; color: white; text-align: center;">Risk</th>'
            products_text += '<th style="padding: 10px 8px; color: white; text-align: center;">Last Sale</th>'
            products_text += '<th style="padding: 10px 8px; color: white; text-align: left;">Why</th>'
            products_text += '</tr>'
            products_text += '</thead><tbody>'
            
            for i, p in enumerate(sorted_products[:100], 1):
                margin = p.get("profit_margin", 0)
                margin_color = 'green' if margin > 20 else 'orange' if margin > 10 else 'red'
                stock = int(inventory.get(p["product"], 0))
                stock_display = f"{stock:,}" if stock > 0 else "0"
                segment = p.get("segment", "Individual")
                segment_icon = segment_icons.get(segment, "📦")
                segment_color = segment_colors.get(segment, "#ffffff")
                risk_val = p.get("risk_score", 0)
                if risk_val < 30:
                    risk_display = f'🟢 {risk_val:.2f}'
                elif risk_val < 70:
                    risk_display = f'🟡 {risk_val:.2f}'
                else:
                    risk_display = f'🔴 {risk_val:.2f}'
                why = p.get("risk_explanation", "?")
                
                products_text += '<tr style="border-bottom: 1px solid #e2e8f0;">'
                products_text += f'<td style="padding: 8px 8px; text-align: center; font-weight: bold; background-color: #f0f0f0;">{i}</td>'
                products_text += f'<td style="padding: 8px 8px; text-align: left; max-width: 150px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="{p["product"]}">{p["product"]}</td>'
                products_text += f'<td style="padding: 8px 8px; text-align: center;"><span style="background: {segment_color}20; color: {segment_color}; padding: 2px 8px; border-radius: 12px; font-size: 11px;">{segment_icon} {segment}</span></td>'
                products_text += f'<td style="padding: 8px 8px; text-align: center;">{stock_display}</td>'
                products_text += f'<td style="padding: 8px 8px; text-align: center;">{round(p.get("total_revenue", 0) / 1_000_000, 1):,.1f}</td>'
                products_text += f'<td style="padding: 8px 8px; text-align: center;">{round(p.get("total_profit", 0) / 1_000_000, 1):,.1f}</td>'
                products_text += f'<td style="padding: 8px 8px; text-align: center; color: {margin_color}; font-weight: 500;">{margin:.1f}%</td>'
                products_text += f'<td style="padding: 8px 8px; text-align: center;">{risk_display}</td>'
                products_text += f'<td style="padding: 8px 8px; text-align: center;">{p.get("days_since_last_sale", 0)}d</td>'
                products_text += f'<td style="padding: 8px 8px; text-align: left; max-width: 200px;">{why}</td>'
                products_text += '</tr>'
            products_text += '</tbody>\\table</div>'
            products_text += '<br><small>⭐ Star | ✅ Reliable | 💀 Deadweight | ⚠️ Risky | 📅 Seasonal | ❓ Outlier | Stock = current inventory | 🟢 Safe | 🟡 Caution | 🔴 High Risk</small>'
        else:
             products_text = "No products analyzed."
        # ========== TAB 3: FORECAST ==========
        forecast_rows = []
        for p in products:
            fc = p.get("forecast") or {}
            if fc and not fc.get("skipped"):
                h30 = fc.get('h30', 0)
                h60 = fc.get('h60', 0)
                h90 = fc.get('h90', 0)
                low_conf = fc.get("low_confidence", False)
                daily_avg = h30 / 30 if h30 > 0 else 0
                segment = p.get("segment", "Individual")
                segment_icons = {"Star":"⭐","Reliable":"✅","Deadweight":"💀","Risky":"⚠️","Seasonal":"📅","Outlier":"❓","Individual":"📌"}
                segment_icon = segment_icons.get(segment, "📦")
                if h30 > 0 and not low_conf:
                    action = "🔴 ORDER MORE — High demand" if daily_avg > 10 else "🟡 Maintain stock — Steady demand" if daily_avg > 3 else "🟢 Reduce order — Low demand"
                elif low_conf:
                    action = "⚠️ Check manually — Not enough data"
                else:
                    action = "⚪ No action needed"
                forecast_rows.append({
                    "Product": p["product"],
                    "Segment": f"{segment_icon} {segment}",
                    "Daily Avg": f"{daily_avg:.1f}",
                    "Next 30 Days": f"{h30:.0f}",
                    "Next 60 Days": f"{h60:.0f}",
                    "Next 90 Days": f"{h90:.0f}",
                    "Confidence": "✓ High" if not low_conf else "⚠️ Low",
                    "Action": action,
                })
        if forecast_rows:
            df_forecast = pd.DataFrame(forecast_rows)
            forecast_text = "### 📈 Sales Forecast (Next 90 Days)\n\n"
            forecast_text += df_forecast.to_markdown(index=False)
            forecast_text += "\n\n---\n### 💡 Action Guide\n"
            forecast_text += "- **ORDER MORE** → High demand products\n- **Maintain** → Steady, predictable sales\n- **Reduce** → Low demand, order less\n- **Check manually** → Not enough data, use judgment\n"
        else:
            forecast_text = "⚠️ Not enough sales history to forecast."
        
        # ========== TAB 4: SEGMENTS ==========
        seg_summary = report_data.get("segment_summary", {})
        products_by_segment = {"Star":[],"Reliable":[],"Deadweight":[],"Risky":[],"Seasonal":[],"Outlier":[],"Individual":[]}
        for p in products:
            seg = p.get("segment", "Individual")
            if seg in products_by_segment:
                products_by_segment[seg].append(p["product"])
        segment_info = {
            "Star":{"icon":"⭐","action":"Keep fully stocked","desc":"Best sellers, high profit"},
            "Reliable":{"icon":"✅","action":"Maintain current stock","desc":"Steady, consistent sellers"},
            "Deadweight":{"icon":"💀","action":"Run clearance sale","desc":"Low margin, slow sales"},
            "Risky":{"icon":"⚠️","action":"Reduce order quantity","desc":"High volatility, unpredictable"},
            "Seasonal":{"icon":"📅","action":"Stock before peak","desc":"Strong seasonal pattern"},
            "Outlier":{"icon":"❓","action":"Review manually","desc":"Doesn't fit patterns"},
            "Individual":{"icon":"📌","action":"Monitor individually","desc":"Too few products"}
        }
        segments_text = "### 🎯 Product Segments\n\n"
        segments_text += "| Segment | Count | Action |\n|---------|-------|--------|\n"
        for seg, count in sorted(seg_summary.items(), key=lambda x: x[1], reverse=True):
            info = segment_info.get(seg, {"action":"Monitor","icon":"📦"})
            segments_text += f"| {info['icon']} {seg} | {count} | {info['action']} |\n"
        segments_text += "\n---\n### 📋 Products by Segment\n\n"
        for seg, product_list in products_by_segment.items():
            if product_list:
                info = segment_info.get(seg, {"icon":"📦","desc":""})
                segments_text += f"**{info['icon']} {seg}** ({len(product_list)} products) — *{info['desc']}*\n\n"
                for prod in product_list[:20]:
                    segments_text += f"`{prod}` "
                if len(product_list) > 20:
                    segments_text += f"\n*... and {len(product_list) - 20} more*"
                segments_text += "\n\n"
        
        # ========== TAB 5: BASKET RULES ==========
        rules = report_data.get("basket_rules", [])
        if rules:
            df_basket = pd.DataFrame([{
                "If Customer Buys": " + ".join(r["antecedent"]),
                "They Usually Buy": " + ".join(r["consequent"]),
                "How Often": f"{r['confidence']*100:.0f}%",
                "Boost": f"{r['lift']:.2f}x",
            } for r in rules[:15]])
            basket_text = "### 🛒 Product Combinations\n\n" + df_basket.to_markdown(index=False)
        else:
            basket_text = "Not enough data to find product combinations."
        
        # ========== TAB 6: PURCHASE ORDER ==========
        order = report_data.get("purchase_order", [])
        if order:
            df_order = pd.DataFrame([{
                "Product": o["product"],
                "Current Stock": o.get("current_stock",0),
                "→ Buy": o["qty"],
                "Final Stock": o.get("final_stock",0),
                "Why": o.get("reason","?"),
            } for o in order])
            total_cost = report_data.get('order_total',0)
            order_md = f"### 💼 What Should You Order?\n\n**Total Cost: {total_cost:,.0f} Toman**\n\n"
            order_md += report_data.get('optimizer_summary','') + "\n\n" + df_order.to_markdown(index=False)
        else:
            order_md = f"### 💼 Order Recommendation\n\n{report_data.get('optimizer_summary','No order generated.')}"
        
        # ========== TAB 7: ROI & CUSTOMERS ==========
        roi_text = f"### 💰 Profit Comparison\n\n{report_data.get('roi_commentary','Not enough data.')}\n\n"
        roi_text += f"| Metric | Value | vs Benchmark |\n|--------|-------|--------------|\n"
        roi_text += f"| **Shop Annual ROI** | {report_data.get('shop_roi',0):.1f}% | - |\n"
        roi_text += f"| **Bank Deposit** | {config.BANK_DEPOSIT_RATE_ANNUAL}% | {report_data.get('vs_bank',0):+.1f}% |\n"
        roi_text += f"| **Gold Return** | {config.GOLD_ANNUAL_RETURN}% | {report_data.get('vs_gold',0):+.1f}% |\n"
        customers = report_data.get("customers", {})
        if customers and not customers.get("skipped"):
            summary = customers.get("summary", {})
            segments_list = customers.get("segments", [])
            roi_text += "\n### 👥 Customer Segments\n\n"
            for seg, count in sorted(summary.items(), key=lambda x: x[1], reverse=True):
                roi_text += f"**{seg}** ({count} customers)\n\n"
                roi_text += "| Customer | Last Purchase | Orders | Total Spent |\n|----------|---------------|--------|-------------|\n"
                seg_customers = [c for c in segments_list if c.get("segment") == seg]
                for cust in seg_customers[:10]:
                    cust_id = cust.get("customer_id","?")
                    recency = cust.get("recency",0)
                    frequency = cust.get("frequency",0)
                    monetary = cust.get("monetary",0)
                    recency_str = f"🟢 {recency} days" if recency < 30 else f"🟡 {recency} days" if recency < 90 else f"🔴 {recency} days"
                    roi_text += f"| {cust_id} | {recency_str} | {frequency} | {monetary:,.0f} |\n"
                roi_text += "\n"
            champ = customers.get("champion_products", [])
            if champ:
                roi_text += "### 🏆 What Champions Buy\n\n"
                for i,prod in enumerate(champ[:10],1):
                    roi_text += f"{i}. {prod}\n"
        else:
            roi_text += "\n⚠️ Not enough customer data for segmentation (minimum 3 customers required)."
        roi_text += "\n---\n### 💡 How to Improve Your ROI\n"
        roi_text += "- 🎯 Send offers to At-Risk customers\n- 🏆 Reward Champions with discounts\n- 📦 Bundle Deadweight with Stars\n- 📈 Raise prices on Star products\n"
        
        # ========== TAB 8: INVENTORY ==========
        inventory_text = render_inventory(report_data, inventory)
        
        # ========== TAB 9: PRIORITY ACTIONS ==========
        priority_md = "## 🎯 Top 3 Actions for Your Shop\n\n"
        if priority_actions:
            for i,action in enumerate(priority_actions[:3],1):
                priority_md += f"### {action['urgency']} {i}. {action['title']}\n\n{action['description']}\n\n"
                if action.get('product'):
                    priority_md += f"**Product:** `{action['product']}`\n\n"
                priority_md += "---\n\n"
        else:
            priority_md = "No priority actions could be generated (insufficient data)."
        
        # ========== TAB 10: JSON REPORT, TAB 11: LLM ADVISOR, STATUS ==========
        report_json = json.dumps(report_data, indent=2, ensure_ascii=False, default=str)
        llm_text = _build_llm_text(report_data, question or "", language) if use_llm and LLM_AVAILABLE else "LLM advisor is disabled or not available."
        cache_text = "Reused cached shop models." if report_data.get("cache_status") == "reused" else "New CSV uploaded — shop models reset."
        status_msg = f"✅ Analysis complete | Shop: {sid} | {cache_text}"
        
        return (
            health_quality_content,
            products_text,
            forecast_text,
            segments_text,
            basket_text,
            order_md,
            roi_text,
            inventory_text,
            priority_md,
            report_json,
            llm_text,
            status_msg,
            products,   # <-- ADD THIS
            inventory   # <-- ADD THIS
        )
    
    except Exception as e:
        logger.error(f"Gradio error: {e}", exc_info=True)
        err = f"❌ Error: {e}\n\n{traceback.format_exc()}"
        return [None] * 12 + [err]

# ============================================================================
# SAMPLE DATA GENERATION
# ============================================================================

def generate_sample_data():
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
    script_path = os.path.join(root_dir, "data", "generate_data.py")
    try:
        result = subprocess.run(
            [sys.executable, script_path],
            cwd=root_dir,
            capture_output=True,
            text=True,
            timeout=900,
        )
        output = result.stdout.strip() if result.stdout else ""
        error = result.stderr.strip() if result.stderr else ""
        if result.returncode == 0:
            status = "✅ Sample data generated successfully."
            details = output or "Generated data files in data/"
            return f"{status}\n\n{details}"
        return f"❌ Failed to generate sample data (exit code {result.returncode}).\n\n{output}\n{error}"
    except Exception as e:
        logger.error(f"Sample data generation failed: {e}", exc_info=True)
        return f"❌ Exception while generating data: {e}\n\n{traceback.format_exc()}"

# ============================================================================
# GRADIO INTERFACE
# ============================================================================

with gr.Blocks(title="SaleYar — Business Intelligence", theme=gr.themes.Soft()) as demo:
    gr.Markdown("# 🧠 SaleYar — Business Intelligence\nUpload your Holoo CSV/Excel file and get actionable insights.")
    with gr.Row():
        file_input = gr.File(label="Upload CSV / Excel", file_types=[".csv", ".xlsx", ".xls"])
        budget_input = gr.Number(label="Budget (Toman)", value=100_000_000, precision=0)
        goal_input = gr.Dropdown(label="Optimization Goal", choices=["maximize_profit","cover_customers","reduce_risk"], value="maximize_profit")
        lang_input = gr.Dropdown(label="Language", choices=["en","fa"], value="en")
        shop_input = gr.Textbox(label="Shop ID", value="demo", placeholder="e.g. shop_001")
        llm_checkbox = gr.Checkbox(label="Use LLM Advisor", value=False)
        llm_question = gr.Textbox(label="Ask the Advisor", placeholder="What should I do next?", lines=1)
        run_btn = gr.Button("🚀 Analyse", variant="primary", scale=0)
        generate_btn = gr.Button("🧪 Generate Sample Data", variant="secondary", scale=0)
    status_out = gr.Textbox(label="Status", interactive=False)
    generate_output = gr.Textbox(label="Generator Output", interactive=False, lines=6)
    with gr.Tabs():
        with gr.Tab("📊 Health & Quality"):
            health_out = gr.Markdown()
        with gr.Tab("🏆 Product Rankings"):
            with gr.Row():
                product_search = gr.Textbox(label="Search Product", placeholder="Type product name...", scale=3)
                search_btn = gr.Button("🔍 Apply Filter", scale=1, variant="secondary")
            products_out = gr.Markdown()
            products_state = gr.State(value=None)
            inventory_state = gr.State(value=None)
        with gr.Tab("📈 Forecast"):
            forecast_out = gr.Markdown()
        with gr.Tab("🎯 Segments"):
            segments_out = gr.Markdown()
        with gr.Tab("🛒 Basket Rules"):
            basket_out = gr.Markdown()
        with gr.Tab("💼 Purchase Order"):
            order_out = gr.Markdown()
        with gr.Tab("💰 ROI & Customers"):
            roi_out = gr.Markdown()
        with gr.Tab("📦 Inventory"):
            inventory_out = gr.Markdown()
        with gr.Tab("🎯 Priority Actions"):
            priority_out = gr.Markdown()
        with gr.Tab("🤖 LLM Advisor"):
            llm_out = gr.Markdown()
        with gr.Tab("📄 Full Report (JSON)"):
            report_out = gr.Code(language="json")
    run_btn.click(
        fn=analyse,
        inputs=[file_input, budget_input, goal_input, lang_input, shop_input, llm_checkbox, llm_question],
        outputs=[health_out, products_out, forecast_out, segments_out, basket_out, order_out, roi_out, inventory_out, priority_out, report_out, llm_out, status_out, products_state, inventory_state],
    )
    search_btn.click(
        fn=filter_products_table,
        inputs=[products_state, inventory_state, product_search],
        outputs=[products_out]
    )
    generate_btn.click(fn=generate_sample_data, inputs=[], outputs=[generate_output])

def run():
    demo.launch(server_name="0.0.0.0", server_port=7860, share=False)

if __name__ == "__main__":
    run()