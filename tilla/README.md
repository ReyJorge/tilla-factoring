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

## Licence

Ukázkový interní MVP — úpravy dle potřeby projektu.
