"""TILLA v3 — bohatý demo dataset (opakovatelné spuštění maže DB a znovu ji naplní)."""

from __future__ import annotations

import logging
import random
from datetime import date, datetime, timedelta

from sqlalchemy import func, inspect

from app.database import SessionLocal, engine, init_db
from app.models import (
    AdvanceInterestLine,
    BankStatement,
    Base,
    Client,
    ClientSetting,
    Contact,
    Debtor,
    EmailLog,
    GlobalSetting,
    InsuranceRecord,
    Invoice,
    InvoiceFile,
    InvoiceStatus,
    OffsetEntry,
    Payment,
    PaymentBatch,
    Reminder,
    RiskCheck,
    TaxDocument,
    User,
    ProtocolFlag,
)
from app.services import invoice_service
from app.services.password_hashing import hash_password
from app.services.settings_service import SETTING_KEYS

logger = logging.getLogger(__name__)


def seed_demo_if_empty() -> None:
    """Na Renderu (bez shellu) naplní demo data pouze pokud jsou tabulky clients/invoices prázdné."""
    import os

    if os.getenv("TILLA_SKIP_AUTO_SEED", "").lower() in ("1", "true", "yes"):
        logger.info("TILLA_SKIP_AUTO_SEED is set; skipping auto demo seed.")
        return

    init_db()
    try:
        table_names = set(inspect(engine).get_table_names())
    except Exception as exc:
        logger.exception("Could not inspect database: %s", exc)
        return

    if "clients" not in table_names or "invoices" not in table_names:
        logger.warning(
            "Tables 'clients' or 'invoices' not present after init_db; skipping auto-seed."
        )
        return

    db = SessionLocal()
    try:
        n_clients = db.query(Client).count()
        n_invoices = db.query(Invoice).count()
    except Exception as exc:
        logger.exception("Could not read client/invoice counts: %s", exc)
        return
    finally:
        db.close()

    if n_clients > 0 or n_invoices > 0:
        logger.info("Database already populated")
        return

    logger.info("Database empty, running demo seed...")
    seed()
    logger.info("Seed completed")


