# Architecture

SaleYar combines a local browser dashboard, a FastAPI service, and a nine-stage
pandas/ML analysis pipeline. `run.py` launches the owner dashboard; developer and
terminal modes import their UI dependencies lazily.

## Request flow

1. The launcher binds API and dashboard servers to loopback. Its dashboard server
   serves only the owner HTML and local assets, never the repository directory.
2. Runtime API connection settings are injected as escaped JSON. API keys stay
   in the dashboard session rather than persistent browser storage.
3. Authenticated uploads pass extension, size, shop ID, language, goal, and budget
   checks. The analysis queue is bounded; synchronous analytics run off the API
   event loop. Finished job payloads expire after the configured TTL.
4. The pipeline validates headers, dates, and numbers; derives product metrics;
   forecasts demand; finds segments/basket associations; scores risk; optimizes
   orders; groups customers; and assembles priority actions.
5. Results return through job polling. Failed quality gates preserve the last
   healthy report. The dashboard handles waiting, errors, timeout, and cancellation.

## Data semantics

Sales contribute to product revenue; supplier purchases do not. Customer returns
reduce customer spend. Purchases and sales returns add inventory; sales, purchase
returns, and damaged items remove it. Incomplete opening-stock or transaction
history makes inferred inventory incomplete.

`profit_margin` is cost-based markup. Forecast and ROI displays are estimates
based on uploaded history. Benchmark constants are configurable assumptions.
The optional shared LightGBM model is trained on synthetic rule-derived targets.

## Persistence and privacy

Paths resolve relative to the project rather than the launch directory. Shop IDs
are validated before filesystem access. Trained models survive startup and new
uploads. Cached analysis is versioned and keyed by input data; basket caches also
include data and configuration fingerprints. Bounded striped locks serialize
same-shop pipeline/cache writes. Reports are in memory unless disk saving is
explicitly enabled in `config.py`.

The frontend escapes imported values, uses plain text for advisor responses,
and protects CSV exports from spreadsheet formulas. No CDN assets are needed.
Optional LLM requests use the endpoint configured by the operator and may leave
this machine if an external endpoint is selected.

## Testing

`pytest tests` includes the original 17 synthetic pipeline checks and regression
coverage for transaction KPIs, dates, inventory, customers, cache behavior,
optimization goals, HTTP errors, bounded jobs, serialization, and asset serving.
Tests isolate shop state; never use real invoices in tests or public issues.
