# Scoring methodology — deterministic vs Excel

## Source workbook

File: **`knowledge_base/credit_risk/scoring_model/invoice_financing_scoring_model_anchor_risk_FINAL.xlsx`**  
Override path: env **`CREDIT_RISK_SCORING_MODEL_PATH`**.

Sheets parsed at runtime (when layout matches): **`Parametry`**, **`Číselníky` / `Ciselniky`**.

## Runtime engine

Python module **`app/services/credit_risk_excel_model.py`** reads parameters and computes:

- Behaviour metrics from `historical_transactions` JSON (paid count, delays, volatility penalties),
- Anchor rating score + gate,
- Concentration percentages (`supplier_to_portfolio_pct`, `anchor_to_portfolio_pct`, flags),
- `total_score`, `risk_band`, `recommended_advance_pct`, `recommended_fee_pct`.

**Production does not invoke Excel calculation services** — only structured reads via openpyxl.

## Wrapper adjustments

**`credit_risk_scoring_engine.calculate_credit_risk`** adds operational lists (`hard_stops`, `manual_review_triggers`, ...), caps advance at **60%** when band **C**, forces advance **0** when band **D**, and stamps `model_version`.

## Deterministic precedence

If AI narrative contradicts `model_result` or `policy_check_result`, **discard the contradiction** — UI and audit store deterministic JSON first; AI fields are explanatory only.
