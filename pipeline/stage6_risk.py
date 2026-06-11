"""
stage6_risk.py — HYBRID RISK SCORING (Adaptive & Explainable)

Improvements:
- Rule‑based scoring (vectorised) with configurable weights
- LightGBM model (optional) with confidence weighting
- For small shops (<20 products) model trust is reduced (configurable)
- Clear English/Persian explanation with comparison to shop average
- Calculates shop ROI vs bank deposit and gold return
"""

import logging
import os
import sys
import joblib
import numpy as np
import pandas as pd
from functools import lru_cache

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

logger = logging.getLogger(__name__)

FEATURE_COLS = [
    "profit_margin",
    "liquidity_rate",
    "price_volatility",
    "hope_rate",
    "portfolio_weight",
    "days_since_last_sale",
    "conversion_rate",
    "margin_vs_avg",
    "price_change_count",
]

# Rule‑based weights (from config)
RISK_BASE = getattr(config, 'RISK_BASE', 50.0)
RISK_MARGIN_WEIGHT = getattr(config, 'RISK_MARGIN_WEIGHT', 0.5)
RISK_LIQUIDITY_WEIGHT = getattr(config, 'RISK_LIQUIDITY_WEIGHT', 0.3)
RISK_VOLATILITY_WEIGHT = getattr(config, 'RISK_VOLATILITY_WEIGHT', -0.2)
RISK_IDLE_WEIGHT = getattr(config, 'RISK_IDLE_WEIGHT', -0.05)
RISK_CONVERSION_WEIGHT = getattr(config, 'RISK_CONVERSION_WEIGHT', 0.2)

RISK_MARGIN_MAX = getattr(config, 'RISK_MARGIN_MAX', 25.0)
RISK_LIQUIDITY_MAX = getattr(config, 'RISK_LIQUIDITY_MAX', 15.0)
RISK_VOLATILITY_MIN = getattr(config, 'RISK_VOLATILITY_MIN', -15.0)
RISK_IDLE_MIN = getattr(config, 'RISK_IDLE_MIN', -20.0)
RISK_CONVERSION_MAX = getattr(config, 'RISK_CONVERSION_MAX', 10.0)

HYBRID_MIN_CONFIDENCE = getattr(config, 'HYBRID_MIN_CONFIDENCE', 0.3)
HYBRID_MAX_CONFIDENCE = getattr(config, 'HYBRID_MAX_CONFIDENCE', 0.7)
RISK_SMALL_SHOP_MAX_PRODUCTS = getattr(config, 'RISK_SMALL_SHOP_MAX_PRODUCTS', 20)
RISK_SMALL_SHOP_MODEL_WEIGHT = getattr(config, 'RISK_SMALL_SHOP_MODEL_WEIGHT', 0.2)

_MODEL_CACHE = None
_MODEL_FEATURES_CACHE = None
_MODEL_AVAILABLE = False


def run(df_kpis: pd.DataFrame, language: str = "en", shop_id: str = None) -> pd.DataFrame:
    """Add risk scores and explanations."""
    logger.info(f"Stage 6: risk scoring | products={len(df_kpis)}")

    rule_scores = _score_rule_based_vectorized(df_kpis)
    model_scores, model_confidence = _get_model_scores(df_kpis)

    # For small shops, reduce model trust
    if len(df_kpis) < RISK_SMALL_SHOP_MAX_PRODUCTS:
        model_confidence = min(model_confidence, RISK_SMALL_SHOP_MODEL_WEIGHT)

    final_scores, score_methods = _combine_scores(rule_scores, model_scores, model_confidence)

    df_out = df_kpis.copy()
    df_out["risk_score"] = final_scores
    df_out["risk_score_method"] = score_methods
    df_out["risk_rule_score"] = rule_scores
    if model_scores is not None:
        df_out["risk_model_score"] = model_scores

    df_out["risk_explanation"] = df_out.apply(
        lambda row: _explain_enhanced(row, language, rule_scores[row.name] if hasattr(rule_scores, '__getitem__') else None),
        axis=1
    )

    shop_roi = _calc_shop_roi(df_out)
    df_out["shop_roi"] = round(shop_roi, 2)
    df_out["vs_bank"] = round(shop_roi - config.BANK_DEPOSIT_RATE_ANNUAL, 2)
    df_out["vs_gold"] = round(shop_roi - config.GOLD_ANNUAL_RETURN, 2)

    logger.info(f"Stage 6 complete | shop_roi={shop_roi:.1f}%")
    return df_out


