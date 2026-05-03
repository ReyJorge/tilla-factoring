# Credit Risk scoring model — role of Excel vs code

The workbook **`knowledge_base/credit_risk/scoring_model/invoice_financing_scoring_model_anchor_risk_FINAL.xlsx`**
(versioned alongside the repo) is the **business reference** for anchor invoice-financing scoring:
thresholds, rating catalogue (AAA … NR), gates (OK / MANUAL / STOP), advance and fee bands, and
concentration discipline.

## Deterministic engine

Runtime scoring is executed by **`app/services/credit_risk_excel_model.py`**:

- Loads the workbook with **openpyxl** (`data_only=False`) when the file is present (overridable via
  **`CREDIT_RISK_SCORING_MODEL_PATH`**).
- Parses **`Parametry`** and **`Číselníky` / `Ciselniky`** where layout matches expectations.
- If the file is missing (e.g. fresh clone before copying from Risk Management), **embedded defaults**
  mirror the intended structure so the API remains usable — **replace the file for audits**.

The LLM **must not invent** thresholds, gates, scores, advance %, fee %, or risk bands.

## AI layer

The Credit Risk Agent calls OpenAI **only after** `model_result` is computed. The model may:

- Explain deterministic outputs,
- Draft credit memo wording,
- List risks, mitigants, missing information and conditions,

but **cannot override** STOP / MANUAL gates or concentration **RED FLAG** outcomes.

Guardrails in **`credit_risk_agent_service.enforce_llm_guardrails`** enforce this server-side.

## Human approval

Always required when:

- `rating_gate` is **MANUAL** or **STOP**,
- `concentration_flag` is **RED FLAG**,
- **NR** / missing anchor rating (treated as NR/MANUAL in defaults),
- **Dispute** or **data mismatch** escalates gates via the deterministic engine.

## Limitations

- Python reproduction tracks Excel logic conceptually; periodic reconciliation against the workbook after
  parameter changes is recommended.
- Historical JSON is self-reported unless connected to ledger data.

## Safe parameter updates

1. Change the workbook in a controlled folder, keep filename or update `CREDIT_RISK_SCORING_MODEL_PATH`.
2. Verify `Parametry` / rating table rows still parse (log line on startup lists loaded ratings).
3. Add/adjust automated tests when business rules change materially.
4. Redeploy — no runtime Excel editing is required in production.
