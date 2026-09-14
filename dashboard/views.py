import calendar as month_calendar
import datetime as dt
from decimal import Decimal

from django.contrib import messages
from django.db.models import Avg, Sum
from django.forms.models import model_to_dict
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import (
    ActivityForm, AdjustmentForm, BodyForm, BodyPhotoForm, ConfigurationForm,
    MealForm, MentalForm, SleepForm, SocialForm, SupplementForm,
)
from .models import Activity, BodyEntry, BodyPhoto, GlobalConfiguration, Meal, MentalEntry, SectionState, SleepEntry, SocialEntry, SourceSubmission, Supplement
from .services.ai import AIUnavailable, BODY_SCHEMA, MEAL_SCHEMA, request_structured_json
from .services.pricing import (
    MODULE_KEYS, active_configuration, get_or_create_day, json_safe, recalculate_day,
    recalculate_mental_from, recalculate_social_week, record_revision,
)


MODULE_META = {
    "body": {"name": "Progreso corporal", "eyebrow": "Estado", "icon": "body"},
    "nutrition": {"name": "Nutricion", "eyebrow": "Energia", "icon": "nutrition"},
    "activity": {"name": "Actividad fisica", "eyebrow": "Movimiento", "icon": "activity"},
    "sleep": {"name": "Sueno", "eyebrow": "Recuperacion", "icon": "sleep"},
    "mental": {"name": "Mental y digital", "eyebrow": "Atencion", "icon": "mental"},
    "social": {"name": "Vida social", "eyebrow": "Conexion", "icon": "social"},
}


def _date(value):
    try:
        return dt.date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise Http404("Fecha invalida") from exc


def _is_ajax(request):
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def _form_error(request, form, day, module):
    if _is_ajax(request):
        return JsonResponse({"ok": False, "errors": form.errors.get_json_data()}, status=422)
    messages.error(request, "Revisa los campos marcados.")
    return _module_render(request, day, module, bound_form=form)


def _saved_response(request, day, module, message="Guardado"):
    day.refresh_from_db()
    if _is_ajax(request):
        return JsonResponse({
            "ok": True, "message": message, "module_value_h": day.module_values_h.get(module, 0),
            "final_value_h": float(day.final_value_h), "final_value_mxn": float(day.final_value_mxn),
            "status": day.status,
        })
    messages.success(request, message)
    return redirect("dashboard:module", date=day.date.isoformat(), module=module)


def home(request):
    return redirect("dashboard:day", date=timezone.localdate().isoformat())


def day_detail(request, date):
    day = get_or_create_day(_date(date))
    day = recalculate_day(day)
    cards = []
    for key, meta in MODULE_META.items():
        cards.append({
            "key": key, **meta, "value": Decimal(str(day.module_values_h.get(key, 0))),
            "breakdown": day.module_breakdowns.get(key, {}),
        })
    adjustment_form = AdjustmentForm(initial={"adjustment_h": day.adjustment_h, "adjustment_justification": day.adjustment_justification})
    return render(request, "dashboard/day.html", {
        "day": day, "cards": cards, "adjustment_form": adjustment_form,
        "previous_date": day.date - dt.timedelta(days=1), "next_date": day.date + dt.timedelta(days=1),
    })


@require_POST
def adjustment(request, date):
    day = get_or_create_day(_date(date))
    form = AdjustmentForm(request.POST)
    if not form.is_valid():
        messages.error(request, "El ajuste requiere una cantidad valida y justificacion cuando no es cero.")
        return redirect("dashboard:day", date=date)
    previous = model_to_dict(day)
    day.adjustment_h = form.cleaned_data["adjustment_h"]
    day.adjustment_justification = form.cleaned_data["adjustment_justification"]
    day.save(update_fields=("adjustment_h", "adjustment_justification", "updated_at"))
    record_revision(day, previous, "Ajuste marginal manual")
    recalculate_day(day)
    return redirect("dashboard:day", date=date)


def module_detail(request, date, module):
    if module not in MODULE_META:
        raise Http404("Modulo inexistente")
    day = get_or_create_day(_date(date))
    if request.method == "POST":
        return _module_post(request, day, module)
    recalculate_day(day)
    return _module_render(request, day, module)


