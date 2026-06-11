Here is the **upgraded production deployment spec** – more detailed, aligned with your current HTML dashboard + LLM improvements, and structured for immediate execution.

---

# SaleYar – Production Deployment Upgrade Spec (v2.0)

## Final Assessment & Actionable Upgrade Plan

Based on full code review of your 9‑stage pipeline, models, UI, API, and supporting modules (including the new HTML dashboard and LLM Talk Mode), here is the **complete, compact production‑ready upgrade plan**.

---

## 📊 CURRENT PROJECT RATINGS (1-10) – Updated

| Component | Score | Notes |
|-----------|-------|-------|
| Stage 1 (Cleaner) | 8.5 | Missing encoding auto‑detect, 3‑way dates, quality formula |
| Stage 2 (KPIs) | 9.0 | Excellent, no changes needed |
| Stage 3 (Forecast) | 7.5 | No Persian calendar multipliers, no partial resume |
| Stage 4 (Segments) | 7.0 | No feedback to forecast, rule‑based fine but could be tighter |
| Stage 5 (Basket) | 8.0 | Solid, FP‑Growth, critical pairs |
| Stage 6 (Risk) | 8.5 | Hybrid works; no SHAP, no LLM‑safe mode |
| Stage 7 (Optimizer) | 7.0 | Missing champion boost, no override for high risk |
| Stage 8 (Customers) | 8.0 | Champion products defined, but not fed back |
| Stage 9 (Priority) | 6.5 | No health score, no alert rules, no trend comparison |
| Reporter | 6.0 | No report history, no charts, no health formula |
| Models (loader/train) | 6.5 | No registry, no ground truth verification |
| UI (HTML dashboard) | 7.5 | Good, but missing: RTL/Persian numerals, chart exports, offline fallback |
| UI (Gradio developer) | 7.0 | Works, but needs tab for model registry |
| API | 8.0 | Missing `/v1/demo` endpoint |
| LLM agent | 7.0 | Talk mode works, but can still hallucinate; needs locked mode |
| Data generator | 7.5 | Missing ground truth planting for verification |
| Logging | 5.0 | Not structured, missing shop_id & component |
| Performance (large shops) | 5.0 | No incremental updates, no chunked processing |
| **Overall** | **7.3** | **Good prototype – needs ~20 upgrades for production** |

---

## 🎯 THE 20 PRODUCTION UPGRADES (Grouped by priority)

### 🔴 CRITICAL (Do first – without these, don't deploy)

1. **Column Mapping Wizard** – First run: user maps 5 columns (invoice_no, product, qty, sell_price, buy_price). Save to `config.py`. Use `rapidfuzz` (score ≥80) for auto‑suggest.  
   *Files: `stage1_cleaner.py`, `config.py`, new `ui/wizard.py`*

2. **Quality Score Formula** – `completeness 25% + consistency 25% + duplicate 20% + outlier 15% + date_continuity 15%`. Score <40 → stop pipeline, return fix report only.  
   *File: `stage1_cleaner.py`*

3. **Health Score Formula** – `quality×0.20 + margin_vs_benchmark×0.20 + (100‑avg_risk)×0.20 + forecast_confidence×0.15 + (100‑dead_stock_ratio)×0.15 + customer_health×0.10`. Grade >80 excellent, 60‑80 good, 40‑60 warning, <40 critical.  
   *File: `reporter.py`*

4. **Alert Rules** – Fire in report if: revenue drop >15% last month; dead stock ratio >20%; any product margin <23%; shop ROI <23%.  
   *File: `reporter.py`, `stage9_priority.py`*

5. **Persian Calendar Layer** – Apply multipliers after forecast: Nowruz (Farvardin) ×1.40 grocery; Ramadan (shifts) demand pattern; Yalda (Dey) ×1.25 fruits/snacks/nuts; Back‑to‑School (Shahrivar) ×1.20 stationery/bags.  
   *File: `stage3_forecast.py`, `config.py`*

6. **Partial Resume** – Each stage saves output to `saved_reports/{shop_id}/stage_cache/stage{N}_output.pkl`. On crash/resume, skip completed stages.  
   *File: `runner.py`*

7. **Incremental Updates** – Store hash per month of data. New file: only process months not seen, merge with cached results. Time drops from 20‑28s → 3‑5s.  
   *File: `runner.py`, `stage1_cleaner.py`*

8. **Report History** – Save every report as `report_{YYYY-MM-DD}.json`. Keep `report_latest.json`. When loading, also load previous to show trend: “Health was 72, now 68”.  
   *File: `reporter.py`*

9. **HTML Dashboard Enhancements (Owner Mode)**  
   - **RTL & Persian numerals** – Add `dir="rtl"` when language=fa. Use `persian_number()` for all numbers.  
   - **Chart exports** – Add download buttons for each chart (PNG/CSV).  
   - **Offline fallback** – If API unreachable, show cached last report with timestamp.  
   - **Keyboard shortcuts** – `Ctrl+U` upload, `Ctrl+S` save settings.  
   *Files: `ui/site.html`, `ui/static/js/charts.js`, `config.py`*

10. **One‑Command Install** – `python install.py` verifies Python ≥3.10, runs conda + pip installs, imports every library, reports OK/FAILED, prints “ALL GOOD — run: python models/train.py”.  
    *New file: `install.py`*

### 🟡 HIGH (For reliability & scale)

11. **Encoding Auto‑Detect** – Use `chardet`. Try detected → UTF‑8 → Windows‑1256 → error.  
    *File: `stage1_cleaner.py`*

