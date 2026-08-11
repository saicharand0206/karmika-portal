"""Karmika Portal views.

Pages: home, register, workers list/search, worker detail, schemes,
apply, status check, dashboard.

chat_api is where Cherry connects everything: before calling the LLM it
gathers live context from the database — portal stats, the scheme
catalogue, and any registration/application numbers detected in the
user's message — so the chatbot can answer questions about *this*
portal's actual data, not just generic questions.
"""
import json
import os
import re
from datetime import date

import requests
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt

from .models import (Worker, Scheme, SubScheme, Application, District, Mandal,
                     Village, ALOCircle, Nominee, Renewal, ChangeRequest,
                     DBTBatch, DBTPayment, Establishment)

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/"
    "models/gemini-2.5-flash:generateContent"
)


def add_years(d, years):
    try:
        return d.replace(year=d.year + years)
    except ValueError:  # Feb 29
        return d.replace(year=d.year + years, day=28)


# ---------------------------------------------------------------- pages
def home(request):
    stats = {
        "schemes": Scheme.objects.count(),
        "subschemes": SubScheme.objects.count(),
        "workers": Worker.objects.count(),
        "applications": Application.objects.count(),
        "pending": Application.objects.filter(status__in=["SUBMITTED", "UNDER_REVIEW"]).count(),
        "failed_payments": DBTPayment.objects.filter(status="FAILED").count(),
    }
    return render(request, "portal/home.html", {"stats": stats})


def worker_detail(request, reg_no):
    try:
        worker = Worker.objects.get(reg_no=reg_no)
    except Worker.DoesNotExist:
        return render(request, "portal/workers.html", {"workers": [], "q": reg_no, "total": 0,
                                                       "error": f"No worker found with registration number {reg_no}."})
    return render(request, "portal/worker_detail.html", {"w": worker, "apps": worker.applications.all()})


def schemes(request):
    return render(request, "portal/schemes.html",
                  {"schemes": Scheme.objects.prefetch_related("subschemes").all()})




def status(request):
    """Universal tracker: accepts KPA (application), KPR (renewal), or KPC
    (correction) numbers in one box and shows the matching record."""
    app_no = request.GET.get("app_no", "").strip()
    application = renewal = change = None
    error = None
    if app_no:
        up = app_no.upper()
        try:
            if up.startswith("KPR"):
                renewal = Renewal.objects.select_related("worker").get(req_no__iexact=app_no)
            elif up.startswith("KPC"):
                change = ChangeRequest.objects.select_related("worker").get(req_no__iexact=app_no)
            else:
                application = Application.objects.select_related(
                    "worker", "subscheme__scheme").prefetch_related("payments__batch").get(app_no__iexact=app_no)
        except (Application.DoesNotExist, Renewal.DoesNotExist, ChangeRequest.DoesNotExist):
            error = f"No record found with number '{app_no}'. Check the prefix (KPA/KPR/KPC) and digits."
    return render(request, "portal/status.html",
                  {"a": application, "r": renewal, "c": change, "app_no": app_no, "error": error})


def dashboard(request):
    by_year = list(Worker.objects.values("reg_year").annotate(n=Count("id")).order_by("reg_year"))
    by_gender = list(Worker.objects.values("gender").annotate(n=Count("id")))
    by_trade = list(Worker.objects.exclude(trade_code="").values("trade_code")
                    .annotate(n=Count("id")).order_by("-n")[:8])
    app_status = list(Application.objects.values("status").annotate(n=Count("id")))
    app_scheme = list(Application.objects.values("subscheme__scheme__description")
                      .annotate(n=Count("id")).order_by("-n"))
    ages = list(Worker.objects.exclude(age=None).values_list("age", flat=True))
    buckets = {"18-25": 0, "26-35": 0, "36-45": 0, "46-55": 0, "56+": 0}
    for a in ages:
        if a <= 25: buckets["18-25"] += 1
        elif a <= 35: buckets["26-35"] += 1
        elif a <= 45: buckets["36-45"] += 1
        elif a <= 55: buckets["46-55"] += 1
        else: buckets["56+"] += 1

    from datetime import date as _date
    dbt_status = list(DBTPayment.objects.values("status").annotate(n=Count("id")))
    renewal_status = list(Renewal.objects.values("status").annotate(n=Count("id")))
    change_status = list(ChangeRequest.objects.values("status").annotate(n=Count("id")))
    expired = Worker.objects.filter(valid_until__lt=_date.today()).count()
    by_district = list(Worker.objects.exclude(village=None)
                       .values("village__mandal__district__name")
                       .annotate(n=Count("id")).order_by("-n"))
    quality = {
        "missing_dob": Worker.objects.filter(date_of_birth=None).count(),
        "invalid_ifsc": Worker.objects.exclude(ifsc_code="").filter(ifsc_valid=False).count(),
        "test_rows": Worker.objects.filter(is_test_row=True).count(),
    }
    chart_data = {
        "by_year": by_year, "by_gender": by_gender, "by_trade": by_trade,
        "age_buckets": buckets, "app_status": app_status, "app_scheme": app_scheme,
        "dbt_status": dbt_status, "renewal_status": renewal_status,
        "change_status": change_status, "by_district": by_district,
    }
    return render(request, "portal/dashboard.html",
                  {"chart_data": json.dumps(chart_data), "quality": quality,
                   "totals": {"workers": Worker.objects.count(),
                              "applications": Application.objects.count(),
                              "expired": expired,
                              "payments": DBTPayment.objects.count(),
                              "establishments": Establishment.objects.count()}})


