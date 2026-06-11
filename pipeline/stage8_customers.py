"""
stage8_customers.py — ADAPTIVE CUSTOMER SEGMENTATION

Improvements:
- Single customer → detailed analysis (not skipped)
- 3–20 customers → manual percentile‑based segmentation (no clustering)
- >20 customers → MiniBatchKMeans (thread‑safe) with fallbacks
- Uses net revenue (sales minus returns) for monetary value
- Champion products derived from best customers
"""

import logging
import os
import sys
import warnings

# Thread‑safe settings
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"
os.environ["MKL_THREADING_LAYER"] = "sequential"

import numpy as np
import pandas as pd
from sklearn.preprocessing import RobustScaler

warnings.filterwarnings("ignore", category=UserWarning)

logger = logging.getLogger(__name__)

import config

N_SEGMENTS = 4


def run(df: pd.DataFrame, language: str = "en") -> dict:
    """Run customer segmentation with adaptive method."""
    logger.info("Stage 8: customer segmentation")

    if "customer_id" not in df.columns or df["customer_id"].isna().all():
        reason = _t(language, "No customer ID column found – segmentation skipped.",
                    "ستون شناسه مشتری وجود ندارد – دسته‌بندی مشتریان انجام نشد.")
        logger.info(f"Stage 8 skipped – {reason}")
        return _skip(reason)

    n_customers = df["customer_id"].nunique()
    if n_customers == 1:
        return _single_customer_analysis(df, language)
    if n_customers < config.MIN_CUSTOMERS:
        reason = _t(language,
                    f"Only {n_customers} unique customers – minimum {config.MIN_CUSTOMERS} needed.",
                    f"فقط {n_customers} مشتری یکتا – حداقل {config.MIN_CUSTOMERS} مشتری نیاز است.")
        logger.info(f"Stage 8 skipped – {reason}")
        return _skip(reason)

    # Build RFM table
    rfm = _build_rfm(df)

    # For very small customer base, use manual percentiles
    if n_customers < 20:
        segments, summary = _percentile_segmentation(rfm, language)
        champion_products = _champion_products(df, rfm[rfm["segment"] == "Champions"]["customer_id"].tolist())
        return {
            "segments": segments,
            "summary": summary,
            "champion_products": champion_products,
            "skipped": False,
            "skip_reason": None,
        }

    # Normal clustering path for larger customer bases
    return _cluster_segmentation(rfm, df, language)


def _single_customer_analysis(df: pd.DataFrame, language: str) -> dict:
    """Handle the case of exactly one customer."""
    customer_id = df["customer_id"].iloc[0]
    # Build simple profile
    customer_df = df[df["customer_id"] == customer_id]
    total_spent = (customer_df["qty"] * customer_df["sell_price"]).sum()
    n_invoices = customer_df["invoice_id"].nunique()
    top_products = customer_df.groupby("product")["qty"].sum().nlargest(5).index.tolist()
    segments = [{
        "customer_id": customer_id,
        "segment": "Solo",
        "recency": (df["date"].max() - customer_df["date"].max()).days,
        "frequency": n_invoices,
        "monetary": total_spent,
    }]
    summary = {"Solo": 1}
    return {
        "segments": segments,
        "summary": summary,
        "champion_products": top_products,
        "skipped": False,
        "skip_reason": None,
    }


def _build_rfm(df: pd.DataFrame) -> pd.DataFrame:
    """Build RFM table with net revenue (sales minus returns)."""
    df_work = df.copy()
    # Ensure numeric
    for col in ["qty", "sell_price"]:
        if col in df_work.columns:
            df_work[col] = pd.to_numeric(df_work[col], errors="coerce").fillna(0)
    # Net revenue: sale increases, return_sale decreases
    df_work["net_revenue"] = df_work["qty"] * df_work["sell_price"]
    # For return_sale, net_revenue is negative (already handled)
    now = df_work["date"].max()
    rfm = df_work.groupby("customer_id").agg(
        recency=("date", lambda x: (now - x.max()).days),
        frequency=("invoice_id", "nunique"),
        monetary=("net_revenue", "sum"),
    ).reset_index()
    rfm["recency"] = rfm["recency"].fillna(999).clip(lower=0)
    rfm["frequency"] = rfm["frequency"].fillna(0).clip(lower=1)
    rfm["monetary"] = rfm["monetary"].fillna(0).clip(lower=0)
    return rfm


