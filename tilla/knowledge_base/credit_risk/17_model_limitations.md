# Model limitations

1. **Historical JSON is user-supplied** unless wired to ERP — delays/volumes may omit adjustments/credits.
2. **Excel parsing tolerance**: malformed workbook tabs silently fall back to coded defaults — monitor startup logs after workbook edits.
3. **Legal interpretation**: structured booleans ≠ counsel opinion — STOP/MANUAL outcomes still require documentary checks.
4. **Portfolio sums**: dashboard totals invoice notionals from audits, not funded balances nor insurer-covered residual risks.
5. **Language**: KB mixes Czech UI labels with English enum tokens (`confirmation_status`) — officers must map ERP vocabulary deliberately.
