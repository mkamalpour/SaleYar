"""
train.py — Offline training for the shared LightGBM risk model

Trains a LightGBM regressor on synthetic data that mimics the rule‑based risk
scoring from stage6_risk.py. This ensures hybrid scoring is consistent.

Run once before deploying the API:
    python models/train.py --shop_id dummy

The model is saved to config.LGBM_MODEL_PATH (default: models/lgbm_risk.pkl).
"""

import argparse
import logging
import os
import sys

import joblib
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def train(shop_id: str, csv_path: str = None, skip_lgbm: bool = False):
    """Train the shared LightGBM risk model on synthetic data."""
    os.makedirs(os.path.dirname(config.LGBM_MODEL_PATH), exist_ok=True)

    if skip_lgbm:
        logger.info("Skipping LightGBM training (--skip_lgbm)")
        return

    if os.path.exists(config.LGBM_MODEL_PATH):
        logger.info(f"Model already exists at {config.LGBM_MODEL_PATH}. Use --force to retrain.")
        return

    logger.info("Training LightGBM risk model on synthetic data...")
    _train_lgbm_synthetic()
    logger.info(f"✅ Model saved to {config.LGBM_MODEL_PATH}")


def _train_lgbm_synthetic(n_samples: int = 10_000):
    """
    Generate synthetic product data and train LightGBM to predict the
    rule‑based risk score defined in stage6_risk.py.
    """
    try:
        import lightgbm as lgb
    except ImportError:
        logger.error("LightGBM not installed. Run: pip install lightgbm")
        raise

    logger.info(f"Generating {n_samples:,} synthetic products...")
    np.random.seed(42)

    n = n_samples

    # ──────────────────────────────────────────────────────────────────────
    # Generate realistic KPI distributions (based on typical retail data)
    # ──────────────────────────────────────────────────────────────────────
    profit_margin      = np.random.beta(2, 5, n) * 60          # 0‑60%, mean ~17%
    liquidity_rate     = np.random.beta(3, 2, n) * 100        # 0‑100%, mean ~60%
    price_volatility   = np.random.exponential(5, n)          # most <15
    price_change_count = np.random.poisson(3, n).astype(float)
    days_since_last    = np.random.exponential(30, n)         # most <90 days
    conversion_rate    = np.random.beta(2, 3, n) * 100        # 0‑100%, mean ~40%
    hope_rate          = np.random.beta(4, 2, n) * 100        # 0‑100%, mean ~66%
    portfolio_weight   = np.random.exponential(3, n)          # most <10%
    margin_vs_avg      = profit_margin - 18.0                 # compared to industry avg

    # ──────────────────────────────────────────────────────────────────────
    # Calculate rule‑based risk score (same formula as stage6_risk.py)
    # ──────────────────────────────────────────────────────────────────────
    base = 50.0
    margin_contrib   = np.clip(profit_margin * 0.5, 0, 25)
    liquidity_contrib = np.clip(liquidity_rate * 0.3, 0, 15)
    volatility_contrib = np.clip(price_volatility * -0.2, -15, 0)   # negative penalty
    idle_contrib       = np.clip(days_since_last * -0.05, -20, 0)
    conversion_contrib = np.clip(conversion_rate * 0.2, 0, 10)

    raw_score = (
        base
        + margin_contrib
        + liquidity_contrib
        + volatility_contrib
        + idle_contrib
        + conversion_contrib
    )
    # Clip to 0‑100 (rule‑based already does this)
    y = np.clip(raw_score, 0, 100)

    # ──────────────────────────────────────────────────────────────────────
    # Feature matrix (must match columns used in stage6_risk)
    # ──────────────────────────────────────────────────────────────────────
    X = pd.DataFrame({
        "profit_margin":        profit_margin,
        "liquidity_rate":       liquidity_rate,
        "price_volatility":     price_volatility,
        "price_change_count":   price_change_count,
        "days_since_last_sale": days_since_last,
        "conversion_rate":      conversion_rate,
        "hope_rate":            hope_rate,
        "portfolio_weight":     portfolio_weight,
        "margin_vs_avg":        margin_vs_avg,
    })

    # ──────────────────────────────────────────────────────────────────────
    # Train LightGBM
    # ──────────────────────────────────────────────────────────────────────
    model = lgb.LGBMRegressor(
        n_estimators=200,
        learning_rate=0.05,
        num_leaves=31,
        min_child_samples=20,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        verbose=-1,
    )
    model.fit(X, y)

    # Save model and feature list
    joblib.dump(
        {"model": model, "feature_cols": list(X.columns)},
        config.LGBM_MODEL_PATH,
    )
    logger.info(f"LightGBM model saved → {config.LGBM_MODEL_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Train the shared LightGBM risk model for SaleYar."
    )
    parser.add_argument(
        "--shop_id", required=True,
        help="Shop identifier (unused, kept for compatibility)."
    )
    parser.add_argument(
        "--csv", default="data/sample_en.csv",
        help="CSV path (unused, kept for compatibility)."
    )
    parser.add_argument(
        "--skip_lgbm", action="store_true",
        help="Skip LightGBM training (if already trained)."
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Force retraining even if model already exists."
    )
    args = parser.parse_args()

    # Override existence check if --force is used
    if args.force and os.path.exists(config.LGBM_MODEL_PATH):
        os.remove(config.LGBM_MODEL_PATH)
        logger.info("Removed existing model due to --force flag.")

    train(args.shop_id, args.csv, args.skip_lgbm)