12. **3‑Way Date Conversion** – Try `jdatetime` → `persiantools` → manual regex fallback. Log method used. Never crash.  
    *File: `stage1_cleaner.py`*

13. **Chunked File Processing** – For files >50MB, process 10,000 rows at a time using pandas `chunksize`.  
    *File: `stage1_cleaner.py`, `config.py`*

14. **Ground Truth Verification** – Synthetic data generator plants known patterns (Star products, dead stock, revenue decline). Pipeline must achieve >90% pass rate in tests.  
    *Files: `data/generate_data.py`, `tests/test_pipeline_full.py`*

15. **Model Registry** – New `models/registry.py` with: `save_model()`, `load_model()`, `list_models()`, `set_active()`, `delete_model()`, `compare_models()`. Each model has metadata: version, trained_date, accuracy, precision, recall, f1, active flag.  
    *New file: `models/registry.py`*

16. **Complete Structured Logging** – Log to `logs/app.log` with: `timestamp | level | shop_id | component | message`. Log every pipeline run, stage start/end, skip, alert, API request, LLM call, config change, model load, error.  
    *All modules, add logging configuration*

17. **Feedback Loops** – Stage 8 champion products → Stage 7 weight ×1.20. Stage 4 seasonal products → Stage 3 tighter seasonal fit. Stage 6 risk >80 → Stage 7 exclude unless override flag in config.  
    *Files: `stage7_optimizer.py`, `stage3_forecast.py`, `runner.py`, `config.py`*

18. **LLM Locked Mode** – LLM only rewrites locked JSON facts into natural language. Never sees raw data. Never produces numbers. Temperature: Persian 0.2, English 0.3. Timeout 10s. If offline → return report without narrative.  
    *File: `llm/agent.py`, `config.py`*

### 🟢 MEDIUM (Polish & enterprise features)

19. **6 Required Charts (HTML Dashboard)** – All Plotly, embedded as base64 HTML: revenue_trend (monthly + trendline), top_products (horizontal bar), segment_map (margin vs velocity scatter), forecast_chart (90‑day with bands), risk_heatmap (products × risk), customer_rfm (3D scatter if data exists). Add toggle for Persian/English labels.  
    *Files: `output/charts.py`, `ui/site.html`*

20. **API Demo Endpoint** – `GET /v1/demo` – no API key. Runs pipeline on built‑in synthetic sample data. Returns complete example report (JSON). For frontend testing.  
    *File: `api/main.py`*

---

## 📁 FILES TO CREATE OR CHANGE

| File | Action |
|------|--------|
| `install.py` | NEW |
| `models/registry.py` | NEW |
| `ui/wizard.py` | NEW |
| `pipeline/stage1_cleaner.py` | Add wizard integration, quality formula, encoding detect, 3‑way dates, chunking |
| `pipeline/stage3_forecast.py` | Add Persian calendar multipliers |
| `pipeline/stage7_optimizer.py` | Add champion boost, risk override |
| `pipeline/runner.py` | Add partial resume, incremental updates, feedback loops |
| `output/reporter.py` | Add health score, report history, alerts, charts |
| `llm/agent.py` | Add locked mode, temperature, timeout, tab guide hardening |
| `ui/site.html` | Add RTL, Persian numerals, chart exports, offline fallback, keyboard shortcuts |
| `ui/developer.py` | Add model registry tab, ground truth test runner |
| `api/main.py` | Add `/v1/demo` endpoint |
| `data/generate_data.py` | Add ground truth planting |
| `tests/test_pipeline_full.py` | Add >90% pass verification |
| `config.py` | Add new thresholds (calendar multipliers, chunk size, LLM locked mode params) |
| `logging.conf` | NEW – structured logging |

---

## 🗓️ IMPLEMENTATION ROADMAP (Weeks)

| Week | Deliver |
|------|---------|
| 1 | `install.py` + column wizard + encoding detect + 3‑way dates |
| 2 | Quality formula + health score + alert rules |
| 3 | Persian calendar + partial resume + incremental updates |
| 4 | Ground truth + model registry + report history |
| 5 | Feedback loops + champion boost + LLM locked |
| 6 | HTML dashboard enhancements (RTL, charts exports, offline fallback, keyboard shortcuts) |
| 7 | Chunked processing + structured logging complete + `/v1/demo` |
| 8 | Test on 3 real shops → retrain LightGBM on real data |

---

## ✅ SUCCESS CRITERIA (After upgrades)

| Metric | Target |
|--------|--------|
| Crash rate | <0.1% |
| Accuracy vs ground truth | >90% |
| Speed (200 products, fresh) | 3‑8 seconds |
| Non‑tech friendly | 9/10 (owner installs in <2 min) |
| Real shops tested | 3+ pilots passing |
| HTML dashboard | RTL, Persian numerals, chart exports, offline fallback |
| LLM locked mode | Never hallucinates numbers |

---

## 🔥 FINAL PROMPT FOR AI

> You have a 9‑stage SaleYar prototype that works for small shops, with an HTML owner dashboard and LLM Talk Mode.  
> Apply the 20 upgrades above in the order: critical (1‑10) → high (11‑18) → medium (19‑20).  
> Follow each spec exactly. Create missing files, modify existing ones.  
> Do not change the pipeline’s core logic unless specified.  
> After implementation, the system must be ready for deployment to real Iranian shops – offline, no cloud, never crashes, owner can install and use without technical help, and the HTML dashboard must be fully production‑ready (RTL, Persian numerals, offline fallback).  

**Build this. Your prototype becomes production‑ready.**