def _module_instances(day):
    body, _ = BodyEntry.objects.get_or_create(day=day)
    sleep, _ = SleepEntry.objects.get_or_create(day=day)
    mental, _ = MentalEntry.objects.get_or_create(day=day)
    social, _ = SocialEntry.objects.get_or_create(day=day)
    return body, sleep, mental, social


def _module_render(request, day, module, bound_form=None):
    body, sleep, mental, social = _module_instances(day)
    editing_meal = get_object_or_404(Meal, pk=request.GET["meal"], day=day) if module == "nutrition" and request.GET.get("meal") else None
    editing_activity = get_object_or_404(Activity, pk=request.GET["activity"], day=day) if module == "activity" and request.GET.get("activity") else None
    forms = {
        "body": bound_form or BodyForm(instance=body),
        "nutrition": bound_form or MealForm(instance=editing_meal),
        "activity": bound_form or ActivityForm(instance=editing_activity),
        "sleep": bound_form or SleepForm(instance=sleep),
        "mental": bound_form or MentalForm(instance=mental),
        "social": bound_form or SocialForm(instance=social),
    }
    state = day.section_states.get(module=module)
    context = {
        "day": day, "module": module, "meta": MODULE_META[module], "form": forms[module], "state": state,
        "breakdown": day.module_breakdowns.get(module, {}), "module_value": day.module_values_h.get(module, 0),
        "previous_date": day.date - dt.timedelta(days=1), "next_date": day.date + dt.timedelta(days=1),
        "body": body, "photo_form": BodyPhotoForm(), "photos": body.photos.all(),
        "meals": day.meals.all(), "activities": day.activities.all(), "supplements": day.supplements.all(),
        "supplement_form": SupplementForm(), "editing_meal": editing_meal, "editing_activity": editing_activity,
        "submissions": day.source_submissions.filter(module=module),
    }
    return render(request, "dashboard/module.html", context)


def _mark_captured(day, module, processing_status="idle", error=""):
    SectionState.objects.filter(day=day, module=module).update(captured=True, processing_status=processing_status, error_message=error)


def _save_singleton(request, day, module, model, form_class):
    instance, _ = model.objects.get_or_create(day=day)
    previous = model_to_dict(instance)
    form = form_class(request.POST, request.FILES, instance=instance)
    if not form.is_valid():
        return _form_error(request, form, day, module)
    saved = form.save()
    _mark_captured(day, module)
    record_revision(saved, previous, f"Captura de {MODULE_META[module]['name']}")
    if module == "mental":
        recalculate_mental_from(day.date)
    elif module == "social":
        recalculate_social_week(day.date)
    else:
        recalculate_day(day)
    return _saved_response(request, day, module)


