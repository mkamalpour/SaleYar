# Contributing

Install `requirements-dev.txt` in a virtual environment and run `python -m pytest
tests -q`. Add regression coverage for behavior changes and keep all fixtures
synthetic. Never commit `.env`, invoices, customer information, model binaries,
report exports, caches, or logs.

Keep API routes in `api/`, analysis in `pipeline/`, dashboard code in `ui/assets/`,
model lifecycle in `models/`, and report generation in `output/`. Preserve both
English and Persian user flows, keyboard access, and local asset loading. Check
mobile layouts and rejected-upload behavior when changing the dashboard.

Use descriptive snake_case Python names and standard formatting. Document
user-visible changes in `docs/changelog.md`. Pull requests should state the
behavior changed and the checks performed.
