from django.contrib import admin
from .models import Worker, Scheme, SubScheme, Application


@admin.register(Worker)
class WorkerAdmin(admin.ModelAdmin):
    list_display = ("reg_no", "worker_name", "gender", "age", "reg_year", "migrant_worker", "is_test_row")
    search_fields = ("reg_no", "worker_name", "father_name")
    list_filter = ("reg_year", "gender", "migrant_worker", "is_test_row")


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