def _module_post(request, day, module):
    action = request.POST.get("action", "save")
    if module == "body":
        if action == "photo-delete":
            photo = get_object_or_404(BodyPhoto, pk=request.POST.get("photo_id"), body__day=day)
            photo.delete()
            recalculate_day(day)
            return _saved_response(request, day, module, "Fotografia eliminada")
        if action == "photo":
            form = BodyPhotoForm(request.POST, request.FILES)
            if not form.is_valid():
                return _form_error(request, form, day, module)
            body, _ = BodyEntry.objects.get_or_create(day=day)
            old = body.photos.filter(kind=form.cleaned_data["kind"]).first()
            photo = form.save(commit=False)
            photo.body = body
            if old:
                photo.pk = old.pk
            photo.save()
            _mark_captured(day, module)
            recalculate_day(day)
            return _saved_response(request, day, module, "Fotografia guardada")
        if action == "analyze":
            return _analyze_body(request, day)
        return _save_singleton(request, day, module, BodyEntry, BodyForm)

    if module == "nutrition":
        if action == "supplement":
            form = SupplementForm(request.POST)
            if not form.is_valid():
                messages.error(request, "Revisa los datos del suplemento.")
                return redirect("dashboard:module", date=day.date.isoformat(), module=module)
            supplement = form.save(commit=False)
            supplement.day = day
            supplement.save()
            _mark_captured(day, module)
            recalculate_day(day)
            return _saved_response(request, day, module, "Suplemento agregado")
        if action == "supplement-delete":
            get_object_or_404(Supplement, pk=request.POST.get("supplement_id"), day=day).delete()
            recalculate_day(day)
            return _saved_response(request, day, module, "Suplemento eliminado")
        if action == "delete":
            meal = get_object_or_404(Meal, pk=request.POST.get("meal_id"), day=day)
            previous = model_to_dict(meal)
            meal_id = meal.pk
            meal.delete()
            from .models import AuditRevision
            AuditRevision.objects.create(day=day, object_type="dashboard.Meal", object_id=meal_id, action="delete", previous_data=json_safe(previous), note="Comida eliminada")
            _mark_captured(day, module)
            recalculate_day(day)
            return _saved_response(request, day, module, "Comida eliminada")
        meal_id = request.POST.get("meal_id")
        instance = get_object_or_404(Meal, pk=meal_id, day=day) if meal_id else None
        previous = model_to_dict(instance) if instance else {}
        form = MealForm(request.POST, request.FILES, instance=instance)
        if not form.is_valid():
            return _form_error(request, form, day, module)
        meal = form.save(commit=False)
        meal.day = day
        meal.corrected_manually = bool(instance)
        meal.save()
        record_revision(meal, previous, "Comida corregida" if instance else "Comida creada")
        _mark_captured(day, module)
        if form.cleaned_data.get("process_with_ai"):
            _process_meal_ai(day, meal)
        recalculate_day(day)
        return _saved_response(request, day, module, "Comida guardada")

    if module == "activity":
        if action == "delete":
            activity = get_object_or_404(Activity, pk=request.POST.get("activity_id"), day=day)
            activity.delete()
            recalculate_day(day)
            return _saved_response(request, day, module, "Actividad eliminada")
        activity_id = request.POST.get("activity_id")
        instance = get_object_or_404(Activity, pk=activity_id, day=day) if activity_id else None
        previous = model_to_dict(instance) if instance else {}
        form = ActivityForm(request.POST, instance=instance)
        if not form.is_valid():
            return _form_error(request, form, day, module)
        activity = form.save(commit=False)
        activity.day = day
        activity.save()
        record_revision(activity, previous, "Actividad corregida" if instance else "Actividad creada")
        _mark_captured(day, module)
        recalculate_day(day)
        return _saved_response(request, day, module, "Actividad agregada")

    singleton = {
        "sleep": (SleepEntry, SleepForm), "mental": (MentalEntry, MentalForm), "social": (SocialEntry, SocialForm)
    }
    model, form_class = singleton[module]
    return _save_singleton(request, day, module, model, form_class)


def _process_meal_ai(day, meal):
    source = SourceSubmission.objects.create(
        day=day, module="nutrition", source_text=meal.description,
        source_file=meal.photo.name if meal.photo else "", status="processing", prompt_version="meal-1.0",
    )
    SectionState.objects.filter(day=day, module="nutrition").update(processing_status="processing")
    try:
        result = request_structured_json(
            system_prompt="Identifica una comida y estima su desglose nutricional y alcohol puro.",
            user_content=meal.description,
            images=[meal.photo.path] if meal.photo else [], schema=MEAL_SCHEMA, schema_name="life_meal",
            context={"date": day.date.isoformat(), "manual_values_are_context_only": True},
        )
        data = result["data"]
        meal.foods = data["foods"]
        for field in ("calories", "protein_g", "carbs_g", "fat_g", "fiber_g", "beverage_volume_ml", "alcohol_abv_percent", "pure_alcohol_ml"):
            setattr(meal, field, Decimal(str(data[field])))
        meal.alcoholic_drink = data["alcoholic_drink"]
        meal.ai_result = data
        meal.save()
        source.status, source.result_json, source.model_used = "processed", data, result["model"]
        source.save()
        SectionState.objects.filter(day=day, module="nutrition").update(processing_status="done", error_message="")
    except AIUnavailable as exc:
        source.status, source.error_message = "error", str(exc)
        source.save(update_fields=("status", "error_message", "updated_at"))
        SectionState.objects.filter(day=day, module="nutrition").update(processing_status="error", error_message=str(exc))


