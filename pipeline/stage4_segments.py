"""
stage4_segments.py — ADAPTIVE & ACCURATE SEGMENTATION

Improvements:
- Adaptive outlier threshold: 2.5 for <30 products, else 1.8
- Uses rule‑based segmentation for <15 products (deterministic)
- Clustering (Agglomerative) for >=15 products
- Seasonal products NEVER become Deadweight
- Star validation (configurable margin/liquidity thresholds)
- All thresholds from config.py
"""

import logging
import os
import sys
import numpy as np
import pandas as pd
from sklearn.cluster import AgglomerativeClustering
from sklearn.preprocessing import RobustScaler
from scipy.spatial.distance import cdist

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

logger = logging.getLogger(__name__)

MIN_PRODUCTS_CLUSTER = getattr(config, 'MIN_PRODUCTS_CLUSTER', 15)
OUTLIER_THRESHOLD = getattr(config, 'OUTLIER_THRESHOLD', 1.8)
OUTLIER_THRESHOLD_SMALL = getattr(config, 'OUTLIER_THRESHOLD_SMALL', 2.5)   # for <30 products
RISKY_VOLATILITY_THRESHOLD = getattr(config, 'RISKY_VOLATILITY_THRESHOLD', 100)
STAR_MARGIN_MIN = getattr(config, 'STAR_MARGIN_MIN', 15)
STAR_LIQUIDITY_MIN = getattr(config, 'STAR_LIQUIDITY_MIN', 40)
N_CLUSTERS = 5
FEATURE_COLS = [
    "profit_margin", "liquidity_rate", "price_volatility", "days_since_last_sale",
    "portfolio_weight", "conversion_rate", "annual_roi", "hope_rate"
]


def run(df_kpis: pd.DataFrame) -> pd.DataFrame:
    """Add segment column to DataFrame."""
    logger.info("Stage 4: product segmentation")
    n_products = len(df_kpis)
    df_out = df_kpis.copy()

    # Small shop: use deterministic rule‑based segmentation
    if n_products < MIN_PRODUCTS_CLUSTER:
        logger.info(f"Rule‑based segmentation ({n_products} products)")
        segments, confidences = _rule_based_segmentation(df_out)
        df_out["segment"] = segments
        df_out["segment_confidence"] = confidences
        df_out["segment_skipped"] = False
        df_out["segment_skip_reason"] = f"Rule‑based (fewer than {MIN_PRODUCTS_CLUSTER} products)"
        return df_out

    # Larger shop: use clustering
    available = [c for c in FEATURE_COLS if c in df_out.columns]
    if len(available) < 3:
        logger.warning(f"Too few features ({len(available)}), falling back to rule‑based")
        segments, confidences = _rule_based_segmentation(df_out)
        df_out["segment"] = segments
        df_out["segment_confidence"] = confidences
        df_out["segment_skipped"] = True
        df_out["segment_skip_reason"] = f"Only {len(available)} features available"
        return df_out

    # Scale features
    X_raw = df_out[available].fillna(0).values
    scaler = RobustScaler()
    X = scaler.fit_transform(X_raw)

    # Clustering
    n_clusters = min(N_CLUSTERS, n_products)
    model = AgglomerativeClustering(n_clusters=n_clusters, linkage="ward")
    raw_labels = model.fit_predict(X)

    # Compute centroids and cluster scores
    centroids = np.array([X[raw_labels == k].mean(axis=0) for k in range(n_clusters)])
    cluster_scores = _score_clusters(centroids, df_out, raw_labels, available)

    # Label clusters semantically
    label_map = _build_label_map(cluster_scores, n_clusters)

    # Assign segments with outlier detection (adaptive threshold)
    outlier_thresh = OUTLIER_THRESHOLD_SMALL if n_products < 30 else OUTLIER_THRESHOLD
    segments, confidences = _assign_with_outlier_detection(
        X, centroids, raw_labels, label_map, outlier_thresh, n_products
    )

    # Post‑processing: validate Star products & protect seasonal from Deadweight
    segments = _validate_star_products(df_out, segments)
    segments = _protect_seasonal_from_deadweight(df_out, segments)

    df_out["segment"] = segments
    df_out["segment_confidence"] = confidences
    df_out["segment_skipped"] = False
    df_out["segment_skip_reason"] = None

    counts = pd.Series(segments).value_counts().to_dict()
    logger.info(f"Stage 4 complete | {counts}")
    return df_out


def _rule_based_segmentation(df: pd.DataFrame) -> tuple:
    """Deterministic rule‑based segmentation (for small shops)."""
    segments = []
    confidences = []

    for _, row in df.iterrows():
        margin = row.get("profit_margin", 0)
        liquidity = row.get("liquidity_rate", 0)
        days_idle = row.get("days_since_last_sale", 999)
        volatility = row.get("price_volatility", 0)
        best_season = row.get("best_season", "")
        is_seasonal = best_season not in ["Unknown", "None", ""]

        # Star
        if margin > STAR_MARGIN_MIN and liquidity > STAR_LIQUIDITY_MIN:
            seg = "Star"
            conf = min(100, 70 + margin/2 + liquidity/4)
        # Seasonal (takes priority over Deadweight)
        elif is_seasonal and (margin > 5 or liquidity > 30):
            seg = "Seasonal"
            conf = 80
        # Deadweight (but not seasonal)
        elif (margin < 5 or days_idle > 90 or liquidity < 10) and not is_seasonal:
            seg = "Deadweight"
            conf = min(90, 60 + (days_idle/10) if days_idle > 90 else 40)
        # Risky
        elif volatility > RISKY_VOLATILITY_THRESHOLD:
            seg = "Risky"
            conf = 70
        # Reliable (the rest)
        else:
            seg = "Reliable"
            conf = 70

        # Outlier condition (extreme cases)
        if margin < -5 or (days_idle > 180 and liquidity < 5):
            seg = "Outlier"
            conf = 90

        segments.append(seg)
        confidences.append(round(conf, 1))

    return segments, confidences


