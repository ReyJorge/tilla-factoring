# Approval matrix — authorities

Roles referenced in outputs (`approval_level_required`) map as follows:

| Situation | Authority |
|-----------|-----------|
| `risk_band` A/B, `rating_gate` OK, `concentration_flag` GREEN, no manual triggers | **Credit Manager** may approve after checklist |
| `risk_band` C | **CRO** approval minimum |
| `rating_gate` MANUAL or anchor NR/BB path | **CRO** approval minimum |
| `concentration_flag` RED FLAG or concentration-driven manual triggers | **CRO** or **Credit Committee** per exposure size |
| Requested advance **> 80%** (`requested_advance_pct`) | **CRO** sign-off on pricing exception |
| `final_policy_status` STOP or hard stops present | **Credit Committee** only if requesting override (product blocks workflow approve button) |

The application **never** executes payment — it stores recommendation + workflow status only.