def _analyze_body(request, day):
    body, _ = BodyEntry.objects.get_or_create(day=day)
    paths = [photo.image.path for photo in body.photos.all()]
    if not paths:
        messages.error(request, "Sube al menos una fotografia antes de analizar.")
        return redirect("dashboard:module", date=day.date.isoformat(), module="body")
    source = SourceSubmission.objects.create(day=day, module="body", status="processing", prompt_version="body-1.0", source_text="Paquete fotografico corporal")
    _mark_captured(day, "body", "processing")
    try:
        result = request_structured_json(
            system_prompt="Evalua el paquete fotografico con una rubrica visual constante. Informa advertencias de calidad.",
            user_content="Analiza solo lo visible y devuelve null si una metrica no puede evaluarse.",
            images=paths, schema=BODY_SCHEMA, schema_name="life_body_assessment",
            context={"photo_types": list(body.photos.values_list("kind", flat=True)), "rating_scale": "0-10"},
        )
        data = result["data"]
        for field in ("visual_fat_percent", "muscularity_rating", "face_rating", "body_rating"):
            setattr(body, field, Decimal(str(data[field])) if data[field] is not None else None)
        body.llm_description, body.analysis_json = data["description"], data
        body.save()
        source.status, source.result_json, source.model_used = "processed", data, result["model"]
        source.save()
        _mark_captured(day, "body", "done")
        messages.success(request, "Analisis corporal procesado.")
    except AIUnavailable as exc:
        source.status, source.error_message = "error", str(exc)
        source.save(update_fields=("status", "error_message", "updated_at"))
        _mark_captured(day, "body", "error", str(exc))
        messages.error(request, str(exc))
    recalculate_day(day)
    return redirect("dashboard:module", date=day.date.isoformat(), module="body")


