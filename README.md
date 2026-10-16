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

Use Python 3.11-3.13 and a virtual environment:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python run.py --mode owner
```

On macOS/Linux, replace `.venv\Scripts\python` with `.venv/bin/python`.
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
are estimates, not guarantees. Financial benchmark values in `config.py` are
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
python -m pip install -r requirements-dev.txt
python -m pytest tests -q
python scripts/check_environment.py
```

Tests use synthetic data and isolate shop caches from real models and reports.
`requirements-lock.txt` records the verified Windows/Python 3.13 environment;
use `requirements.txt` for installation on other platforms and Python versions.

| Directory | Purpose |
| --- | --- |
| `api/` | FastAPI authentication, uploads, jobs, and results |
| `pipeline/` | Import, metrics, forecasts, segments, basket, risk, orders, customers |
| `ui/` | Owner dashboard assets, server, developer and terminal interfaces |
| `models/` | Training and loading code; local model files remain ignored |
| `data/` | Synthetic invoice generator and invoice merger |
| `output/` | Report assembly, charts, and language templates |
| `tests/` | Integration checks and behavioral regressions |
| `docs/` | Architecture and changelog |

See [architecture](docs/architecture.md), [changelog](docs/changelog.md), and
[contributing](CONTRIBUTING.md).
