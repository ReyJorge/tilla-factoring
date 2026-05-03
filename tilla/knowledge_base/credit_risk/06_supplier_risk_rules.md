# Supplier risk rules

## Financial disclosure

Minimum structured fields expected per deal intake:

- `revenue_latest_year`
- `ebitda_latest_year`

If either is blank → **`POLICY_MISSING_SUPPLIER_FINANCIAL_FIELDS`** (manual review path).

## Relationship thickness

When paid invoice count from behaviour JSON **`paid_invoice_count < 5`** → **`POLICY_NEW_SUPPLIER_OR_THIN_PAYMENT_HISTORY`** (synced from model/manual triggers).

## Dependency heuristic

Strong anchor + weak supplier may still route **CONDITIONAL** if rating gate OK and concentration GREEN — officer validates invoice-level assurance (delivery proof / acknowledgment).

Weak anchor + weak supplier → expect **STOP / MANUAL / Reject** outcomes once gates fire.
