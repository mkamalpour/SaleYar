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

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from saleyar import config
from models import risk_model

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def train(shop_id: str = "shared", csv_path: str = None, skip_lgbm: bool = False, force: bool = False):
    """Create a native model or migrate a readable legacy model without deleting it."""
    if skip_lgbm:
        logger.info("Skipping LightGBM training")
        return None
    loaded = risk_model.get_model(force=True)
    if not force and loaded:
        if loaded["source"] == "legacy":
            path = risk_model.migrate_legacy()
            logger.info("Migrated existing model to %s; original pickle preserved", path)
            return path
        logger.info("Compatible native model already exists at %s; use --force to retrain", risk_model.native_path())
        return risk_model.native_path()
    if not force and (os.path.exists(config.LGBM_MODEL_PATH) or risk_model.native_path().exists()):
        raise RuntimeError("Existing model is unreadable. Run python models/train.py --force to create a compatible native model. Legacy files will be preserved.")
    return _train_lgbm_synthetic()


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
    from pipeline.stage6_risk import _score_rule_based_vectorized
    y = _score_rule_based_vectorized(X)

    model = lgb.LGBMRegressor(
        n_estimators=200,
        learning_rate=0.05,
        num_leaves=31,
        min_child_samples=20,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        verbose=-1,
        n_jobs=2,
    )
    model.fit(X, y)

    path = risk_model.save_model(model.booster_, list(X.columns))
    logger.info("Native LightGBM model saved to %s", path)
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Train the shared LightGBM risk model for SaleYar."
    )
    parser.add_argument(
        "--shop_id", "--shop-id", default="shared",
        help="Shop identifier (unused, kept for compatibility)."
    )
    parser.add_argument(
        "--csv", default="data/sample_en.csv",
        help="CSV path (unused, kept for compatibility)."
    )
    parser.add_argument(
        "--skip_lgbm", "--skip-lgbm", action="store_true",
        help="Skip LightGBM training (if already trained)."
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Force retraining even if model already exists."
    )
    args = parser.parse_args()

    try:
        train(args.shop_id, args.csv, args.skip_lgbm, force=args.force)
    except Exception as exc:
        logger.error("Model setup failed: %s", exc)
        raise SystemExit(1) from exc
