"""Shared input validation for APIs, CLI, and filesystem-backed shop state."""
import math
import re

SHOP_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$"
GOALS = {"maximize_profit", "cover_customers", "reduce_risk"}

def validate_shop_id(shop_id: str) -> str:
    if not isinstance(shop_id, str) or re.fullmatch(SHOP_ID_PATTERN, shop_id) is None:
        raise ValueError("Shop ID must be 1-64 letters, digits, hyphens or underscores, starting with a letter or digit.")
    return shop_id

def validate_analysis(budget, goal, language):
    if not math.isfinite(budget) or budget <= 0:
        raise ValueError("Budget must be finite and greater than zero.")
    if goal not in GOALS:
        raise ValueError("Unsupported optimization goal.")
    if language not in {"en", "fa"}:
        raise ValueError("Language must be en or fa.")


# Bounded striped locks prevent concurrent writes to the same shop caches.
from functools import wraps
from inspect import signature
from threading import RLock
_SHOP_LOCKS = [RLock() for _ in range(64)]

def shop_serialized(function):
    arguments = signature(function)
    @wraps(function)
    def wrapped(*args, **kwargs):
        bound = arguments.bind(*args, **kwargs)
        bound.apply_defaults()
        shop_id = validate_shop_id(bound.arguments.get("shop_id", "default"))
        with _SHOP_LOCKS[hash(shop_id) % len(_SHOP_LOCKS)]:
            return function(*args, **kwargs)
    return wrapped
