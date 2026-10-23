"""Small deterministic demand baseline and chronological validation scores."""
import numpy as np


def values(history, horizon):
    history = np.asarray(history, dtype=float)
    if history.ndim != 1 or not len(history) or not np.isfinite(history).all() or (history < 0).any():
        raise ValueError("Demand history must contain finite nonnegative daily quantities")
    if len(history) >= 14:
        return np.resize(history[-7:], horizon), "Weekly seasonal naive (local baseline)"
    return np.full(horizon, history[-7:].mean()), "Recent mean (local baseline)"


def scores(actual, predicted, method):
    actual, predicted = np.asarray(actual, dtype=float), np.asarray(predicted, dtype=float)
    if actual.shape != predicted.shape or not len(actual) or not np.isfinite(actual).all() or not np.isfinite(predicted).all():
        raise ValueError("Validation requires matching finite held-out observations and predictions")
    errors = np.abs(actual - predicted)
    denominator = float(np.abs(actual).sum())
    return {"method": method, "split": "chronological holdout", "days": len(actual),
            "mae": round(float(errors.mean()), 4),
            "wape_percent": round(float(errors.sum()) / denominator * 100, 2) if denominator else None}


def forecast(ts, reason):
    history = np.asarray(ts["y"], dtype=float)
    prediction, method = values(history, 90)
    validation = None
    if len(history) >= 21:
        heldout, validation_method = values(history[:-7], 7)
        validation = scores(history[-7:], heldout, validation_method)
    return {"method": method, "daily_forecast": prediction.tolist(),
            "daily_lo80": None, "daily_hi80": None,
            "h30": round(float(prediction[:30].sum()), 1),
            "h60": round(float(prediction[:60].sum()), 1),
            "h90": round(float(prediction.sum()), 1),
            "confidence": "Low", "low_confidence": True, "skipped": False, "skip_reason": None,
            "validation": validation, "data_end": str(ts["ds"].iloc[-1].date()),
            "note": reason + ". Baseline only; assumes the invoice history is complete and missing sale days mean zero demand. No calibrated prediction interval."}
