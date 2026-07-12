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
    GENDER_CHOICES = [("Male", "Male"), ("Female", "Female"), ("Unknown", "Unknown")]

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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-reg_year", "reg_no"]

    def __str__(self):
        return f"{self.reg_no} — {self.worker_name}"


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
