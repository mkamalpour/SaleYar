#!/usr/bin/env python3
"""
test_all.py

Comprehensive test suite for SaleYar project.
Run with: python test_all.py

Tests all components FAST. Skips slow parts, uses small data.
"""

import sys
import os
import io
import time
import traceback
import subprocess
import pandas as pd
import numpy as np

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def timing_decorator(func):
    """Decorator to time test functions with proper error handling"""
    def wrapper():
        start = time.time()
        try:
            result = func()
            elapsed = (time.time() - start) * 1000
            status = "✅" if result else "❌"
            print(f"  [{elapsed:>5.0f}ms] {status} {func.__name__}")
            return result
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            print(f"  [{elapsed:>5.0f}ms] ❌ {func.__name__}")
            print(f"     Error: {str(e)[:100]}")
            return False
    return wrapper


@timing_decorator
def test_config():
    """Test configuration loads"""
    import config
    assert hasattr(config, 'API_KEY')
    assert hasattr(config, 'MIN_SALES_RICH')
    assert hasattr(config, 'FORECAST_HORIZON')
    return True


@timing_decorator
def test_imports():
    """Test all critical imports"""
    import config
    from models import loader
    from output import reporter
    from pipeline import stage1_cleaner, stage2_metrics, stage3_forecast
    from pipeline import stage4_segments, stage5_basket, stage6_risk
    from pipeline import stage7_optimizer, stage8_customers, stage9_priority
    from data.generate_data import make_invoices
    return True


@timing_decorator
def test_column_map():
    """Test column mapping works"""
    from pipeline.column_map import map_column, REQUIRED_FIELDS
    assert map_column('product') == 'product'
    assert map_column('نام کالا') == 'product'
    assert map_column('تعداد') == 'qty'
    assert map_column('قیمت فروش') == 'sell_price'
    assert 'invoice_id' in REQUIRED_FIELDS
    return True


@timing_decorator
def test_data_generation():
    """Test data generation (small sample)"""
    from data.generate_data import make_invoices
    df, _ = make_invoices(n_invoices=20, n_customers=5)
    assert len(df) > 0
    assert 'customer_id' in df.columns
    assert 'product' in df.columns
    assert 'date' in df.columns
    return True


@timing_decorator
def test_stage1_cleaner():
    """Test Stage 1 Cleaner"""
    from data.generate_data import make_invoices
    from pipeline.stage1_cleaner import run as stage1_run
    
    df, _ = make_invoices(n_invoices=20, n_customers=5)
    csv_bytes = df.to_csv(index=False).encode('utf-8')
    
    result = stage1_run(csv_bytes, "test.csv", "en")
    assert result["passed"] == True
    assert result["quality"] >= 0
    assert result["df"] is not None
    return True


@timing_decorator
def test_stage2_metrics():
    """Test Stage 2 KPIs"""
    from data.generate_data import make_invoices
    from pipeline.stage1_cleaner import run as stage1_run
    from pipeline.stage2_metrics import run as stage2_run
    
    df, _ = make_invoices(n_invoices=30, n_customers=5)
    csv_bytes = df.to_csv(index=False).encode('utf-8')
    
    s1 = stage1_run(csv_bytes, "test.csv", "en")
    df_clean = s1["df"]
    
    df_kpis = stage2_run(df_clean)
    assert len(df_kpis) > 0
    assert 'profit_margin' in df_kpis.columns
    assert 'sufficiency' in df_kpis.columns
    return True


@timing_decorator
def test_stage3_forecast():
    """Test Stage 3 Forecast"""
    from data.generate_data import make_invoices
    from pipeline.stage1_cleaner import run as stage1_run
    from pipeline.stage2_metrics import run as stage2_run
    from pipeline.stage3_forecast import run as stage3_run
    
    df, _ = make_invoices(n_invoices=100, n_customers=10)
    csv_bytes = df.to_csv(index=False).encode('utf-8')
    
    s1 = stage1_run(csv_bytes, "test.csv", "en")
    df_clean = s1["df"]
    df_kpis = stage2_run(df_clean)
    forecasts = stage3_run(df_clean, df_kpis)
    
    assert len(forecasts) > 0
    # Check that daily_forecast exists (or product was skipped)
    first_product = list(forecasts.keys())[0]
    fc = forecasts[first_product]
    if not fc.get('skipped', False):
        assert 'daily_forecast' in fc
    return True


