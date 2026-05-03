# Portfolio monitoring — MVP dashboard

Route **`/credit-risk-agent/portfolio`** aggregates latest audit rows:

- Sum of audited invoice amounts (proxy until treasury feeds exposure-at-risk).
- Anchor/supplier concentration ranking by summed notionals.
- Manual review queue derived from runs whose stored JSON demands human review **or** workflow status **`Human review required`**.
- Risk band histogram from persisted column / JSON snapshot.

Alerts outside scope: scheduled batch jobs watching ledger repayment behaviour — integrate later via warehouse feeds.
