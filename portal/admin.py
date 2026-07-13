import re

from django.contrib import admin

from .models import (Worker, Scheme, SubScheme, Application, District, Mandal,
                     Village, ALOCircle, Nominee, Renewal, ChangeRequest,
                     DBTBatch, DBTPayment, Establishment)


class NomineeInline(admin.TabularInline):
    model = Nominee
    extra = 0


@admin.register(Worker)
class WorkerAdmin(admin.ModelAdmin):
    list_display = ("reg_no", "worker_name", "gender", "age", "reg_year",
                    "valid_until", "alo_circle", "migrant_worker", "is_test_row")
    search_fields = ("reg_no", "worker_name", "father_name")
    list_filter = ("reg_year", "gender", "migrant_worker", "is_test_row", "alo_circle")
    inlines = [NomineeInline]


class SubSchemeInline(admin.TabularInline):
    model = SubScheme
    extra = 0


@admin.register(Scheme)
class SchemeAdmin(admin.ModelAdmin):
    list_display = ("code", "description", "scheme_type")
    inlines = [SubSchemeInline]


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ("app_no", "worker", "subscheme", "status", "submitted_at")
    list_filter = ("status", "subscheme__scheme")
    search_fields = ("app_no", "worker__reg_no", "worker__worker_name")
    list_editable = ("status",)


@admin.register(Renewal)
class RenewalAdmin(admin.ModelAdmin):
    """Approving a renewal automatically extends the worker's validity."""
    list_display = ("req_no", "worker", "period_from", "period_to", "status", "requested_at")
    list_filter = ("status",)
    search_fields = ("req_no", "worker__reg_no", "worker__worker_name")
    list_editable = ("status",)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if obj.status == "APPROVED":
            w = obj.worker
            if not w.valid_until or obj.period_to > w.valid_until:
                w.valid_until = obj.period_to
                w.save(update_fields=["valid_until"])
                if "validity extended" not in obj.remarks:
                    obj.remarks = (obj.remarks + " | " if obj.remarks else "") + \
                                  f"validity extended to {obj.period_to}"
                    obj.save(update_fields=["remarks"])


@admin.register(ChangeRequest)
class ChangeRequestAdmin(admin.ModelAdmin):
    """Approving a change request applies it to the worker record."""
    list_display = ("req_no", "worker", "request_type", "new_value", "status", "created_at")
    list_filter = ("status", "request_type")
    search_fields = ("req_no", "worker__reg_no", "worker__worker_name")
    list_editable = ("status",)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if obj.status == "APPROVED" and "applied" not in obj.remarks:
            w = obj.worker
            if obj.request_type == "NAME_CHANGE":
                w.worker_name = obj.new_value.strip().title()
                w.save(update_fields=["worker_name"])
            elif obj.request_type == "BANK_CHANGE":
                w.ifsc_code = obj.new_value.strip().upper()
                w.ifsc_valid = bool(re.fullmatch(r"[A-Z]{4}0[A-Z0-9]{6}", w.ifsc_code))
                w.save(update_fields=["ifsc_code", "ifsc_valid"])
            elif obj.request_type == "NOMINEE_CHANGE":
                nominee = w.nominees.filter(is_primary=True).first()
                if nominee:
                    nominee.name = obj.new_value.strip().title()
                    nominee.save(update_fields=["name"])
                else:
                    Nominee.objects.create(worker=w, name=obj.new_value.strip().title(),
                                           relationship="Nominee", is_primary=True)
            obj.remarks = (obj.remarks + " | " if obj.remarks else "") + "applied to worker record"
            obj.save(update_fields=["remarks"])


class DBTPaymentInline(admin.TabularInline):
    model = DBTPayment
    extra = 0


@admin.register(DBTBatch)
class DBTBatchAdmin(admin.ModelAdmin):
    list_display = ("batch_no", "status", "created_at")
    inlines = [DBTPaymentInline]


@admin.register(DBTPayment)
class DBTPaymentAdmin(admin.ModelAdmin):
    list_display = ("batch", "application", "amount", "status", "failure_reason")
    list_filter = ("status", "batch")
    list_editable = ("status",)
    actions = ["retry_failed"]

    @admin.action(description="Retry selected FAILED payments in a new batch")
    def retry_failed(self, request, queryset):
        failed = queryset.filter(status="FAILED")
        if not failed.exists():
            self.message_user(request, "No FAILED payments selected.")
            return
        serial = DBTBatch.objects.count() + 1
        batch = DBTBatch.objects.create(batch_no=f"DBT-2026-{serial:03d}", status="OPEN")
        for p in failed:
            DBTPayment.objects.create(batch=batch, application=p.application,
                                      amount=p.amount, status="PENDING", retry_of=p)
        self.message_user(request, f"Created {batch.batch_no} with {failed.count()} retried payment(s).")


admin.site.register(District)
admin.site.register(Mandal)
admin.site.register(Village)
admin.site.register(ALOCircle)
admin.site.register(Nominee)


@admin.register(Establishment)
class EstablishmentAdmin(admin.ModelAdmin):
    list_display = ("est_no", "name", "employer_name", "category",
                    "est_workers_count", "cess_paid", "valid_until")
    search_fields = ("est_no", "name", "employer_name")
    list_filter = ("category",)
