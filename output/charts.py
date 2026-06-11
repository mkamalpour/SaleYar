"""
charts.py — Perfect Plotly Charts for Gradio Dashboard

Generates all visualisations for the SaleYar developer UI.
Robust: handles missing data, empty DataFrames, and missing columns gracefully.
All charts are interactive and ready for export.
"""

import logging
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# Helper: empty chart (fallback)
# ----------------------------------------------------------------------

def _empty_chart(message: str) -> go.Figure:
    """Return a blank figure with a centred text message."""
    fig = go.Figure()
    fig.add_annotation(
        text=message,
        xref="paper", yref="paper",
        x=0.5, y=0.5,
        showarrow=False,
        font=dict(size=14, color="#6B6860"),
    )
    fig.update_layout(
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
    )
    return fig

# ----------------------------------------------------------------------
# 1. Forecast bar chart with confidence bands
# ----------------------------------------------------------------------

def forecast_chart(product_name: str, forecast: dict) -> go.Figure:
    """
    Bar chart showing 30/60/90 day forecasts with 95% confidence intervals.
    Handles missing or skipped forecasts gracefully.
    """
    if not forecast or forecast.get("skipped"):
        return _empty_chart(f"No forecast available for {product_name}")

    h30 = forecast.get("h30")
    h60 = forecast.get("h60")
    h90 = forecast.get("h90")

    # If any horizon is None, treat as 0
    values = [_to_float(h30), _to_float(h60), _to_float(h90)]

    # Confidence bands (lo95, hi95) – if missing, use ±15%
    lo95 = forecast.get("lo95")
    hi95 = forecast.get("hi95")
    if lo95 is None or hi95 is None:
        lo95 = values[0] * 0.85 if values[0] else 0
        hi95 = values[2] * 1.15 if values[2] else 0
    # Expand to three horizons
    lo95_vals = [lo95, lo95, lo95]
    hi95_vals = [hi95, hi95, hi95]

    errors_minus = [v - lo for v, lo in zip(values, lo95_vals)]
    errors_plus  = [hi - v for v, hi in zip(values, hi95_vals)]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=["30 days", "60 days", "90 days"],
        y=values,
        name="Forecast",
        marker_color="#2563EB",
        error_y=dict(
            type="data",
            symmetric=False,
            array=errors_plus,
            arrayminus=errors_minus,
            color="#6B6860",
        ),
    ))

    method = forecast.get("method", "Unknown")
    warn = " ⚠ Low confidence" if forecast.get("low_confidence") else ""

    fig.update_layout(
        title=f"{product_name} — Demand Forecast ({method}){warn}",
        xaxis_title="Horizon",
        yaxis_title="Units",
        plot_bgcolor="#F5F4F0",
        paper_bgcolor="#FFFFFF",
        showlegend=False,
    )
    return fig

# ----------------------------------------------------------------------
# 2. Segment pie chart
# ----------------------------------------------------------------------

def segment_pie(segment_summary: dict) -> go.Figure:
    """Pie chart of product segments with consistent colour mapping."""
    if not segment_summary:
        return _empty_chart("No segment data")

    colour_map = {
        "Star":       "#16A34A",   # green
        "Reliable":   "#2563EB",   # blue
        "Seasonal":   "#7C3AED",   # purple
        "Deadweight": "#DC2626",   # red
        "Risky":      "#D97706",   # orange
        "Outlier":    "#6B6860",   # grey
        "Individual": "#9CA3AF",   # light grey
        "Unknown":    "#9CA3AF",   # fallback
    }

    labels = list(segment_summary.keys())
    values = list(segment_summary.values())
    colors = [colour_map.get(l, colour_map["Unknown"]) for l in labels]

    fig = go.Figure(go.Pie(
        labels=labels,
        values=values,
        marker=dict(colors=colors),
        hole=0.4,
        textinfo="label+percent",
    ))
    fig.update_layout(
        title="Product Segments",
        paper_bgcolor="#FFFFFF",
    )
    return fig

# ----------------------------------------------------------------------
# 3. ROI comparison bar chart
# ----------------------------------------------------------------------

