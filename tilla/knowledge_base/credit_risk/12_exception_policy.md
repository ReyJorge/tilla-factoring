# Exception policy — coded triggers

Automatic exceptions are represented only via enumerated **`manual_review_triggers`** / **`hard_stops`** — there is no implicit exception outside JSON lists.

Examples requiring documented exception files offline:

1. Overdue invoice flagged pending dated waiver (`POLICY_INVOICE_OVERDUE_REQUIRES_EXCEPTION`).
2. Anchor confirmation pending (`POLICY_ANCHOR_CONFIRMATION_PENDING`).
3. Advance above 80% (`POLICY_ADVANCE_ABOVE_80_PCT_REQUIRES_CRO`).
4. External legacy scoring grade **D** (`POLICY_LEGACY_EXTERNAL_SCORE_D`) → STOP path.

Exceptions never remove STOP outcomes automatically — workflow approval endpoint rejects **`Approved by human`** while STOP persists.
