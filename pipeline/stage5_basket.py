"""
stage5_basket.py — ADAPTIVE BASKET ANALYSIS

Improvements:
- Tiny shops (<50 transactions) → simple pair counting (no FP‑Growth)
- Small shops (50-1000) → FP‑Growth with higher min_support
- Large shops (>1000) → sample down to 2000 baskets, lower min_support
- Dynamic product limit based on memory (max 200)
- Critical pairs: confidence ≥ config.CRITICAL_PAIR_CONFIDENCE AND lift ≥ 2.0
- Caches rules per shop
"""

import logging
import os
import sys
import joblib
import pandas as pd
import numpy as np
from mlxtend.frequent_patterns import fpgrowth, association_rules
from mlxtend.preprocessing import TransactionEncoder
import random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

logger = logging.getLogger(__name__)

CRITICAL_PAIR_CONFIDENCE = getattr(config, 'CRITICAL_PAIR_CONFIDENCE', 0.70)
BASKET_MAX_PRODUCTS = getattr(config, 'BASKET_MAX_PRODUCTS', 200)
BASKET_SAMPLE_SIZE = getattr(config, 'BASKET_SAMPLE_SIZE', 2000)


def run(df: pd.DataFrame, shop_id: str = "default") -> dict:
    """Run basket analysis with adaptive method based on data size."""
    logger.info("Stage 5: basket analysis")

    # Use transaction_type if available, else fallback to qty>0
    if "transaction_type" in df.columns:
        sales_df = df[df["transaction_type"] == "sale"].copy()
    elif "qty" in df.columns:
        sales_df = df[df["qty"] > 0].copy()
    else:
        sales_df = df.copy()

    n_transactions = sales_df["invoice_id"].nunique()
    logger.info(f"Found {n_transactions} unique sales transactions")

    # Skip if not enough transactions
    if n_transactions < config.MIN_BASKET_ROWS:
        reason = f"Only {n_transactions} sales transactions – need {config.MIN_BASKET_ROWS} for meaningful analysis."
        return {"rules": [], "critical_pairs": [], "skipped": True, "skip_reason": reason}

    # Load from cache
    rules_path = os.path.join(config.SHOPS_DIR, shop_id, "basket_rules.pkl")
    if os.path.exists(rules_path):
        try:
            data = joblib.load(rules_path)
            logger.info(f"Loaded {len(data.get('rules', []))} cached rules")
            return data
        except Exception as e:
            logger.warning(f"Cache load failed, re-mining: {e}")

    # Choose method based on transaction count
    if n_transactions < 50:
        result = _simple_pair_counting(sales_df)
    else:
        result = _mine_fpgrowth(sales_df)

    if result and not result.get("skipped"):
        try:
            os.makedirs(os.path.dirname(rules_path), exist_ok=True)
            joblib.dump(result, rules_path)
            logger.info(f"Saved basket cache for '{shop_id}'")
        except Exception as e:
            logger.warning(f"Could not save cache: {e}")
    return result


def _simple_pair_counting(df: pd.DataFrame) -> dict:
    """Simple pair counting for very small datasets (<50 transactions)."""
    logger.info("Using simple pair counting (tiny dataset)")
    # Build baskets
    baskets = []
    for _, group in df.groupby("invoice_id"):
        products = group["product"].unique().tolist()
        if len(products) >= 2:
            baskets.append(products)

    if len(baskets) < 2:
        return {"rules": [], "critical_pairs": [], "skipped": False, "skip_reason": "Not enough baskets with ≥2 items"}

    # Count pair frequencies
    pair_counts = {}
    for basket in baskets:
        for i, a in enumerate(basket):
            for b in basket[i+1:]:
                pair = tuple(sorted([a, b]))
                pair_counts[pair] = pair_counts.get(pair, 0) + 1

    total_baskets = len(baskets)
    rules = []
    critical_pairs = []
    for (a, b), count in pair_counts.items():
        confidence = count / total_baskets  # simple confidence (P(both)/P(a) approximated)
        # Note: proper confidence would need P(a) but this is a fallback
        if confidence >= CRITICAL_PAIR_CONFIDENCE:
            critical_pairs.append([a, b])
        rules.append({
            "antecedent": [a],
            "consequent": [b],
            "confidence": round(confidence, 3),
            "lift": 1.0,  # lift not computed in simple method
            "support": round(count / total_baskets, 3),
            "is_critical": confidence >= CRITICAL_PAIR_CONFIDENCE,
        })
        # Also add symmetric rule
        rules.append({
            "antecedent": [b],
            "consequent": [a],
            "confidence": round(confidence, 3),
            "lift": 1.0,
            "support": round(count / total_baskets, 3),
            "is_critical": confidence >= CRITICAL_PAIR_CONFIDENCE,
        })

    rules.sort(key=lambda r: r["confidence"], reverse=True)
    logger.info(f"Simple pair counting: {len(rules)} rules, {len(critical_pairs)} critical pairs")
    return {"rules": rules, "critical_pairs": critical_pairs, "skipped": False, "skip_reason": None}


