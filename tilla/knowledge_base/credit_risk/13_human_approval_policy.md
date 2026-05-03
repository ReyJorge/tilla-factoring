# Human approval policy — workflow statuses

Persisted column **`workflow_status`** on `credit_risk_agent_runs`:

1. `Draft`
2. `Recommended approve`
3. `Conditional approve`
4. `Human review required`
5. `Approved by human`
6. `Rejected by human`
7. `Funded`
8. `Settled`

Initial insert mirrors deterministic headline (`workflow_status_from_final_decision`). Humans advance states via PATCH `/api/credit-risk-agent/run/{id}/workflow`.

STOP guardrail: UI/API refuses **`Approved by human`** when `final_policy_status == STOP`, `rating_gate == STOP`, or any `hard_stops` remain.