# ---------------------------------------------------------------- Cherry
BASE_PROMPT = """You are Cherry, the AI assistant of the Karmika Monitor — an ACADEMIC DEMO
web application (not a real government website) built by a student for a department-style
use case: scheme information and monitoring for construction worker welfare.

You are TASK-ORIENTED. For every scheme you handle a fixed set of tasks:
1. EXPLAIN the scheme in simple words.
2. ELIGIBILITY — who can apply (from the specification below).
3. DOCUMENTS — list the required documents for the scheme/sub-scheme.
4. PROCEDURE — the steps to be followed for applying.
5. BENEFIT AMOUNT — the sanctioned amount (sample values in this demo).
6. STATUS — when the user gives a number, report that record precisely.
7. MONITORING — summaries for officers: pending items, completed items, failed DBT
   payments (with reasons), expired registrations, scheme-wise counts.

Identify which task the question is asking for and answer ONLY that task, short and clear.
Answer in simple words, since workers also use this. Use short points for documents and
numbered steps for procedures. The pages available are: /schemes/ (scheme information),
/track/ (Tracking Center with all records), /dashboard/ (analytics). There is no
registration or application form in this app — those are handled by the department's own
system; politely say so if asked to register or apply here.

Rules: answer only from the data injected below; never invent records or amounts. If a
number or scheme is not found in the data, say so and ask for the correct one. Remind
users this is a demo with sample data when they ask about real benefits."""


DEPT_API_URL = os.environ.get("DEPT_API_URL", "").rstrip("/")
DEPT_API_KEY = os.environ.get("DEPT_API_KEY", "")


def fetch_department_record(kind, number):
    """Optional LIVE lookup against the department's own record API.

    IMPORTANT — this deliberately calls an HTTPS API, not the department's Postgres
    database directly. Cherry runs on a public host (Render) and the department DB
    lives on a private network address, so a direct database connection from here is
    neither reachable nor appropriate. The correct integration is a small internal
    API service (built with Django, running somewhere WITH access to that database)
    that exposes read-only endpoints like the one this function expects below.
    See dept_api_example/ in this project for a starting point for that service.

    This function is a safe no-op until DEPT_API_URL is configured as an environment
    variable (in Render's dashboard, or a local .env file — never hardcoded here or
    committed to the repo). Until then, Cherry simply uses the local demo database.

    Expected department endpoint shape (adjust to match the real API once it exists):
        GET {DEPT_API_URL}/api/{kind}/{number}
        Header: Authorization: Bearer <DEPT_API_KEY>
        Returns JSON with the record's fields.
    """
    if not DEPT_API_URL:
        return None
    try:
        r = requests.get(
            f"{DEPT_API_URL}/api/{kind}/{number}",
            headers={"Authorization": f"Bearer {DEPT_API_KEY}"} if DEPT_API_KEY else {},
            timeout=8,
        )
        if r.status_code == 200:
            return r.json()
    except requests.RequestException:
        pass
    return None


