# TILLA — Invoice Financing MVP

Interní nástroj pro správu **invoice financingu / factoringu**, inspirovaný funkční logikou legacy systémů v českém prostředí, s novým brandem **TILLA** (*Anchored in Trust*).

## Stack

- Python 3.11+
- FastAPI, Jinja2, Uvicorn
- SQLAlchemy 2.x + SQLite (`data/tilla.db`)
- Bootstrap 5 + vlastní téma (`static/css/tilla.css`)

## Instalace

```bash
cd tilla
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Seed databáze

### Ruční seed (vývoj)

```bash
cd tilla
python -m app.seed
```

Tím se databáze **smaže a znovu naplní** (`drop_all`) — používejte jen lokálně / když chcete resetovat demo.

### Automaticky na Renderu (prázdná DB)

Při startu aplikace (`startup`) se po `init_db()` zkontroluje, zda existují tabulky `clients` / `invoices` a zda jsou **obě prázdné**. Pokud ano, proběhne stejný demo seed jako výše — **bez nutnosti shellu** na Render Free.

Při dalším deployi se seed **přeskočí** (už jsou řádky v `clients` nebo `invoices`), takže nedochází k duplicitám.

Logy v stdout:

- `Database empty, running demo seed...` → `Seed completed`
- `Database already populated` → nic se nemění

Chcete-li auto-seed vypnout (např. prázdná produkční DB bez dema), nastavte env **`TILLA_SKIP_AUTO_SEED=1`**.

### Oprava starého schématu Postgres (`TILLA_FORCE_REBUILD`)

Pokud Render hlásí nekonzistentní schéma (např. `UndefinedTable` při `drop_all`), nastavte **`TILLA_FORCE_REBUILD=1`**.

- **PostgreSQL:** při startu se provede **`DROP SCHEMA public CASCADE`**, **`CREATE SCHEMA public`**, **`GRANT ALL ON SCHEMA public TO public`**, pak **`create_all`** a **`seed()`** (bez druhého `drop_all`). Logy: **`FORCE REBUILD ENABLED`** → **`POSTGRES SCHEMA RESET`** → **`DATABASE RECREATED`** → **`SEED COMPLETE`**.
- **SQLite:** stejně jako dříve `metadata.drop_all` + `create_all` + seed.

**Bezpečnost:** pokud je **`ENVIRONMENT=production`**, rebuild projde jen s **`TILLA_ALLOW_DEMO_REBUILD=1`** (jinak startup skončí chybou).

**Concurrency:** na Renderu nastavte **`WEB_CONCURRENCY=1`** (v blueprintu i v Docker CMD přes tuto proměnnou), aby se při rebuildu nepřihlásily dva worker procesy naráz.

**Po jednom úspěšném deployi** nastavte **`TILLA_FORCE_REBUILD=0`** nebo proměnnou smažte — jinak se databáze při každém startu znovu vymaže. `render.yaml` má `1` pro první opravu schématu; pak hodnotu v Dashboard / YAML změňte.

## Spuštění

Po instalaci a seedu stačí jeden příkaz pro lokální vývoj:

```bash
cd tilla
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Nebo kompletní řetězec od nuly:

```bash
cd tilla && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && python -m app.seed && uvicorn app.main:app --reload
```

Otevřete v prohlížeči: **http://127.0.0.1:8000** → přesměrování na **`/home`** (landing). Dashboard: **`/dashboard`**.

Podrobný přehled změn v3 v souboru **[CHANGELOG_V3.md](./CHANGELOG_V3.md)**.

## Moduly

| Oblast | Popis |
|--------|--------|
| **Úvod (`/home`)** | Landing TILLA v3, CTA do demo aplikace |
| **Dashboard** | KPI + tabulky po splatnosti, finalizace, platby, zápočty, upomínky |
| **Klienti** | Detail se sídlem, filtrovatelné faktury, nastavení vs. globální |
| **Faktury** | Workflow, záložky (základní, platby, soubory, daň, emaily), párování platby |
| **Odběratelé** | Anchors, tabulka s risk / pojištěním, stránka **`/debtors/risk-checks`** |
| **Financování** | Platby, párování, dávky, výpisy, daňové doklady, úroky, pojištění, **`/finance/settlement`**, inkaso, fronty **`/finance/overdue-invoices`**, **`/finance/finalize-candidates`**, **`/finance/reminders-due`** |
| **Diagnostika** | **`GET /debug/db-counts`** — počty řádků hlavních tabulek (demo / kontrola seedu) |
| **Analýza** | Tabulka výkonu + více grafů (Chart.js) |
| **Nastavení** | Globální parametry (`GlobalSetting`), přepsání u klienta |

## Business pravidla (zjednodušeně MVP)

