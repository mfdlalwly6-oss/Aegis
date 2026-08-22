# AEGIS v2.2.0 — Future Improvements (Post-Launch Roadmap)

> **Important:** None of the items below are current defects. The system as
> delivered passes all verified tests (P0→P13) and runs correctly on the live
> environment. These are **future enhancements required for full production
> launch**, not bugs blocking the current release.

---

## 1. Retrain & Improve the ML Model with Real Labeled Data

- **Current state:** The model works and is loaded at runtime
  (`gradient_boosting` + `isolation_forest`, version `v20260822`), and the
  readiness endpoint reports `ml_ready: true`.
- **Caveat:** It is trained on a **synthetic dataset**
  (`models/synthetic_fraud_dataset.csv`). The model metadata is explicitly
  labeled `EXPERIMENTAL — synthetic data; do NOT treat as production-grade`.
- **Required future work:**
  - Collect real, labeled transaction data (confirmed fraud / confirmed legit).
  - Re-validate the pipeline: temporal split, leakage checks, per-currency
    (USD/SAR/YER) and per-typology evaluation, class-imbalance metrics.
  - Retrain and promote a champion model only after real-data evaluation.
  - Do NOT rely on the current model for sensitive/high-value decisions until
    it has been retrained on real data.

## 2. Switch Runtime Environment to Production

- **Current state:** `AEGIS_ENV=development`.
- **Required future work:**
  - Prepare production settings (logging level, CORS, rate limits, secrets).
  - Test the production configuration in staging.
  - Switch to `AEGIS_ENV=production` only after verification.

## 3. Rotate All Secrets & Keys

- **Current state:** Secrets live in `.env` on the server (never committed to
  Git, never included in the release package).
- **Required future work — before official launch, generate fresh values for:**
  - `AEGIS_SECRET_KEY`
  - All API keys / HMAC secrets (`x-api-key`, `x-wallet-signature` secrets)
  - JWT signing material
  - `AEGIS_OWNER_TOKEN`, investigator credentials, and any other secrets
- **Rule:** Never place real secrets in Git or in the final release archive.

## 4. Connect FX to a Trusted Automatic Rate Provider

- **Current state:** FX rates are stored manually in `fx_rates` (7 rates for
  USD/SAR/YER, region-aware for Aden/Sanaa). The normalization engine works.
- **Required future work:**
  - Integrate a trusted external FX provider to update rates automatically.
  - **Must preserve** the existing safety mechanisms:
    - `FX_MISSING` → force REVIEW (never silently block or allow).
    - `FX_STALE` → detect outdated rates.
    - `FX_DIVERGENT` → institution-reported rate that deviates from the
      reference raises risk, never lowers it.

---

## Summary

These four items are **planned production hardening steps**, not open bugs.
The delivered system is fully functional under its current configuration.
