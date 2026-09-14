from django.urls import path

from . import views


app_name = "dashboard"
urlpatterns = [
    path("", views.home, name="home"),
    path("dia/<str:date>/", views.day_detail, name="day"),
    path("dia/<str:date>/ajuste/", views.adjustment, name="adjustment"),
    path("dia/<str:date>/<slug:module>/", views.module_detail, name="module"),
    path("calendario/", views.calendar_view, name="calendar_current"),
    path("calendario/<int:year>/<int:month>/", views.calendar_view, name="calendar"),
    path("dashboard/", views.dashboard_view, name="dashboard"),
    path("configuracion/", views.settings_view, name="settings"),
]
