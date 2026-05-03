# Governance — Tilla Credit Risk Officer v1

## Authority

1. **Deterministic scoring** (`calculate_credit_risk` → `model_result`) is the sole source for numeric score, risk band, rating gate, recommended advance % and fee % loaded from the Excel-parameterized engine (`credit_risk_excel_model`).
2. **Policy engine** (`run_policy_checks` → `policy_check_result`) applies eligibility and operational gates on top of the model; `final_policy_status` ∈ `PASS | CONDITIONAL | MANUAL | STOP`.
3. **AI layer** produces narrative memo fields only; server-side steps overwrite AI `recommendation`, `human_review_required`, `approval_level_required`, and align conditions with `final_decision`.
4. **Human approval** is mandatory before booking funds whenever `final_decision.can_fund_now` is false or workflow status is not `Approved by human`.

## Versions

- Record `model_version` from scoring engine (`cro-scoring-v1.0` baseline) and `kb_version` (`cro-kb-v1`) on each audit row (`credit_risk_agent_runs`).
- KB markdown consumed by the memo layer uses files named `NN_topic.md` under `knowledge_base/credit_risk/` (numbered files).

## Escalation

- Any change to workbook thresholds requires Risk sign-off and regression tests in `tests/test_credit_risk_scoring_model.py`.