@timing_decorator
def test_stage4_segments():
    """Test Stage 4 Segmentation"""
    from data.generate_data import make_invoices
    from pipeline.stage1_cleaner import run as stage1_run
    from pipeline.stage2_metrics import run as stage2_run
    from pipeline.stage4_segments import run as stage4_run
    
    df, _ = make_invoices(n_invoices=50, n_customers=10)
    csv_bytes = df.to_csv(index=False).encode('utf-8')
    
    s1 = stage1_run(csv_bytes, "test.csv", "en")
    df_kpis = stage2_run(s1["df"])
    df_segmented = stage4_run(df_kpis)
    
    assert 'segment' in df_segmented.columns
    return True


@timing_decorator
def test_stage5_basket():
    """Test Stage 5 Basket Analysis"""
    from data.generate_data import make_invoices
    from pipeline.stage1_cleaner import run as stage1_run
    from pipeline.stage5_basket import run as stage5_run
    
    df, _ = make_invoices(n_invoices=100, n_customers=10)
    csv_bytes = df.to_csv(index=False).encode('utf-8')
    
    s1 = stage1_run(csv_bytes, "test.csv", "en")
    result = stage5_run(s1["df"], "test_shop")
    
    assert 'rules' in result
    assert 'critical_pairs' in result
    return True


@timing_decorator
def test_stage6_risk():
    """Test Stage 6 Risk Scoring"""
    from data.generate_data import make_invoices
    from pipeline.stage1_cleaner import run as stage1_run
    from pipeline.stage2_metrics import run as stage2_run
    from pipeline.stage4_segments import run as stage4_run
    from pipeline.stage6_risk import run as stage6_run
    
    df, _ = make_invoices(n_invoices=50, n_customers=10)
    csv_bytes = df.to_csv(index=False).encode('utf-8')
    
    s1 = stage1_run(csv_bytes, "test.csv", "en")
    df_kpis = stage2_run(s1["df"])
    df_kpis = stage4_run(df_kpis)
    df_risk = stage6_run(df_kpis, "en")
    
    assert 'risk_score' in df_risk.columns
    assert 'risk_explanation' in df_risk.columns
    return True


@timing_decorator
def test_stage7_optimizer():
    """Test Stage 7 Optimizer"""
    from data.generate_data import make_invoices
    from pipeline.stage1_cleaner import run as stage1_run
    from pipeline.stage2_metrics import run as stage2_run
    from pipeline.stage3_forecast import run as stage3_run
    from pipeline.stage4_segments import run as stage4_run
    from pipeline.stage6_risk import run as stage6_run
    from pipeline.stage7_optimizer import run as stage7_run
    
    df, _ = make_invoices(n_invoices=100, n_customers=10)
    csv_bytes = df.to_csv(index=False).encode('utf-8')
    
    s1 = stage1_run(csv_bytes, "test.csv", "en")
    df_clean = s1["df"]
    df_kpis = stage2_run(df_clean)
    forecasts = stage3_run(df_clean, df_kpis)
    df_kpis = stage4_run(df_kpis)
    df_kpis = stage6_run(df_kpis, "en")
    
    result = stage7_run(
        df_kpis=df_kpis,
        budget=1_000_000,
        goal="maximize_profit",
        forecasts=forecasts,
        current_inventory={},
        language="en"
    )
    
    assert 'feasible' in result
    assert 'order' in result
    return True


@timing_decorator
def test_stage8_customers():
    """Test Stage 8 Customer Segmentation"""
    from data.generate_data import make_invoices
    from pipeline.stage1_cleaner import run as stage1_run
    from pipeline.stage8_customers import run as stage8_run
    
    df, _ = make_invoices(n_invoices=100, n_customers=15)
    csv_bytes = df.to_csv(index=False).encode('utf-8')
    
    s1 = stage1_run(csv_bytes, "test.csv", "en")
    result = stage8_run(s1["df"], "en")
    
    assert 'segments' in result
    assert 'summary' in result
    return True


