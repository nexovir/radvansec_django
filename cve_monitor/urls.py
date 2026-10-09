from django.urls import path
from . import views

app_name = "cve_monitor"

urlpatterns = [
    path("monitor/", views.cve_list, name="list"),
]