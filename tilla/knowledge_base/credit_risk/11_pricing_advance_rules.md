# Pricing & advance rules

## Standard advance ceiling

Maximum structural advance recommendation defaults to **80%** unless workbook overrides lower.

Request **`requested_advance_pct > 80`** adds **`POLICY_ADVANCE_ABOVE_80_PCT_REQUIRES_CRO`** and blocks automated funding until CRO documented pricing waiver (`conditions_before_funding` carries reminder).

## Risk band overlays

Wrapper caps band **C** advances at **60%** (`credit_risk_scoring_engine`). Band **D** advances forced to **0%**.

## Fees

`recommended_fee_pct` is workbook-derived base + rating uplift — AI must cite verbatim numbers only.