def _score_clusters(centroids, df_kpis, raw_labels, feature_cols):
    """Score each cluster based on average KPIs."""
    df_tmp = df_kpis.copy()
    df_tmp["_cluster"] = raw_labels
    scores = {}
    for k in range(len(centroids)):
        group = df_tmp[df_tmp["_cluster"] == k]
        scores[k] = {
            "margin":     float(group["profit_margin"].mean()) if "profit_margin" in group else 0,
            "liquidity":  float(group["liquidity_rate"].mean()) if "liquidity_rate" in group else 0,
            "volatility": float(group["price_volatility"].mean()) if "price_volatility" in group else 0,
            "days_idle":  float(group["days_since_last_sale"].mean()) if "days_since_last_sale" in group else 0,
            "roi":        float(group["annual_roi"].mean()) if "annual_roi" in group else 0,
            "size":       len(group),
        }
    return scores


def _build_label_map(cluster_scores: dict, n_clusters: int) -> dict:
    """Assign semantic labels (Star, Deadweight, Risky, Seasonal, Reliable)."""
    assigned = {}
    remaining = list(cluster_scores.keys())

    # Star: highest (margin + liquidity) combo, require size >=2
    if remaining:
        best_star = max(remaining, key=lambda k: cluster_scores[k]["margin"] * 0.6 + cluster_scores[k]["liquidity"] * 0.4)
        if cluster_scores[best_star]["size"] >= 2 and cluster_scores[best_star]["margin"] > 10:
            assigned[best_star] = "Star"
            remaining.remove(best_star)

    # Deadweight: lowest margin * liquidity
    if remaining:
        dead = min(remaining, key=lambda k: cluster_scores[k]["margin"] * cluster_scores[k]["liquidity"])
        assigned[dead] = "Deadweight"
        remaining.remove(dead)

    # Risky: highest volatility
    if remaining:
        risky = max(remaining, key=lambda k: cluster_scores[k]["volatility"])
        assigned[risky] = "Risky"
        remaining.remove(risky)

    # Seasonal: highest ROI
    if remaining:
        seasonal = max(remaining, key=lambda k: cluster_scores[k]["roi"] if cluster_scores[k]["roi"] else 0)
        assigned[seasonal] = "Seasonal"
        remaining.remove(seasonal)

    # Everything else becomes Reliable
    for k in remaining:
        assigned[k] = "Reliable"

    return assigned


def _assign_with_outlier_detection(X, centroids, raw_labels, label_map, outlier_threshold, n_products):
    """Assign segments, marking outliers."""
    distances = cdist(X, centroids)
    nearest_idx = distances.argmin(axis=1)
    nearest_dist = distances.min(axis=1)

    dist_mean = nearest_dist.mean()
    dist_std = nearest_dist.std() + 1e-9
    z_scores = (nearest_dist - dist_mean) / dist_std

    max_dist = nearest_dist.max() + 1e-9
    base_conf = (1 - nearest_dist / max_dist) * 100

    segments = []
    confidences = []
    for i, k in enumerate(nearest_idx):
        if z_scores[i] > outlier_threshold:
            segments.append("Outlier")
            confidences.append(round(max(0.0, base_conf[i] - 20), 1))
        else:
            seg = label_map.get(int(k), "Reliable")
            segments.append(seg)
            cluster_size = sum(raw_labels == k)
            size_boost = min(15, cluster_size / n_products * 20)
            conf = min(100.0, base_conf[i] + size_boost)
            confidences.append(round(conf, 1))

    return segments, confidences


def _validate_star_products(df: pd.DataFrame, segments: list) -> list:
    """Reassign products to 'Star' only if they truly meet criteria."""
    new_segments = segments.copy()
    for i, (idx, row) in enumerate(df.iterrows()):
        if segments[i] == "Star":
            margin = row.get("profit_margin", 0)
            liquidity = row.get("liquidity_rate", 0)
            if margin < STAR_MARGIN_MIN or liquidity < STAR_LIQUIDITY_MIN:
                new_segments[i] = "Reliable"
                logger.debug(f"Product {row['product']} demoted from Star (margin={margin}, liq={liquidity})")
    return new_segments


def _protect_seasonal_from_deadweight(df: pd.DataFrame, segments: list) -> list:
    """Ensure seasonal products are never marked Deadweight."""
    new_segments = segments.copy()
    for i, (idx, row) in enumerate(df.iterrows()):
        best_season = row.get("best_season", "")
        is_seasonal = best_season not in ["Unknown", "None", ""]
        if is_seasonal and segments[i] == "Deadweight":
            new_segments[i] = "Seasonal"
            logger.debug(f"Product {row['product']} protected from Deadweight (seasonal)")
    return new_segments