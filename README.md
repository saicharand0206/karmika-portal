# 🍒 Karmika Monitor — Scheme Information & Monitoring (Django + Cherry AI)

An academic demo built for a department-style use case: the chatbot does the work.
Cherry is a task-oriented assistant that answers scheme questions and monitors all
records; the site itself has only three sections — Schemes (information), the
Tracking Center, and the Dashboard.

> ⚠️ Demo project by a student. Not affiliated with any government body.
> Sample/test data only; benefit amounts are sample values.

## What changed from the earlier portal
The registration, application, renewal, correction and establishment FORM pages were
removed as per the revised requirement — the department already has its own system
for those. The records remain in the database as monitored data (to be fed by the
department API later), and Cherry works on top of them.

## The three sections
- **/schemes/** — task-oriented specification of every scheme: eligibility,
  documents (per benefit category), procedure, and benefit amount.
- **/track/** — Tracking Center: all applications, renewals, corrections and DBT
  payments in one place, with Cherry embedded and quick-action buttons.
- **/dashboard/** — 8 live charts + data-quality panel.
- **/admin/** — back-office where officers update statuses (admin / karmika123 — change it).

## Cherry: task-oriented by design
For any scheme: explain · eligibility · documents · procedure · benefit amount.
For any number (registration, KPA, KPR, KPC, EST, DBT): precise status from the DB.
For officers: pending counts, failed DBT payments with reasons, expired registrations,
scheme-wise summaries. Uses a RAG pattern — the server injects the relevant records
and the scheme specification into every prompt, so answers come from data, not memory.

## Local run
```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_data
set GEMINI_API_KEY=your_key     # Windows; export on Mac/Linux
python manage.py runserver
```

## Deploy on Render (free)
Connected repo + render.yaml → every `git push` redeploys (build runs
migrate + seed + collectstatic). Environment variable required: GEMINI_API_KEY.
