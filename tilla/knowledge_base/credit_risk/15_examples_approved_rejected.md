# Examples — approved vs rejected (illustrative)

## Approved automated path (illustrative)

- Anchor rating **BBB**, gate **OK**, band **A**, concentration **GREEN**.
- `confirmation_status = confirmed`, `legal_status = ok`, `bank_account_verified = true`.
- No disputes/mismatches/fraud flags.
- Expected JSON: `final_policy_status = PASS`, `final_decision.can_fund_now = true`, workflow seeds **`Recommended approve`** pending human button.

## Rejected STOP path

- Anchor rating **B** → deterministic **`STOP`** gate OR `dispute = true`.
- Expected JSON: `final_policy_status = STOP`, `final_decision.recommendation = Reject`, `can_fund_now = false`.

## Conditional pricing exception

- Anchor OK but requested advance **85%**.
- Expect **`POLICY_ADVANCE_ABOVE_80_PCT_REQUIRES_CRO`** plus workflow **`Conditional approve`** / **`Human review required`** depending on conditional logic — funding blocked until officer pricing sign-off captured externally.
