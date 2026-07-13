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
        "workers": Worker.objects.count(),
        "schemes": Scheme.objects.count(),
        "subschemes": SubScheme.objects.count(),
        "applications": Application.objects.count(),
        "approved": Application.objects.filter(status="APPROVED").count(),
        "establishments": Establishment.objects.count(),
    }
    return render(request, "portal/home.html", {"stats": stats})


def register(request):
    if request.method == "POST":
        name = request.POST.get("worker_name", "").strip()
        if not name:
            return render(request, "portal/register.html",
                          {"error": "Worker name is required.",
                           "villages": Village.objects.select_related("mandal__district").all(),
                           "establishments": Establishment.objects.all()})
        year = date.today().year
        serial = Worker.objects.filter(reg_year=year).count() + 1
        reg_no = f"KP/{year}/{serial:05d}"
        # Guard against collisions if rows were deleted
        while Worker.objects.filter(reg_no=reg_no).exists():
            serial += 1
            reg_no = f"KP/{year}/{serial:05d}"

        age = request.POST.get("age") or None
        worker = Worker.objects.create(
            reg_no=reg_no,
            reg_year=year,
            reg_date=date.today(),
            worker_name=name.title(),
            father_name=request.POST.get("father_name", "").strip().title(),
            gender=request.POST.get("gender", "Unknown"),
            age=int(age) if age else None,
            ifsc_code=request.POST.get("ifsc_code", "").strip().upper(),
            trade_code=request.POST.get("trade_code", "").strip(),
            district_code=request.POST.get("district_code", "").strip(),
            migrant_worker=request.POST.get("migrant_worker") == "on",
            trade_union_member=request.POST.get("trade_union_member") == "on",
        )
        worker.ifsc_valid = bool(re.fullmatch(r"[A-Z]{4}0[A-Z0-9]{6}", worker.ifsc_code or ""))
        worker.age_flag = bool(worker.age and (worker.age < 18 or worker.age > 60))
        worker.valid_until = add_years(date.today(), 5)
        village_id = request.POST.get("village")
        if village_id:
            worker.village = Village.objects.filter(pk=village_id).first()
            if worker.village:
                worker.district_code = worker.village.mandal.district.code
        worker.save()
        est_id = request.POST.get("establishment")
        if est_id:
            worker.employer = Establishment.objects.filter(pk=est_id).first()
            worker.save(update_fields=["employer"])
        nominee_name = request.POST.get("nominee_name", "").strip()
        if nominee_name:
            Nominee.objects.create(worker=worker, name=nominee_name.title(),
                                   relationship=request.POST.get("nominee_relationship", "Nominee").strip() or "Nominee",
                                   is_primary=True)
        return render(request, "portal/register_success.html", {"worker": worker})
    return render(request, "portal/register.html",
                  {"villages": Village.objects.select_related("mandal__district").all(),
                   "establishments": Establishment.objects.all()})


def workers_list(request):
    q = request.GET.get("q", "").strip()
    expired = request.GET.get("expired") == "1"
    qs = Worker.objects.select_related("employer", "village").all()
    if q:
        qs = qs.filter(worker_name__icontains=q) | qs.filter(reg_no__icontains=q)
    if expired:
        qs = qs.filter(valid_until__lt=date.today())
    return render(request, "portal/workers.html",
                  {"workers": qs[:100], "q": q, "total": qs.count(), "expired": expired})


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


