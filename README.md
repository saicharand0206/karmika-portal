# 🏗️ Karmika Portal — Worker Welfare Web App (Django + Cherry AI)

An academic demo portal inspired by construction-worker welfare-board workflows:
worker registration, scheme catalogue, benefit applications, status tracking,
analytics dashboards, an admin back-office, and Cherry — an AI assistant wired
into the live database.

> ⚠️ Demo project. Not affiliated with any government body. Sample/test data only.

## Features
- **Worker registration** with auto-generated registration numbers (KP/YYYY/NNNNN) and IFSC validation
- **Worker directory** with search, detail pages (English + Telugu names), data-quality flags
- **Scheme catalogue**: 14 schemes / 26 benefit categories, each with its required documents checklist
- **Benefit applications** with auto-generated application numbers (KPA-YYYY-NNNNN) and status tracking
- **Analytics dashboard**: 6 live Chart.js charts (registrations by year, age, gender, trades, application status/schemes) + data-quality panel
- **Admin back-office** (/admin/): approve/reject applications, manage all records (admin / karmika123 — change it)
- **Cherry AI assistant** on every page, connected to the database:
  paste a registration number → it fetches the worker; paste an application number → it reports status;
  ask about a scheme → it lists the required documents; it also knows live portal stats and guides navigation.

## How Cherry connects everything
Before each AI call, the backend (`portal/views.py → build_context`) injects:
live stats, the full scheme catalogue, any worker/application record whose number
appears in the user's message, and matching document checklists. The LLM (Gemini
2.5 Flash) answers from that injected context — a lightweight RAG pattern.

## Local run
```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_data
set GEMINI_API_KEY=your_key     # Windows; use export on Mac/Linux
python manage.py runserver
```
Open http://127.0.0.1:8000

## Deploy on Render (free)
1. Push this folder to a new GitHub repo.
2. render.com → New → Web Service → connect the repo (render.yaml pre-fills everything;
   the build step runs migrate + seed_data + collectstatic automatically).
3. Add environment variable GEMINI_API_KEY.
4. Deploy → live at https://karmika-portal.onrender.com (or similar).

**Free-tier notes:** the service sleeps after ~15 min idle (first visit takes ~40s);
SQLite lives on ephemeral storage, so user-entered records reset on each deploy/restart —
the seed data always reloads, which keeps the demo consistent. For persistence, switch
DATABASES to a hosted Postgres and remove seed_data from the build command.

## Project structure
```
karmika/
├── render.yaml               # Render blueprint (build = migrate + seed + collectstatic)
├── requirements.txt          # Django, gunicorn, requests, whitenoise
├── manage.py
├── portal_project/           # settings, urls, wsgi
├── portal/
│   ├── models.py             # Worker, Scheme, SubScheme, Application (see SCHEMA.md)
│   ├── views.py              # all pages + dashboard + Cherry chat API with DB context
│   ├── admin.py              # back-office config
│   └── management/commands/seed_data.py   # loads cleaned CSVs, demo apps, admin user
├── templates/portal/         # base + 9 pages (Cherry widget lives in base.html)
├── data/                     # workers_clean.csv, schemes_clean.csv, subschemes_clean.csv
├── clean_analyze.py          # the pandas cleaning/analysis pipeline (reproducible)
├── SCHEMA.md                 # database schema documentation
└── DATA_REPORT.md            # cleaning steps + analysis findings
```
