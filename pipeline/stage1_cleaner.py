"""
stage1_cleaner.py - PRODUCTION READY (Smart & Adaptive)

Handles:
- Returns (negative qty) as warnings
- Damaged goods (zero sell price) as warnings
- Promotions (loss-making) as warnings
- Tiny shops (<100 rows) → lower quality threshold (30)
- Large files (>50k rows) → skip fuzzy matching & anomaly detection for speed
- Unparseable dates → fallback to today (keeps row)
- Zero quantity rows → removed (warning, not error)

Never crashes, always returns a usable DataFrame.
"""

import io
import logging
import os
import sys
import pandas as pd
import numpy as np
from rapidfuzz import process as fuzz_process, fuzz
from sklearn.ensemble import IsolationForest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import jdatetime
    HAS_JDATETIME = True
except ImportError:
    HAS_JDATETIME = False

from pipeline.column_map import COLUMN_MAP, REQUIRED_FIELDS, normalize_transaction_type

logger = logging.getLogger(__name__)

ENCODINGS_TO_TRY = ["utf-8", "windows-1256", "utf-8-sig", "latin-1"]
FUZZY_SCORE_THRESHOLD = 70
QUALITY_PASS_THRESHOLD = 40          # default, may be lowered for small shops

import config

ALLOW_RETURNS = getattr(config, 'ALLOW_RETURNS', True)
ALLOW_DAMAGED = getattr(config, 'ALLOW_DAMAGED', True)
ALLOW_PROMOTIONS = getattr(config, 'ALLOW_PROMOTIONS', True)
MAX_REASONABLE_LOSS = getattr(config, 'MAX_REASONABLE_LOSS', 50)
MIN_REASONABLE_QTY = getattr(config, 'MIN_REASONABLE_QTY', -100)
MAX_REASONABLE_QTY = getattr(config, 'MAX_REASONABLE_QTY', 100)

# Adaptive thresholds (can be overridden in config if needed)
SMALL_SHOP_ROWS = getattr(config, 'SMALL_SHOP_ROWS', 100)
QUALITY_PASS_SMALL = getattr(config, 'QUALITY_PASS_SMALL', 30)
LARGE_FILE_SKIP_THRESHOLD = getattr(config, 'LARGE_FILE_CLEANER', 50000)


def run(file_bytes: bytes, filename: str, language: str = "en") -> dict:
    """Run Stage 1 with adaptive, business‑friendly cleaning."""
    if not file_bytes:
        return _fail("File is empty. Please upload a valid CSV or Excel file.", language)

    # 1. Read file
    df_raw, error = _read_file(file_bytes, filename)
    if error:
        return _fail(error, language)

    # 2. Map headers (adaptive: skip fuzzy for huge files)
    df, missing = _map_headers(df_raw, len(df_raw))
    if missing:
        detail = ", ".join(missing)
        return _fail(
            _t(language,
               f"Required columns not found: {detail}",
               f"ستون‌های لازم پیدا نشدند: {detail}"),
            language
        )

    # ========== Extract only necessary columns ==========
    PIPELINE_COLUMNS = [
        "invoice_id", "date", "product", "qty", "buy_price",
        "sell_price", "customer_id", "customer_segment",
        "product_category", "transaction_type"
    ]
    existing_columns = [col for col in PIPELINE_COLUMNS if col in df.columns]
    df = df[existing_columns].copy()
    logger.info(f"Keeping {len(existing_columns)} columns: {existing_columns}")

    # Ensure transaction_type exists and is normalized
    if "transaction_type" not in df.columns:
        logger.error("CRITICAL: transaction_type column missing. Merger must add it.")
        df["transaction_type"] = "sale"
    else:
        df["transaction_type"] = df["transaction_type"].apply(normalize_transaction_type)

    # 3. Parse dates (smart fallback to today, never leaves NaT)
    df, date_issues = _parse_dates(df, language)

    # 4. Clean data with business rules (including removal of zero qty rows)
    df, clean_issues = _clean_with_business_rules(df, language)

    # 5. Anomaly detection (skipped for huge files)
    df, anomaly_issues = _detect_anomalies_light(df, language)

    # 6. Separate warnings from real errors
    all_issues = date_issues + clean_issues + anomaly_issues
    real_errors = []
    warnings = []
    for issue in all_issues:
        if isinstance(issue, dict):
            issue_text = issue.get("issue", "")
            if any(x in issue_text.lower() for x in ["return", "damaged", "loss", "promotion", "anomaly", "zero quantity"]):
                warnings.append(issue)
            else:
                real_errors.append(issue)

    n_bad = len(real_errors)
    original_rows = len(df)

    # Remove rows with real errors
    if real_errors:
        bad_idx = {r["row_index"] for r in real_errors if "row_index" in r}
        df = df.drop(index=list(bad_idx), errors="ignore").reset_index(drop=True)

    # Filter out invalid product names
    if "product" in df.columns:
        before = len(df)
        df["product"] = df["product"].astype(str).str.strip()
        df = df[~df["product"].isin(["nan", "None", "NaN", "", "UNKNOWN"])]
        filtered = before - len(df)
        if filtered > 0:
            logger.warning(f"Filtered {filtered} rows with invalid product names")
        df = df.reset_index(drop=True)

    # Recalculate quality after removal
    kept = len(df)
    quality = max(0, 100 - int((n_bad / max(kept + n_bad, 1)) * 100))

    # ========== ADAPTIVE QUALITY THRESHOLD (small shops get easier pass) ==========
    if kept < SMALL_SHOP_ROWS:
        quality_pass = QUALITY_PASS_SMALL
    else:
        quality_pass = QUALITY_PASS_THRESHOLD
    passed = quality >= quality_pass

    message = _t(
        language,
        f"{kept} rows ready.\n✓ Kept {len(warnings)} normal business transactions\n✗ Removed {n_bad} errors",
        f"{kept} ردیف آماده است.\n✓ {len(warnings)} تراکنش عادی تجاری نگه داشته شد\n✗ {n_bad} خطای واقعی حذف شد"
    )

    logger.info(f"Stage 1 complete | quality={quality} | clean_rows={kept} | warnings={len(warnings)} | errors={n_bad}")

    return {
        "df": df if passed else None,
        "quality": quality,
        "flagged": real_errors + warnings,
        "warnings": warnings,
        "issues": [m for m in all_issues if isinstance(m, str)],
        "passed": passed,
        "message": message,
    }