@timing_decorator
def test_stage9_priority():
    """Test Stage 9 Priority Actions"""
    from data.generate_data import make_invoices
    from pipeline.stage1_cleaner import run as stage1_run
    from pipeline.stage2_metrics import run as stage2_run
    from pipeline.stage3_forecast import run as stage3_run
    from pipeline.stage4_segments import run as stage4_run
    from pipeline.stage5_basket import run as stage5_run
    from pipeline.stage6_risk import run as stage6_run
    from pipeline.stage7_optimizer import run as stage7_run
    from pipeline.stage8_customers import run as stage8_run
    from pipeline.stage9_priority import run as stage9_run
    
    df, _ = make_invoices(n_invoices=100, n_customers=10)
    csv_bytes = df.to_csv(index=False).encode('utf-8')
    
    s1 = stage1_run(csv_bytes, "test.csv", "en")
    df_clean = s1["df"]
    df_kpis = stage2_run(df_clean)
    forecasts = stage3_run(df_clean, df_kpis)
    df_kpis = stage4_run(df_kpis)
    basket = stage5_run(df_clean, "test_shop")
    df_kpis = stage6_run(df_kpis, "en")
    optimizer = stage7_run(
        df_kpis=df_kpis,
        budget=1_000_000,
        forecasts=forecasts,
        current_inventory={}
    )
    customers = stage8_run(df_clean, "en")
    
    products_list = [{"product": row["product"], "segment": row.get("segment"), 
                     "days_since_last_sale": row.get("days_since_last_sale", 0),
                     "risk_score": row.get("risk_score", 50)} 
                    for _, row in df_kpis.iterrows()]
    
    actions = stage9_run(
        df=df_clean,
        products=products_list,
        forecasts=forecasts,
        basket_rules=basket.get("rules", []),
        customers=customers,
        optimizer=optimizer,
        language="en"
    )
    
    assert len(actions) <= 3
    return True


@timing_decorator
def test_full_pipeline():
    """Test full pipeline integration"""
    from data.generate_data import make_invoices
    from pipeline.runner import run_pipeline
    
    df, _ = make_invoices(n_invoices=100, n_customers=10)
    csv_bytes = df.to_csv(index=False).encode('utf-8')
    
    result = run_pipeline(
        file_bytes=csv_bytes,
        filename="test.csv",
        budget=1_000_000,
        shop_id="test",
        goal="maximize_profit",
        language="en"
    )
    
    assert result.get("passed", False) == True
    assert "report" in result
    return True


@timing_decorator
def test_models_loader():
    """Test models loader works offline"""
    from models import loader
    loader.load_all()
    return True


@timing_decorator
def test_output_reporter():
    """Test output reporter"""
    from output import reporter
    assert hasattr(reporter, 'assemble_and_save')
    return True


@timing_decorator
def test_llm_offline():
    """Test LLM works offline (no crash)"""
    try:
        from llm.agent import ask_llm, enabled
        is_enabled = enabled()
        assert isinstance(is_enabled, bool)
        response = ask_llm({}, "")
        assert response is None or isinstance(response, str)
        return True
    except ImportError:
        return True


def run_all_tests():
    """Run all test functions with timing"""
    print("\n" + "="*60)
    print("🧪 SaleYar Comprehensive Test Suite")
    print("="*60 + "\n")
    
    tests = [
        test_config,
        test_imports,
        test_column_map,
        test_data_generation,
        test_stage1_cleaner,
        test_stage2_metrics,
        test_stage3_forecast,      # ← ADDED
        test_stage4_segments,
        test_stage5_basket,
        test_stage6_risk,
        test_stage7_optimizer,
        test_stage8_customers,
        test_stage9_priority,
        test_full_pipeline,
        test_models_loader,
        test_output_reporter,
        test_llm_offline,
    ]
    
    passed = 0
    total = len(tests)
    
    print("Running tests...\n")
    
    for test in tests:
        if test():
            passed += 1
    
    print("\n" + "="*60)
    print(f"📊 RESULTS: {passed}/{total} tests passed")
    print("="*60)
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED! Project is production ready.\n")
        return True
    else:
        print(f"\n⚠️  {total - passed} test(s) failed.\n")
        return False


if __name__ == "__main__":
    start = time.time()
    success = run_all_tests()
    elapsed = time.time() - start
    print(f"Total time: {elapsed:.2f} seconds")
    sys.exit(0 if success else 1)