def build_context(message):
    """Gather live DB context so Cherry can answer about this portal's actual data."""
    parts = []

    # Optional: check the department's own live system first (see fetch_department_record
    # below for how this gets wired up once that API exists). Falls back to local data.
    dept_hit = None

    # Live stats
    parts.append(
        f"LIVE PORTAL STATS: {Worker.objects.count()} registered workers, "
        f"{Scheme.objects.count()} schemes with {SubScheme.objects.count()} sub-schemes, "
        f"{Application.objects.count()} applications "
        f"({Application.objects.filter(status='APPROVED').count()} approved, "
        f"{Application.objects.filter(status='SUBMITTED').count()} submitted, "
        f"{Application.objects.filter(status='UNDER_REVIEW').count()} under review, "
        f"{Application.objects.filter(status='REJECTED').count()} rejected). "
        f"Renewals: {Renewal.objects.count()} ({Renewal.objects.filter(status='SUBMITTED').count()} pending). "
        f"Change requests: {ChangeRequest.objects.count()} ({ChangeRequest.objects.filter(status='SUBMITTED').count()} pending). "
        f"DBT payments: {DBTPayment.objects.count()} "
        f"({DBTPayment.objects.filter(status='SUCCESS').count()} success, "
        f"{DBTPayment.objects.filter(status='FAILED').count()} failed, "
        f"{DBTPayment.objects.filter(status='PENDING').count()} pending). "
        f"Expired registrations: {Worker.objects.filter(valid_until__lt=date.today()).count()}. "
        f"Establishments: {Establishment.objects.count()}."
    )

    # Scheme catalogue (compact)
    lines = []
    for s in Scheme.objects.prefetch_related("subschemes"):
        subs = "; ".join(f"{ss.code}) {ss.description}" for ss in s.subschemes.all())
        lines.append(f"{s.code}. {s.description} — sub-schemes: {subs}")
    parts.append("SCHEME CATALOGUE:\n" + "\n".join(lines))

    # Detect registration numbers in the message (e.g. KP/2026/00001 or ALOTEST/2019/00008)
    for reg in set(re.findall(r"[A-Za-z]{2,10}/\d{4}/\d{3,6}", message)):
        dept_hit = fetch_department_record("worker", reg)
        if dept_hit:
            parts.append(f"WORKER LOOKUP {reg} (LIVE from department system): {json.dumps(dept_hit)}")
            continue  # trust the live department record over the local demo copy
        try:
            w = Worker.objects.get(reg_no__iexact=reg)
            apps = "; ".join(f"{a.app_no}: {a.subscheme.description} [{a.status}]"
                             for a in w.applications.all()) or "no applications yet"
            noms = ", ".join(f"{n.name} ({n.relationship})" for n in w.nominees.all()) or "none on record"
            rens = "; ".join(f"{r.req_no} [{r.status}] to {r.period_to}" for r in w.renewals.all()) or "none"
            chgs = "; ".join(f"{c.req_no} {c.get_request_type_display()} [{c.status}]"
                             for c in w.change_requests.all()) or "none"
            validity = (f"valid until {w.valid_until}" + (" (EXPIRED — advise renewal at /renew/)" if w.is_expired else "")) if w.valid_until else "validity not set"
            parts.append(
                f"WORKER LOOKUP {w.reg_no}: name={w.worker_name}, father={w.father_name}, "
                f"gender={w.gender}, age={w.age}, registered={w.reg_year}, {validity}, "
                f"village={w.village or w.district_code}, ALO circle={w.alo_circle_id and w.alo_circle.code}, "
                f"employer={w.employer.name if w.employer_id else 'not linked'}, "
                f"nominees: {noms}; applications: {apps}; renewals: {rens}; change requests: {chgs}"
            )
        except Worker.DoesNotExist:
            parts.append(f"WORKER LOOKUP {reg}: not found in database.")

    # Detect application numbers (e.g. KPA-2026-00001)
    for app_no in set(re.findall(r"KPA-\d{4}-\d{3,6}", message, re.IGNORECASE)):
        try:
            a = Application.objects.select_related("worker", "subscheme__scheme").get(app_no__iexact=app_no)
            parts.append(
                f"APPLICATION LOOKUP {a.app_no}: worker={a.worker.worker_name} ({a.worker.reg_no}), "
                f"scheme={a.subscheme.scheme.description} / {a.subscheme.description}, "
                f"applicant={a.applicant_name}, status={a.status}, "
                f"submitted={a.submitted_at:%d %b %Y}, remarks={a.remarks or 'none'}, "
                f"payments: "
                + ("; ".join(f"{p.batch.batch_no} ₹{p.amount} [{p.status}"
                             + (f": {p.failure_reason}" if p.failure_reason else "") + "]"
                             for p in a.payments.all()) or "no DBT payment yet")
            )
        except Application.DoesNotExist:
            parts.append(f"APPLICATION LOOKUP {app_no}: not found in database.")

    # Renewal request numbers (KPR-YYYY-NNNNN)
    for req in set(re.findall(r"KPR-\d{4}-\d{3,6}", message, re.IGNORECASE)):
        try:
            r = Renewal.objects.select_related("worker").get(req_no__iexact=req)
            parts.append(f"RENEWAL LOOKUP {r.req_no}: worker={r.worker.worker_name} ({r.worker.reg_no}), "
                         f"period {r.period_from} to {r.period_to}, status={r.status}, remarks={r.remarks or 'none'}")
        except Renewal.DoesNotExist:
            parts.append(f"RENEWAL LOOKUP {req}: not found.")

    # Change request numbers (KPC-YYYY-NNNNN)
    for req in set(re.findall(r"KPC-\d{4}-\d{3,6}", message, re.IGNORECASE)):
        try:
            c = ChangeRequest.objects.select_related("worker").get(req_no__iexact=req)
            parts.append(f"CHANGE REQUEST LOOKUP {c.req_no}: worker={c.worker.worker_name} ({c.worker.reg_no}), "
                         f"type={c.get_request_type_display()}, '{c.old_value}' -> '{c.new_value}', "
                         f"status={c.status}, remarks={c.remarks or 'none'}")
        except ChangeRequest.DoesNotExist:
            parts.append(f"CHANGE REQUEST LOOKUP {req}: not found.")

    # DBT batch numbers (DBT-YYYY-NNN)
    for bno in set(re.findall(r"DBT-\d{4}-\d{2,4}", message, re.IGNORECASE)):
        try:
            b = DBTBatch.objects.get(batch_no__iexact=bno)
            pays = "; ".join(f"{p.application.app_no} ₹{p.amount} [{p.status}]" for p in b.payments.all()[:15])
            parts.append(f"DBT BATCH LOOKUP {b.batch_no}: status={b.status}, payments: {pays}")
        except DBTBatch.DoesNotExist:
            parts.append(f"DBT BATCH LOOKUP {bno}: not found.")

    # Establishment numbers (EST-YYYY-NNNNN) or asking about employers
    for eno in set(re.findall(r"EST-\d{4}-\d{3,6}", message, re.IGNORECASE)):
        try:
            e = Establishment.objects.get(est_no__iexact=eno)
            parts.append(f"ESTABLISHMENT LOOKUP {e.est_no}: {e.name}, owner={e.employer_name}, "
                         f"category={e.get_category_display()}, declared workers={e.est_workers_count}, "
                         f"cess paid=₹{e.cess_paid}, valid until {e.valid_until}, "
                         f"registered workers linked: {e.workers.count()}")
        except Establishment.DoesNotExist:
            parts.append(f"ESTABLISHMENT LOOKUP {eno}: not found.")

    # Conversational list intents for the Tracking Center
    msg_l = message.lower()
    if any(k in msg_l for k in ["pending application", "all application", "applications pending",
                                "show applications", "list applications", "open applications"]):
        rows = Application.objects.select_related("worker", "subscheme").filter(
            status__in=["SUBMITTED", "UNDER_REVIEW"])[:15]
        listing = "; ".join(f"{a.app_no} {a.worker.worker_name} — {a.subscheme.description} [{a.status}]"
                            for a in rows) or "none"
        parts.append(f"PENDING APPLICATIONS LIST: {listing}")
    if "failed" in msg_l and ("payment" in msg_l or "dbt" in msg_l or "transaction" in msg_l):
        rows = DBTPayment.objects.select_related("application__worker").filter(status="FAILED")[:15]
        listing = "; ".join(f"{p.application.app_no} ({p.application.worker.worker_name}) ₹{p.amount} — {p.failure_reason}"
                            for p in rows) or "none"
        parts.append(f"FAILED DBT PAYMENTS: {listing}. Failed payments can be retried in a new batch by the admin.")
    if "expired" in msg_l or "renewal due" in msg_l or "due for renewal" in msg_l:
        rows = Worker.objects.filter(valid_until__lt=date.today(), is_test_row=False)[:15]
        listing = "; ".join(f"{w.reg_no} {w.worker_name} (expired {w.valid_until})" for w in rows) or "none"
        parts.append(f"EXPIRED REGISTRATIONS (renewal due): {Worker.objects.filter(valid_until__lt=date.today()).count()} total. Examples: {listing}")
    if any(k in msg_l for k in ["pending renewal", "renewals pending", "renewal requests", "pending change", "change requests"]):
        rens = "; ".join(f"{r.req_no} {r.worker.worker_name} [{r.status}]"
                         for r in Renewal.objects.select_related("worker")[:10]) or "none"
        chgs = "; ".join(f"{c.req_no} {c.worker.worker_name} {c.get_request_type_display()} [{c.status}]"
                         for c in ChangeRequest.objects.select_related("worker")[:10]) or "none"
        parts.append(f"RENEWAL REQUESTS: {rens}. CHANGE REQUESTS: {chgs}")

    # Task specification injection: when a scheme is mentioned, provide its full spec
    msg_lower = message.lower()
    mentioned = set()
    for sch in Scheme.objects.all():
        words = [w for w in sch.description.lower().split() if len(w) > 4]
        if any(w in msg_lower for w in words):
            mentioned.add(sch.pk)
    for sch in Scheme.objects.filter(pk__in=list(mentioned)[:3]):
        docs = []
        for ss in sch.subschemes.all():
            docs.append(f"[{ss.description}] " + "; ".join(ss.required_list()[:25]))
        parts.append(
            f"SCHEME SPECIFICATION — {sch.description}:\n"
            f"Eligibility: {sch.eligibility}\n"
            f"Procedure: {sch.procedure}\n"
            f"Benefit amount: {sch.benefit_amount}\n"
            f"Documents by sub-scheme: " + " | ".join(docs)
        )
    # Sub-scheme direct mention (documents)
    for ss in SubScheme.objects.select_related("scheme"):
        if ss.description.lower() in msg_lower and ss.scheme_id not in mentioned:
            parts.append(f"REQUIRED FOR '{ss.scheme.description} / {ss.description}': "
                         + "; ".join(ss.required_list()[:40]))

    return "\n\n".join(parts)