def _score_rule_based_vectorized(df: pd.DataFrame) -> np.ndarray:
    """Vectorised rule‑based risk score (0–100)."""
    scores = np.full(len(df), RISK_BASE, dtype=float)

    margin = df.get("profit_margin", pd.Series([0]*len(df))).fillna(0).values
    scores += np.minimum(margin * RISK_MARGIN_WEIGHT, RISK_MARGIN_MAX)

    liquidity = df.get("liquidity_rate", pd.Series([0]*len(df))).fillna(0).values
    scores += np.minimum(liquidity * RISK_LIQUIDITY_WEIGHT, RISK_LIQUIDITY_MAX)

    volatility = df.get("price_volatility", pd.Series([0]*len(df))).fillna(0).values
    scores += np.maximum(volatility * RISK_VOLATILITY_WEIGHT, RISK_VOLATILITY_MIN)

    days_idle = df.get("days_since_last_sale", pd.Series([0]*len(df))).fillna(0).values
    scores += np.maximum(days_idle * RISK_IDLE_WEIGHT, RISK_IDLE_MIN)

    conversion = df.get("conversion_rate", pd.Series([0]*len(df))).fillna(0).values
    scores += np.minimum(conversion * RISK_CONVERSION_WEIGHT, RISK_CONVERSION_MAX)

    return np.clip(scores, 0.0, 100.0).round(1)


def _get_model_scores(df: pd.DataFrame):
    """Return model predictions and confidence (if model exists)."""
    global _MODEL_CACHE, _MODEL_FEATURES_CACHE, _MODEL_AVAILABLE
    if _MODEL_CACHE is None:
        _load_model()
    if not _MODEL_AVAILABLE or _MODEL_CACHE is None:
        return None, 0.0

    try:
        available = [c for c in _MODEL_FEATURES_CACHE if c in df.columns]
        if len(available) < 3:
            return None, 0.0
        X = df[available].fillna(0)
        raw = _MODEL_CACHE.predict(X)
        r_min, r_max = raw.min(), raw.max()
        scores = (raw - r_min) / (r_max - r_min) * 100 if r_max > r_min else np.full(len(raw), 50.0)
        confidence = _calculate_model_confidence(df)
        return scores.round(1).tolist(), confidence
    except Exception as e:
        logger.warning(f"Model scoring failed: {e}")
        return None, 0.0


def _load_model():
    global _MODEL_CACHE, _MODEL_FEATURES_CACHE, _MODEL_AVAILABLE
    if os.path.exists(config.LGBM_MODEL_PATH):
        try:
            model_data = joblib.load(config.LGBM_MODEL_PATH)
            _MODEL_CACHE = model_data["model"]
            _MODEL_FEATURES_CACHE = model_data.get("feature_cols", FEATURE_COLS)
            _MODEL_AVAILABLE = True
            logger.info(f"LightGBM model loaded from {config.LGBM_MODEL_PATH}")
        except Exception as e:
            logger.warning(f"Could not load LightGBM model: {e}")
            _MODEL_AVAILABLE = False
    else:
        logger.info(f"No model found at {config.LGBM_MODEL_PATH}, using rule‑based only")
        _MODEL_AVAILABLE = False


def _calculate_model_confidence(df: pd.DataFrame) -> float:
    """Heuristic confidence based on data size and history length."""
    confidence = 0.5
    n = len(df)
    if n > 100:
        confidence += 0.2
    elif n > 50:
        confidence += 0.1
    elif n < 20:
        confidence -= 0.2

    if "date_range_days" in df.columns:
        avg_history = df["date_range_days"].mean()
        if avg_history > 180:
            confidence += 0.15
        elif avg_history < 60:
            confidence -= 0.15

    if not _MODEL_AVAILABLE:
        confidence -= 0.5

    return np.clip(confidence, HYBRID_MIN_CONFIDENCE, HYBRID_MAX_CONFIDENCE)


def _combine_scores(rule_scores: np.ndarray, model_scores: list, model_confidence: float):
    """Combine rule‑based and model scores using confidence weight."""
    n = len(rule_scores)
    if model_scores is None or model_confidence <= 0:
        return rule_scores.tolist(), ["rule‑based only"] * n

    rule_weight = 1 - model_confidence
    final_scores = []
    methods = []
    for i, (rule, model) in enumerate(zip(rule_scores, model_scores)):
        if model is None:
            final_scores.append(rule)
            methods.append("rule‑based only")
        else:
            final = rule * rule_weight + model * model_confidence
            if abs(rule - model) > 20:
                methods.append(f"hybrid (model weight: {model_confidence:.0%}, ⚠️ scores differ)")
            else:
                methods.append(f"hybrid (model weight: {model_confidence:.0%})")
            final_scores.append(round(final, 1))
    return final_scores, methods


