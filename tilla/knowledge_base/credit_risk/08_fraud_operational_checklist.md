# Fraud & operational checklist

Structured booleans enforced in policy engine:

| Flag | STOP when true |
|------|----------------|
| `fraud_suspicion` | **`POLICY_FRAUD_SUSPICION_STOP`** |
| `duplicate_invoice` | **`POLICY_DUPLICATE_INVOICE_STOP`** |
| `invoice_financed_elsewhere` | **`POLICY_INVOICE_ALREADY_FINANCED_ELSEWHERE_STOP`** |

## Free-text escalation

If `overdue_information` matches material keywords (`insolvency`, `konkurs`, `likvidace`, `exekuce`, `default`, `90+`, … regex list in code) → **`POLICY_OVERDUE_INFORMATION_MATERIAL`** manual trigger.

## Data integrity

`data_mismatch = true` → **`POLICY_DATA_MISMATCH_HUMAN_REVIEW`** — blocks `can_fund_now`.

Env caps (`CREDIT_RISK_SUPPLIER_CAP_CZK`, `CREDIT_RISK_ANCHOR_CAP_CZK`) emit triggers **`POLICY_INVOICE_EXCEEDS_*`** / **`POLICY_COMBINED_EXPOSURE_EXCEEDS_*`** when breached — automated funding forbidden until cleared.
