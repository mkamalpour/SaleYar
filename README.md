# SaleYar

**Local retail intelligence for Iranian shops.** Analyze Holoo CSV/Excel invoices,
understand product performance, and plan purchases in English or Persian.

[![Tests](https://github.com/mkamalpour/SaleYar/actions/workflows/tests.yml/badge.svg)](https://github.com/mkamalpour/SaleYar/actions/workflows/tests.yml)

## Features

- Responsive owner dashboard with Persian RTL and nine analysis sections.
- Product sales, profit, demand forecasts, stock movements, and risk signals.
- Basket associations, customer groups, and budget-constrained purchase orders.
- Profit, customer-coverage, and risk optimization goals.
- Offline keyword advisor and optional configurable local LLM connection.
- Paginated tables, product search, safe CSV export, upload progress and cancellation.
- Developer Gradio interface, terminal interface, and authenticated FastAPI endpoints.

The owner dashboard uses local assets and needs no CDN. Invoice processing stays
on this machine. If you configure an external LLM endpoint, report summaries are
sent to that endpoint; leave LLM integration disabled for fully local operation.

## Quick start

Activate an existing compatible environment. The current lightweight suite was verified in Conda `base` with Python 3.13.5; no dedicated environment or model training is required to start the dashboard.

```powershell
conda activate base
python run.py --mode owner
```

Dependencies are recorded in `requirements.txt`. Review that specification before any optional installation; the launcher does not install them.

Use `python` from your active compatible environment on other platforms too.
The launcher starts loopback-only API and dashboard servers, then opens the
browser. Use the launcher URL; the HTML depends on its local assets and API.

An API key is generated privately on first use. Optionally copy `.env.example`
to `.env` and set your own key. Secrets, invoices, reports, and trained models
are excluded from Git. Set `SALEYAR_API_PORT`/`SALEYAR_WEB_PORT` to change ports.

## Input and analysis

Upload CSV or Excel with invoice ID, date, product, quantity, buy price, and sell
price. English/Persian headers are mapped automatically. Explicit transaction
types distinguish sales, purchases, returns, and damaged stock. Without a type,
rows default to sales, so stock inference may be incomplete. Invalid dates and
nonfinite numbers are flagged instead of being silently invented.

Budgets must be positive. Shop IDs use 1-64 letters, digits, underscores or
hyphens and start with a letter or digit. Inferred inventory depends on complete
transaction history, including opening stock. Forecasts and purchase suggestions
are estimates, not guarantees. Financial benchmark values in `saleyar/config.py` are
illustrative assumptions, not current bank rates or promised gold returns.
The metric named `profit_margin` is markup relative to purchase cost.

Generate synthetic invoices with `python run.py --generate-data`. The optional
`python models/train.py` builds the synthetic risk model; rule-based risk scoring
works without it. Run `python data/invoice_merger.py` for the desktop invoice
merger (requires Tkinter).

## Other modes

```bash
python run.py --mode developer
python run.py --mode terminal
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

API clients send `X-API-Key`. `POST /analyze` returns a job ID; poll
`GET /result/{job_id}`. Other endpoints include `/optimize`, `/basket`, `/risk`,
`/report/{shop_id}`, `/health/{shop_id}`, `/healthcheck`, and `/llm/ask`.
Local interactive API documentation is available at `/docs`.

## Development

```bash
# Optional dependency setup; requires explicit permission and connectivity.
python -m pip install -r requirements.txt
python -m pytest tests -q
```

Tests use synthetic data and isolate shop caches from real models and reports.
`requirements.txt` records the original Python 3.10 dependency baseline, plus
`xlrd` for legacy Excel files. The current lightweight suite also passes with the
existing base environment. Avoid unrestricted upgrades of ML dependencies; native
model files require matching training versions.

Model setup uses `python models/train.py`. It migrates a readable legacy
`models/lgbm_risk.pkl` to native LightGBM `models/lgbm_risk.json` without deleting
the original. Native files include feature order and training versions. If an old
pickle cannot load, `python models/train.py --force` builds the synthetic model
while preserving the old file. Changed models reload automatically; `/healthcheck`
reports model availability and recovery details. Higher risk scores mean greater
business risk; older strength-oriented models are adapted automatically.

| Directory | Purpose |
| --- | --- |
| `saleyar/` | Shared configuration, validation, and console setup |
| `api/` | FastAPI authentication, uploads, jobs, and results |
| `pipeline/` | Import, metrics, forecasts, segments, basket, risk, orders, customers |
| `ui/` | Owner dashboard assets, server, developer and terminal interfaces |
| `models/` | Training and loading code; local model files remain ignored |
| `data/` | Synthetic invoice generator and invoice merger |
| `output/` | Report assembly, charts, and language templates |
| `tests/` | Integration checks and behavioral regressions |

Current lightweight check (Windows, existing Conda base / Python 3.13.5): **84 passed**. No dependency installs, model downloads, live publishing, or heavy datasets were used.

Forecast output distinguishes unavailable predictions from low-support estimates. All available forecasts include 30/60/90-day totals. When StatsForecast is unavailable or fails, an explicitly labelled local baseline repeats the last observed week (at least 14 daily observations) or uses a recent mean. Its support remains Low; no calibrated interval is invented. Category averages remain separately labelled fallbacks for insufficient history.

A seven-day chronological holdout reports MAE and WAPE where sufficient history exists. Statistical support bands use actual held-out predictions, rather than comparing future estimates with past observations. A missing/zero-demand validation denominator is shown as unavailable, not zero error. Optional statistical adapters are checked with fixtures; the installed StatsForecast stack was not exercised. Purchase planning uses the existing greedy fallback when OR-Tools is absent.

Daily series combine same-day timestamps and include zero-sale days through the dataset's last date. This assumes a complete invoice history: missing records, closures and stockouts can distort demand. The dashboard shows methods, held-out WAPE and expandable method details. These estimates and short holdouts do not establish real-world predictive accuracy.

Basket confidence is directional P(B|A), support includes single-product invoices, and lift is computed against the destination product's overall frequency. Critical pairs require both the confidence and lift thresholds. The cache version prevents reuse of rules calculated with the older denominator. Associations do not establish causation.

Read-only job-status requests retry bounded transient failures without re-uploading the file or starting a duplicate analysis. Authentication failures and cancellation are not retried. The browser check injected a failed read and completed with one upload/two reads. Optional Node-based frontend tests run when Node is already available; Node is not needed to run the Python application.