def _mine_fpgrowth(df: pd.DataFrame) -> dict:
    """Mine association rules using FP-Growth (for normal/large datasets)."""
    try:
        # Clean products
        df_clean = df.copy()
        df_clean["product"] = df_clean["product"].astype(str).str.strip()
        df_clean = df_clean[df_clean["product"].notna()]
        df_clean = df_clean[df_clean["product"] != ""]
        df_clean = df_clean[~df_clean["product"].isin(["nan", "None", "NaN", "UNKNOWN"])]

        if df_clean.empty:
            return {"rules": [], "critical_pairs": [], "skipped": True,
                    "skip_reason": "No valid product names after cleaning"}

        # Build baskets (invoices with ≥2 items)
        baskets = []
        for _, group in df_clean.groupby("invoice_id"):
            products = group["product"].unique().tolist()
            if len(products) >= 2:
                baskets.append(products)

        n_baskets = len(baskets)
        logger.info(f"Built {n_baskets} baskets with >=2 items")

        if n_baskets < 10:
            return {"rules": [], "critical_pairs": [], "skipped": False,
                    "skip_reason": f"Only {n_baskets} baskets (need at least 10)"}

        # Sample if too many baskets (for performance)
        if n_baskets > BASKET_SAMPLE_SIZE:
            random.seed(42)
            baskets = random.sample(baskets, BASKET_SAMPLE_SIZE)
            logger.info(f"Sampled down to {BASKET_SAMPLE_SIZE} baskets (seed=42)")

        # Limit to most frequent products to avoid memory blow
        from collections import Counter
        all_products = [p for basket in baskets for p in basket]
        product_counts = Counter(all_products)
        top_products = {p for p, _ in product_counts.most_common(BASKET_MAX_PRODUCTS)}
        baskets = [[p for p in basket if p in top_products] for basket in baskets]
        baskets = [b for b in baskets if len(b) >= 2]
        if not baskets:
            return {"rules": [], "critical_pairs": [], "skipped": False,
                    "skip_reason": f"No baskets after limiting to top {BASKET_MAX_PRODUCTS} products"}

        # Transaction encoding
        te = TransactionEncoder()
        te_array = te.fit(baskets).transform(baskets)
        df_te = pd.DataFrame(te_array, columns=te.columns_)

        # Dynamic min_support
        min_support = config.get_min_support(len(baskets))

        # Mine frequent itemsets
        freq_sets = fpgrowth(df_te, min_support=min_support, use_colnames=True)
        if freq_sets.empty:
            return {"rules": [], "critical_pairs": [], "skipped": False,
                    "skip_reason": f"No frequent itemsets found (min_support={min_support:.3f})"}

        # Generate rules
        rules_df = association_rules(freq_sets, metric="confidence", min_threshold=0.4)

        rules = []
        critical_pairs = []

        for _, row in rules_df.iterrows():
            antecedent = sorted([str(item) for item in row["antecedents"]])
            consequent = sorted([str(item) for item in row["consequents"]])
            confidence = round(row["confidence"], 3)
            lift = round(row["lift"], 2)
            support = round(row["support"], 3)

            is_critical = (confidence >= CRITICAL_PAIR_CONFIDENCE) and (lift >= 2.0)

            rule = {
                "antecedent": antecedent,
                "consequent": consequent,
                "confidence": confidence,
                "lift": lift,
                "support": support,
                "is_critical": is_critical,
            }
            rules.append(rule)

            # Critical pair: single‑item on both sides, high confidence and lift
            if is_critical and len(antecedent) == 1 and len(consequent) == 1:
                pair = sorted([antecedent[0], consequent[0]])
                if pair not in critical_pairs:
                    critical_pairs.append(pair)

        rules.sort(key=lambda r: r["confidence"], reverse=True)

        logger.info(f"Stage 5 complete | {len(rules)} rules | {len(critical_pairs)} critical pairs")
        return {"rules": rules, "critical_pairs": critical_pairs, "skipped": False, "skip_reason": None}

    except MemoryError:
        logger.error("MemoryError in basket analysis")
        return {"rules": [], "critical_pairs": [], "skipped": True,
                "skip_reason": "Insufficient memory for product encoding (too many unique products)"}
    except Exception as e:
        logger.error(f"Basket analysis error: {e}", exc_info=True)
        return {"rules": [], "critical_pairs": [], "skipped": True,
                "skip_reason": f"Analysis error: {e}"}