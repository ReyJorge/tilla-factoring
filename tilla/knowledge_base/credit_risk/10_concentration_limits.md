# Concentration limits — runtime signals

Concentration metrics (`supplier_to_portfolio_pct`, `anchor_to_portfolio_pct`, etc.) are emitted inside **`model_result`** by `credit_risk_excel_model`.

## Flags

- **`GREEN`**: PASS-eligible concentration path when no other triggers fire.
- **`AMBER`**: Policy maps to **`CONDITIONAL`** status when bands/gates permit — funding still blocked automatically (`can_fund_now = false`).
- **`RED FLAG`**: **`POLICY_CONCENTRATION_RED_FLAG`** manual trigger — officer must justify exposure reduction / collateral.

Portfolio dashboard aggregates notionally by summing audited invoice amounts — replace with ledger exposures when treasury integration lands.
