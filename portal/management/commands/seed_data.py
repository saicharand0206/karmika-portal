"""Load cleaned CSVs + phase-2 demo data. Safe to run repeatedly.

Seeds: master tables (districts/mandals/villages/ALO circles), workers with
5-year validity, nominees, schemes/sub-schemes, demo applications, renewals,
change requests, and DBT batches/payments (including failed transactions).
"""
import csv
import random
from datetime import date, datetime, timedelta
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from portal.models import (Worker, Scheme, SubScheme, Application, District,
                           Mandal, Village, ALOCircle, Nominee, Renewal,
                           ChangeRequest, DBTBatch, DBTPayment, Establishment)

DATA = Path(__file__).resolve().parents[3] / "data"

SCHEME_SPECS = {
    1: ("Nominee or legal heir of a registered worker whose death occurred due to an accident, with the registration active on the date of the accident.",
        "The nominee submits the claim form with the FIR copy, post-mortem report, death certificate and bank passbook at the ALO office. After the ALO enquiry and approval, the amount is credited through DBT.",
        "Rs. 6,00,000 including funeral expenses (sample value)"),
    2: ("Registered worker who suffered a permanent partial or total disability due to an accident, certified by the medical board.",
        "The worker submits the disability certificate and the medical records at the ALO office. The sanction is given based on the percentage of disability after verification.",
        "Up to Rs. 5,00,000 based on disability percentage (sample value)"),
    3: ("Nominee or legal heir of a registered worker whose death occurred due to natural causes.",
        "The nominee submits the death certificate, the registration card of the worker and the bank passbook at the ALO office. The amount is credited after verification.",
        "Rs. 1,00,000 including funeral expenses (sample value)"),
    4: ("Registered woman worker, or the wife of a registered worker, limited to the first two deliveries.",
        "The claim is submitted with the discharge summary, the birth certificate and the bank passbook within the prescribed time after the delivery.",
        "Rs. 30,000 per delivery (sample value)"),
    9: ("Registered worker or the children of a registered worker, as a one-time marriage gift.",
        "The claim is submitted with the marriage certificate, the age proofs and the bank passbook at the ALO office after the marriage.",
        "Rs. 25,000 one-time (sample value)"),
    12: ("Registered worker facing distress due to a major illness or a natural calamity.",
        "The application is submitted with the supporting proofs of the distress and the medical records, and the relief is sanctioned after the ALO enquiry.",
        "Up to Rs. 20,000 (sample value)"),
    13: ("Registered worker who lost a limb in an accident and requires an artificial limb.",
        "The application is submitted with the medical recommendation. The artificial limb is provided through the empanelled agency after approval.",
        "Cost of the artificial limb (sample value)"),
}
GENERIC_SPEC = (
    "Registered construction workers and their dependents, as applicable to the scheme.",
    "The application is submitted at the ALO office with the required documents, and the benefit is provided after verification and approval.",
    "As per the scheme norms (sample value)")



MASTER = {
    "Hyderabad": {"Amberpet": ["Amberpet", "Golnaka"], "Musheerabad": ["Musheerabad", "Bholakpur"]},
    "Medchal-Malkajgiri": {"Uppal": ["Uppal Kalan", "Peerzadiguda"], "Kapra": ["Kapra", "Cherlapally"]},
    "Rangareddy": {"Serilingampally": ["Gachibowli", "Nallagandla"], "Ibrahimpatnam": ["Ibrahimpatnam", "Dandumailaram"]},
    "Warangal": {"Hanamkonda": ["Hanamkonda", "Kazipet"]},
    "Karimnagar": {"Huzurabad": ["Huzurabad", "Jammikunta"]},
}


def parse_date(s):
    if not s:
        return None
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_bool(s):
    return str(s).strip().lower() in ("true", "1")


def add_years(d, years):
    try:
        return d.replace(year=d.year + years)
    except ValueError:  # Feb 29
        return d.replace(year=d.year + years, day=28)


