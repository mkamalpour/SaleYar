"""Real model training, loading, migration, and version-safe prediction checks."""
import json
from pathlib import Path
import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
import pytest
from saleyar import config
from models import loader, risk_model, train
from pipeline import stage6_risk

@pytest.fixture(scope="module")
def fitted():
    rng = np.random.default_rng(42)
    frame = pd.DataFrame(rng.uniform(0, 50, (80, len(risk_model.FEATURE_COLS))), columns=risk_model.FEATURE_COLS)
    model = lgb.LGBMRegressor(n_estimators=12, min_child_samples=5, n_jobs=1, verbosity=-1)
    model.fit(frame, 20 + frame["profit_margin"])
    return model, frame


def test_native_training_and_shared_loading():
    path = train._train_lgbm_synthetic(n_samples=128)
    assert path.exists()
    assert not Path(config.LGBM_MODEL_PATH).exists()
    loaded = risk_model.get_model()
    assert loaded["source"] == "native"
    assert loader.get_shared("lgbm_risk")["model"] is loaded["model"]
    assert risk_model.status()["training_versions"]["lightgbm"]


def test_predictions_keep_calibration_and_column_order(fitted):
    model, frame = fitted
    risk_model.save_model(model.booster_, list(frame.columns))
    expected = np.clip(model.booster_.predict(frame, num_threads=1), 0, 100).round(1).tolist()
    assert risk_model.predict(frame[frame.columns[::-1]]) == expected
    assert risk_model.predict(frame.iloc[[0]]) == [expected[0]]
    actual, confidence = stage6_risk._get_model_scores(frame)
    assert actual == expected and confidence > 0


def test_legacy_migration_preserves_original(fitted):
    model, frame = fitted
    path = Path(config.LGBM_MODEL_PATH)
    joblib.dump({"model": model, "feature_cols": list(frame.columns)}, path)
    original = path.read_bytes()
    assert risk_model.get_model()["source"] == "legacy"
    migrated = train.train()
    assert migrated == risk_model.native_path() and migrated.exists()
    assert path.read_bytes() == original
    assert risk_model.get_model()["source"] == "native"


def test_bad_schema_falls_back_without_crashing(fitted):
    model, frame = fitted
    path = risk_model.save_model(model.booster_, list(frame.columns))
    payload = json.loads(path.read_text())
    payload["feature_cols"] = payload["feature_cols"][::-1]
    path.write_text(json.dumps(payload))
    assert risk_model.get_model() is None
    assert risk_model.status()["state"] == "incompatible"
    assert stage6_risk._get_model_scores(frame) == (None, 0.0)
    assert loader.is_ready()


def test_corrupt_native_uses_readable_legacy(fitted):
    model, frame = fitted
    joblib.dump({"model": model, "feature_cols": list(frame.columns)}, config.LGBM_MODEL_PATH)
    risk_model.native_path().write_text("corrupt json")
    assert risk_model.get_model()["source"] == "legacy"
    assert risk_model.status()["warning"]


def test_cached_model_is_cleared_after_deletion(fitted):
    model, frame = fitted
    path = risk_model.save_model(model.booster_, list(frame.columns))
    assert risk_model.predict(frame) is not None
    path.unlink()
    assert risk_model.predict(frame) is None
    assert risk_model.status()["state"] == "missing"


def test_missing_features_and_nonfinite_values_are_handled(fitted):
    model, frame = fitted
    risk_model.save_model(model.booster_, list(frame.columns))
    assert risk_model.predict(frame.drop(columns=[frame.columns[0]])) is None
    frame = frame.copy()
    frame.iloc[0, 0] = np.inf
    assert np.isfinite(risk_model.predict(frame)).all()


def test_force_training_preserves_unreadable_legacy(fitted, monkeypatch):
    model, frame = fitted
    legacy = Path(config.LGBM_MODEL_PATH)
    legacy.write_bytes(b"unreadable legacy model")
    monkeypatch.setattr(train, "_train_lgbm_synthetic", lambda: risk_model.save_model(model.booster_, list(frame.columns)))
    with pytest.raises(RuntimeError, match="--force"):
        train.train()
    assert train.train(force=True).exists()
    assert legacy.read_bytes() == b"unreadable legacy model"
