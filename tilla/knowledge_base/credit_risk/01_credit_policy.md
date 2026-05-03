# Credit policy — invoice financing MVP

## Scope

This programme finances **eligible receivables** from suppliers against **creditworthy anchors** under Czech assignment / factoring-style documentation tracked outside this tool.

## Operating rule

Funding is permitted only when simultaneously:

1. `final_policy_status` is **`PASS`**,
2. `rating_gate` is **`OK`**,
3. `risk_band` ∈ **`{A,B}`**,
4. `concentration_flag` is **`GREEN`**,
5. `manual_review_triggers` is empty (including synced model triggers),
6. System output sets **`final_decision.can_fund_now = true`**,

and a human marks workflow **`Approved by human`** after KYC/delivery checks.

Any deviation requires documented officer or committee action **before** disbursement.
