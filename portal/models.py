"""Karmika Portal database schema.

Four tables mirror the real-world domain:

Worker       — one row per registered construction worker (from workers_clean.csv)
Scheme       — the 7 main welfare schemes (from schemes_clean.csv)
SubScheme    — 26 sub-categories, each with its required form fields/documents
Application  — a worker's claim for a sub-scheme benefit, with a status lifecycle

Relationships:
  Scheme 1--* SubScheme          (a scheme has many sub-categories)
  Worker 1--* Application        (a worker can file many claims)
  SubScheme 1--* Application     (a sub-scheme receives many claims)
"""
from django.db import models


class Worker(models.Model):
    GENDER_CHOICES = [("Male", "Male"), ("Female", "Female"), ("Others", "Others"), ("Unknown", "Unknown")]

    reg_no = models.CharField(max_length=40, unique=True)
    temp_id = models.CharField(max_length=20, blank=True)
    alo_code = models.CharField(max_length=10, blank=True)
    reg_year = models.IntegerField()
    reg_date = models.DateField(null=True, blank=True)
    worker_name = models.CharField(max_length=120)
    father_name = models.CharField(max_length=120, blank=True)
    worker_name_telugu = models.CharField(max_length=200, blank=True)
    father_name_telugu = models.CharField(max_length=200, blank=True)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, default="Unknown")
    date_of_birth = models.DateField(null=True, blank=True)
    age = models.IntegerField(null=True, blank=True)
    caste_code = models.CharField(max_length=10, blank=True)
    bank_code = models.CharField(max_length=20, blank=True)
    ifsc_code = models.CharField(max_length=20, blank=True)
    ifsc_valid = models.BooleanField(default=False)
    trade_union_member = models.BooleanField(default=False)
    migrant_worker = models.BooleanField(default=False)
    trade_code = models.CharField(max_length=10, blank=True)
    district_code = models.CharField(max_length=10, blank=True)
    # Data-quality flags from the cleaning pipeline
    is_test_row = models.BooleanField(default=False)
    age_flag = models.BooleanField(default=False)
    # Phase 2: 5-year registration validity + geographic/administrative links
    valid_until = models.DateField(null=True, blank=True,
                                   help_text="Registration valid for 5 years; extended by approved renewals")
    village = models.ForeignKey("Village", null=True, blank=True, on_delete=models.SET_NULL,
                                related_name="workers")
    alo_circle = models.ForeignKey("ALOCircle", null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="workers")
    employer = models.ForeignKey("Establishment", null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="workers")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-reg_year", "reg_no"]

    def __str__(self):
        return f"{self.reg_no} — {self.worker_name}"

    @property
    def is_expired(self):
        from datetime import date as _date
        return bool(self.valid_until and self.valid_until < _date.today())


class Scheme(models.Model):
    code = models.IntegerField(unique=True)
    description = models.CharField(max_length=200)
    scheme_type = models.CharField(max_length=40, default="WELFARE")

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code}. {self.description}"


class SubScheme(models.Model):
    scheme = models.ForeignKey(Scheme, on_delete=models.CASCADE, related_name="subschemes")
    code = models.IntegerField()
    description = models.CharField(max_length=200)
    required_fields = models.TextField(blank=True, help_text="Pipe-separated form fields & documents")

    class Meta:
        ordering = ["scheme__code", "code"]
        unique_together = [("scheme", "code")]

    def __str__(self):
        return f"{self.scheme.code}.{self.code} {self.description}"

    def required_list(self):
        return [x.strip() for x in self.required_fields.split("|") if x.strip()]


class Application(models.Model):
    STATUS_CHOICES = [
        ("SUBMITTED", "Submitted"),
        ("UNDER_REVIEW", "Under Review"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
    ]

    app_no = models.CharField(max_length=30, unique=True)
    worker = models.ForeignKey(Worker, on_delete=models.CASCADE, related_name="applications")
    subscheme = models.ForeignKey(SubScheme, on_delete=models.CASCADE, related_name="applications")
    applicant_name = models.CharField(max_length=120)
    relationship = models.CharField(max_length=60, blank=True, help_text="Relationship with the worker (Self/Wife/Son...)")
    phone = models.CharField(max_length=15, blank=True)
    bank_account = models.CharField(max_length=30, blank=True)
    details = models.TextField(blank=True)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default="SUBMITTED")
    remarks = models.CharField(max_length=250, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-submitted_at"]

    def __str__(self):
        return f"{self.app_no} — {self.subscheme.description} [{self.status}]"


# ============================================================ Phase 2
# Master tables (geographic + administrative hierarchies) and
# transaction tables (renewals, change requests, DBT payments).
# Design follows the "master tables vs request tables" split.

class District(models.Model):
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=80)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Mandal(models.Model):
    district = models.ForeignKey(District, on_delete=models.CASCADE, related_name="mandals")
    code = models.CharField(max_length=10)
    name = models.CharField(max_length=80)

    class Meta:
        ordering = ["name"]
        unique_together = [("district", "code")]

    def __str__(self):
        return f"{self.name} ({self.district.name})"


