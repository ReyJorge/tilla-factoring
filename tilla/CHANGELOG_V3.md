# TILLA v3 — changelog (demo)

## Co je nového

- **Landing `/home`** — marketingový úvod TILLA (embedded factoring), CTA na demo dashboard.
- **Kořen `/`** přesměruje na `/home`; aplikace zůstává na FastAPI + Jinja + SQLite / Render-ready struktuře.
- **Seed `python -m app.seed`** — kompletně přepsaný: 10 pojmenovaných klientů, 20 anchors, **168 faktur**, mix měn CZK/EUR, stavy napříč životním cyklem, nespárované platby s `probable_invoice_id`, zápočty (úročené / neúročené), upomínky, demo soubory a email log pro VS **20201642**, individuální nastavení pro **Šlechta transport**, globální parametry factoringu dle specifikace v3.
- **Auto-seed při startu** — na prázdné DB (`clients` i `invoices` bez řádků) se při deployi na Render spustí demo seed automaticky; opakovaný deploy bez mazání DB seed nepřidává duplicity.
- **Dashboard** — KPI karty (expozice, aktivní FA, po splatnosti, nespárované platby CZK≈, průměrná durace, risk OK rate), vyplněné tabulky včetně částky po splatnosti, stavu settlement řádků a odběratele u upomínek.
- **Klient — detail** — sídlo, jazyk, souhrnné metriky, náhled nastavení, **filtrovatelný seznam faktur** přímo na stránce (`?inv_filter=`).
- **Faktura** — záložky Základní / Platby / Soubory / Daňové doklady / Emaily na čteném detailu; párování platby z detailu i ze záložky úprav.
- **Financování** — `/finance/settlement` (globální úročené / neúročené + souhrn), vylepšené **nespárované platby** (VS, pravděpodobná FA), **platební dávky** se statusem, typem a součtem.
- **Odběratelé** — plnější tabulka (provedeno, expirace risk TTL, pojištění), **`/debtors/risk-checks`** s protokolem a tlačítkem *Lustrovat*.
- **Analýza** — více grafů Chart.js (durace, ETA, donut otevřené/uzavřené, výkon / objem), tabulka s pořadím, expirací risk checku a pojištěním.
- **UI** — sticky navigace, breadcrumbs, KPI bloky, zebra tabulky, TILLA barvy (navy / gold / off-white), Chart.js přes CDN v `base.html`.

## Spuštění seed

Z kořene balíčku `tilla/`:

```bash
python -m app.seed
```

Ruční seed **smaže všechny tabulky a znovu je vytvoří** (`drop_all` + `init_db`).

**Render / nasazení bez shellu:** při startu aplikace se automaticky zavolá `seed_demo_if_empty()` — pokud jsou tabulky `clients` i `invoices` prázdné, proběhne demo seed jednou; při dalším deployi se přeskočí (`Database already populated`). Opt-out: env `TILLA_SKIP_AUTO_SEED=1`.

## Lokální běh

```bash
cd tilla
pip install -r requirements.txt
python -m app.seed
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Demo URL (smoke test)

| URL | Popis |
|-----|--------|
| `/home` | Landing |
| `/health` | Health check (Render) |
| `/dashboard` | Řídicí panel |
| `/clients`, `/clients/{id}` | Klienti + detail s fakturami |
| `/clients/{id}/invoices` | Plná správa faktur klienta |
| `/invoices/{id}`, `/invoices/{id}/edit` | Detail + záložky |
| `/debtors`, `/debtors/risk-checks` | Anchors + lustrace |
| `/finance/unmatched-payments` | Párování |
| `/finance/payment-batches` | Dávky |
| `/finance/settlement` | Settlement portfolio |
| `/analysis/debtors` | Analýza + grafy |
| `/settings/global` | Globální + klientská pravidla (v editaci klienta) |

## Hotové moduly (demo)

Portfolio přehled, klienti, faktury (workflow), odběratelé + risk, finance (platby, dávky, settlement, daňové doklady), analýza, nastavení, landing.

## Známé limity

- Platební **CSV export** u dávek je disabled tlačítkem (demo).
- Bankovní pohyby, emaily a část risk logiky jsou **simulované** (bez externích API).
- Párování a přepočty používají zjednodušené business pravidla MVP — nejedná se o produkční účetní systém.

## Doporučení pro v4

- OAuth / role podle uživatele, audit všech změn v UI.
- Reálný bankovní import (CAMT) + idempotentní importéry.
- API vrstva pro ERP embedded okno (JWT, webhooky).
- Nahrazení globálního `drop_all` seedu na migrace Alembic pro produkční DB.
