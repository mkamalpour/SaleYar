"""Behavioral regressions for imports, calculations, API validation and serving."""
import json
from pathlib import Path
import threading
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from api import main as api
from models import loader
from output import reporter
from pipeline import runner, stage1_cleaner, stage2_metrics, stage7_optimizer, stage8_customers
from ui.server import create_dashboard_handler


def transactions():
    return pd.DataFrame([
        {"invoice_id": "p", "date": "2025-01-01", "product": "Tea", "qty": 100, "buy_price": 10, "sell_price": 99, "transaction_type": "purchase", "customer_id": "supplier"},
        {"invoice_id": "s", "date": "2025-01-02", "product": "Tea", "qty": 3, "buy_price": 10, "sell_price": 15, "transaction_type": "sale", "customer_id": "customer"},
        {"invoice_id": "r", "date": "2025-01-03", "product": "Tea", "qty": 1, "buy_price": 10, "sell_price": 15, "transaction_type": "return_sale", "customer_id": "customer"},
        {"invoice_id": "d", "date": "2025-01-04", "product": "Tea", "qty": 2, "buy_price": 10, "sell_price": 0, "transaction_type": "damaged", "customer_id": None},
    ]).assign(date=lambda frame: pd.to_datetime(frame.date))


def test_purchases_do_not_inflate_sales_or_margin():
    row = stage2_metrics.run(transactions()).iloc[0]
    assert row.total_sold == 3
    assert row.total_revenue == 45
    assert row.total_profit == 15
    assert row.avg_sell_price == 15
    assert row.profit_margin == 50


def test_inventory_damaged_goods_reduce_stock():
    assert runner.calculate_net_change_from_transactions(transactions()) == {"Tea": 96.0}


def test_customers_exclude_suppliers_and_subtract_returns():
    result = stage8_customers.run(transactions())
    assert len(result["segments"]) == 1
    assert result["segments"][0]["customer_id"] == "customer"
    assert result["segments"][0]["monetary"] == 30


def test_jalali_and_invalid_dates_are_not_fabricated():
    result, issues = stage1_cleaner._parse_dates(pd.DataFrame({"date": ["\u06f1\u06f4\u06f0\u06f3/\u06f0\u06f1/\u06f0\u06f1", "bad", "2025-01-02"]}), "en")
    assert result.date.iloc[0] == pd.Timestamp("2024-03-20")
    assert pd.isna(result.date.iloc[1])
    assert any(issue["row_index"] == 1 and issue["severity"] == "error" for issue in issues)


@pytest.mark.parametrize("shop", ["../outside", "..", "/tmp", "x/y", "x\\y", "", "a" * 65])
def test_shop_paths_reject_traversal(shop):
    with pytest.raises(ValueError):
        loader.get_shop_dir(shop)
    with pytest.raises(ValueError):
        reporter.load_latest(shop)


def test_health_counts_sale_today_as_fresh():
    assert reporter._calculate_health_score({"products": [{"days_since_last_sale": 0}], "data_quality": 0, "vs_bank": -100}) == 25


def test_json_nonfinite_values_become_null():
    output = api.safe_json_serialize({"a": np.nan, "b": [float("inf"), np.float64("-inf")]})
    assert output == {"a": None, "b": [None, None]}
    json.dumps(output, allow_nan=False)


@pytest.mark.parametrize("form", [{"budget": "-1"}, {"budget": "nan"}, {"shop_id": "../outside"}, {"goal": "unknown"}, {"language": "xx"}])
def test_api_rejects_invalid_form_inputs(form):
    client = TestClient(api.app)
    response = client.post("/analyze", data=form, files={"file": ("report.csv", b"a,b,c\n1,2,3")}, headers={"X-API-Key": "saleyar-test-key-not-a-secret"})
    assert response.status_code == 422


def test_api_requires_key():
    assert TestClient(api.app).get("/healthcheck").status_code == 403


@pytest.mark.parametrize("endpoint", ["/analyze", "/optimize", "/basket", "/risk"])
def test_upload_size_errors_keep_413(endpoint, monkeypatch):
    monkeypatch.setattr(api, "MAX_UPLOAD_BYTES", 4)
    response = TestClient(api.app).post(endpoint, files={"file": ("x.csv", b"a,b,c\n123")}, headers={"X-API-Key": "saleyar-test-key-not-a-secret"})
    assert response.status_code == 413


def test_analysis_queue_is_bounded(monkeypatch):
    monkeypatch.setattr(api.config, "MAX_PENDING_JOBS", 0)
    response = TestClient(api.app).post("/analyze", files={"file": ("x.csv", b"a,b,c\n1,2,3")}, headers={"X-API-Key": "saleyar-test-key-not-a-secret"})
    assert response.status_code == 429


def test_deadweight_never_restocked_and_fractional_demand_rounds_up():
    assert stage7_optimizer._calculate_needed_quantity(0, [10] * 30, 30, segment="Deadweight") == 0
    assert stage7_optimizer._calculate_needed_quantity(0, [0.1] * 3, 3) == 1


def test_optimizer_goals_change_priorities():
    frame = pd.DataFrame({"avg_buy_price": [10, 10], "avg_sell_price": [20, 30], "risk_score": [5, 95], "conversion_rate": [90, 10]})
    assert stage7_optimizer._objective_scores(frame, "maximize_profit").idxmax() == 1
    assert stage7_optimizer._objective_scores(frame, "reduce_risk").idxmax() == 0
    assert stage7_optimizer._objective_scores(frame, "cover_customers").idxmax() == 0