def _percentile_segmentation(rfm: pd.DataFrame, language: str):
    """Manual percentile‑based segmentation for very small customer base."""
    # Score each customer: lower recency better, higher frequency & monetary better
    recency_score = pd.qcut(rfm["recency"].rank(method="first"), 4, labels=False, duplicates="drop")
    freq_score = pd.qcut(rfm["frequency"].rank(method="first"), 4, labels=False, duplicates="drop")
    mon_score = pd.qcut(rfm["monetary"].rank(method="first"), 4, labels=False, duplicates="drop")
    # Higher score = better customer
    combined = (4 - recency_score) + freq_score + mon_score
    # Assign segments based on combined score percentiles
    if combined.nunique() >= 4:
        labels = pd.qcut(combined, 4, labels=["Champions", "Loyal", "At-Risk", "Lost"], duplicates="drop")
    else:
        # fallback
        labels = pd.cut(combined, bins=4, labels=["Lost", "At-Risk", "Loyal", "Champions"])
    rfm["segment"] = labels
    segments = rfm[["customer_id", "segment", "recency", "frequency", "monetary"]].to_dict("records")
    summary = rfm["segment"].value_counts().to_dict()
    return segments, summary


def _cluster_segmentation(rfm: pd.DataFrame, df: pd.DataFrame, language: str):
    """Cluster customers using MiniBatchKMeans with fallbacks."""
    # Log transform monetary to reduce skew
    if getattr(config, 'RFM_LOG_TRANSFORM', True):
        rfm["monetary_log"] = np.log1p(rfm["monetary"])
        features = ["recency", "frequency", "monetary_log"]
    else:
        features = ["recency", "frequency", "monetary"]
    X = rfm[features].values
    scaler = RobustScaler()
    X_scaled = scaler.fit_transform(X)

    n_clusters = min(N_SEGMENTS, len(rfm))
    labels = None

    # Try MiniBatchKMeans
    try:
        from sklearn.cluster import MiniBatchKMeans
        kmeans = MiniBatchKMeans(n_clusters=n_clusters, random_state=42, batch_size=100)
        labels = kmeans.fit_predict(X_scaled)
        logger.info("Clustering: MiniBatchKMeans")
    except Exception as e:
        logger.warning(f"MiniBatchKMeans failed: {e}")

    # Fallback to AgglomerativeClustering
    if labels is None:
        try:
            from sklearn.cluster import AgglomerativeClustering
            clustering = AgglomerativeClustering(n_clusters=n_clusters)
            labels = clustering.fit_predict(X_scaled)
            logger.info("Clustering: AgglomerativeClustering")
        except Exception as e:
            logger.warning(f"AgglomerativeClustering failed: {e}")

    # Final fallback: manual percentiles
    if labels is None:
        segments, summary = _percentile_segmentation(rfm, language)
        champion_products = _champion_products(df, [])
        return {
            "segments": segments,
            "summary": summary,
            "champion_products": champion_products,
            "skipped": False,
            "skip_reason": None,
        }

    # Label clusters semantically
    cluster_stats = rfm.copy()
    cluster_stats["_cluster"] = labels
    rfm["_cluster"] = labels                     # <-- ADD THIS LINE
    cluster_quality = cluster_stats.groupby("_cluster").agg({
        "recency": "mean",
        "frequency": "mean",
        "monetary": "mean"
    }).reset_index()
    cluster_quality["score"] = (-cluster_quality["recency"].rank() +
                                cluster_quality["frequency"].rank() +
                                cluster_quality["monetary"].rank())
    cluster_quality = cluster_quality.sort_values("score", ascending=False)
    seg_names = ["Champions", "Loyal", "At-Risk", "Lost"]
    label_map = {}
    for i, row in cluster_quality.iterrows():
        label_map[row["_cluster"]] = seg_names[i] if i < len(seg_names) else "Other"
    rfm["segment"] = rfm["_cluster"].map(label_map)

    segments = rfm[["customer_id", "segment", "recency", "frequency", "monetary"]].to_dict("records")
    summary = rfm["segment"].value_counts().to_dict()
    champion_ids = rfm[rfm["segment"] == "Champions"]["customer_id"].tolist()
    champion_products = _champion_products(df, champion_ids)

    return {
        "segments": segments,
        "summary": summary,
        "champion_products": champion_products,
        "skipped": False,
        "skip_reason": None,
    }


def _champion_products(df: pd.DataFrame, champion_ids: list) -> list:
    """Top 5 products purchased by Champion customers."""
    if not champion_ids:
        return []
    champ_df = df[df["customer_id"].isin(champion_ids)]
    if "qty" not in champ_df.columns or "product" not in champ_df.columns:
        return []
    champ_df["qty"] = pd.to_numeric(champ_df["qty"], errors="coerce").fillna(0)
    top = champ_df.groupby("product")["qty"].sum().nlargest(5).index.tolist()
    return top


def _skip(reason: str) -> dict:
    return {
        "segments": [],
        "summary": {},
        "champion_products": [],
        "skipped": True,
        "skip_reason": reason,
    }


def _t(language: str, en: str, fa: str) -> str:
    return fa if language == "fa" else en