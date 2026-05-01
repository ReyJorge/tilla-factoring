"""Create or reset SQLite demo data for TILLA."""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta

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
    RiskResult,
    TaxDocument,
    User,
    ProtocolFlag,
)
from app.services import invoice_service


def seed() -> None:
    Base.metadata.drop_all(bind=engine)
    init_db()
    db = SessionLocal()
    rnd = random.Random(42)
    today = date.today()

    users = [
        User(
            username="admin",
            email="admin@tilla.cz",
            full_name="Tereza Dvořáková",
            role="superadmin",
            signature_cz="S pozdravem,\nTereza Dvořáková\nTILLA",
            signature_en="Best regards,\nTereza Dvořáková\nTILLA",
        ),
        User(
            username="mnovak",
            email="mnovak@tilla.cz",
            full_name="Martin Novák",
            role="user",
            signature_cz="",
            signature_en="",
        ),
        User(
            username="zberg",
            email="zberg@tilla.cz",
            full_name="Zuzana Bergmannová",
            role="user",
            signature_cz="",
            signature_en="",
        ),
        User(
            username="lkovar",
            email="lkovar@tilla.cz",
            full_name="Lukáš Kovář",
            role="owner",
            signature_cz="",
            signature_en="",
        ),
    ]
    db.add_all(users)
    db.flush()

    defaults = {
        "kurz.EUR": "25.80",
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
    from app.services.settings_service import SETTING_KEYS

    label_map = {k: lab for k, _, lab in SETTING_KEYS}
    for key, val in defaults.items():
        db.add(GlobalSetting(key=key, value=val, description=label_map.get(key)))

    clients_payload = [
        {
            "contract_number": "2024-013",
            "ic": "27900266",
            "name": "Šlechta transport, s.r.o.",
            "short_name": "SlechtaTrans",
            "dic": "CZ27900266",
            "email": "finance@slechta.demo",
            "iban": "CZ0820100000002001505317",
            "swift": "FIBCZPPXXX",
            "bank_account_number": "2700868221",
            "bank_code": "2010",
            "salutation": "Vážený pane řediteli",
            "resp_idx": 0,
        },
        {
            "contract_number": "2024-027",
            "ic": "24699551",
            "name": "RoJa logistics s.r.o.",
            "short_name": "RoJa",
            "dic": "CZ24699551",
            "email": "fakturace@roja.demo",
            "iban": "CZ7555100000013098736989",
            "swift": "RZBCCZPP",
            "bank_account_number": "1309873698",
            "bank_code": "5500",
            "salutation": "Dobrý den",
            "resp_idx": 1,
        },
        {
            "contract_number": "2024-041",
            "ic": "03454791",
            "name": "Belfords Freight s.r.o.",
            "short_name": "Belfords",
            "dic": "CZ03454791",
            "email": "ops@belfords.demo",
            "iban": "CZ6708000000193524467399",
            "swift": "GIBACZPX",
            "bank_account_number": "9352446739",
            "bank_code": "0800",
            "salutation": "Vážení",
            "resp_idx": 2,
        },
        {
            "contract_number": "2024-058",
            "ic": "69238472",
            "name": "NordAxis EU s.r.o.",
            "short_name": "NordAxis",
            "dic": "CZ69238472",
            "email": "treasury@nordaxis.demo",
            "iban": "CZ913030000011594853728",
            "swift": "AIRACZPP",
            "bank_account_number": "1159485372",
            "bank_code": "3030",
            "salutation": "Dear team",
            "resp_idx": 3,
        },
        {
            "contract_number": "2024-063",
            "ic": "08765432",
            "name": "Baltic Wave Logistics SE",
            "short_name": "BalticWave",
            "dic": "CZ08765432",
            "email": "finance@balticwave.demo",
            "iban": "CZ1020100000002900876512",
            "swift": "FIOBCZPPXXX",
            "bank_account_number": "2900876512",
            "bank_code": "2010",
            "salutation": "Hello",
            "resp_idx": 1,
        },
    ]

    clients: list[Client] = []
    for cp in clients_payload:
        c = Client(
            contract_number=cp["contract_number"],
            ic=cp["ic"],
            name=cp["name"],
            short_name=cp["short_name"],
            dic=cp["dic"],
            email=cp["email"],
            iban=cp["iban"],
            swift=cp["swift"],
            bank_account_number=cp["bank_account_number"],
            bank_code=cp["bank_code"],
            salutation=cp["salutation"],
            responsible_user_id=users[cp["resp_idx"]].id,
        )
        db.add(c)
        clients.append(c)
    db.flush()

    for c in clients:
        db.add_all(
            [
                Contact(client_id=c.id, name="Operativa", email=f"ops@{c.short_name.lower()}.demo", phone="+420 777 000 111"),
                Contact(client_id=c.id, name="Účetnictví", email=c.email, phone="+420 777 000 222"),
            ]
        )

    debtor_names = [
        ("AP Freight, s.r.o.", "03992114", "CZ"),
        ("JKD SPED S.R.O.", "28473921", "CZ"),
        ("Magneta Group UAB", "LT998877665", "LT"),
        ("Auto-moto tech s.r.o.", "17283946", "CZ"),
        ("12Logistics GmbH", "DE449921003", "DE"),
        ("K + M TRANS spol. s r.o.", "45218976", "CZ"),
        ("EU Logistika s.r.o.", "66120987", "CZ"),
        ("SilverRoad Poland Sp. z o.o.", "PL884422119", "PL"),
        ("Radislava Rácová", "74500211", "CZ"),
        ("Helén Nordic AB", "SE559103628", "SE"),
        ("CargoNest s.r.o.", "03288451", "CZ"),
        ("FreshLane BV", "NL884477661", "NL"),
        ("StoneGate carriers s.r.o.", "05933218", "CZ"),
        ("DanubeBridge Kft.", "HU338821904", "HU"),
        ("Alpine Cold Chain AG", "CH339928441", "CH"),
        ("BlueHarbor Logistics OU", "EE991203348", "EE"),
        ("Roman Zednik — RZ Transport", "87362201", "CZ"),
        ("Arcadia Trade s.r.o.", "02938471", "CZ"),
        ("NorthSea Freight ApS", "DK33882109", "DK"),
        ("LatPow cargo SIA", "LV441928377", "LV"),
        ("Moravia Steel Logistics s.r.o.", "29384756", "CZ"),
        ("CentralEuro Hub s.r.o.", "05673829", "CZ"),
        ("GreenFox forwarding s.r.o.", "04992837", "CZ"),
        ("BlackOak GmbH", "DE774029881", "DE"),
        ("BrightRiver UAB", "LT554433221", "LT"),
        ("Vltava Cargo s.r.o.", "04883192", "CZ"),
        ("HarbourLink SIA", "EE773829104", "EE"),
        ("Saxon Freight GmbH", "DE883921004", "DE"),
        ("Carpathian Express s.r.o.", "05882193", "CZ"),
        ("Adriatic Loop d.o.o.", "HR993821771", "HR"),
    ]

    debtors: list[Debtor] = []
    for nm, ic, cc in debtor_names:
        ins_amt = rnd.choice([None, None, 200000, 350000, 500000])
        ins_from = today - timedelta(days=rnd.randint(40, 600)) if ins_amt else None
        d = Debtor(name=nm, ic=ic, email=f"faktury@{ic.lower()}.demo", country_code=cc, insurance_amount=ins_amt, insurance_from=ins_from)
        db.add(d)
        debtors.append(d)
    db.flush()

    for idx, d in enumerate(debtors):
        if idx % 9 == 0:
            result = RiskResult.BLOCK.value
            pins = ProtocolFlag.ISSUE.value
            ptax = ProtocolFlag.OK.value
        elif idx % 5 == 0:
            result = RiskResult.WARNING.value
            pins = ProtocolFlag.OK.value
            ptax = ProtocolFlag.UNKNOWN.value
        else:
            result = RiskResult.OK.value
            pins = ProtocolFlag.OK.value
            ptax = ProtocolFlag.OK.value
        db.add(
            RiskCheck(
                debtor_id=d.id,
                checked_at=datetime.utcnow() - timedelta(days=rnd.randint(1, 120)),
                result=result,
                protocol_insolvency=pins,
                protocol_taxpayer=ptax,
                protocol_execution=ProtocolFlag.OK.value,
                protocol_cese=ProtocolFlag.OK.value,
                protocol_rating=ProtocolFlag.OK.value,
            )
        )
        if rnd.random() < 0.35:
            db.add(
                InsuranceRecord(
                    debtor_id=d.id,
                    insured_limit=float(d.insurance_amount or 250000),
                    valid_from=today - timedelta(days=120),
                    valid_to=today + timedelta(days=240),
                    insurer_name="Euler Hermes DEMO",
                )
            )

    status_cycle = [
        InvoiceStatus.NEW.value,
        InvoiceStatus.PENDING_CHECK.value,
        InvoiceStatus.PENDING_DEBTOR_CONFIRM.value,
        InvoiceStatus.DEBTOR_CONFIRMED.value,
        InvoiceStatus.PURCHASED.value,
        InvoiceStatus.ADVANCE_FINANCED.value,
        InvoiceStatus.AWAITING_COLLECTION.value,
        InvoiceStatus.PARTIALLY_PAID.value,
        InvoiceStatus.FULLY_SETTLED.value,
        InvoiceStatus.OVERDUE.value,
        InvoiceStatus.PROBLEM.value,
    ]

    invoices: list[Invoice] = []
    for i in range(80):
        c = clients[i % len(clients)]
        d = debtors[i % len(debtors)]
        currency = "EUR" if rnd.random() < 0.68 else "CZK"
        amount = rnd.randint(8_000, 220_000) if currency == "CZK" else rnd.randint(300, 9000)
        issued = today - timedelta(days=rnd.randint(10, 520))
        submitted = issued + timedelta(days=rnd.randint(0, 3))
        maturity = rnd.randint(14, 95)
        due = submitted + timedelta(days=maturity)

        status = rnd.choice(status_cycle)
        if status == InvoiceStatus.OVERDUE.value:
            due = today - timedelta(days=rnd.randint(5, 240))
        if status == InvoiceStatus.FULLY_SETTLED.value:
            collected = float(amount)
        elif status == InvoiceStatus.PARTIALLY_PAID.value:
            collected = float(amount) * rnd.uniform(0.2, 0.75)
        elif status in {InvoiceStatus.PURCHASED.value, InvoiceStatus.ADVANCE_FINANCED.value, InvoiceStatus.AWAITING_COLLECTION.value}:
            collected = float(amount) * rnd.choice([0.0, 0.0, 0.15])
        else:
            collected = 0.0

        purchased_date = None
        if status in {
            InvoiceStatus.PURCHASED.value,
            InvoiceStatus.ADVANCE_FINANCED.value,
            InvoiceStatus.AWAITING_COLLECTION.value,
            InvoiceStatus.PARTIALLY_PAID.value,
            InvoiceStatus.FULLY_SETTLED.value,
            InvoiceStatus.OVERDUE.value,
        }:
            purchased_date = submitted + timedelta(days=rnd.randint(2, 15))

        inv = Invoice(
            client_id=c.id,
            debtor_id=d.id,
            variable_symbol=f"VS{470000 + i}",
            invoice_number=f"FA-{2024}-{4200 + i}",
            amount=amount,
            currency=currency,
            issued_date=issued,
            submitted_date=submitted,
            due_date=due,
            purchased_date=purchased_date,
            collected_amount=collected,
            status=status,
            note="Seedovaná ukázková faktura." if rnd.random() < 0.15 else None,
            reminder_level=rnd.randint(0, 4),
        )
        db.add(inv)
        invoices.append(inv)
    db.flush()

    for inv in invoices:
        invoice_service.apply_fee_and_advance(db, inv)

    # Demo overrides client 1
    db.add(ClientSetting(client_id=clients[0].id, key="faktura.zaloha", value="75"))
    db.add(ClientSetting(client_id=clients[0].id, key="poplatek.pasmo1_nepojistene", value="0.61"))

    file_types = ["cmr", "order", "issued_invoice", "other"]
    for inv in rnd.sample(invoices, k=26):
        for ft in rnd.sample(file_types, k=rnd.randint(1, 3)):
            db.add(
                InvoiceFile(
                    invoice_id=inv.id,
                    file_type=ft,
                    original_filename=f"{inv.id}_{ft}.pdf",
                    stored_path=f"uploads/{inv.id}/{ft}.pdf",
                )
            )

    batch = PaymentBatch(reference="SEPA-IMPORT-240901", batch_date=today - timedelta(days=6), description="Import demo")
    db.add(batch)
    db.flush()

    for i in range(38):
        matched = rnd.random() > 0.38
        inv = rnd.choice(invoices) if matched else None
        pay = Payment(
            batch_id=batch.id if rnd.random() < 0.85 else None,
            amount=rnd.randint(5_000, 180_000) if rnd.random() < 0.55 else rnd.randint(200, 6500),
            currency=rnd.choice(["CZK", "EUR"]),
            payer_name=rnd.choice(["Kuhne + Nagel DEMO", "GEFCO ČR DEMO", "DHL Freight DEMO", "ShipServ DEMO"]),
            payment_date=today - timedelta(days=rnd.randint(1, 40)),
            matched_invoice_id=inv.id if inv else None,
            variable_symbol_hint=inv.variable_symbol if inv else f"HINT-{i}",
        )
        db.add(pay)
    db.flush()

    # Offsets — intentional imbalance for dashboard
    fx = float(defaults["kurz.EUR"])
    db.add_all(
        [
            OffsetEntry(
                client_id=clients[0].id,
                invoice_id=invoices[0].id,
                movement_date=today - timedelta(days=30),
                description="Převod zálohy VS seed",
                original_amount=-1040,
                original_currency="EUR",
                fx_rate_to_czk=fx,
                amount_czk=round(-1040 * fx, 2),
                interest_bearing=True,
            ),
            OffsetEntry(
                client_id=clients[0].id,
                movement_date=today - timedelta(days=27),
                description="Inkaso nefinancované faktury — seed",
                original_amount=41000,
                original_currency="CZK",
                fx_rate_to_czk=1,
                amount_czk=41000,
                interest_bearing=False,
            ),
            OffsetEntry(
                client_id=clients[2].id,
                movement_date=today - timedelta(days=11),
                description="LEVELING seed položka",
                original_amount=-250000,
                original_currency="CZK",
                fx_rate_to_czk=1,
                amount_czk=-250000,
                interest_bearing=True,
            ),
        ]
    )

    reminder_candidates = [i for i in invoices if i.status in {InvoiceStatus.OVERDUE.value, InvoiceStatus.AWAITING_COLLECTION.value}]
    for inv in rnd.sample(reminder_candidates, k=min(14, len(reminder_candidates))):
        db.add(
            Reminder(
                invoice_id=inv.id,
                level=min(inv.reminder_level + 1, 5),
                scheduled_for=today - timedelta(days=rnd.randint(0, 3)),
                sent_at=None,
            )
        )

    for inv in rnd.sample(invoices, k=35):
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
            EmailLog(
                invoice_id=invoices[5].id,
                sent_at=datetime.utcnow() - timedelta(days=3),
                recipients="client.demo@tilla.cz",
                subject="uhrazení faktur — seed",
                attachments_summary="VS471005.pdf",
                error_message=None,
            ),
            EmailLog(
                invoice_id=invoices[11].id,
                sent_at=datetime.utcnow() - timedelta(days=9),
                recipients="finance@demo.tilla",
                subject="vyčíslení pohledávek — seed",
                attachments_summary=None,
                error_message=None,
            ),
        ]
    )

    db.add_all(
        [
            BankStatement(
                imported_at=datetime.utcnow() - timedelta(days=2),
                account_iban="CZ000000000000000000001",
                period_from=today - timedelta(days=32),
                period_to=today - timedelta(days=2),
                opening_balance=1_250_000,
                closing_balance=1_410_550,
                currency="CZK",
            ),
            BankStatement(
                imported_at=datetime.utcnow() - timedelta(days=1),
                account_iban="CZ000000000000000000002",
                period_from=today - timedelta(days=30),
                period_to=today - timedelta(days=1),
                opening_balance=185_300,
                closing_balance=176_840,
                currency="EUR",
            ),
        ]
    )

    financed = [i for i in invoices if i.status in {InvoiceStatus.PURCHASED.value, InvoiceStatus.ADVANCE_FINANCED.value}]
    for inv in rnd.sample(financed, k=min(18, len(financed))):
        db.add(
            AdvanceInterestLine(
                invoice_id=inv.id,
                period_month=(today.replace(day=1) - timedelta(days=28)).strftime("%Y-%m"),
                interest_amount_czk=round(float(inv.advance_amount) * 0.002 * float(defaults["kurz.EUR"] if inv.currency == "EUR" else 1), 2),
            )
        )

    db.commit()
    db.close()


if __name__ == "__main__":
    seed()
