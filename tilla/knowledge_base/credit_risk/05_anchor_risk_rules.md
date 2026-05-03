# Anchor (debtor) risk rules

## Primary repayment source

Repayment expectation is the anchor’s payment of the invoice; anchor PD proxies use external rating mapped in the workbook catalogue.

## Confirmation reliability

Structured fields:

- `confirmation_status` must be **`confirmed` | `yes` | `verified`** for automated PASS eligibility.
- Values **`refused` | `anchor_refused` | `no`** → policy hard stop **`POLICY_ANCHOR_CONFIRMATION_REFUSED`**.
- **`pending`** → manual trigger **`POLICY_ANCHOR_CONFIRMATION_PENDING`** — funding blocked (`can_fund_now = false`).

## Operational indicators

Include in narrative review:

- Delay metrics from historical JSON (`average_delay_days`, `late_payment_share`, … as emitted by engine).
- Evidence of recurring disputes on prior invoices — captured via `dispute` flag on current deal or officer notes outside KB.