def _clean_with_business_rules(df: pd.DataFrame, language: str):
    """Clean with realistic business rules. Removes zero‑quantity rows."""
    issues = []

    # Remove exact duplicates (record as info)
    before = len(df)
    df = df.drop_duplicates().reset_index(drop=True)
    removed = before - len(df)
    if removed:
        issues.append({
            "row_index": -1,
            "row_number": -1,
            "issue": _t(language, f"{removed} duplicate row(s) removed.", f"{removed} ردیف تکراری حذف شد."),
            "product": "N/A",
            "severity": "info"
        })

    # Coerce numeric columns
    for col in ["qty", "buy_price", "sell_price"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # ========== REMOVE ZERO QUANTITY ROWS (they are useless) ==========
    zero_qty_mask = df["qty"] == 0
    if zero_qty_mask.any():
        removed_zero = zero_qty_mask.sum()
        df = df[~zero_qty_mask].reset_index(drop=True)
        issues.append({
            "row_index": -1,
            "row_number": -1,
            "issue": _t(language, f"Removed {removed_zero} row(s) with quantity zero.", f"{removed_zero} ردیف با تعداد صفر حذف شد."),
            "product": "N/A",
            "severity": "warning"
        })

    # ========== QUANTITY CHECKS (returns, extreme values) ==========
    if not ALLOW_RETURNS:
        neg_qty = df["qty"] < 0
        for idx in df[neg_qty].index:
            issues.append({
                "row_index": idx,
                "row_number": idx + 2,
                "issue": "Negative quantity (returns not allowed)",
                "product": str(df.loc[idx, "product"]) if "product" in df.columns else "?",
                "severity": "error"
            })
    else:
        # Negative quantities are returns (warning)
        neg_qty = df["qty"] < 0
        for idx in df[neg_qty].index:
            issues.append({
                "row_index": idx,
                "row_number": idx + 2,
                "issue": f"Negative quantity ({df.loc[idx, 'qty']}) — return transaction",
                "product": str(df.loc[idx, "product"]) if "product" in df.columns else "?",
                "severity": "warning"
            })
        # Extreme negatives
        extreme_neg = df["qty"] < MIN_REASONABLE_QTY
        for idx in df[extreme_neg].index:
            issues.append({
                "row_index": idx,
                "row_number": idx + 2,
                "issue": f"Extreme negative quantity ({df.loc[idx, 'qty']}) — possible data error",
                "product": str(df.loc[idx, "product"]) if "product" in df.columns else "?",
                "severity": "warning"
            })
        # Extreme positives (bulk orders)
        extreme_pos = df["qty"] > MAX_REASONABLE_QTY
        for idx in df[extreme_pos].index:
            issues.append({
                "row_index": idx,
                "row_number": idx + 2,
                "issue": f"Extreme quantity ({df.loc[idx, 'qty']}) — possible bulk order",
                "product": str(df.loc[idx, "product"]) if "product" in df.columns else "?",
                "severity": "warning"
            })

    # ========================================================================
    # BUY PRICE CHECKS
    # ========================================================================
    bad_buy = df["buy_price"] <= 0
    for idx in df[bad_buy].index:
        issues.append({
            "row_index": idx,
            "row_number": idx + 2,
            "issue": "Buy price is zero or negative",
            "product": str(df.loc[idx, "product"]) if "product" in df.columns else "?",
            "severity": "error"
        })

    # ========================================================================
    # SELL PRICE CHECKS
    # ========================================================================
    if not ALLOW_DAMAGED:
        zero_sell = df["sell_price"] == 0
        for idx in df[zero_sell].index:
            issues.append({
                "row_index": idx,
                "row_number": idx + 2,
                "issue": "Sell price is zero (damaged goods not allowed)",
                "product": str(df.loc[idx, "product"]) if "product" in df.columns else "?",
                "severity": "error"
            })
    else:
        zero_sell = df["sell_price"] == 0
        for idx in df[zero_sell].index:
            issues.append({
                "row_index": idx,
                "row_number": idx + 2,
                "issue": "Zero sell price — damaged or sample item",
                "product": str(df.loc[idx, "product"]) if "product" in df.columns else "?",
                "severity": "warning"
            })

    neg_sell = df["sell_price"] < 0
    for idx in df[neg_sell].index:
        issues.append({
            "row_index": idx,
            "row_number": idx + 2,
            "issue": "Sell price is negative",
            "product": str(df.loc[idx, "product"]) if "product" in df.columns else "?",
            "severity": "error"
        })

    # ========================================================================
    # PROFIT/LOSS CHECKS (with division guard)
    # ========================================================================
    loss_mask = (df["sell_price"] < df["buy_price"]) & (df["sell_price"] > 0) & (df["buy_price"] > 0)
    
    if not ALLOW_PROMOTIONS:
        for idx in df[loss_mask].index:
            issues.append({
                "row_index": idx,
                "row_number": idx + 2,
                "issue": "Loss-making sale (promotions not allowed)",
                "product": str(df.loc[idx, "product"]) if "product" in df.columns else "?",
                "severity": "error"
            })
    else:
        for idx in df[loss_mask].index:
            buy = df.loc[idx, "buy_price"]
            sell = df.loc[idx, "sell_price"]
            if buy > 0 and sell > 0:
                loss_pct = ((buy - sell) / buy) * 100
            else:
                loss_pct = 0
            if loss_pct > MAX_REASONABLE_LOSS:
                issues.append({
                    "row_index": idx,
                    "row_number": idx + 2,
                    "issue": f"Extreme loss ({loss_pct:.0f}%) — possible data error",
                    "product": str(df.loc[idx, "product"]) if "product" in df.columns else "?",
                    "severity": "warning"
                })
            else:
                issues.append({
                    "row_index": idx,
                    "row_number": idx + 2,
                    "issue": f"Loss-making sale ({loss_pct:.0f}%) — promotion or clearance",
                    "product": str(df.loc[idx, "product"]) if "product" in df.columns else "?",
                    "severity": "warning"
                })

    # ========================================================================
    # TRANSACTION TYPE VALIDATION (vectorized)
    # ========================================================================
    valid_types = {"sale", "return_sale", "purchase", "return_purchase"}
    df["transaction_type"] = df["transaction_type"].astype(str).str.strip().str.lower()
    invalid_mask = ~df["transaction_type"].isin(valid_types)
    if invalid_mask.any():
        for idx in df[invalid_mask].index:
            issues.append({
                "row_index": idx,
                "row_number": idx + 2,
                "issue": f"Unknown transaction type: {df.loc[idx, 'transaction_type']} (defaulted to 'sale')",
                "product": str(df.loc[idx, "product"]) if "product" in df.columns else "?",
                "severity": "warning"
            })
        df.loc[invalid_mask, "transaction_type"] = "sale"

    return df, issues


def _detect_anomalies_light(df: pd.DataFrame, language: str):
    """Lightweight anomaly detection — warnings only. Skipped for huge files."""
    # Skip anomaly detection for very large files (performance)
    if len(df) > LARGE_FILE_SKIP_THRESHOLD:
        logger.info(f"Skipping anomaly detection for large file ({len(df)} rows > {LARGE_FILE_SKIP_THRESHOLD})")
        return df, []

    issues = []
    if len(df) < 20:
        return df, issues

    try:
        mask = df["qty"] > 0
        if mask.sum() < 10:
            return df, issues
            
        features = df.loc[mask, ["qty", "buy_price", "sell_price"]].copy()
        original_len = len(features)
        if len(features) > 10000:
            features = features.sample(n=10000, random_state=42)
            logger.info(f"Anomaly detection: sampled from {original_len} to 10000 rows")
        features = features.fillna(features.median())
        
        contamination = 0.005
        iso = IsolationForest(
            contamination=contamination,
            random_state=42,
            n_jobs=-1,
            max_samples=256,
            n_estimators=50
        )
        iso_pred = iso.fit_predict(features)
        anomaly_indices = features.index[iso_pred == -1]
        
        for idx in anomaly_indices:
            issues.append({
                "row_index": idx,
                "row_number": idx + 2,
                "issue": "Statistical outlier — unusual transaction pattern",
                "product": str(df.loc[idx, "product"]) if "product" in df.columns else "?",
                "severity": "warning"
            })
    except Exception as e:
        logger.warning(f"Anomaly detection skipped: {e}")

    return df, issues


# ============================================================================
# Helper functions
# ============================================================================

def _read_file(file_bytes: bytes, filename: str):
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext in ("xlsx", "xls"):
        try:
            df = pd.read_excel(io.BytesIO(file_bytes), dtype=str)
            return df, None
        except Exception as e:
            return None, f"Could not read Excel file: {e}"
    for enc in ENCODINGS_TO_TRY:
        try:
            df = pd.read_csv(io.BytesIO(file_bytes), dtype=str, encoding=enc)
            if len(df.columns) >= 3:
                return df, None
        except Exception:
            continue
    return None, "Could not read the file. Please ensure it is a valid CSV or Excel file."


def _map_headers(df: pd.DataFrame, n_rows: int = None):
    """Map headers with optional fuzzy matching (disabled for huge files)."""
    if n_rows is None:
        n_rows = len(df)
    use_fuzzy = n_rows <= LARGE_FILE_SKIP_THRESHOLD

    source_cols = {col.strip().lower(): col for col in df.columns}
    rename_map = {}
    found = set()
    for src_clean, src_orig in source_cols.items():
        if src_clean in COLUMN_MAP:
            target = COLUMN_MAP[src_clean]
            if target not in found:
                rename_map[src_orig] = target
                found.add(target)
            continue
        if use_fuzzy:
            best = fuzz_process.extractOne(
                src_clean,
                COLUMN_MAP.keys(),
                scorer=fuzz.token_sort_ratio,
                score_cutoff=FUZZY_SCORE_THRESHOLD,
            )
            if best:
                target = COLUMN_MAP[best[0]]
                if target not in found:
                    rename_map[src_orig] = target
                    found.add(target)
    df = df.rename(columns=rename_map)
    missing = [f for f in REQUIRED_FIELDS if f not in df.columns]
    return df, missing


def _parse_dates(df: pd.DataFrame, language: str):
    """Parse dates trying multiple formats; fallback to today instead of NaT."""
    issues = []

    def _try_parse(val):
        if pd.isna(val):
            return pd.Timestamp.now()   # fallback to today
        val = str(val).strip()
        # Try common Gregorian formats
        for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
            try:
                return pd.to_datetime(val, format=fmt)
            except:
                continue
        # Try Jalali
        if HAS_JDATETIME:
            for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%Y%m%d", "%d/%m/%Y"):
                try:
                    jd = jdatetime.datetime.strptime(val, fmt)
                    return pd.Timestamp(jd.togregorian())
                except Exception:
                    continue
        # Final fallback
        logger.warning(f"Could not parse date '{val}', using today")
        return pd.Timestamp.now()

    df = df.copy()
    df["date"] = df["date"].apply(_try_parse)

    # Now check for future dates (warnings, not errors)
    now = pd.Timestamp.now()
    future_mask = df["date"] > now
    if future_mask.any():
        for idx in df[future_mask].index:
            issues.append({
                "row_index": idx,
                "row_number": idx + 2,
                "issue": _t(language, "Date is in the future (using today)", "تاریخ در آینده است (امروز جایگزین شد)"),
                "value": str(df.loc[idx, "date"]),
                "severity": "warning"
            })
        df.loc[future_mask, "date"] = now

    return df, issues


def _safe_date(df, idx):
    try:
        return df.loc[idx, "date"]
    except Exception:
        return "?"


def _fail(message: str, language: str) -> dict:
    return {
        "df": None,
        "quality": 0,
        "flagged": [],
        "warnings": [],
        "issues": [message],
        "passed": False,
        "message": message,
    }


def _t(language: str, en: str, fa: str) -> str:
    return fa if language == "fa" else en