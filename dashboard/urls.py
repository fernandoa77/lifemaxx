from django.urls import path
from django.contrib.auth.decorators import login_required

from . import views


app_name = "dashboard"
urlpatterns = [
    path("", login_required(views.home), name="home"),
    path("dia/<str:date>/", login_required(views.day_detail), name="day"),
    path("dia/<str:date>/ajuste/", login_required(views.adjustment), name="adjustment"),
    path("dia/<str:date>/<slug:module>/", login_required(views.module_detail), name="module"),
    path("calendario/", login_required(views.calendar_view), name="calendar_current"),
    path("calendario/<int:year>/<int:month>/", login_required(views.calendar_view), name="calendar"),
    path("dashboard/", login_required(views.dashboard_view), name="dashboard"),
    path("configuracion/", login_required(views.settings_view), name="settings"),
]
