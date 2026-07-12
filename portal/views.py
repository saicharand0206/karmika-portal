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

from .models import Worker, Scheme, SubScheme, Application

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/"
    "models/gemini-2.5-flash:generateContent"
)


# ---------------------------------------------------------------- pages
def home(request):
    stats = {
        "workers": Worker.objects.count(),
        "schemes": Scheme.objects.count(),
        "subschemes": SubScheme.objects.count(),
        "applications": Application.objects.count(),
        "approved": Application.objects.filter(status="APPROVED").count(),
    }
    return render(request, "portal/home.html", {"stats": stats})


def register(request):
    if request.method == "POST":
        name = request.POST.get("worker_name", "").strip()
        if not name:
            return render(request, "portal/register.html", {"error": "Worker name is required."})
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
        worker.save()
        return render(request, "portal/register_success.html", {"worker": worker})
    return render(request, "portal/register.html")


def workers_list(request):
    q = request.GET.get("q", "").strip()
    qs = Worker.objects.all()
    if q:
        qs = qs.filter(worker_name__icontains=q) | qs.filter(reg_no__icontains=q)
    return render(request, "portal/workers.html", {"workers": qs[:100], "q": q, "total": qs.count()})


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
    app_no = request.GET.get("app_no", "").strip()
    application = None
    error = None
    if app_no:
        try:
            application = Application.objects.select_related("worker", "subscheme__scheme").get(app_no__iexact=app_no)
        except Application.DoesNotExist:
            error = f"No application found with number '{app_no}'."
    return render(request, "portal/status.html", {"a": application, "app_no": app_no, "error": error})


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

    quality = {
        "missing_dob": Worker.objects.filter(date_of_birth=None).count(),
        "invalid_ifsc": Worker.objects.exclude(ifsc_code="").filter(ifsc_valid=False).count(),
        "test_rows": Worker.objects.filter(is_test_row=True).count(),
    }
    chart_data = {
        "by_year": by_year, "by_gender": by_gender, "by_trade": by_trade,
        "age_buckets": buckets, "app_status": app_status, "app_scheme": app_scheme,
    }
    return render(request, "portal/dashboard.html",
                  {"chart_data": json.dumps(chart_data), "quality": quality,
                   "totals": {"workers": Worker.objects.count(),
                              "applications": Application.objects.count()}})


# ---------------------------------------------------------------- Cherry
BASE_PROMPT = """You are Cherry, the AI assistant of the Karmika Portal — an ACADEMIC DEMO
web application (not a real government website) for construction worker welfare,
built by a student. You help visitors use the portal.

You can help with:
- Explaining the welfare schemes and their required documents (from the catalogue below)
- Looking up worker registrations and application statuses (lookup results are injected below when found)
- Guiding users: Register at /register/, browse or search workers at /workers/, view schemes at /schemes/,
  apply for a benefit at /apply/, check application status at /status/, see analytics at /dashboard/
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
        f"{Application.objects.filter(status='REJECTED').count()} rejected)."
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
            parts.append(
                f"WORKER LOOKUP {w.reg_no}: name={w.worker_name}, father={w.father_name}, "
                f"gender={w.gender}, age={w.age}, registered={w.reg_year}, "
                f"district_code={w.district_code}, applications: {apps}"
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
                f"submitted={a.submitted_at:%d %b %Y}, remarks={a.remarks or 'none'}"
            )
        except Application.DoesNotExist:
            parts.append(f"APPLICATION LOOKUP {app_no}: not found in database.")

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
