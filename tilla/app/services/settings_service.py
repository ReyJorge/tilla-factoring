from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import AuditLog, ClientSetting, GlobalSetting


def _parse_float(val: str) -> float:
    return float(val.replace(",", "."))


def _parse_int(val: str) -> int:
    return int(float(val.replace(",", ".")))


# Fallback hodnoty, když v DB chybí řádek GlobalSetting (staré schéma / prázdná tabulka).
# Demo kurz EUR→CZK při chybějícím kurz.EUR — aplikační kód používá .get(..., DEFAULT_KURZ_EUR).
DEFAULT_KURZ_EUR = "25.00"
DEFAULT_ODBERATEL_RISK_TTL = "30"


SETTING_KEYS = [
    ("kurz.EUR", "float", "Kurz EUR"),
    ("dph", "float", "Standardní sazba DPH (%)"),
    ("faktura.maxKoncentrace", "float", "Maximální koncentrace jednoho odběratele (%)"),
    ("faktura.minOdberatele", "int", "Minimální počet odběratelů"),
    ("faktura.neodkoupenaMsg", "int", "Prodleva upozornění na neodkoupenou fakturu (sekundy)"),
    ("faktura.zaloha", "float", "Záloha za odkoupenou fakturu (%)"),
    ("odberatel.riskTTL", "int", "Platnost risk checku (dny)"),
    ("poplatek.pasmo1_dny", "int", "Poplatek pásmo 1 — hranice dnů"),
    ("poplatek.pasmo1_nepojistene", "float", "Poplatek pásmo 1 nepojištěné (%)"),
    ("poplatek.pasmo1_pojistene", "float", "Poplatek pásmo 1 pojištěné (%)"),
    ("poplatek.pasmo2_dny", "int", "Poplatek pásmo 2 — hranice dnů"),
    ("poplatek.pasmo2_nepojistene", "float", "Poplatek pásmo 2 nepojištěné (%)"),
    ("poplatek.pasmo2_pojistene", "float", "Poplatek pásmo 2 pojištěné (%)"),
    ("poplatek.pasmo3_dny", "int", "Poplatek pásmo 3 — hranice dnů"),
    ("poplatek.pasmo3_nepojistene", "float", "Poplatek pásmo 3 nepojištěné (%)"),
    ("poplatek.pasmo3_pojistene", "float", "Poplatek pásmo 3 pojištěné (%)"),
    ("poplatek.urok", "float", "Denní úrok ze zálohy (%)"),
    ("poplatek.urok_penale", "float", "Denní penále po splatnosti (%)"),
]


def global_map(db: Session) -> dict[str, str]:
    rows = db.query(GlobalSetting).all()
    return {r.key: r.value for r in rows}


def global_float(db: Session, key: str, default_str: str) -> float:
    raw = global_map(db).get(key, default_str)
    return float(str(raw).replace(",", "."))


def global_int(db: Session, key: str, default_str: str) -> int:
    raw = global_map(db).get(key, default_str)
    return int(float(str(raw).replace(",", ".")))


def merged_settings(db: Session, client_id: int | None) -> dict[str, str]:
    g = global_map(db)
    if client_id is None:
        return dict(g)
    overrides = {
        r.key: r.value
        for r in db.query(ClientSetting).filter(ClientSetting.client_id == client_id).all()
        if r.value is not None and r.value.strip() != ""
    }
    out = dict(g)
    out.update(overrides)
    return out


def get_numeric(db: Session, client_id: int | None, key: str, kind: str = "float"):
    m = merged_settings(db, client_id)
    raw = m.get(key)
    if raw is None:
        raise KeyError(key)
    return _parse_float(raw) if kind == "float" else _parse_int(raw)


def log_audit(
    db: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: int | None = None,
    detail: str | None = None,
    user_id: int | None = None,
):
    db.add(
        AuditLog(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            detail=detail,
            user_id=user_id,
        )
    )
