# Invoice eligibility rules

An invoice row is treated as **eligible for automated PASS** only when **all** hold:

1. **Exists**: `invoice_amount > 0`, `due_date` parseable.
2. **Identity**: `invoice_number` populated (otherwise **`POLICY_INVOICE_NUMBER_MISSING`** manual trigger).
3. **Delivery / match**: free-text `receivable_status` must describe delivered goods/services or ERP match language acceptable to officer — MVP relies on manual interpretation + ERP evidence outside tool.
4. **Anchor dispute**: boolean `dispute` must be **false**. If **true** → policy **`POLICY_DISPUTE_YES_NO_AUTOFUND`** + model STOP gate → **`Reject`** / no funding.
5. **Duplicate**: `duplicate_invoice` must be **false** — else **`POLICY_DUPLICATE_INVOICE_STOP`**.
6. **Prior assignment**: `invoice_financed_elsewhere` must be **false** — else **`POLICY_INVOICE_ALREADY_FINANCED_ELSEWHERE_STOP`**.
7. **Terms**: `supplier_terms_accepted` must be **true** — else **`POLICY_SUPPLIER_TERMS_NOT_ACCEPTED`** hard stop.
8. **Legal**: `legal_status` ∈ **`ok | satisfied | cleared`**. **`blocked | impossible | fail`** → **`POLICY_LEGAL_ASSIGNMENT_BLOCKED`**.
9. **Bank**: `bank_account_verified` must be **true** — else **`POLICY_BANK_ACCOUNT_NOT_VERIFIED`** manual trigger.

## Overdue invoice

If parsed `due_date` **< today** → **`POLICY_INVOICE_OVERDUE_REQUIRES_EXCEPTION`** — automated funding forbidden until dated officer exception logged externally.