def apply(request):
    subschemes = SubScheme.objects.select_related("scheme").all()
    if request.method == "POST":
        reg_no = request.POST.get("reg_no", "").strip()
        sub_id = request.POST.get("subscheme")
        try:
            worker = Worker.objects.get(reg_no__iexact=reg_no)
        except Worker.DoesNotExist:
            return render(request, "portal/apply.html",
                          {"subschemes": subschemes, "error": f"No worker registered with number '{reg_no}'. Register first."})
        try:
            sub = SubScheme.objects.get(pk=sub_id)
        except (SubScheme.DoesNotExist, ValueError):
            return render(request, "portal/apply.html",
                          {"subschemes": subschemes, "error": "Please choose a valid scheme."})

        serial = Application.objects.count() + 1
        app_no = f"KPA-{date.today().year}-{serial:05d}"
        while Application.objects.filter(app_no=app_no).exists():
            serial += 1
            app_no = f"KPA-{date.today().year}-{serial:05d}"

        application = Application.objects.create(
            app_no=app_no,
            worker=worker,
            subscheme=sub,
            applicant_name=request.POST.get("applicant_name", worker.worker_name).strip().title(),
            relationship=request.POST.get("relationship", "").strip(),
            phone=request.POST.get("phone", "").strip(),
            bank_account=request.POST.get("bank_account", "").strip(),
            details=request.POST.get("details", "").strip(),
        )
        return render(request, "portal/apply_success.html", {"a": application})
    return render(request, "portal/apply.html", {"subschemes": subschemes})


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
BASE_PROMPT = """You are Cherry, the AI assistant of the Karmika Portal — an ACADEMIC DEMO
web application (not a real government website) for construction worker welfare,
built by a student. You help visitors use the portal.

You can help with:\n- Establishments/employers register at /register-establishment/ and are listed at /establishments/ (they pay cess that funds the schemes)
- Explaining the welfare schemes and their required documents (from the catalogue below)
- Looking up worker registrations and application statuses (lookup results are injected below when found)
- Guiding users: Register at /register/, browse or search workers at /workers/, view schemes at /schemes/,
  apply for a benefit at /apply/, check application status at /status/, renew a 5-year registration at /renew/,
  request name/nominee/bank corrections at /change-request/, track EVERYTHING at /track/ (the Tracking Center),
  see analytics at /dashboard/
- Explaining DBT (Direct Benefit Transfer) payments, batches, and failed-transaction retries
- Registrations are valid for 5 YEARS and must be renewed; expired workers should file a renewal at /renew/
- Employers register establishments at /register-establishment/ and browse them at /establishments/
- Workers can download a printable registration card from their worker page
- Answering general questions about the portal's live statistics (below)

Rules: be warm and concise. Use short paragraphs. If a lookup result is provided below, answer from it
precisely. If the user asks for a registration or application number you don't see data for, ask them
to share the exact number. Remind users this is a demo when they ask about real government benefits,
and suggest the official board for real claims. Never invent worker data."""


def build_context(message):
    """Gather live DB context so Cherry can answer about this portal's actual data."""
    parts = []

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

    # If the user asks about required documents for a scheme, inject them
    msg_lower = message.lower()
    for ss in SubScheme.objects.select_related("scheme"):
        if ss.description.lower() in msg_lower or (
            ss.scheme.description.lower() in msg_lower and ("document" in msg_lower or "required" in msg_lower or "need" in msg_lower)
        ):
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


# ---------------------------------------------------------------- phase 2 pages
def renew(request):
    """5-year registration renewal request."""
    error = success = None
    if request.method == "POST":
        reg_no = request.POST.get("reg_no", "").strip()
        try:
            worker = Worker.objects.get(reg_no__iexact=reg_no)
        except Worker.DoesNotExist:
            error = f"No worker registered with number '{reg_no}'."
        else:
            if worker.renewals.filter(status="SUBMITTED").exists():
                error = f"{worker.reg_no} already has a renewal pending review."
            else:
                pf = worker.valid_until or date.today()
                serial = Renewal.objects.count() + 1
                req_no = f"KPR-{date.today().year}-{serial:05d}"
                while Renewal.objects.filter(req_no=req_no).exists():
                    serial += 1
                    req_no = f"KPR-{date.today().year}-{serial:05d}"
                r = Renewal.objects.create(req_no=req_no, worker=worker,
                                           period_from=pf, period_to=add_years(pf, 5))
                success = r
    return render(request, "portal/renew.html", {"error": error, "success": success})