def roi_comparison(shop_roi: float, bank_rate: float, gold_rate: float) -> go.Figure:
    """
    Horizontal bar chart comparing shop ROI with bank deposit and gold return.
    Handles negative values gracefully.
    """
    categories = ["Shop ROI", "Bank Deposit", "Gold Return"]
    values = [shop_roi, bank_rate, gold_rate]

    # Ensure x‑axis range is sensible (positive or at least includes 0)
    max_val = max(values) if values else 1
    if max_val <= 0:
        x_max = 1
    else:
        x_max = max_val * 1.2

    # Colour: green if shop ROI >= bank deposit, else red
    colors = [
        "#16A34A" if shop_roi >= bank_rate else "#DC2626",
        "#2563EB",
        "#D97706",
    ]

    fig = go.Figure(go.Bar(
        x=values,
        y=categories,
        orientation="h",
        marker_color=colors,
        text=[f"{v:.1f}%" for v in values],
        textposition="outside",
    ))
    fig.update_layout(
        title="Annual Return Comparison",
        xaxis_title="Annual Return (%)",
        plot_bgcolor="#F5F4F0",
        paper_bgcolor="#FFFFFF",
        showlegend=False,
        xaxis=dict(range=[0, x_max]),
    )
    return fig

# ----------------------------------------------------------------------
# 4. Risk vs Margin scatter plot
# ----------------------------------------------------------------------

def risk_scatter(df_products: pd.DataFrame) -> go.Figure:
    """
    Scatter plot: profit margin vs risk score, coloured by segment.
    Requires columns: profit_margin, risk_score, product, segment.
    """
    if df_products is None or df_products.empty:
        return _empty_chart("No product data")

    required = ["profit_margin", "risk_score", "product", "segment"]
    missing = [col for col in required if col not in df_products.columns]
    if missing:
        return _empty_chart(f"Missing required columns: {missing}")

    colour_map = {
        "Star":       "#16A34A",
        "Reliable":   "#2563EB",
        "Seasonal":   "#7C3AED",
        "Deadweight": "#DC2626",
        "Risky":      "#D97706",
        "Outlier":    "#6B6860",
        "Individual": "#9CA3AF",
        "Unknown":    "#9CA3AF",
    }

    fig = px.scatter(
        df_products,
        x="profit_margin",
        y="risk_score",
        color="segment",
        hover_name="product",
        hover_data=["profit_margin", "risk_score", "days_since_last_sale"],
        color_discrete_map=colour_map,
        title="Product Risk vs Margin",
        labels={
            "profit_margin": "Profit Margin (%)",
            "risk_score":    "Risk Score (0–100, higher = better)",
        },
    )
    fig.update_layout(
        plot_bgcolor="#F5F4F0",
        paper_bgcolor="#FFFFFF",
    )
    return fig

# ----------------------------------------------------------------------
# 5. Basket rules table (heatmap‑style table)
# ----------------------------------------------------------------------

def basket_table(rules: list, max_rules: int = 20) -> go.Figure:
    """
    Table of top basket rules (antecedent → consequent) with confidence, lift, and critical flag.
    """
    if not rules:
        return _empty_chart("No basket rules found")

    top = rules[:max_rules]
    rows = []
    for r in top:
        ante = " + ".join(r.get("antecedent", []))
        cons = " + ".join(r.get("consequent", []))
        rows.append({
            "If bought": ante,
            "Then also": cons,
            "Confidence": f"{r.get('confidence', 0)*100:.0f}%",
            "Lift": f"{r.get('lift', 0):.2f}x",
            "Critical": "✓" if r.get("is_critical") else "",
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return _empty_chart("No rules to display")

    fig = go.Figure(go.Table(
        header=dict(
            values=list(df.columns),
            fill_color="#EFF4FF",
            font=dict(color="#1A1A18", size=12),
            align="left",
        ),
        cells=dict(
            values=[df[c] for c in df.columns],
            fill_color=[["#FFFFFF", "#F5F4F0"] * len(df)],
            align="left",
        ),
    ))
    fig.update_layout(title="Top Basket Rules")
    return fig

# ----------------------------------------------------------------------
# Helper: safe conversion to float
# ----------------------------------------------------------------------

def _to_float(value, default=0.0):
    """Safely convert any value to float; return default if None or error."""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default