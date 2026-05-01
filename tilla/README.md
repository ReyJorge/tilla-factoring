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

```bash
cd tilla
python -m app.seed
```

Směnný kurz, poplatková pásma, zálohy, klienti, odběratelé, faktury, platby, zápočty, risk checks a další ukázková data se založí znovu při každém spuštění seedu (databáze se smaže a založí nanovo).

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

Otevřete v prohlížeči: **http://127.0.0.1:8000** (přesměruje na `/dashboard`).

## Moduly

| Oblast | Popis |
|--------|--------|
| **Dashboard** | Po splatnosti, finalizace, nespárované platby, zápočty, upomínky |
| **Klienti** | CRUD základních údajů, kontakty, individuální nastavení vs. globální |
| **Faktury** | Workflow stavů, odkup s kontrolou risk checku a koncentrace, záloha/poplatek z nastavení |
| **Odběratelé** | Evidence Anchors, simulovaná lustrace s protokolem |
| **Financování** | Platby, párování, dávky, výpisy, daňové doklady, úroky, pojištění, inkaso |
| **Analýza** | Tabulka výkonu + graf (Chart.js) |
| **Nastavení** | Globální parametry (`GlobalSetting`) |

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
