# Legal preconditions — structured fields

Map ERP / counsel outputs into intake JSON:

| `legal_status` value | Meaning |
|---------------------|---------|
| `ok`, `satisfied`, `cleared` | Assignment documentation executable |
| `pending` | **`POLICY_LEGAL_PRECONDITION_PENDING`** — manual review |
| `blocked`, `impossible`, `fail` | **`POLICY_LEGAL_ASSIGNMENT_BLOCKED`** — STOP |

Ban funding without verified assignment chain consistent with Czech Civil Code obligations handled offline.