class Command(BaseCommand):
    help = "Seed the database from cleaned CSVs + demo transactions"

    def handle(self, *args, **options):
        random.seed(42)

        # ---- Master tables ----
        dcode = 0
        for dname, mandals in MASTER.items():
            dcode += 1
            district, _ = District.objects.get_or_create(code=str(dcode), defaults={"name": dname})
            mcode = 0
            for mname, villages in mandals.items():
                mcode += 1
                mandal, _ = Mandal.objects.get_or_create(district=district, code=str(mcode),
                                                         defaults={"name": mname})
                for vi, vname in enumerate(villages, 1):
                    Village.objects.get_or_create(mandal=mandal, code=str(vi),
                                                  defaults={"name": vname})
        self.stdout.write(f"Master: {District.objects.count()} districts, "
                          f"{Mandal.objects.count()} mandals, {Village.objects.count()} villages")

        # ---- Schemes ----
        with open(DATA / "schemes_clean.csv", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                Scheme.objects.get_or_create(
                    code=int(row["scheme_code"]),
                    defaults={"description": row["scheme_desc"].strip(),
                              "scheme_type": row["scheme_type"].strip() or "WELFARE"})

        # ---- SubSchemes (some parents are absent in the source; create inferred) ----
        inferred_names = {
            5: "Recognition of Prior Learning (RPL) Training",
            6: "Residential Skill Upgradation Training",
            7: "Assistance for Women Dependents",
            8: "Assistance for Unemployed Youth Dependents",
            10: "Setwin Training for Workers/Dependents",
            11: "Setwin Offline Training",
            15: "APPC Skill Training & Upgradation",
        }
        with open(DATA / "subschemes_clean.csv", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                code = int(row["scheme_code"])
                scheme = Scheme.objects.filter(code=code).first()
                if not scheme:
                    scheme, _ = Scheme.objects.get_or_create(
                        code=code,
                        defaults={"description": inferred_names.get(code, row["subscheme_desc"].strip()),
                                  "scheme_type": "WELFARE (name inferred)"})
                SubScheme.objects.get_or_create(
                    scheme=scheme, code=int(row["subscheme_code"]),
                    defaults={"description": row["subscheme_desc"].strip(),
                              "required_fields": row["form_fields"].strip()})
        self.stdout.write(f"Schemes: {Scheme.objects.count()} / SubSchemes: {SubScheme.objects.count()}")

        # ---- Task-oriented specifications for every scheme ----
        for scheme in Scheme.objects.all():
            elig, proc, amount = SCHEME_SPECS.get(scheme.code, GENERIC_SPEC)
            if not scheme.eligibility:
                scheme.eligibility = elig
                scheme.procedure = proc
                scheme.benefit_amount = amount
                scheme.save(update_fields=["eligibility", "procedure", "benefit_amount"])
        self.stdout.write("Scheme specifications filled")

        # ---- Workers ----
        villages = list(Village.objects.all())
        with open(DATA / "workers_clean.csv", encoding="utf-8") as f:
            for i, row in enumerate(csv.DictReader(f)):
                age = row["age"]
                alo_code = (row["alo_code"] or "").strip() or "ALO-GEN"
                circle, _ = ALOCircle.objects.get_or_create(
                    code=alo_code, defaults={"name": f"Circle {alo_code}",
                                             "district": villages[i % len(villages)].mandal.district})
                reg_date = parse_date(row["reg_date"])
                reg_year = int(float(row["reg_year"]))
                base = reg_date or date(reg_year, 12, 31)
                Worker.objects.get_or_create(
                    reg_no=row["reg_no"].strip(),
                    defaults=dict(
                        temp_id=row["temp_id"].split(".")[0],
                        alo_code=alo_code,
                        alo_circle=circle,
                        reg_year=reg_year,
                        reg_date=reg_date,
                        valid_until=add_years(base, 5),
                        village=villages[i % len(villages)],
                        worker_name=(row["worker_name"] or "Unknown").strip(),
                        father_name=(row["father_name"] or "").strip(),
                        worker_name_telugu=row["worker_name_telugu"] or "",
                        father_name_telugu=row["father_name_telugu"] or "",
                        gender=row["gender"] or "Unknown",
                        date_of_birth=parse_date(row["date_of_birth"]),
                        age=int(float(age)) if age else None,
                        caste_code=str(row["caste_code"]).split(".")[0],
                        bank_code=str(row["bank_code"]).split(".")[0] if row["bank_code"] else "",
                        ifsc_code=row["ifsc_code"] or "",
                        ifsc_valid=parse_bool(row["ifsc_valid"]),
                        trade_union_member=parse_bool(row["trade_union_member"]),
                        migrant_worker=parse_bool(row["migrant_worker"]),
                        trade_code=str(row["trade_code"]).split(".")[0],
                        district_code=str(row["district_code"]).split(".")[0] if row["district_code"] else "",
                        is_test_row=parse_bool(row["is_test_row"]),
                        age_flag=parse_bool(row["age_flag"]),
                    ))
        self.stdout.write(f"Workers: {Worker.objects.count()}")

        real_workers = list(Worker.objects.filter(is_test_row=False))

        # ---- Nominees ----
        if Nominee.objects.count() == 0:
            first_names = ["Lakshmi", "Saraswati", "Padma", "Anitha", "Ramesh",
                           "Suresh", "Venkat", "Divya", "Kavitha", "Ravi"]
            rels = ["Wife", "Wife", "Son", "Daughter", "Wife", "Husband"]
            for i, w in enumerate(real_workers[:20]):
                Nominee.objects.create(worker=w, name=first_names[i % len(first_names)],
                                       relationship=rels[i % len(rels)],
                                       age=random.randint(18, 50), is_primary=True)
            self.stdout.write(f"Nominees: {Nominee.objects.count()}")

        # ---- Demo applications ----
        if Application.objects.count() == 0:
            subs = list(SubScheme.objects.all())
            statuses = ["SUBMITTED", "UNDER_REVIEW", "APPROVED", "APPROVED", "REJECTED"]
            for i, w in enumerate(real_workers[:15], start=1):
                Application.objects.create(
                    app_no=f"KPA-2026-{i:05d}", worker=w, subscheme=random.choice(subs),
                    applicant_name=w.worker_name, relationship="Self",
                    status=random.choice(statuses), remarks="Demo record seeded for dashboard")
            self.stdout.write(f"Applications: {Application.objects.count()}")

        # ---- Renewals ----
        if Renewal.objects.count() == 0:
            for i, w in enumerate(real_workers[:3], start=1):
                pf = w.valid_until or date.today()
                status = ["APPROVED", "SUBMITTED", "REJECTED"][i - 1]
                r = Renewal.objects.create(req_no=f"KPR-2026-{i:05d}", worker=w,
                                           period_from=pf, period_to=add_years(pf, 5),
                                           status=status,
                                           remarks="Demo renewal" if status != "REJECTED"
                                                   else "Challan copy missing")
                if status == "APPROVED":
                    w.valid_until = r.period_to
                    w.save(update_fields=["valid_until"])
            self.stdout.write(f"Renewals: {Renewal.objects.count()}")

        # ---- Change requests ----
        if ChangeRequest.objects.count() == 0:
            w1, w2, w3 = real_workers[3], real_workers[4], real_workers[5]
            ChangeRequest.objects.create(req_no="KPC-2026-00001", worker=w1,
                                         request_type="NAME_CHANGE", old_value=w1.worker_name,
                                         new_value=w1.worker_name, status="APPROVED",
                                         remarks="spelling correction | applied to worker record")
            ChangeRequest.objects.create(req_no="KPC-2026-00002", worker=w2,
                                         request_type="BANK_CHANGE", old_value=w2.ifsc_code,
                                         new_value="SBIN0004321", status="SUBMITTED")
            nom = w3.nominees.first()
            ChangeRequest.objects.create(req_no="KPC-2026-00003", worker=w3,
                                         request_type="NOMINEE_CHANGE",
                                         old_value=nom.name if nom else "",
                                         new_value="Updated Nominee", status="REJECTED",
                                         remarks="supporting document unclear")
            self.stdout.write(f"Change requests: {ChangeRequest.objects.count()}")

        # ---- DBT batches & payments ----
        if DBTBatch.objects.count() == 0:
            approved = list(Application.objects.filter(status="APPROVED"))
            b1 = DBTBatch.objects.create(batch_no="DBT-2026-001", status="PROCESSED")
            fail_reasons = ["Invalid IFSC code", "Account closed", "Name mismatch at bank"]
            failed_payments = []
            for i, app in enumerate(approved):
                amount = random.choice([15000, 25000, 30000, 50000, 100000])
                if i % 3 == 2:  # every third payment fails
                    p = DBTPayment.objects.create(batch=b1, application=app, amount=amount,
                                                  status="FAILED",
                                                  failure_reason=random.choice(fail_reasons))
                    failed_payments.append(p)
                else:
                    DBTPayment.objects.create(batch=b1, application=app, amount=amount,
                                              status="SUCCESS")
            if failed_payments:
                b2 = DBTBatch.objects.create(batch_no="DBT-2026-002", status="OPEN")
                for p in failed_payments:
                    DBTPayment.objects.create(batch=b2, application=p.application,
                                              amount=p.amount, status="PENDING", retry_of=p)
            self.stdout.write(f"DBT: {DBTBatch.objects.count()} batches, "
                              f"{DBTPayment.objects.count()} payments")

        # ---- Establishments (employer/organization side) ----
        if Establishment.objects.count() == 0:
            demo_ests = [
                ("Sri Venkateswara Constructions", "K. Prasad Rao", "CONTRACTOR", 45, 250000),
                ("Deccan Infra Developers", "M. Anitha Reddy", "DEVELOPER", 120, 780000),
                ("Bhagyanagar Builders", "S. Rajesh Kumar", "BUILDER", 60, 340000),
                ("Telangana Roads Project Unit-3", "Executive Engineer, R&B", "GOVT_PROJECT", 200, 1500000),
                ("Sai Teja Civil Works", "P. Naresh", "CONTRACTOR", 25, 90000),
            ]
            for i, (name, owner, cat, count, cess) in enumerate(demo_ests, start=1):
                Establishment.objects.create(
                    est_no=f"EST-2026-{i:05d}", name=name, employer_name=owner,
                    category=cat, est_workers_count=count, cess_paid=cess,
                    village=villages[i % len(villages)],
                    address=f"{villages[i % len(villages)]}, Telangana",
                    valid_until=add_years(date.today(), 5))
            ests = list(Establishment.objects.all())
            for i, w in enumerate(real_workers):
                if i % 2 == 0:  # link roughly half the workers to an employer
                    w.employer = ests[i % len(ests)]
                    w.save(update_fields=["employer"])
            self.stdout.write(f"Establishments: {Establishment.objects.count()} "
                              f"(employer linked for {Worker.objects.exclude(employer=None).count()} workers)")

        # ---- Admin user ----
        User = get_user_model()
        if not User.objects.filter(username="admin").exists():
            User.objects.create_superuser("admin", "admin@example.com", "karmika123")
            self.stdout.write("Admin user created: admin / karmika123 (change this!)")

        self.stdout.write(self.style.SUCCESS("Seeding complete."))