def calendar_view(request, year=None, month=None):
    today = timezone.localdate()
    year, month = int(year or today.year), int(month or today.month)
    if month < 1 or month > 12:
        raise Http404("Mes invalido")
    cal = month_calendar.Calendar(firstweekday=0)
    records = {d.date: d for d in __import__("dashboard.models", fromlist=["DayRecord"]).DayRecord.objects.filter(date__year=year, date__month=month)}
    weeks = [[{"date": date, "record": records.get(date), "in_month": date.month == month} for date in week] for week in cal.monthdatescalendar(year, month)]
    current = dt.date(year, month, 1)
    previous = current - dt.timedelta(days=1)
    next_month = (current.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    spanish_months = ("", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre")
    return render(request, "dashboard/calendar.html", {"weeks": weeks, "year": year, "month": month, "month_name": spanish_months[month], "previous": previous, "next": next_month, "today": today})


def _period(request):
    today = timezone.localdate()
    kind = request.GET.get("period", "month")
    try:
        if kind == "day":
            start = end = _date(request.GET.get("date", today.isoformat()))
        elif kind == "week":
            anchor = _date(request.GET.get("date", today.isoformat()))
            start, end = anchor - dt.timedelta(days=anchor.weekday()), anchor - dt.timedelta(days=anchor.weekday()) + dt.timedelta(days=6)
        elif kind == "custom":
            start, end = _date(request.GET.get("start")), _date(request.GET.get("end"))
        else:
            anchor = _date(request.GET.get("date", today.isoformat()))
            start = anchor.replace(day=1)
            end = (start.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)
            kind = "month"
    except Http404:
        start, end, kind = today.replace(day=1), today, "month"
    if end < start:
        start, end = end, start
    return kind, start, end


def dashboard_view(request):
    from .models import DayRecord
    kind, start, end = _period(request)
    days = list(DayRecord.objects.filter(date__range=(start, end)).order_by("date"))
    span = (end - start).days + 1
    previous_start, previous_end = start - dt.timedelta(days=span), start - dt.timedelta(days=1)
    previous_days = list(DayRecord.objects.filter(date__range=(previous_start, previous_end)))
    total = sum((day.final_value_h for day in days), Decimal("0"))
    average = total / len(days) if days else Decimal("0")
    module_rows = []
    for key, meta in MODULE_META.items():
        value = sum((Decimal(str(day.module_values_h.get(key, 0))) for day in days), Decimal("0"))
        previous_value = sum((Decimal(str(day.module_values_h.get(key, 0))) for day in previous_days), Decimal("0"))
        module_rows.append({
            "key": key, "name": meta["name"], "value": value, "average": value / len(days) if days else 0,
            "contribution": (value / total * 100) if total else 0, "change": value - previous_value,
            "series": [float(day.module_values_h.get(key, 0)) for day in days],
        })
    positive = sum(day.final_value_h > 0 for day in days)
    negative = sum(day.final_value_h < 0 for day in days)
    neutral = len(days) - positive - negative
    best = max(days, key=lambda day: day.final_value_h) if days else None
    worst = min(days, key=lambda day: day.final_value_h) if days else None
    adjustment_total = sum((day.adjustment_h for day in days), Decimal("0"))
    config_changes = GlobalConfiguration.objects.filter(effective_from__date__range=(start, end)).order_by("effective_from")
    def total_path(module, key):
        return sum((Decimal(str((day.module_breakdowns.get(module) or {}).get(key) or 0)) for day in days), Decimal("0"))

    latest_body = next(((day.module_breakdowns.get("body") or {}) for day in reversed(days) if (day.module_breakdowns.get("body") or {}).get("weight_am_kg")), {})
    sleep_values = [Decimal(str((day.module_breakdowns.get("sleep") or {}).get("total_minutes") or 0)) for day in days if (day.module_breakdowns.get("sleep") or {}).get("total_minutes")]
    mental_totals = {key: 0 for key in ("pp", "pi", "pn", "ai", "ap")}
    social_raw = social_rewarded = Decimal("0")
    for day in days:
        mental_minutes = (day.module_breakdowns.get("mental") or {}).get("minutes") or {}
        for key in mental_totals:
            mental_totals[key] += int(mental_minutes.get(key) or 0)
        social = day.module_breakdowns.get("social") or {}
        social_raw += sum((Decimal(str(value or 0)) for value in (social.get("raw_hours") or {}).values()), Decimal("0"))
        social_rewarded += sum((Decimal(str(value or 0)) for value in (social.get("rewarded_hours") or {}).values()), Decimal("0"))
    behavior_groups = [
        {"name": "Progreso corporal", "metrics": [("Peso AM mas reciente", latest_body.get("weight_am_kg"), "kg"), ("Grasa visual", latest_body.get("visual_fat_percent"), "%"), ("Panza", latest_body.get("abdomen_cm"), "cm")]},
        {"name": "Nutricion", "metrics": [("Calorias", total_path("nutrition", "calories"), "kcal"), ("Proteina", total_path("nutrition", "protein"), "g"), ("Alcohol puro", total_path("nutrition", "alcohol"), "ml")]},
        {"name": "Actividad", "metrics": [("Pasos intencionales", total_path("activity", "steps"), ""), ("Lagartijas", total_path("activity", "pushups"), ""), ("Calorias activas", total_path("activity", "active_kcal"), "kcal")]},
        {"name": "Sueno", "metrics": [("Promedio por noche", (sum(sleep_values) / len(sleep_values)) if sleep_values else 0, "min"), ("Desviacion acumulada", total_path("sleep", "deviation_minutes"), "min"), ("Noches capturadas", len(sleep_values), "")]},
        {"name": "Mental / digital", "metrics": [("Pasivo positivo", mental_totals["pp"], "min"), ("Pasivo negativo", mental_totals["pn"], "min"), ("Activo positivo", mental_totals["ap"], "min")]},
        {"name": "Vida social", "metrics": [("Tiempo bruto", social_raw, "h"), ("Tiempo bonificado", social_rewarded, "h"), ("Diferencia por topes", social_raw - social_rewarded, "h")]},
    ]
    return render(request, "dashboard/dashboard.html", {
        "kind": kind, "start": start, "end": end, "days": days, "total": total, "average": average,
        "positive": positive, "negative": negative, "neutral": neutral, "complete": sum(day.status == "complete" for day in days),
        "partial": sum(day.status != "complete" for day in days), "best": best, "worst": worst,
        "module_rows": module_rows, "adjustment_total": adjustment_total, "config_changes": config_changes,
        "behavior_groups": behavior_groups,
    })


def settings_view(request):
    current = active_configuration()
    if request.method == "POST":
        form = ConfigurationForm(request.POST, instance=current)
        if form.is_valid():
            form.save()
            messages.success(request, "Nueva configuracion activa. El historial no fue recalculado.")
            return redirect("dashboard:settings")
    else:
        form = ConfigurationForm(instance=current)
    history = GlobalConfiguration.objects.order_by("-effective_from")[:12]
    return render(request, "dashboard/settings.html", {"form": form, "current": current, "history": history})
