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
    path("dashboard/", views.dashboard, name="dashboard"),
    path("api/chat", views.chat_api, name="chat_api"),
    path("admin/", admin.site.urls),
]
