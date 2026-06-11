"""
loader.py

Loads trained models at server startup and holds them in memory.
The API never reads .pkl files per request — always uses objects loaded here.

Models loaded:
  - models/lgbm_risk.pkl               — shared LightGBM model (all shops)
  - models/shops/{shop_id}/basket_rules.pkl   — per‑shop basket rules
  - models/shops/{shop_id}/metadata.json      — shop metadata

NOT loaded (unused):
  - cluster_products.pkl (Stage 4 never uses pre‑trained clusters)
"""

import json
import logging
import os
import shutil
import sys

import joblib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

logger = logging.getLogger(__name__)

_SHARED_MODELS = {}      # { model_name: model_object }
_SHOP_MODELS   = {}      # { shop_id: { model_name: model_object } }
_LOAD_STATUS   = {}      # { "shared": {...}, shop_id: {...} }


def load_all():
    """Call once at server startup."""
    _load_shared_models()
    _load_all_shops()


def _load_shared_models():
    _LOAD_STATUS["shared"] = {}
    path = config.LGBM_MODEL_PATH
    if os.path.exists(path):
        try:
            _SHARED_MODELS["lgbm_risk"] = joblib.load(path)
            _LOAD_STATUS["shared"]["lgbm_risk"] = "loaded"
            logger.info(f"Loaded shared LightGBM model from {path}")
        except Exception as e:
            _LOAD_STATUS["shared"]["lgbm_risk"] = f"error: {e}"
            logger.error(f"Failed to load LightGBM model: {e}")
    else:
        _LOAD_STATUS["shared"]["lgbm_risk"] = "not found"
        logger.warning(
            f"LightGBM model not found at {path}. "
            "Run 'python models/train.py --shop_id demo' to train it."
        )


def _load_all_shops():
    shops_dir = config.SHOPS_DIR
    if not os.path.exists(shops_dir):
        logger.warning(f"shops directory not found: {shops_dir}")
        return
    for shop_id in os.listdir(shops_dir):
        shop_path = os.path.join(shops_dir, shop_id)
        if os.path.isdir(shop_path):
            _load_shop(shop_id)


def _load_shop(shop_id: str):
    shop_dir = os.path.join(config.SHOPS_DIR, shop_id)
    _SHOP_MODELS[shop_id] = {}
    _LOAD_STATUS[shop_id] = {}

    # Basket rules (used by Stage 5)
    basket_path = os.path.join(shop_dir, "basket_rules.pkl")
    if os.path.exists(basket_path):
        try:
            _SHOP_MODELS[shop_id]["basket_rules"] = joblib.load(basket_path)
            _LOAD_STATUS[shop_id]["basket_rules"] = "loaded"
            logger.info(f"Loaded basket rules for shop '{shop_id}'")
        except Exception as e:
            _LOAD_STATUS[shop_id]["basket_rules"] = f"error: {e}"
            logger.error(f"Failed to load basket rules for shop '{shop_id}': {e}")
    else:
        _LOAD_STATUS[shop_id]["basket_rules"] = "not found"

    # Metadata (optional)
    meta_path = os.path.join(shop_dir, "metadata.json")
    if os.path.exists(meta_path):
        try:
            with open(meta_path, encoding="utf-8") as f:
                _SHOP_MODELS[shop_id]["metadata"] = json.load(f)
        except Exception as e:
            logger.warning(f"Could not load metadata for shop '{shop_id}': {e}")


def get_shared(model_name: str):
    """Retrieve a shared model (e.g., 'lgbm_risk')."""
    return _SHARED_MODELS.get(model_name)


def get_shop_model(shop_id: str, model_name: str):
    """Retrieve a per‑shop model (e.g., 'basket_rules')."""
    return _SHOP_MODELS.get(shop_id, {}).get(model_name)


def get_shop_basket_rules(shop_id: str):
    """Convenience: return basket rules for a shop, or None."""
    return get_shop_model(shop_id, "basket_rules")


def get_status() -> dict:
    """Return load status (used by /healthcheck)."""
    return {
        "shared": _LOAD_STATUS.get("shared", {}),
        "shops":  {k: v for k, v in _LOAD_STATUS.items() if k != "shared"},
    }


def get_shop_dir(shop_id: str) -> str:
    return os.path.join(config.SHOPS_DIR, shop_id)


def get_shop_metadata(shop_id: str):
    """Return metadata dict for a shop, or None."""
    return _SHOP_MODELS.get(shop_id, {}).get("metadata")


def save_shop_metadata(shop_id: str, metadata: dict) -> None:
    shop_dir = get_shop_dir(shop_id)
    os.makedirs(shop_dir, exist_ok=True)
    with open(os.path.join(shop_dir, "metadata.json"), "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)


def clear_shop_models(shop_id: str) -> None:
    shop_dir = get_shop_dir(shop_id)
    if os.path.exists(shop_dir):
        shutil.rmtree(shop_dir)
        # Also remove from in‑memory cache
        _SHOP_MODELS.pop(shop_id, None)
        _LOAD_STATUS.pop(shop_id, None)
        logger.info(f"Cleared all models for shop '{shop_id}'")


def is_ready(shop_id: str = None) -> bool:
    """
    True if the system is ready to serve requests.
    Requires at least the shared LightGBM model to be loaded.
    For basket rules, we don't require them (stage can skip).
    """
    lgbm_ok = _LOAD_STATUS.get("shared", {}).get("lgbm_risk") == "loaded"
    return lgbm_ok