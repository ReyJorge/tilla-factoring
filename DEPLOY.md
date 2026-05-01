# Nasazení TILLA — Render + Netlify

Aplikační backend běží na **Render** (Docker + PostgreSQL).  
Adresa typu **`něco.netlify.app`** pouze **přesměruje** návštěvníky na Render — samotná aplikace (FastAPI) na Netlify běžet nemůže.

## 1. Git repozitář

Projekt musí být na GitHubu / GitLabu / Bitbucketu, který Render i Netlify umí připojit.

Kořen repozitáře má obsahovat **`tilla/`**, **`render.yaml`** a **`netlify.toml`** na stejné úrovni (jako v `Tilla_4trans`). Pokud je Git repo jen složka `tilla/`, přesuňte do ní `render.yaml` a nastavte `dockerfilePath: ./Dockerfile`, `dockerContext: .`; `netlify.toml` pak držte v kořeni toho repa (nebo samostatný malý repo jen pro Netlify).

## 2. Render — databáze + web služba (Blueprint)

1. V [Render Dashboard](https://dashboard.render.com) → **New** → **Blueprint**.
2. Vyberte repozitář a větev.
3. Render načte [`render.yaml`](render.yaml): vytvoří **PostgreSQL** `tilla-db` a **Web Service** `tilla-web` z [`tilla/Dockerfile`](tilla/Dockerfile).

   Postgres v Blueprintu může být placený podle aktuálních pravidel Renderu — pokud databázi nevytvoří, založte ji ručně a ve webové službě nastavte **`DATABASE_URL`** z připojení k databázi.

4. Po úspěšném deployi zkopírujte URL služby, např. `https://tilla-web-xxxx.onrender.com`.

**Proměnné prostředí (nastaví Blueprint automaticky)**

- `DATABASE_URL` — z napojené databáze  
- `SESSION_SECRET` — náhodná hodnota  
- Volitelně můžete změnit region v `render.yaml` (`frankfurt` / `oregon`).

## 3. Jednorázově: seed dat na Renderu

Tabulky se vytvoří při startu aplikace (`init_db`). Data pro demo:

1. Render → vaše **Web Service** → **Shell**.
2. Spusťte: `python -m app.seed`  
   Pozor: seed **maže a znovu vytváří** tabulky — v produkci už nespouštějte opakovaně.

## 4. Netlify — doména `*.netlify.app`

1. [Netlify](https://app.netlify.com) → **Add new site** → **Import an existing project** → vyberte **stejný repozitář**.
2. Build settings:
   - **Base directory**: ponechte prázdné (kořen repa, kde leží `netlify.toml`).
   - Build command: prázdné (statický publish).
   - **Publish directory**: musí odpovídat `netlify.toml` → už je `netlify-public`.
3. Deploy.
4. V souborech [`netlify.toml`](netlify.toml) a [`netlify-public/index.html`](netlify-public/index.html) nahraďte **`PLACEHOLDER_SUBDOMAIN`** skutečným poddoménem z Renderu (část před `.onrender.com`, např. `tilla-web-ab12`).
5. Commit, push → Netlify znovu nasadí.

Otevřete `https://váš-web.netlify.app` — měl byste být přesměrováni na Render a uvidět TILLU.

## 5. Limity (MVP)

- **Upload souborů** na Render free/starter: disk kontejneru je **nestálý** — po redeploy soubory mizí. Na trvalé soubory později S3 / Render Disk.
- **První požadavek** po idle může na free/starter trvat déle (cold start).

## 6. Kontrola

- `GET https://…onrender.com/health` → `{"status":"ok",…}`
- Prohlížeč: Netlify URL → přesměrování na `/dashboard` na Renderu.