def seed(skip_schema_reset: bool = False) -> None:
    if not skip_schema_reset:
        Base.metadata.drop_all(bind=engine)
        init_db()
    db = SessionLocal()
    rnd = random.Random(42)
    today = date.today()

    FINANCED_BLOCK_FORBIDDEN = frozenset(
        {
            InvoiceStatus.PURCHASED.value,
            InvoiceStatus.ADVANCE_FINANCED.value,
            InvoiceStatus.AWAITING_COLLECTION.value,
            InvoiceStatus.PARTIALLY_PAID.value,
            InvoiceStatus.OVERDUE.value,
        }
    )
    BLOCK_DEBTOR_POSITIONS = frozenset({18, 19})

    import os

    admin_pwd = os.getenv("ADMIN_PASSWORD", "changeme")
    users = [
        User(
            username="admin",
            email="admin@tilla.cz",
            full_name="Tereza Dvořáková",
            role="superadmin",
            password_hash=hash_password(admin_pwd),
        ),
        User(username="mnovak", email="mnovak@tilla.cz", full_name="Martin Novák", role="user"),
        User(username="zberg", email="zberg@tilla.cz", full_name="Zuzana Bergmannová", role="user"),
        User(username="lkovar", email="lkovar@tilla.cz", full_name="Lukáš Kovář", role="owner"),
        User(username="mcizik", email="mcizik@tilla.cz", full_name="Mirek Čižík", role="user"),
    ]
    db.add_all(users)
    db.flush()

    owner_mail = os.getenv("OWNER_EMAIL", "").strip().lower()
    if owner_mail:
        ou = db.query(User).filter(func.lower(User.email) == owner_mail).first()
        if ou and not ou.password_hash:
            ou.password_hash = hash_password(admin_pwd)

    defaults = {
        "kurz.EUR": "25.00",
        "dph": "21",
        "faktura.maxKoncentrace": "20",
        "faktura.minOdberatele": "5",
        "faktura.neodkoupenaMsg": "43200",
        "faktura.zaloha": "70",
        "odberatel.riskTTL": "30",
        "poplatek.pasmo1_dny": "31",
        "poplatek.pasmo1_nepojistene": "1.2",
        "poplatek.pasmo1_pojistene": "1.2",
        "poplatek.pasmo2_dny": "62",
        "poplatek.pasmo2_nepojistene": "2.4",
        "poplatek.pasmo2_pojistene": "2.4",
        "poplatek.pasmo3_dny": "94",
        "poplatek.pasmo3_nepojistene": "3.6",
        "poplatek.pasmo3_pojistene": "3.6",
        "poplatek.urok": "0.05",
        "poplatek.urok_penale": "0.08",
    }
    label_map = {k: lab for k, _, lab in SETTING_KEYS}
    for key, val in defaults.items():
        desc = label_map.get(key)
        if key == "kurz.EUR":
            desc = "Demo FX rate EUR to CZK"
        db.add(GlobalSetting(key=key, value=val, description=desc))

    clients_payload = [
        {"nm": "Šlechta transport, s.r.o.", "sn": "Šlechta", "ic": "27900266", "contract": "2019013", "hq": "Praha 4", "email": "finance@slechta.demo"},
        {"nm": "RoJa Logistics s.r.o.", "sn": "RoJa", "ic": "24699551", "contract": "2019027", "hq": "Praha 9", "email": "fakturace@roja.demo"},
        {"nm": "LinhartTrans s.r.o.", "sn": "LinhartTrans", "ic": "25588901", "contract": "2019035", "hq": "Brno", "email": "ops@linharttrans.demo"},
        {"nm": "KK Deliv s.r.o.", "sn": "KK Deliv", "ic": "04882193", "contract": "2021038", "hq": "Ostrava", "email": "finance@kkdeliv.demo"},
        {"nm": "Fullpack Cars s.r.o.", "sn": "Fullpack", "ic": "05933218", "contract": "2021044", "hq": "Plzeň", "email": "ucetni@fullpack.demo"},
        {"nm": "Gross Trans s.r.o.", "sn": "Gross Trans", "ic": "06120987", "contract": "2021052", "hq": "Olomouc", "email": "billing@grosstr.demo"},
        {"nm": "OVO Trans s.r.o.", "sn": "OVO Trans", "ic": "03288451", "contract": "2021061", "hq": "České Budějovice", "email": "faktury@ovo.demo"},
        {"nm": "Saso Trans s.r.o.", "sn": "Saso Trans", "ic": "02938471", "contract": "2021077", "hq": "Zlín", "email": "finance@saso.demo"},
        {"nm": "VVF-Trans-Speed s.r.o.", "sn": "VVF Trans", "ic": "05882193", "contract": "2021089", "hq": "Pardubice", "email": "speed@vvf.demo"},
        {"nm": "Benke s.r.o.", "sn": "Benke", "ic": "03992114", "contract": "2021097", "hq": "Liberec", "email": "benke@benke.demo"},
    ]
    clients: list[Client] = []
    for i, cp in enumerate(clients_payload):
        c = Client(
            contract_number=cp["contract"],
            ic=cp["ic"],
            name=cp["nm"],
            short_name=cp["sn"],
            dic=f"CZ{cp['ic']}",
            email=cp["email"],
            headquarters=cp["hq"],
            iban=f"CZ650800000019200014539{i:02d}",
            swift="FIBCZPPXXX",
            bank_account_number=str(2700868221 + i),
            bank_code="2010",
            salutation="Vážený obchodní partnere",
            responsible_user_id=users[i % len(users)].id,
        )
        db.add(c)
        clients.append(c)
    db.flush()

    for c in clients:
        db.add(Contact(client_id=c.id, name="Operativa", email=f"dispatch@{c.short_name.lower()}.demo"))

    debtor_specs = [
        ("AP Freight, s.r.o.", "03992114", "CZ", "apfreight.demo"),
        ("Kuehne + Nagel (AG + Co.) KG", "DE884477661", "DE", "kuehne-nagel.demo"),
        ("DSV Road a.s.", "28473921", "CZ", "dsv.demo"),
        ("JKD Sped s.r.o.", "66120987", "CZ", "jkdsped.demo"),
        ("Gefco Česká republika", "45218976", "CZ", "gefco.demo"),
        ("PMG Logistic Int. s.r.o.", "05673829", "CZ", "pmg.demo"),
        ("Univa Spedition s.r.o.", "04992837", "CZ", "univa.demo"),
        ("Ekol Logistics spol.", "04883192", "CZ", "ekol.demo"),
        ("Lagermax spedice a logistika", "05882193", "CZ", "lagermax.demo"),
        ("LevSped s.r.o.", "03288451", "CZ", "levsped.demo"),
        ("Nord-Spedition OÜ", "EE991203348", "EE", "nord.demo"),
        ("Freja Transport & Logistics A/S", "DK33882109", "DK", "freja.demo"),
        ("TitanDrius UAB", "LT554433221", "LT", "titandrius.demo"),
        ("Magnetta Group UAB", "LT998877665", "LT", "magnetta.demo"),
        ("Tu-Tell Logistic", "HU338821904", "HU", "tutell.demo"),
        ("Auto-moto tech s.r.o.", "17283946", "CZ", "automotech.demo"),
        ("Baltijos unigrupė UAB", "LT441928377", "LT", "baltijos.demo"),
        ("Quick-Sped s.r.o.", "29384756", "CZ", "quicksped.demo"),
        ("Bunny Transport s.r.o.", "03454791", "CZ", "bunny.demo"),
        ("12Logistics GmbH", "DE449921003", "DE", "12logistics.demo"),
    ]
    debtors: list[Debtor] = []
    ins_cycle = [280000.0, None, 400000.0, None, 520000.0, None, 360000.0, None, 450000.0, None]
    for idx, (nm, ic, cc, dom) in enumerate(debtor_specs):
        ins_amt = ins_cycle[idx % len(ins_cycle)]
        ins_from = today - timedelta(days=120 + idx * 7) if ins_amt else None
        d = Debtor(name=nm, ic=ic, email=f"faktury@{dom}", country_code=cc, insurance_amount=ins_amt, insurance_from=ins_from)
        db.add(d)
        debtors.append(d)
    db.flush()

    for idx, d in enumerate(debtors):
        # ~70 % OK (fresh), WARNING 3×, EXPIRED výsledek 1×, BLOCK 2× — viz BLOCK_DEBTOR_POSITIONS u faktur
        if idx <= 13:
            rs, age_d = "OK", 9
        elif idx <= 16:
            rs, age_d = "WARNING", 11
        elif idx == 17:
            rs, age_d = "EXPIRED", 42
        else:
            rs, age_d = "BLOCK", 6
        pins = ProtocolFlag.ISSUE.value if rs == "BLOCK" else ProtocolFlag.OK.value
        prat = ProtocolFlag.ISSUE.value if rs == "BLOCK" else ProtocolFlag.UNKNOWN.value if rs == "EXPIRED" else ProtocolFlag.OK.value
        ptax = (
            ProtocolFlag.UNKNOWN.value
            if rs in {"WARNING", "EXPIRED"}
            else ProtocolFlag.OK.value
            if rs == "OK"
            else ProtocolFlag.UNKNOWN.value
        )
        db.add(
            RiskCheck(
                debtor_id=d.id,
                checked_at=datetime.utcnow() - timedelta(days=age_d),
                result=rs,
                protocol_insolvency=pins,
                protocol_taxpayer=ptax,
                protocol_execution=ProtocolFlag.OK.value,
                protocol_cese=ProtocolFlag.OK.value,
                protocol_rating=prat,
            )
        )
        if float(d.insurance_amount or 0) > 0:
            db.add(
                InsuranceRecord(
                    debtor_id=d.id,
                    insured_limit=float(d.insurance_amount),
                    valid_from=today - timedelta(days=200),
                    valid_to=today + timedelta(days=400),
                    insurer_name="Euler Hermes DEMO",
                )
            )

    slechta = next(c for c in clients if "Šlechta" in c.name)
    for key, val in [
        ("faktura.zaloha", "75"),
        ("poplatek.pasmo1_nepojistene", "0.61"),
        ("poplatek.pasmo1_pojistene", "1.05"),
        ("poplatek.pasmo2_nepojistene", "1.23"),
    ]:
        db.add(ClientSetting(client_id=slechta.id, key=key, value=val))

    vs_presets = [
        "20201642",
        "20201631",
        "20201630",
        "20201621",
        "VS20190339",
        "VS20190331",
        "VS20190332",
        "VS20190333",
        "VS20190334",
        "VS20190335",
    ]
    amt_presets = [
        (1210.0, "EUR"),
        (42350.0, "CZK"),
        (2662.0, "EUR"),
        (87120.0, "CZK"),
        (33880.0, "CZK"),
        (12100.0, "CZK"),
        (5500.0, "CZK"),
        (600.0, "EUR"),
        (545.0, "EUR"),
        (4840.0, "CZK"),
        (8470.0, "CZK"),
        (15730.0, "CZK"),
    ]

    categories = ["SETTLED"] * 52 + ["OVERDUE"] * 14 + ["FINALIZE"] * 8 + ["PIPE"] * 56 + ["EARLY"] * 10
    rnd.shuffle(categories)

    invoices: list[Invoice] = []
    featured_idx: int | None = None

    for i in range(140):
        cat = categories[i]
        c = clients[i % 10]
        base_di = i % 20
        di = base_di
        if cat in {"OVERDUE", "FINALIZE", "PIPE"}:
            for step in range(20):
                cand = (base_di + step) % 20
                if cand not in BLOCK_DEBTOR_POSITIONS:
                    di = cand
                    break
        d = debtors[di]

        amt, cur = amt_presets[i % len(amt_presets)]
        amount = round(amt * (0.97 + (i % 5) * 0.007), 2)
        vs_base = vs_presets[i % len(vs_presets)]
        vs = vs_base if i < len(vs_presets) else f"{vs_base}-{i}"

        issued = submitted = due = today
        collected = 0.0
        status = InvoiceStatus.NEW.value
        purchased_date = None
        reminder_level = min(3, i % 5)

        if cat == "SETTLED":
            issued = today - timedelta(days=95 + (i % 75))
            submitted = issued + timedelta(days=i % 3)
            due = submitted + timedelta(days=22 + (i % 20))
            status = InvoiceStatus.FULLY_SETTLED.value
            collected = amount
            purchased_date = submitted + timedelta(days=6 + (i % 9))
        elif cat == "OVERDUE":
            issued = today - timedelta(days=48 + (i % 30))
            submitted = issued + timedelta(days=i % 2)
            due = today - timedelta(days=6 + (i % 26))
            status = InvoiceStatus.OVERDUE.value
            purchased_date = submitted + timedelta(days=5 + (i % 7))
            collected = round(amount * [0.0, 0.07, 0.14][i % 3], 2)
        elif cat == "FINALIZE":
            issued = today - timedelta(days=52 + (i % 38))
            submitted = issued + timedelta(days=1)
            # Částka už dorazila — splatnost ještě před námi → nepatří do „po splatnosti“ KPI
            due = today + timedelta(days=3 + (i % 12))
            status = InvoiceStatus.AWAITING_COLLECTION.value
            purchased_date = submitted + timedelta(days=7)
            collected = round(amount * 0.9996, 2)
        elif cat == "PIPE":
            issued = today - timedelta(days=10 + (i % 48))
            submitted = issued + timedelta(days=i % 2)
            due = today + timedelta(days=18 + (i % 24))
            purchased_date = submitted + timedelta(days=5 + (i % 8))
            collected = round(amount * [0.0, 0.04][i % 2], 2)
            mod = i % 3
            if mod == 0:
                status = InvoiceStatus.PURCHASED.value
            elif mod == 1:
                status = InvoiceStatus.ADVANCE_FINANCED.value
            else:
                status = InvoiceStatus.AWAITING_COLLECTION.value
            if featured_idx is None and c.id == slechta.id:
                featured_idx = len(invoices)
        else:
            issued = today - timedelta(days=7 + (i % 26))
            submitted = issued + timedelta(days=i % 2)
            due = today + timedelta(days=32 + (i % 20))
            collected = 0.0
            purchased_date = None
            status = InvoiceStatus.NEW.value if i % 2 == 0 else InvoiceStatus.PENDING_CHECK.value

        inv = Invoice(
            client_id=c.id,
            debtor_id=d.id,
            variable_symbol=vs,
            invoice_number=f"FA-{issued.year}-{8200 + i}",
            amount=amount,
            currency=cur,
            issued_date=issued,
            submitted_date=submitted,
            due_date=due,
            purchased_date=purchased_date,
            collected_amount=collected,
            status=status,
            note=None,
            reminder_level=reminder_level,
        )
        db.add(inv)
        invoices.append(inv)

    db.flush()

    fi = featured_idx if featured_idx is not None else next(j for j, inv in enumerate(invoices) if inv.client_id == slechta.id)
    feat_inv = invoices[fi]
    feat_inv.variable_symbol = "20201642"

    for inv in invoices:
        invoice_service.apply_fee_and_advance(db, inv)

    demo_files = [
        ("issued_invoice", "Vydana faktura - 20201642.pdf"),
        ("cmr", "20201642_CMR.pdf"),
        ("order", "20201642_objednavka.pdf"),
    ]
    for ft, fn in demo_files:
        db.add(
            InvoiceFile(
                invoice_id=feat_inv.id,
                file_type=ft,
                original_filename=fn,
                stored_path=f"uploads/{feat_inv.id}/{fn}",
            )
        )

    for i, subj in enumerate(
        [
            ("Žádost o potvrzení faktury — VS", "Potvrďte prosím přijetí služeb."),
            ("Potvrzení odběratele — VS", "Potvrzujeme řádné přijetí."),
            ("Upomínka — VS", "Žádáme o úhradu po splatnosti."),
            ("Oznámení o financování — VS", "Záloha byla vyplacena."),
        ]
    ):
        db.add(
            EmailLog(
                invoice_id=feat_inv.id,
                sent_at=datetime.utcnow() - timedelta(days=7 + i * 11),
                recipients="anchor.demo@tilla.cz",
                subject=f"{subj[0]} {feat_inv.variable_symbol}",
                attachments_summary=subj[1],
                error_message=None,
            )
        )

    batches_meta = [
        ("SEPA-240901", "SEPA import", "processed"),
        ("CAMT-240902", "CAMT výpis", "processed"),
        ("MANUAL-240903", "Ruční dávka", "review"),
        ("SEPA-240910", "SEPA import", "processed"),
        ("RETURN-240915", "Vratka / oprava", "processed"),
    ]
    batch_dates = [11, 19, 27, 36, 48]
    batches: list[PaymentBatch] = []
    for bi, (ref, btype, st) in enumerate(batches_meta):
        b = PaymentBatch(
            reference=ref,
            batch_date=today - timedelta(days=batch_dates[bi]),
            description=f"TILLA demo {ref}",
            batch_type=btype,
            status=st,
        )
        db.add(b)
        batches.append(b)
    db.flush()

    payers = ["Kuehne + Nagel DEMO", "DSV DEMO", "GEFCO DEMO", "JKD SPED DEMO", "Bank klient DEMO"]

    settled_inv = [inv for inv in invoices if inv.status == InvoiceStatus.FULLY_SETTLED.value]
    pipe_inv = [inv for inv in invoices if inv.status != InvoiceStatus.FULLY_SETTLED.value]
    per_batch = [7, 6, 7, 8, 7]
    seq = 0
    mult = [0.82, 0.91, 1.0, 0.88, 0.95]
    for bi, batch in enumerate(batches):
        for j in range(per_batch[bi]):
            matched = (seq % 18) != 0
            pool = settled_inv if matched else pipe_inv
            inv = pool[(seq + bi * 3 + j) % len(pool)]
            amt_tpl = amt_presets[seq % len(amt_presets)]
            amt = round(amt_tpl[0] * mult[seq % len(mult)], 2)
            cur = amt_tpl[1]
            hint = inv.variable_symbol if (seq % 7) != 2 else f"HINT-{seq}"
            db.add(
                Payment(
                    batch_id=batch.id,
                    amount=amt,
                    currency=cur,
                    payer_name=payers[(seq + bi) % len(payers)],
                    payment_date=today - timedelta(days=4 + (seq % 38)),
                    matched_invoice_id=inv.id if matched else None,
                    probable_invoice_id=None if matched else inv.id,
                    variable_symbol_hint=hint,
                )
            )
            seq += 1

    unmatched_amounts = [
        (8400.0, "CZK"),
        (380.0, "EUR"),
        (12150.0, "CZK"),
        (515.0, "EUR"),
        (22340.0, "CZK"),
        (910.0, "EUR"),
        (4820.0, "CZK"),
        (620.0, "EUR"),
        (15680.0, "CZK"),
        (445.0, "EUR"),
    ]
    for j, (amt, cur) in enumerate(unmatched_amounts):
        inv = pipe_inv[(j * 5 + 3) % len(pipe_inv)]
        db.add(
            Payment(
                batch_id=None,
                amount=amt,
                currency=cur,
                payer_name=payers[(j + 2) % len(payers)],
                payment_date=today - timedelta(days=2 + (j % 14)),
                matched_invoice_id=None,
                probable_invoice_id=inv.id,
                variable_symbol_hint=inv.variable_symbol,
            )
        )

    db.flush()

    fx = float(defaults["kurz.EUR"])
    offset_specs = [
        (slechta.id, feat_inv.id, -1040, "EUR", fx, True, "Převod zálohy VS 20201642"),
        (slechta.id, None, 41000, "CZK", 1.0, False, "Inkaso nefinancované faktury"),
        (clients[2].id, None, -185000, "CZK", 1.0, True, "LEVELING settlement seed"),
        (clients[4].id, None, 92000, "CZK", 1.0, False, "Připsání inkasa na ZÚ"),
        (clients[7].id, None, -2400, "EUR", fx, True, "Úroková složka zálohy"),
        (clients[8].id, None, 15500, "EUR", fx, False, "Oprava kurzového rozdílu"),
        (clients[3].id, None, -67000, "CZK", 1.0, True, "Doúčtování poplatku"),
    ]
    for oi, (cid, iid, orig_amt, cur, rate, bearing, desc) in enumerate(offset_specs):
        db.add(
            OffsetEntry(
                client_id=cid,
                invoice_id=iid,
                movement_date=today - timedelta(days=14 + oi * 11),
                description=desc,
                original_amount=orig_amt,
                original_currency=cur,
                fx_rate_to_czk=rate,
                amount_czk=round(orig_amt * rate, 2),
                interest_bearing=bearing,
            )
        )

    cand_rem = sorted(
        [
            inv
            for inv in invoices
            if inv.status
            in {InvoiceStatus.OVERDUE.value, InvoiceStatus.AWAITING_COLLECTION.value, InvoiceStatus.PARTIALLY_PAID.value}
        ],
        key=lambda x: x.due_date,
    )
    for inv in cand_rem[:12]:
        db.add(
            Reminder(
                invoice_id=inv.id,
                level=min(inv.reminder_level + 1, 4),
                scheduled_for=today - timedelta(days=inv.id % 6),
                sent_at=None,
            )
        )

    for inv in invoices:
        base = float(inv.amount) / (1 + float(defaults["dph"]) / 100)
        db.add(
            TaxDocument(
                invoice_id=inv.id,
                doc_type="normal",
                variable_symbol=inv.variable_symbol,
                issued_date=inv.issued_date,
                tax_supply_date=inv.issued_date,
                base_amount=round(base, 2),
                total_amount=float(inv.amount),
                currency=inv.currency,
            )
        )

    db.add_all(
        [
            BankStatement(
                imported_at=datetime.utcnow() - timedelta(days=2),
                account_iban="CZ000000000000000000011",
                period_from=today - timedelta(days=30),
                period_to=today - timedelta(days=2),
                opening_balance=2_410_000,
                closing_balance=2_628_350,
                currency="CZK",
            ),
            BankStatement(
                imported_at=datetime.utcnow() - timedelta(days=1),
                account_iban="CZ000000000000000000012",
                period_from=today - timedelta(days=28),
                period_to=today - timedelta(days=1),
                opening_balance=412_800,
                closing_balance=398_120,
                currency="EUR",
            ),
        ]
    )

    fin = sorted(
        [x for x in invoices if x.status in {InvoiceStatus.PURCHASED.value, InvoiceStatus.ADVANCE_FINANCED.value}],
        key=lambda x: x.id,
    )
    for ix, inv in enumerate(fin):
        if ix % 2:
            continue
        db.add(
            AdvanceInterestLine(
                invoice_id=inv.id,
                period_month=(today.replace(day=1) - timedelta(days=28)).strftime("%Y-%m"),
                interest_amount_czk=round(float(inv.advance_amount) * 0.002 * (fx if inv.currency == "EUR" else 1), 2),
            )
        )

    db.commit()
    db.close()


if __name__ == "__main__":
    seed()
