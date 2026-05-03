# Risk appetite — bands and gates

Quantitative thresholds are loaded from **`invoice_financing_scoring_model_anchor_risk_FINAL.xlsx`** (`Parametry`, rating catalogue).

## Anchor rating gate (deterministic)

| Input rating | Gate |
|----------------|------|
| AAA, AA, A, BBB | OK (subject to behaviour + concentration) |
| BB, NR | MANUAL |
| B, CCC | STOP |

## Behaviour concentration outputs

The engine emits `concentration_flag`:

- **GREEN**: within coded portfolio/share limits after the proposed invoice.
- **AMBER**: elevated share — policy maps to **CONDITIONAL** path when no hard stops exist.
- **RED FLAG**: breach — manual review required; auto funding forbidden.

## Risk bands A–D

Band comes from total behavioural score vs workbook thresholds (see scoring workbook). **Band D** implies reject path in product logic; **Band C** always requires officer review (`POLICY_RISK_BAND_C_REQUIRES_OFFICER`).