def test_greedy_respects_budget_share_and_stock():
    frame = pd.DataFrame({"product": ["Tea"], "avg_buy_price": [10.0], "avg_sell_price": [15.0], "unified_score": [50.0], "profit_margin": [50.0], "daily_sales": [10.0], "segment": ["Star"]})
    result = stage7_optimizer._solve_greedy(frame, 100, "maximize_profit", {"Tea": 0}, {}, "en")
    assert result["total_cost"] <= 35
    assert result["order"][0]["qty"] <= 3


def test_dashboard_server_exposes_only_public_assets(tmp_path):
    (tmp_path / "ui/assets").mkdir(parents=True)
    (tmp_path / "ui/owner.html").write_text('<script type="application/json">__SALEYAR_RUNTIME_CONFIG__</script>')
    (tmp_path / "ui/assets/owner.css").write_text('body {}')
    (tmp_path / ".env").write_text('PRIVATE DATA')
    handler = create_dashboard_handler(tmp_path, "test-key</script>", 8123)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        body = urllib.request.urlopen(base + "/ui/owner.html").read().decode()
        assert "8123" in body and "__SALEYAR_RUNTIME_CONFIG__" not in body
        assert "test-key</script>" not in body
        runtime = json.loads(body.split(">", 1)[1].rsplit("</script>", 1)[0])
        assert runtime["apiKey"] == "test-key</script>"
        assert urllib.request.urlopen(base + "/ui/assets/owner.css").status == 200
        for route in ("/.env", "/config.py", "/models/.local_api_key", "/ui/assets/../../.env"):
            with pytest.raises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(base + route)
            assert error.value.code == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_invalid_date_indices_survive_duplicate_removal():
    frame = transactions()
    frame = pd.concat([frame.iloc[[0]], frame.iloc[[0]], frame.iloc[[1]], frame.iloc[[2]]], ignore_index=True)
    frame["date"] = frame["date"].astype(str)
    frame.loc[3, "date"] = "invalid"
    result = stage1_cleaner.run(frame.to_csv(index=False).encode(), "report.csv")
    assert result["passed"]
    assert "s" in set(result["df"].invoice_id)
    assert "r" not in set(result["df"].invoice_id)


def test_basket_cache_is_bound_to_current_data(monkeypatch):
    from pipeline import stage5_basket
    seen = []
    def mine(frame):
        names = sorted(frame["product"].unique().tolist())
        seen.append(names)
        return {"rules": names, "skipped": False}
    monkeypatch.setattr(stage5_basket, "_simple_pair_counting", mine)
    frame = pd.DataFrame({"invoice_id": range(20), "product": ["Tea"] * 20, "qty": [1] * 20, "transaction_type": ["sale"] * 20})
    assert stage5_basket.run(frame, "cache-test")["rules"] == ["Tea"]
    assert stage5_basket.run(frame, "cache-test")["rules"] == ["Tea"]
    frame["product"] = "Coffee"
    assert stage5_basket.run(frame, "cache-test")["rules"] == ["Coffee"]
    assert seen == [["Tea"], ["Coffee"]]


def test_saved_metadata_updates_memory_cache():
    metadata = {"data_hash": "new-data"}
    loader.save_shop_metadata("example", metadata)
    assert loader.get_shop_metadata("example") == metadata


def test_healthy_report_not_replaced_by_rejected_upload(monkeypatch):
    api._jobs.clear()
    api._reports.clear()
    api._store_report("default", {"health_score": 75})
    class ImmediateExecutor:
        def submit(self, task):
            task()
    monkeypatch.setattr(api, "_executor", ImmediateExecutor())
    monkeypatch.setattr(runner, "run_pipeline", lambda *args: {"passed": False, "stop_reason": "bad dates"})
    client = TestClient(api.app)
    headers = {"X-API-Key": "saleyar-test-key-not-a-secret"}
    response = client.post("/analyze", files={"file": ("x.csv", b"a,b,c\n1,2,3")}, headers=headers)
    assert response.status_code == 200
    result = client.get("/result/" + response.json()["job_id"], headers=headers).json()
    assert result["result"]["passed"] is False
    assert api._load_report("default")["health_score"] == 75
    api._jobs.clear()
    api._reports.clear()


def test_api_analysis_pipeline_round_trip_preserves_shop_artifacts():
    class ImmediateExecutor:
        def submit(self, task):
            task()
    from unittest.mock import patch
    api._jobs.clear()
    api._reports.clear()
    shop_dir = Path(loader.get_shop_dir("round-trip"))
    shop_dir.mkdir(parents=True)
    sentinel = shop_dir / "trained-artifact.txt"
    sentinel.write_text("keep")
    frame = transactions()
    client = TestClient(api.app)
    headers = {"X-API-Key": "saleyar-test-key-not-a-secret"}
    with patch.object(api, "_executor", ImmediateExecutor()):
        response = client.post("/analyze", data={"shop_id": "round-trip"},
            files={"file": ("synthetic.csv", frame.to_csv(index=False).encode())}, headers=headers)
    assert response.status_code == 200
    result = client.get("/result/" + response.json()["job_id"], headers=headers).json()
    assert result["status"] == "done"
    assert result["result"]["passed"] is True
    assert result["result"]["inventory"]["Tea"] == 96.0
    assert result["result"]["report"]["products"][0]["total_revenue"] == 45
    assert sentinel.read_text() == "keep"
    assert client.get("/report/round-trip", headers=headers).status_code == 200
    api._jobs.clear()
    api._reports.clear()


def test_trend_uses_stable_linear_slope():
    from pipeline.stage3_forecast import _calculate_trend
    values = np.arange(1, 31, dtype=float)
    assert _calculate_trend(pd.DataFrame({"y": values})) == pytest.approx(1 / values.mean())
    assert _calculate_trend(pd.DataFrame({"y": [5.0] * 30})) == 0.0
    assert _calculate_trend(pd.DataFrame({"y": [np.nan] * 30})) == 0.0
