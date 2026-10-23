"""Invoice-based basket associations, with exact pairs for small datasets.

Single-product invoices remain observations. Confidence is directional P(B|A),
support is P(A and B), and lift compares that confidence with P(B).
Larger datasets use bounded FP-Growth sampling and product selection.
"""

from saleyar.validation import shop_serialized

import hashlib
import logging
import os
import sys
import joblib
import pandas as pd
from mlxtend.frequent_patterns import fpgrowth, association_rules
from mlxtend.preprocessing import TransactionEncoder
import random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from saleyar import config
from models.loader import get_shop_dir

logger = logging.getLogger(__name__)

CRITICAL_PAIR_CONFIDENCE = getattr(config, 'CRITICAL_PAIR_CONFIDENCE', 0.70)
BASKET_MAX_PRODUCTS = getattr(config, 'BASKET_MAX_PRODUCTS', 200)
BASKET_SAMPLE_SIZE = getattr(config, 'BASKET_SAMPLE_SIZE', 2000)


@shop_serialized
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
    rules_path = os.path.join(get_shop_dir(shop_id), "basket_rules.pkl")
    fingerprint = hashlib.sha256(pd.util.hash_pandas_object(
        sales_df[["invoice_id", "product", "qty"]], index=False).values.tobytes() +
        str(('conditional-v2-all-invoices', config.MIN_BASKET_ROWS, CRITICAL_PAIR_CONFIDENCE, BASKET_MAX_PRODUCTS, BASKET_SAMPLE_SIZE)).encode()).hexdigest()
    if os.path.exists(rules_path):
        try:
            data = joblib.load(rules_path)
            if data.get("fingerprint") == fingerprint and "result" in data:
                return data["result"]
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
            joblib.dump({"fingerprint": fingerprint, "result": result}, rules_path)
            logger.info(f"Saved basket cache for '{shop_id}'")
        except Exception as e:
            logger.warning(f"Could not save cache: {e}")
    return result


def _baskets(df):
    """Each invoice is one observation, including single-product purchases."""
    clean = df.dropna(subset=["invoice_id", "product"]).copy()
    clean["product"] = clean["product"].astype(str).str.strip()
    clean = clean[~clean["product"].isin(["", "nan", "None", "NaN", "UNKNOWN"])]
    if "qty" in clean:
        clean = clean[pd.to_numeric(clean["qty"], errors="coerce") > 0]
    return [sorted(set(group["product"])) for _, group in clean.groupby("invoice_id")]


def _simple_pair_counting(df: pd.DataFrame) -> dict:
    """Exact directional pair statistics over all valid invoices."""
    from collections import Counter
    from itertools import combinations
    baskets = _baskets(df)
    if len(baskets) < 2:
        return {"rules": [], "critical_pairs": [], "skipped": False,
                "skip_reason": "Need at least two valid invoices for basket rules"}
    singles = Counter(product for basket in baskets for product in basket)
    pairs = Counter(pair for basket in baskets for pair in combinations(basket, 2))
    total = len(baskets)
    rules, critical_pairs = [], []
    for (a, b), count in sorted(pairs.items()):
        support = count / total
        lift = count * total / (singles[a] * singles[b])
        critical = False
        for source, destination in [(a, b), (b, a)]:
            confidence = count / singles[source]
            is_critical = confidence >= CRITICAL_PAIR_CONFIDENCE and lift >= 2.0
            critical |= is_critical
            rules.append({"antecedent": [source], "consequent": [destination],
                          "confidence": round(confidence, 3), "lift": round(lift, 2),
                          "support": round(support, 3), "is_critical": is_critical})
        if critical:
            critical_pairs.append([a, b])
    rules.sort(key=lambda row: (-row["confidence"], row["antecedent"], row["consequent"]))
    return {"rules": rules, "critical_pairs": critical_pairs, "skipped": False,
            "skip_reason": None, "invoices_used": total}


def _mine_fpgrowth(df: pd.DataFrame) -> dict:
    """Mine association rules using FP-Growth (for normal/large datasets)."""
    try:
        baskets = _baskets(df)
        n_baskets = len(baskets)
        if n_baskets < 10:
            return _simple_pair_counting(df)

        # Sample if too many baskets (for performance)
        if n_baskets > BASKET_SAMPLE_SIZE:
            baskets = random.Random(42).sample(baskets, BASKET_SAMPLE_SIZE)
            logger.info(f"Sampled down to {BASKET_SAMPLE_SIZE} baskets (seed=42)")

        # Limit to most frequent products to avoid memory blow
        from collections import Counter
        all_products = [p for basket in baskets for p in basket]
        product_counts = Counter(all_products)
        top_products = {p for p, _ in product_counts.most_common(BASKET_MAX_PRODUCTS)}
        baskets = [[p for p in basket if p in top_products] for basket in baskets]
        # Keep single-item and empty trimmed rows in the probability denominator.
        if not any(baskets):
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

            is_critical = (float(row["confidence"]) >= CRITICAL_PAIR_CONFIDENCE) and (float(row["lift"]) >= 2.0)

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