- **Záloha**: částka × `faktura.zaloha` % (globálně nebo přepsáno u klienta).
- **Poplatek**: podle počtu dnů od zadání do splatnosti a pásem `poplatek.pasmo*_dny`; rozlišení pojištěné/nepojištěné dle limitu na odběrateli.
- **Po splatnosti**: automatický přechod na stav „po splatnosti“, kde to dává smysl (není ukončená ani problém).
- **Odkup**: vyžaduje platný risk check (ne starší než `odberatel.riskTTL`), výsledek nesmí být **BLOCK**, kontrola koncentrace portfolia klienta vůči jednomu odběrateli (`faktura.maxKoncentrace`).
- **Párování platby**: připíše částku na inkaso faktury a případně mění stav na částečně/plně uhrazenou.

## Další kroky k produkci

- Autentizace a role (JWT / session), napojení na firemní SSO.
- Migrace na PostgreSQL, Alembic migrace.
- Skutečné napojení na ARES / platební API / ERP (Byznys, iDoklad).
- Fronta úloh (Celery/RQ) pro emaily, import výpisů a reminder workflow.
- Komplexnější účetní zápočty a měnové přeceňování.

## Tilla Credit Risk Officer v1

Interní embedded invoice-financing risk stack **`/credit-risk-agent`** + **`/credit-risk-agent/portfolio`**.

### Princip vrstev

| Vrstva | Zdroj pravdy | Soubor / výstup |
|--------|----------------|-----------------|
| Deterministické skóre | Excel workbook → Python runtime | `credit_risk_excel_model.py`, wrapper `credit_risk_scoring_engine.calculate_credit_risk` → `model_result` |
| Policy kontroly | Pravidla nad vstupem + sync model triggerů | `credit_risk_policy_engine.run_policy_checks` → `policy_check_result` (`PASS` / `CONDITIONAL` / `MANUAL` / `STOP`) |
| AI memo | Pouze narrative JSON | `credit_risk_agent_service.analyse_credit_risk` — nesmí měnit advance/fee/brány; server přepíše `recommendation` podle `final_decision` |
| Workflow | Člověk | HTTP `PATCH /api/credit-risk-agent/run/{id}/workflow`, audit tabulka |

Knowledge base (memo vrstva načítá **`NN_*.md`**): `tilla/knowledge_base/credit_risk/00_governance.md` … `17_model_limitations.md`.

### Tvrdé zákazy (STOP)

Nevydává se automatické financování (`final_decision.can_fund_now = false`), pokud platí STOP (`policy_check_result.final_policy_status == STOP`, případně `rating_gate == STOP`, spor, fraud příznaky atd.). Workflow akce **`Approved by human`** je API zamítnuto při STOP / hard stops.

### Proměnné prostředí

| Proměnná | Popis |
|----------|--------|
| **`OPENAI_API_KEY`** | Volitelné — bez klíče se použije deterministický memo fallback (viz testy). |
| **`OWNER_EMAIL`** | Shoda emailu uživatele v DB ⇒ přístup k CRO (vedle rolí admin/superadmin). |
| **`ADMIN_PASSWORD`** | Seed heslo admin účtu. |
| **`SESSION_SECRET`** | Cookie session + mini test harness. |
| **`OPENAI_MODEL`** | Např. `gpt-4o-mini`. |
| **`DEBUG`** | `1` ⇒ více logů (citlivá data — jen vývoj). |
| **`CREDIT_RISK_SUPPLIER_CAP_CZK`** / **`CREDIT_RISK_ANCHOR_CAP_CZK`** | Volitelné limity pro policy překročení (viz `08_fraud_operational_checklist.md`). |
| **`CREDIT_RISK_SCORING_MODEL_PATH`** | Absolutní cesta k `.xlsx` (jinak výchozí soubor ve `knowledge_base/credit_risk/scoring_model/`). |

### Render / Postgres / SQLite

- Nové instalace: SQLAlchemy `create_all()` vytvoří rozšířené sloupce na `credit_risk_agent_runs`.
- Existující DB: proveďte migraci **`migrations/extend_credit_risk_agent_runs_market_standard.sql`** (záloha předem).

### Testy

```bash
cd tilla && python -m compileall app && python -m unittest discover -s tests -p 'test_*.py'
```

### Omezení modelu

Shrnuto v **`knowledge_base/credit_risk/17_model_limitations.md`** — např. self-report historického JSON, notionální portfolio součty na MVP dashboardu.

---

## Legacy poznámka (invoice scoring workbook)

- **Soubor modelu:** `tilla/knowledge_base/credit_risk/scoring_model/invoice_financing_scoring_model_anchor_risk_FINAL.xlsx` — viz `scoring_model/README.txt`.
- Metodiku vs Excel viz **`04_scoring_methodology.md`**.

---

## Migrace DB (existující Postgres na Renderu)

Pro doplnění tabulek auditu apod. použijte také historické SQL:

**`migrations/create_credit_risk_agent_runs.sql`**

Nové rozšíření CRO v1:

**`migrations/extend_credit_risk_agent_runs_market_standard.sql`**

## Licence

Ukázkový interní MVP — úpravy dle potřeby projektu.