@csrf_exempt
def chat_api(request):
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return JsonResponse({"error": "Server is missing the GEMINI_API_KEY secret."}, status=500)

    try:
        body = json.loads(request.body or "{}")
        messages = body.get("messages") or []
        if not isinstance(messages, list) or not messages:
            return JsonResponse({"error": "No messages provided."}, status=400)

        last_user_msg = next((m.get("content", "") for m in reversed(messages)
                              if m.get("role") == "user"), "")
        system = BASE_PROMPT + "\n\n" + build_context(str(last_user_msg))

        contents = [{"role": "model" if m.get("role") == "assistant" else "user",
                     "parts": [{"text": str(m.get("content", ""))}]} for m in messages]

        r = requests.post(
            f"{GEMINI_URL}?key={api_key}",
            json={"systemInstruction": {"parts": [{"text": system}]},
                  "contents": contents,
                  "generationConfig": {"maxOutputTokens": 900}},
            timeout=60,
        )
        data = r.json()
        if "error" in data:
            return JsonResponse({"error": data["error"].get("message", "AI provider error.")}, status=502)

        parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        reply = "".join(p.get("text", "") for p in parts).strip()
        if not reply:
            return JsonResponse({"error": "Empty response from AI. Try again."}, status=502)
        return JsonResponse({"reply": reply})

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid request body."}, status=400)
    except requests.RequestException:
        return JsonResponse({"error": "Could not reach the AI provider."}, status=502)
    except Exception:
        return JsonResponse({"error": "Server error. Try again."}, status=500)




def track(request):
    """Cherry Tracking Center — every application, renewal, change request and
    DBT payment in one place, with Cherry embedded for conversational tracking."""
    applications = (Application.objects
                    .select_related("worker", "subscheme__scheme")
                    .prefetch_related("payments__batch")[:50])
    renewals = Renewal.objects.select_related("worker")[:50]
    changes = ChangeRequest.objects.select_related("worker")[:50]
    payments = DBTPayment.objects.select_related("application__worker", "batch")[:50]
    chips = {
        "apps_pending": Application.objects.filter(status__in=["SUBMITTED", "UNDER_REVIEW"]).count(),
        "apps_approved": Application.objects.filter(status="APPROVED").count(),
        "renewals_pending": Renewal.objects.filter(status="SUBMITTED").count(),
        "changes_pending": ChangeRequest.objects.filter(status="SUBMITTED").count(),
        "pay_failed": DBTPayment.objects.filter(status="FAILED").count(),
        "pay_success": DBTPayment.objects.filter(status="SUCCESS").count(),
        "expired": Worker.objects.filter(valid_until__lt=date.today()).count(),
    }
    return render(request, "portal/track.html",
                  {"applications": applications, "renewals": renewals,
                   "changes": changes, "payments": payments, "chips": chips})