def change_request(request):
    """Name / nominee / bank-detail correction requests."""
    error = success = None
    if request.method == "POST":
        reg_no = request.POST.get("reg_no", "").strip()
        req_type = request.POST.get("request_type", "NAME_CHANGE")
        new_value = request.POST.get("new_value", "").strip()
        try:
            worker = Worker.objects.get(reg_no__iexact=reg_no)
        except Worker.DoesNotExist:
            error = f"No worker registered with number '{reg_no}'."
        else:
            if not new_value:
                error = "Please enter the corrected value."
            else:
                old = ""
                if req_type == "NAME_CHANGE":
                    old = worker.worker_name
                elif req_type == "BANK_CHANGE":
                    old = worker.ifsc_code
                elif req_type == "NOMINEE_CHANGE":
                    nom = worker.nominees.filter(is_primary=True).first()
                    old = nom.name if nom else ""
                serial = ChangeRequest.objects.count() + 1
                req_no = f"KPC-{date.today().year}-{serial:05d}"
                while ChangeRequest.objects.filter(req_no=req_no).exists():
                    serial += 1
                    req_no = f"KPC-{date.today().year}-{serial:05d}"
                success = ChangeRequest.objects.create(
                    req_no=req_no, worker=worker, request_type=req_type,
                    old_value=old, new_value=new_value)
    return render(request, "portal/change_request.html", {"error": error, "success": success})


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


def establishment_detail(request, est_no):
    try:
        est = Establishment.objects.select_related("village__mandal__district").get(est_no__iexact=est_no)
    except Establishment.DoesNotExist:
        return render(request, "portal/establishments.html",
                      {"establishments": [], "q": est_no, "total": 0,
                       "error": f"No establishment found with number {est_no}."})
    return render(request, "portal/establishment_detail.html",
                  {"e": est, "workers": est.workers.all()[:100]})


# ---------------------------------------------------------------- polish features
def worker_card(request, reg_no):
    """Printable registration card for a worker."""
    try:
        worker = Worker.objects.select_related("village__mandal__district", "alo_circle").get(reg_no=reg_no)
    except Worker.DoesNotExist:
        return redirect("workers")
    nominee = worker.nominees.filter(is_primary=True).first()
    return render(request, "portal/worker_card.html", {"w": worker, "nominee": nominee})


def workers_export(request):
    """Download the worker register as CSV."""
    import csv as _csv
    from django.http import HttpResponse
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="karmika_workers.csv"'
    writer = _csv.writer(response)
    writer.writerow(["reg_no", "worker_name", "father_name", "gender", "age", "reg_year",
                     "valid_until", "village", "alo_circle", "employer",
                     "migrant_worker", "ifsc_code", "ifsc_valid"])
    for w in Worker.objects.select_related("village", "alo_circle", "employer").all():
        writer.writerow([w.reg_no, w.worker_name, w.father_name, w.gender, w.age, w.reg_year,
                         w.valid_until, w.village or "", w.alo_circle or "", w.employer or "",
                         w.migrant_worker, w.ifsc_code, w.ifsc_valid])
    return response


# ---------------------------------------------------------------- establishments
def establishments_list(request):
    q = request.GET.get("q", "").strip()
    qs = Establishment.objects.select_related("village__mandal__district").all()
    if q:
        qs = qs.filter(name__icontains=q) | qs.filter(est_no__icontains=q) | qs.filter(employer_name__icontains=q)
    return render(request, "portal/establishments.html",
                  {"establishments": qs[:100], "q": q, "total": qs.count()})


def register_establishment(request):
    villages = Village.objects.select_related("mandal__district").all()
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        employer_name = request.POST.get("employer_name", "").strip()
        if not name or not employer_name:
            return render(request, "portal/register_establishment.html",
                          {"villages": villages, "error": "Establishment name and employer name are required."})
        serial = Establishment.objects.count() + 1
        est_no = f"EST-{date.today().year}-{serial:05d}"
        while Establishment.objects.filter(est_no=est_no).exists():
            serial += 1
            est_no = f"EST-{date.today().year}-{serial:05d}"
        workers_count = request.POST.get("est_workers_count") or 0
        cess = request.POST.get("cess_paid") or 0
        est = Establishment.objects.create(
            est_no=est_no, name=name.title(), employer_name=employer_name.title(),
            category=request.POST.get("category", "CONTRACTOR"),
            phone=request.POST.get("phone", "").strip(),
            address=request.POST.get("address", "").strip(),
            village=Village.objects.filter(pk=request.POST.get("village")).first(),
            est_workers_count=int(workers_count),
            cess_paid=float(cess),
            valid_until=add_years(date.today(), 5),
        )
        return render(request, "portal/register_establishment.html",
                      {"villages": villages, "success": est})
    return render(request, "portal/register_establishment.html", {"villages": villages})
