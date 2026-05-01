from __future__ import annotations

import random
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Debtor, ProtocolFlag, RiskCheck, RiskResult
from app.services import settings_service


def protocol_summary(rc: RiskCheck) -> str:
    parts = [
        f"insolvence:{rc.protocol_insolvency}",
        f"spolehlivy_platce:{rc.protocol_taxpayer}",
        f"exekuce:{rc.protocol_execution}",
        f"cese:{rc.protocol_cese}",
        f"rating:{rc.protocol_rating}",
        f"result:{rc.result}",
    ]
    return ", ".join(parts)


def simulate_screening(db: Session, debtor_id: int, bias_ok: float = 0.82) -> RiskCheck:
    debtor = db.get(Debtor, debtor_id)
    if not debtor:
        raise ValueError("Debtor missing")

    rand = random.Random(debtor_id + int(datetime.utcnow().timestamp()) % 10000)

    def pick_flag():
        r = rand.random()
        if r < bias_ok:
            return ProtocolFlag.OK.value
        if r < bias_ok + 0.12:
            return ProtocolFlag.UNKNOWN.value
        return ProtocolFlag.ISSUE.value

    flags = {
        "protocol_insolvency": pick_flag(),
        "protocol_taxpayer": pick_flag(),
        "protocol_execution": pick_flag(),
        "protocol_cese": pick_flag(),
        "protocol_rating": pick_flag(),
    }
    issues = sum(1 for v in flags.values() if v == ProtocolFlag.ISSUE.value)
    if issues >= 3:
        result = RiskResult.BLOCK.value
    elif issues >= 1:
        result = RiskResult.WARNING.value
    else:
        result = RiskResult.OK.value

    rc = RiskCheck(debtor_id=debtor_id, checked_at=datetime.utcnow(), result=result, **flags)
    db.add(rc)
    db.flush()
    settings_service.log_audit(
        db,
        action="risk_check_run",
        entity_type="debtor",
        entity_id=debtor_id,
        detail=protocol_summary(rc),
    )
    return rc


def latest_check(db: Session, debtor_id: int) -> RiskCheck | None:
    return (
        db.query(RiskCheck)
        .filter(RiskCheck.debtor_id == debtor_id)
        .order_by(RiskCheck.checked_at.desc())
        .first()
    )


def risk_ok_for_ui(db: Session, debtor_id: int) -> tuple[str, str]:
    chk = latest_check(db, debtor_id)
    if not chk:
        return "unknown", "bez kontroly"
    ttl = int(settings_service.global_map(db)["odberatel.riskTTL"].replace(",", "."))
    age_days = (datetime.utcnow().date() - chk.checked_at.date()).days
    expired = age_days > ttl
    if chk.result == RiskResult.BLOCK.value:
        return "danger", "BLOCK"
    if expired:
        return "warning", "expirováno"
    if chk.result == RiskResult.WARNING.value:
        return "warning", "WARNING"
    return "ok", "OK"
