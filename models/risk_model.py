"""Version-resilient LightGBM artifacts and one shared, file-aware model cache."""
from importlib.metadata import PackageNotFoundError, version
import json
import logging
import os
from pathlib import Path
import platform
import tempfile
from threading import RLock

import numpy as np
import pandas as pd
from saleyar import config

logger = logging.getLogger(__name__)
FEATURE_COLS = ["profit_margin", "liquidity_rate", "price_volatility", "hope_rate",
                "portfolio_weight", "days_since_last_sale", "conversion_rate",
                "margin_vs_avg", "price_change_count"]
FORMAT = "saleyar-lightgbm"
SCHEMA_VERSION = 1
_lock = RLock()
_cached_signature = None
_cached_model = None
_status = {"available": False, "state": "not loaded"}


def native_path():
    return Path(config.LGBM_MODEL_PATH).with_suffix(".json")


def environment_versions():
    values = {"python": platform.python_version()}
    for package in ("lightgbm", "scikit-learn", "numpy", "pandas", "scipy", "joblib"):
        try:
            values[package] = version(package)
        except PackageNotFoundError:
            values[package] = "not installed"
    return values


def _signature():
    result = []
    for path in (native_path(), Path(config.LGBM_MODEL_PATH)):
        try:
            stat = path.stat()
            result.append((str(path.resolve()), stat.st_mtime_ns, stat.st_size))
        except OSError:
            result.append((str(path.absolute()), None, None))
    return tuple(result)


def _validate_booster(booster, features):
    if not isinstance(features, list) or not features or len(set(features)) != len(features):
        raise ValueError("The model has an invalid or missing feature schema.")
    if not all(isinstance(name, str) and name in FEATURE_COLS for name in features):
        raise ValueError("The model uses unsupported feature names; retrain with models/train.py.")
    if booster.num_feature() != len(features):
        raise ValueError("Model feature count does not match its saved schema.")
    names = booster.feature_name()
    if names != features:
        raise ValueError("Model feature order does not match its saved schema.")
    return {"model": booster, "feature_cols": features}


def _read_native(path):
    import lightgbm as lgb
    with path.open(encoding="utf-8") as source:
        payload = json.load(source)
    if payload.get("format") != FORMAT or payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unsupported risk model format/schema; retrain with models/train.py.")
    booster = lgb.Booster(model_str=payload["model_text"])
    result = _validate_booster(booster, payload["feature_cols"])
    result.update({"source": "native", "training_versions": payload.get("training_versions", {})})
    return result


def _read_legacy(path):
    # Legacy pickle files are local operator-owned artifacts, never uploaded models.
    import joblib
    import lightgbm as lgb
    payload = joblib.load(path)
    if isinstance(payload, dict):
        predictor = payload.get("model")
        features = payload.get("feature_cols")
    else:
        predictor, features = payload, None
    booster = predictor if isinstance(predictor, lgb.Booster) else getattr(predictor, "booster_", None)
    if booster is None:
        raise ValueError("Legacy file does not contain a fitted LightGBM model.")
    if features is None:
        features = booster.feature_name()
    # Rehydrate the native tree model: prediction no longer uses a pickled sklearn wrapper.
    native = lgb.Booster(model_str=booster.model_to_string())
    result = _validate_booster(native, list(features))
    result.update({"source": "legacy", "training_versions": payload.get("training_versions", {}) if isinstance(payload, dict) else {}})
    return result


def get_model(force=False):
    """Reload on replacement, creation, deletion, or explicit invalidation."""
    global _cached_signature, _cached_model, _status
    with _lock:
        signature = _signature()
        if not force and signature == _cached_signature:
            return _cached_model
        _cached_signature, _cached_model = signature, None
        errors = []
        for path, reader in ((native_path(), _read_native), (Path(config.LGBM_MODEL_PATH), _read_legacy)):
            if not path.is_file():
                continue
            try:
                _cached_model = reader(path)
                _status = {"available": True, "state": "loaded", "source": _cached_model["source"],
                           "path": str(path), "training_versions": _cached_model["training_versions"],
                           "warning": "; ".join(errors) or None}
                return _cached_model
            except Exception as exc:
                errors.append(f"{path.name}: {type(exc).__name__}: {exc}")
        _status = {"available": False, "state": "incompatible" if errors else "missing",
                   "error": "; ".join(errors) or None,
                   "recovery": "Run python models/train.py --force to create a compatible native model; existing pickle files are preserved."}
        if errors:
            logger.warning("Risk model unavailable; using rules. %s", _status["error"])
        return None


def status():
    get_model()
    with _lock:
        return dict(_status)


def save_model(booster, features, training_versions=None):
    """Atomically save native trees and schema; never overwrite legacy pickle files."""
    _validate_booster(booster, list(features))
    payload = {"format": FORMAT, "schema_version": SCHEMA_VERSION,
               "feature_cols": list(features), "model_text": booster.model_to_string(),
               "training_versions": training_versions or environment_versions(),
               "target": "rule_score_0_100", "training_source": "synthetic-rule-derived"}
    path = native_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=path.name + ".", suffix=".tmp", delete=False) as target:
            temporary = target.name
            json.dump(payload, target, ensure_ascii=False, allow_nan=False)
            target.flush()
            os.fsync(target.fileno())
        # Validate the file before publishing it to running processes.
        _read_native(Path(temporary))
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
    get_model(force=True)
    return path


def migrate_legacy():
    """Convert a readable trusted legacy model without retraining or deleting it."""
    loaded = _read_legacy(Path(config.LGBM_MODEL_PATH))
    return save_model(loaded["model"], loaded["feature_cols"], loaded["training_versions"] or environment_versions())


def predict(frame):
    loaded = get_model()
    if loaded is None or frame.empty:
        return None
    features = loaded["feature_cols"]
    missing = [name for name in features if name not in frame.columns]
    if missing:
        logger.warning("Risk model inputs missing: %s; using rules.", ", ".join(missing))
        return None
    inputs = frame.reindex(columns=features).apply(pd.to_numeric, errors="coerce")
    inputs = inputs.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    try:
        # Single-thread inference avoids oversubscription alongside forecast jobs.
        values = np.asarray(loaded["model"].predict(inputs, num_threads=1, validate_features=True), dtype=float)
        if values.shape != (len(frame),) or not np.isfinite(values).all():
            raise ValueError("Model returned invalid predictions.")
        # Predictions already represent 0-100 scores; batch min/max scaling changes meaning.
        return np.clip(values, 0, 100).round(1).tolist()
    except Exception as exc:
        logger.warning("Risk model prediction failed; using rules: %s", exc)
        return None
