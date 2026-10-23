"""Known-answer demand and association regressions using fictional transactions."""
import numpy as np
import pandas as pd
import pytest
from pipeline import stage3_forecast as forecasts, stage5_basket as baskets
from pipeline import forecast_baseline


def invoices(groups):
    return pd.DataFrame([{"invoice_id": i, "product": p, "qty": 1, "transaction_type": "sale"}
                         for i, group in enumerate(groups) for p in group])


def test_directional_probabilities_include_single_product_invoices():
    frame = invoices([["A", "B"], ["A", "B"], ["A"], ["A"], ["A"], ["B"], ["C"], ["C"], ["C"], ["C"]])
    result = baskets._simple_pair_counting(frame)
    by_source = {r["antecedent"][0]: r for r in result["rules"]}
    assert by_source["A"]["confidence"] == pytest.approx(0.4)
    assert by_source["B"]["confidence"] == pytest.approx(2 / 3, abs=0.001)
    assert by_source["A"]["support"] == 0.2
    assert by_source["A"]["lift"] == pytest.approx(4 / 3, abs=0.01)
    assert result["critical_pairs"] == []


def test_high_conditional_probability_alone_does_not_make_critical_pair():
    result = baskets._simple_pair_counting(invoices([["A", "B"]] * 5 + [["A"]] * 5))
    assert any(r["confidence"] == 1 for r in result["rules"])
    assert all(r["lift"] == 1 for r in result["rules"])
    assert result["critical_pairs"] == []


def test_fpgrowth_keeps_same_invoice_denominator():
    result = baskets._mine_fpgrowth(invoices([["A", "B"]] * 10 + [["A"]] * 20 + [["C"]] * 20))
    assert not result["skipped"]
    rule = next(r for r in result["rules"] if r["antecedent"] == ["B"] and r["consequent"] == ["A"])
    assert rule["support"] == 0.2
    assert rule["confidence"] == 1
    assert rule["lift"] == pytest.approx(5 / 3, abs=0.01)
    assert not rule["is_critical"]


def test_baseline_runs_without_statsforecast_and_validates_only_past_data(monkeypatch):
    monkeypatch.setattr(forecasts, "HAS_STATSFORECAST", False)
    pattern = np.tile(np.arange(1, 8), 6)
    raw = pd.DataFrame({"date": pd.date_range("2026-01-01", periods=42), "product": "A",
                        "transaction_type": "sale", "qty": pattern, "sell_price": 1})
    kpis = pd.DataFrame({"product": ["A"], "sufficiency": ["rich"]})
    result = forecasts.run(raw, kpis)["A"]
    assert not result["skipped"]
    assert len(result["daily_forecast"]) == 90
    np.testing.assert_array_equal(result["daily_forecast"][:7], pattern[-7:])
    assert result["h90"] == pytest.approx(sum(result["daily_forecast"]))
    assert result["validation"]["mae"] == 0
    assert result["validation"]["wape_percent"] == 0
    assert result["confidence"] == "Low" and result["daily_lo80"] is None
    assert "baseline" in result["method"] and "StatsForecast" in result["note"]


def test_baseline_holdout_is_not_trained_on_its_answers():
    frame = pd.DataFrame({"ds": pd.date_range("2026-01-01", periods=28), "y": [1.] * 21 + [100.] * 7})
    result = forecast_baseline.forecast(frame, "test")
    assert result["validation"]["mae"] == 99
    assert result["validation"]["wape_percent"] == 99
    assert result["daily_forecast"][:7] == [100.] * 7


def test_zero_demand_holdout_does_not_divide_by_zero():
    result = forecast_baseline.forecast(pd.DataFrame({"ds": pd.date_range("2026-01-01", periods=28), "y": [0.] * 28}), "test")
    assert result["validation"]["mae"] == 0
    assert result["validation"]["wape_percent"] is None
    assert result["h90"] == 0


def test_daily_series_combines_times_and_includes_trailing_zero_sale_days():
    frame = pd.DataFrame({"date": list(pd.date_range("2026-01-01", periods=8)) + [pd.Timestamp("2026-01-01 18:00")], "qty": [1.] * 9})
    result = forecasts._build_timeseries(frame, "A", pd.Timestamp("2026-01-21"))
    assert len(result) == 21
    assert result["y"].iloc[0] == 2
    assert result["y"].iloc[-1] == 0
    assert result["y"].sum() == 9


def test_unvalidated_forecast_is_never_rated_high():
    assert forecasts._calculate_confidence(None, "rich") == "Unvalidated"
    assert forecasts._calculate_confidence({"wape_percent": None}, "rich") == "Unvalidated"


def test_statistical_validation_uses_reserved_dates_and_training_only(monkeypatch):
    monkeypatch.setattr(forecasts.config, "ENABLE_TREND_ADJUSTMENT", False)
    dates = pd.date_range("2026-01-01", periods=28)
    batch = pd.DataFrame({"unique_id": "A", "ds": dates, "y": [2.] * 21 + [10.] * 7})
    class Model:
        def forecast(self, df, h, level):
            assert h == 7 and df["ds"].max() == dates[20]
            assert set(df["y"]) == {2.}
            return pd.DataFrame({"unique_id": "A", "ds": dates[-7:], "AutoTheta": [2.] * 7})
    result = forecasts._model_validation(Model(), batch, "AutoTheta")["A"]
    assert result["mae"] == 8 and result["wape_percent"] == 80
    assert forecasts._calculate_confidence(result, "rich") == "Low"


@pytest.mark.parametrize("average", [float("nan"), float("inf"), -1.0])
def test_invalid_category_average_does_not_become_an_available_forecast(average):
    assert forecasts._category_fallback("A", "category", {"category": average})["skipped"]


@pytest.mark.parametrize("prediction,expected_error,expected_support", [(2., 80, "Low"), (7., 30, "Medium")])
def test_statistical_support_is_based_on_holdout_not_future_history_similarity(monkeypatch, prediction, expected_error, expected_support):
    monkeypatch.setattr(forecasts, "HAS_STATSFORECAST", True)
    monkeypatch.setattr(forecasts, "AutoTheta", lambda **kw: object(), raising=False)
    monkeypatch.setattr(forecasts.config, "ENABLE_TREND_ADJUSTMENT", False)
    monkeypatch.setattr(forecasts.config, "FORECAST_CONFIDENCE_MAPE_HIGH", 20)
    monkeypatch.setattr(forecasts.config, "FORECAST_CONFIDENCE_MAPE_LOW", 50)
    dates = pd.date_range("2026-01-01", periods=28)
    class Model:
        def __init__(self, **kw): pass
        def forecast(self, df, h, level):
            start = pd.to_datetime(df["ds"]).max() + pd.Timedelta(days=1)
            return pd.DataFrame({"unique_id": ["A"] * h, "ds": pd.date_range(start, periods=h), "AutoTheta": [prediction] * h})
    monkeypatch.setattr(forecasts, "StatsForecast", Model, raising=False)
    raw = pd.DataFrame({"date": dates, "product": "A", "transaction_type": "sale", "qty": [2.] * 21 + [10.] * 7, "sell_price": 1})
    result = forecasts.run(raw, pd.DataFrame({"product": ["A"], "sufficiency": ["rich"]}))["A"]
    assert result["validation"]["wape_percent"] == expected_error and result["confidence"] == expected_support
    assert result["low_confidence"] is (expected_support == "Low")
    assert result["h90"] == 90 * prediction
