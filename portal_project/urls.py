from django.contrib import admin
from django.urls import path
from portal import views

urlpatterns = [
    path("", views.home, name="home"),
    path("register/", views.register, name="register"),
    path("workers/", views.workers_list, name="workers"),
    path("worker/<path:reg_no>/", views.worker_detail, name="worker_detail"),
    path("schemes/", views.schemes, name="schemes"),
    path("apply/", views.apply, name="apply"),
    path("status/", views.status, name="status"),
    path("renew/", views.renew, name="renew"),
    path("change-request/", views.change_request, name="change_request"),
    path("track/", views.track, name="track"),
    path("establishments/", views.establishments_list, name="establishments"),
    path("register-establishment/", views.register_establishment, name="register_establishment"),
    path("establishment/<path:est_no>/", views.establishment_detail, name="establishment_detail"),
    path("worker/<path:reg_no>/card/", views.worker_card, name="worker_card"),
    path("workers/export/", views.workers_export, name="workers_export"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("api/chat", views.chat_api, name="chat_api"),
    path("admin/", admin.site.urls),
]