class Village(models.Model):
    mandal = models.ForeignKey(Mandal, on_delete=models.CASCADE, related_name="villages")
    code = models.CharField(max_length=10)
    name = models.CharField(max_length=80)

    class Meta:
        ordering = ["name"]
        unique_together = [("mandal", "code")]

    def __str__(self):
        return f"{self.name}, {self.mandal.name}"


class ALOCircle(models.Model):
    """Assistant Labour Officer circle — the administrative unit that
    processes registrations (State -> District -> ALO circle)."""
    code = models.CharField(max_length=15, unique=True)
    name = models.CharField(max_length=100)
    district = models.ForeignKey(District, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} — {self.name}"


class Nominee(models.Model):
    """Dependent/nominee attached to a worker (receives benefits on death claims)."""
    worker = models.ForeignKey(Worker, on_delete=models.CASCADE, related_name="nominees")
    name = models.CharField(max_length=120)
    relationship = models.CharField(max_length=60)
    age = models.IntegerField(null=True, blank=True)
    share_percent = models.IntegerField(default=100)
    is_primary = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} ({self.relationship}) — nominee of {self.worker.worker_name}"


class Renewal(models.Model):
    """Registrations are valid for 5 years; workers file a renewal to extend."""
    STATUS_CHOICES = [("SUBMITTED", "Submitted"), ("APPROVED", "Approved"), ("REJECTED", "Rejected")]

    req_no = models.CharField(max_length=30, unique=True)
    worker = models.ForeignKey(Worker, on_delete=models.CASCADE, related_name="renewals")
    period_from = models.DateField()
    period_to = models.DateField()
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="SUBMITTED")
    remarks = models.CharField(max_length=250, blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-requested_at"]

    def __str__(self):
        return f"{self.req_no} — {self.worker.reg_no} [{self.status}]"


class ChangeRequest(models.Model):
    """Worker-initiated corrections: name change, nominee change, bank change."""
    TYPE_CHOICES = [("NAME_CHANGE", "Name change"), ("NOMINEE_CHANGE", "Nominee change"),
                    ("BANK_CHANGE", "Bank/IFSC change")]
    STATUS_CHOICES = [("SUBMITTED", "Submitted"), ("APPROVED", "Approved"), ("REJECTED", "Rejected")]

    req_no = models.CharField(max_length=30, unique=True)
    worker = models.ForeignKey(Worker, on_delete=models.CASCADE, related_name="change_requests")
    request_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    old_value = models.CharField(max_length=200, blank=True)
    new_value = models.CharField(max_length=200)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="SUBMITTED")
    remarks = models.CharField(max_length=250, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.req_no} — {self.get_request_type_display()} [{self.status}]"


class DBTBatch(models.Model):
    """Direct Benefit Transfer batch — approved benefits are paid in batches."""
    batch_no = models.CharField(max_length=20, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=12, default="OPEN",
                              choices=[("OPEN", "Open"), ("PROCESSED", "Processed")])

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "DBT batches"

    def __str__(self):
        return self.batch_no


class DBTPayment(models.Model):
    """One benefit payment to a worker's bank account. Failed transactions
    stay on record and can be retried in a later batch."""
    STATUS_CHOICES = [("PENDING", "Pending"), ("SUCCESS", "Success"), ("FAILED", "Failed")]

    batch = models.ForeignKey(DBTBatch, on_delete=models.CASCADE, related_name="payments")
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="PENDING")
    failure_reason = models.CharField(max_length=150, blank=True)
    retry_of = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="retries")

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return f"{self.batch.batch_no} / {self.application.app_no} — ₹{self.amount} [{self.status}]"


class Establishment(models.Model):
    """Employer/organization registration (the 'Enterprise/Labour' side of the
    note). Under the BOCW Act, construction establishments register with the
    board and pay cess that funds the welfare schemes."""
    CATEGORY_CHOICES = [("BUILDER", "Builder"), ("CONTRACTOR", "Contractor"),
                        ("DEVELOPER", "Developer"), ("GOVT_PROJECT", "Government project"),
                        ("OTHER", "Other")]

    est_no = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=150)
    employer_name = models.CharField(max_length=120, help_text="Owner / responsible person")
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default="CONTRACTOR")
    phone = models.CharField(max_length=15, blank=True)
    address = models.CharField(max_length=250, blank=True)
    village = models.ForeignKey(Village, null=True, blank=True, on_delete=models.SET_NULL,
                                related_name="establishments")
    est_workers_count = models.IntegerField(default=0, help_text="Declared number of workers")
    cess_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0,
                                    help_text="Cess contribution to the welfare fund (₹)")
    registered_date = models.DateField(auto_now_add=True)
    valid_until = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return f"{self.est_no} — {self.name}"

    @property
    def is_expired(self):
        from datetime import date as _date
        return bool(self.valid_until and self.valid_until < _date.today())