def _explain_enhanced(row: pd.Series, language: str, rule_score: float = None) -> str:
    """Generate plain English/Persian explanation of risk score."""
    score = row.get("risk_score", 50)
    margin = float(row.get("profit_margin", 0))
    days_idle = int(row.get("days_since_last_sale", 0))
    volatility = float(row.get("price_volatility", 0))
    vs_avg = float(row.get("margin_vs_avg", 0))
    segment = row.get("segment", "")
    changes = int(row.get("price_change_count", 0))
    method = row.get("risk_score_method", "rule‑based")
    model_score = row.get("risk_model_score", None)
    shop_avg_margin = margin - vs_avg  # because margin_vs_avg = product_margin - shop_avg

    if language == "fa":
        parts = []
        if margin < 10:
            parts.append(f"سود خالص {margin:.1f}٪ — پایین‌تر از میانگین فروشگاه")
        elif margin > 25:
            parts.append(f"سود خالص {margin:.1f}٪ — بالای میانگین فروشگاه")
        if days_idle > 30:
            parts.append(f"آخرین فروش {days_idle} روز پیش")
        elif days_idle <= 7:
            parts.append(f"فروش فعال — آخرین فروش {days_idle} روز پیش")
        if volatility > 5:
            parts.append(f"نوسان قیمتی بالا ({changes} بار تغییر قیمت)")
        elif volatility < 1 and changes == 0:
            parts.append("قیمت کاملاً پایدار")
        if segment == "Deadweight":
            parts.append("کالای راکد — توصیه می‌شود حذف شود")
        elif segment == "Star":
            parts.append("کالای برتر — اولویت در تأمین موجودی")
        reason = " ".join(parts) if parts else "عملکرد خوب در همه معیارها"
        if model_score and abs(score - model_score) > 15:
            return f"امتیاز {score:.0f}/100. {reason}\n\n⚠️ امتیاز مدل: {model_score:.0f} — این دو امتیاز متفاوت هستند. لطفاً بررسی کنید."
        return f"امتیاز {score:.0f}/100. {reason}"
    else:
        parts = []
        if margin < 10:
            parts.append(f"Thin margin at {margin:.1f}% (shop avg: {shop_avg_margin:.1f}%)")
        elif margin > 25:
            parts.append(f"Strong margin at {margin:.1f}% — {abs(vs_avg):.1f}% above shop avg")
        if days_idle > 60:
            parts.append(f"No sales for {days_idle} days — extremely slow")
        elif days_idle > 30:
            parts.append(f"Last sold {days_idle} days ago — slow mover")
        elif days_idle <= 7:
            parts.append(f"Hot item — last sale {days_idle} days ago")
        if volatility > 10:
            parts.append(f"Very high price volatility ({changes} price changes)")
        elif volatility > 5:
            parts.append(f"High price volatility ({changes} price changes)")
        elif volatility < 1 and changes == 0:
            parts.append("Price completely stable — low risk")
        if segment == "Deadweight":
            parts.append("Classified as Deadweight — liquidate or stop ordering")
        elif segment == "Star":
            parts.append("Star product — always keep in stock")
        elif segment == "Risky":
            parts.append("Classified as Risky — monitor closely")
        reason = " ".join(parts) if parts else "Good all‑around performer"
        if model_score and abs(score - model_score) > 15:
            return f"**Risk Score: {score:.0f}/100** (Model: {model_score:.0f})\n\n⚠️ **Scores disagree significantly** — review this product manually.\n\n{reason}"
        return f"**Risk Score: {score:.0f}/100**\n\n{reason}"


def _calc_shop_roi(df: pd.DataFrame) -> float:
    """Revenue‑weighted average annual ROI."""
    if "annual_roi" not in df.columns:
        total_profit = df.get("total_profit", pd.Series(dtype=float)).sum()
        total_cost = df.get("total_cost", pd.Series(dtype=float)).sum()
        return float(total_profit / total_cost * 100) if total_cost > 0 else 0.0

    valid = df[df["annual_roi"].notna()].copy()
    if valid.empty:
        total_profit = df["total_profit"].sum() if "total_profit" in df.columns else 0
        total_cost = df["total_cost"].sum() if "total_cost" in df.columns else 1
        return float(total_profit / total_cost * 100) if total_cost > 0 else 0.0

    total_rev = valid["total_revenue"].sum()
    if total_rev <= 0:
        return 0.0
    weights = valid["total_revenue"] / total_rev
    return float((valid["annual_roi"] * weights).sum())