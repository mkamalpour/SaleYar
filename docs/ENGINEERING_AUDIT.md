# Engineering audit — 2026-10-26

Purpose: Invoice analysis, basket insights and purchase planning.

Classification: **A** (single application/tool).
Final structure: saleyar/, pipeline/, api/, ui/, models/, tests/. Existing capabilities and source material were retained.

| Assessment | Result |
| --- | --- |
| Idea strength | 9/10 |
| Implementation strength | 8/10 |
| Core strength | Synthetic analysis coverage, owner workflow and isolated model/report state. |
| Main limitation | Real invoice conventions and business outcomes require separate evaluation. |
| Readiness | Local prototype/tool with the verified baseline below; no production certification |

Scores are subjective engineering estimates, not measured product or model quality.

## Delivered

Fixed process-local discovery of the active environment's bundled Arrow runtime and native BLAS directory. Added test.py to initialize runtime before pytest and exclude unrelated global plugins. No installed environment files were edited.

Assigned environment: **ml**. Run `.\run.cmd --check`, then `.\run.cmd`.
The launcher installs nothing and preserves its child exit status. On this workstation
it selects the assigned interpreter; standalone clones fall back to active Python.
VS Code's local interpreter settings were aligned with the same assignment.

## Verification

- **Automated tests:** 96 passed; 0 reported skips; 0 private-report cases deselected.
- **Startup check:** `run.cmd --check` passed from outside the repository;
  required startup modules were imported in the assigned environment.
- **Tested runtime:** Windows; Conda ml; Python 3.10.19.
- **Data handling:** tests used temporary/synthetic fixtures. No live transactions,
  provider generation, deployment, new model downloads or package installs were performed.
- **Repository check:** origin/main fetched before publication; no pre-existing local
  changes were present. A tracked-file scan found no matches for the high-confidence
  credential patterns checked. That scan is not a guarantee that all personal data
  or arbitrary secret formats are absent. Ignored local data was not staged.
- **Limits:** optional external workflows, representative real-data quality and all
  possible platform/version combinations remain unverified.

Test command from the repository root:

```powershell
conda activate ml
python test.py
```

## Next three upgrades

1. Invoice mapping profiles.
2. Explainable purchase-plan tradeoffs.
3. Exported forecast baseline comparisons.

Expected benefit: clearer decisions, more reproducible workflows and stronger evidence
for quality. These are proposed upgrades, not implemented features or measured speedups.

External assets: No hosted model is needed for core analysis; representative anonymized invoices are needed for business validation.

No root license file is set. No license was selected or changed.

## Additional implementation pass

Demand validation reports include RMSE, signed mean/percentage bias and zero-demand-day counts. Invalid vector shapes, negative demand and invalid horizons fail clearly.

Use: Owner dashboard → Forecasts → Holdout bias (+ overforecast). Existing WAPE and low-support warnings remain.

Verification: the complete offline suite passed in the assigned **ml**
environment after this change (96 tests). Regression fixtures remain
temporary/synthetic. Optional real-model/data quality and external integrations
remain unverified. No packages, models or additional environments were installed.

The earlier numeric scores are subjective historical assessments; new features do
not automatically establish a higher score or production readiness.
