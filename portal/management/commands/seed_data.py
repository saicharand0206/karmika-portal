"""Load the cleaned CSVs into the database and create demo content.

Run with:  python manage.py seed_data
Safe to run repeatedly (skips rows that already exist).
"""
import csv
import random
from datetime import datetime
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from portal.models import Worker, Scheme, SubScheme, Application

DATA = Path(__file__).resolve().parents[3] / "data"


def parse_date(s):
    if not s or s == "":
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_bool(s):
    return str(s).strip().lower() in ("true", "1")


class Command(BaseCommand):
    help = "Seed the database from the cleaned CSV files"

    def handle(self, *args, **options):
        # ---- Schemes ----
        with open(DATA / "schemes_clean.csv", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                Scheme.objects.get_or_create(
                    code=int(row["scheme_code"]),
                    defaults={"description": row["scheme_desc"].strip(),
                              "scheme_type": row["scheme_type"].strip() or "WELFARE"},
                )
        self.stdout.write(f"Schemes: {Scheme.objects.count()}")

        # ---- SubSchemes ----
        # NOTE (data quality): the source sheet's sub-schemes reference scheme
        # codes 5,6,7,8,10,11,15 that are absent from the main scheme list.
        # We create those parents with names inferred from their first sub-scheme.
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
                                  "scheme_type": "WELFARE (name inferred)"},
                    )
                SubScheme.objects.get_or_create(
                    scheme=scheme, code=int(row["subscheme_code"]),
                    defaults={"description": row["subscheme_desc"].strip(),
                              "required_fields": row["form_fields"].strip()},
                )
        self.stdout.write(f"SubSchemes: {SubScheme.objects.count()}")

        # ---- Workers ----
        with open(DATA / "workers_clean.csv", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                age = row["age"]
                Worker.objects.get_or_create(
                    reg_no=row["reg_no"].strip(),
                    defaults=dict(
                        temp_id=row["temp_id"].split(".")[0],
                        alo_code=row["alo_code"],
                        reg_year=int(float(row["reg_year"])),
                        reg_date=parse_date(row["reg_date"]),
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
                    ),
                )
        self.stdout.write(f"Workers: {Worker.objects.count()}")

        # ---- Demo applications (only if none exist yet) ----
        if Application.objects.count() == 0:
            random.seed(42)
            workers = list(Worker.objects.filter(is_test_row=False)[:15])
            subs = list(SubScheme.objects.all())
            statuses = ["SUBMITTED", "UNDER_REVIEW", "APPROVED", "APPROVED", "REJECTED"]
            for i, w in enumerate(workers, start=1):
                sub = random.choice(subs)
                Application.objects.create(
                    app_no=f"KPA-2026-{i:05d}",
                    worker=w,
                    subscheme=sub,
                    applicant_name=w.worker_name,
                    relationship="Self",
                    status=random.choice(statuses),
                    remarks="Demo record seeded for dashboard",
                )
            self.stdout.write(f"Applications: {Application.objects.count()} demo records created")

        # ---- Admin user for /admin/ ----
        User = get_user_model()
        if not User.objects.filter(username="admin").exists():
            User.objects.create_superuser("admin", "admin@example.com", "karmika123")
            self.stdout.write("Admin user created: admin / karmika123 (change this!)")

        self.stdout.write(self.style.SUCCESS("Seeding complete."))
