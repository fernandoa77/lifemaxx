import datetime as dt
import json
import math
from decimal import Decimal, ROUND_HALF_UP

from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Sum
from django.forms.models import model_to_dict
from django.utils import timezone

from dashboard.models import (
    Activity,
    AuditRevision,
    DayRecord,
    GlobalConfiguration,
    MentalEntry,
    SectionState,
)


D = Decimal
MODULE_KEYS = ("body", "nutrition", "activity", "sleep", "mental", "social")


def q(value, places="0.0001"):
    return D(str(value)).quantize(D(places), rounding=ROUND_HALF_UP)


def json_safe(value):
    return json.loads(json.dumps(value, default=str))


def active_configuration(moment=None):
    moment = moment or timezone.now()
    config = GlobalConfiguration.objects.filter(effective_from__lte=moment).order_by("-effective_from", "-pk").first()
    if config:
        return config
    return GlobalConfiguration.objects.create()


def configuration_for_date(date):
    end = timezone.make_aware(dt.datetime.combine(date, dt.time.max), timezone.get_current_timezone())
    return active_configuration(end)


def challenge_start_date():
    return active_configuration().challenge_start_date


@transaction.atomic
def get_or_create_day(date):
    day = DayRecord.objects.filter(date=date).first()
    if day:
        return day
    config = configuration_for_date(date)
    day = DayRecord.objects.create(date=date, configuration_snapshot=config.snapshot())
    SectionState.objects.bulk_create([SectionState(day=day, module=key) for key in MODULE_KEYS])
    return recalculate_day(day)


def record_revision(instance, previous, note=""):
    day = instance if isinstance(instance, DayRecord) else instance.day
    current = model_to_dict(instance)
    if previous == current:
        return
    AuditRevision.objects.create(
        day=day,
        object_type=instance._meta.label,
        object_id=instance.pk,
        previous_data=json_safe(previous),
        new_data=json_safe(current),
        note=note,
    )


def state_map(day):
    states = {s.module: s for s in day.section_states.all()}
    missing = [k for k in MODULE_KEYS if k not in states]
    if missing:
        SectionState.objects.bulk_create([SectionState(day=day, module=k) for k in missing])
        states.update({s.module: s for s in day.section_states.filter(module__in=missing)})
    return states


def nutrition_value(day, h):
    totals = day.meals.aggregate(
        calories=Sum("calories"), protein=Sum("protein_g"), carbs=Sum("carbs_g"),
        fat=Sum("fat_g"), fiber=Sum("fiber_g"), alcohol=Sum("pure_alcohol_ml"),
    )
    values = {key: D(str(value or 0)) for key, value in totals.items()}
    snap = day.configuration_snapshot
    e = values["alcohol"] / D("15.975")
    if e == 0:
        bonus = D("0.50") * h
    elif e <= D("1.5"):
        bonus = D("0.375") * h
    else:
        bonus = D("0.25") * h

    excess = max(values["calories"] - D(str(snap["calorie_goal"])), D("0"))
    fat_multiplier = {"maintain": D("1"), "lose": D("2"), "urgent": D("3")}[snap["fat_priority"]]
    calorie_cost = fat_multiplier * D("0.40") * h * min((excess / D("2000")) ** D("1.5"), D("1"))

    deficit = max(D(str(snap["protein_goal_g"])) - values["protein"], D("0"))
    protein_rate = {"maintain": D("0.004"), "gain": D("0.008"), "urgent": D("0.012")}[snap["muscle_priority"]]
    protein_cost = deficit * protein_rate * h

    if e <= 4:
        alcohol_cost_h = D("0.02") * e
    elif e <= 8:
        alcohol_cost_h = D("0.08") + D("0.04") * (e - 4)
    elif e <= 12:
        alcohol_cost_h = D("0.24") + D("0.12") * (e - 8)
    else:
        alcohol_cost_h = D("0.72") + D("0.18") * (e - 12)
    alcohol_cost = alcohol_cost_h * h
    value = bonus - calorie_cost - protein_cost - alcohol_cost
    return q(value / h), {
        **{key: float(val) for key, val in values.items()},
        "calorie_goal": snap["calorie_goal"], "protein_goal_g": snap["protein_goal_g"],
        "beer_equivalents": float(q(e, "0.001")),
        "base_bonus_h": float(q(bonus / h)), "calorie_cost_h": float(q(calorie_cost / h)),
        "protein_cost_h": float(q(protein_cost / h)), "alcohol_cost_h": float(q(alcohol_cost / h)),
        "meal_count": day.meals.count(),
    }


def _latest_weight(day):
    body = getattr(day, "body", None)
    if body and body.weight_am_kg:
        return D(body.weight_am_kg)
    prior = DayRecord.objects.filter(date__lte=day.date, body__weight_am_kg__isnull=False).order_by("-date").select_related("body").first()
    return D(prior.body.weight_am_kg) if prior else D("0")


def _base_energy(day, weight):
    profile = day.configuration_snapshot.get("body_profile") or {}
    height = D(str(profile.get("height_cm") or 0))
    birth = profile.get("birth_date")
    if not weight or not height or not birth:
        return D("0")
    birth_date = dt.date.fromisoformat(birth)
    age = day.date.year - birth_date.year - ((day.date.month, day.date.day) < (birth_date.month, birth_date.day))
    sex_constant = D("5") if profile.get("biological_sex") == "male" else D("-161")
    bmr = D("10") * weight + D("6.25") * height - D("5") * age + sex_constant
    return max(bmr * D("1.2"), D("0"))


def activity_value(day, h):
    sums = {key: D("0") for key, _ in Activity.CATEGORIES}
    weight = _latest_weight(day)
    active_kcal = D("0")
    for activity in day.activities.all():
        amount = D(activity.amount)
        sums[activity.category] += amount
        if activity.category == "steps":
            kcal = amount * D("0.04")
        elif activity.category == "functional_moderate":
            kcal = (D("5") - 1) * D("3.5") * weight / D("200") * amount if weight else 0
        elif activity.category == "functional_intense":
            kcal = (D("8") - 1) * D("3.5") * weight / D("200") * amount if weight else 0
        elif activity.category == "gym":
            kcal = (D("5") - 1) * D("3.5") * weight / D("200") * amount if weight else 0
        else:  # Lagartijas no entran al gasto hasta cerrar esa decision de producto.
            kcal = D("0")
        active_kcal += D(kcal)
        normalized = q(kcal, "0.01")
        if activity.estimated_active_kcal != normalized:
            Activity.objects.filter(pk=activity.pk).update(estimated_active_kcal=normalized)

    steps_credit_h = min(sums["steps"] / D("200") * D("0.004"), D("0.20"))
    pushups = sums["pushups"]
    if pushups <= 100:
        pushups_credit_h = D("0.0008") * pushups
    elif pushups <= 500:
        pushups_credit_h = D("0.08") + D("0.0004") * (pushups - 100)
    else:
        pushups_credit_h = D("0.24")
    time_credit_h = (
        D("0.40") * sums["functional_intense"] / 60
        + D("0.20") * sums["functional_moderate"] / 60
        + D("0.20") * sums["gym"] / 60
    )
    gross_h = steps_credit_h + pushups_credit_h + time_credit_h
    value_h = gross_h - D("0.20") if gross_h < D("0.20") else min(gross_h, D("1.20"))
    base_kcal = _base_energy(day, weight)
    return q(value_h), {
        **{key: float(value) for key, value in sums.items()},
        "gross_credit_h": float(q(gross_h)), "inactivity_penalty_h": 0.20,
        "base_kcal": float(q(base_kcal, "0.01")),
        "active_kcal": float(q(active_kcal, "0.01")), "total_kcal": float(q(base_kcal + active_kcal, "0.01")),
        "weight_used_kg": float(weight), "energy_version": "energy-1.0",
    }


def _circular_distance(a, b):
    raw = abs(a - b) % 1440
    return min(raw, 1440 - raw)


def _circular_median(values):
    if not values:
        return None
    return min(values, key=lambda candidate: sum(_circular_distance(candidate, other) for other in values))


def sleep_value(day, h):
    entry = day.sleep
    rising_blocked = DayRecord.objects.filter(
        date=day.date - dt.timedelta(days=1), sleep__no_sleep=True,
    ).exists()
    rise_penalty_h = D("0") if rising_blocked else {
        "quick": D("0"), "medium": D("0.25"), "slow": D("0.50"), "na": D("0"),
    }[entry.rising_category]
    incomplete = False
    if entry.no_sleep:
        total, midpoint, reference, deviation = 0, None, None, None
        duration_h, regularity_h = D("-0.25"), D("0")
    elif not entry.fell_asleep_at or not entry.woke_up_at:
        total, midpoint, reference, deviation = 0, None, None, None
        duration_h, regularity_h = D("0"), D("0")
        incomplete = True
    else:
        start, end = entry.fell_asleep_at, entry.woke_up_at
        if end <= start:
            end += dt.timedelta(days=1)
        main_minutes = int((end - start).total_seconds() // 60)
        total = max(main_minutes + entry.adjustment_minutes, 0)
        local_start = timezone.localtime(start)
        midpoint_dt = local_start + dt.timedelta(minutes=main_minutes / 2)
        midpoint = midpoint_dt.hour * 60 + midpoint_dt.minute
        prior = list(
            DayRecord.objects.filter(date__lt=day.date, sleep__midpoint_minute__isnull=False)
            .order_by("-date").values_list("sleep__midpoint_minute", flat=True)[:14]
        )
        reference = _circular_median(prior)
        deviation = _circular_distance(midpoint, reference) if reference is not None else None
        hours = D(total) / 60
        duration_h = D("-0.25") if hours <= 2 else D("0.375") if 8 <= hours <= 9 else D("0")
        if len(prior) < 6 or deviation is None:
            regularity_h = D("0")
        elif deviation <= 45:
            regularity_h = D("0.375") if 7 <= hours <= 9 else D("0")
        elif deviation <= 90:
            regularity_h = D("0")
        elif deviation <= 150:
            regularity_h = D("-0.25")
        else:
            regularity_h = D("-0.50")
    value_h = max(min(duration_h + regularity_h - rise_penalty_h, D("0.75")), D("-0.75"))
    entry.total_sleep_minutes = total
    entry.midpoint_minute = midpoint
    entry.circadian_reference_minute = reference
    entry.circadian_deviation_minutes = deviation
    entry.save(update_fields=("total_sleep_minutes", "midpoint_minute", "circadian_reference_minute", "circadian_deviation_minutes", "updated_at"))
    return q(value_h), {
        "total_minutes": total, "midpoint_minute": midpoint, "reference_minute": reference,
        "deviation_minutes": deviation, "duration_h": float(duration_h),
        "regularity_h": float(regularity_h), "rising_penalty_h": float(rise_penalty_h),
        "fell_asleep_at": entry.fell_asleep_at.isoformat() if entry.fell_asleep_at else None,
        "woke_up_at": entry.woke_up_at.isoformat() if entry.woke_up_at else None,
        "rising_category": "No aplica" if rising_blocked else entry.get_rising_category_display(),
        "rising_blocked": rising_blocked, "incomplete": incomplete,
    }


def _prior_glass_streak(date):
    streak, cursor = 0, date - dt.timedelta(days=1)
    while True:
        entry = MentalEntry.objects.filter(day__date=cursor, day__section_states__module="mental", day__section_states__captured=True).first()
        if not entry or entry.broken_glasses:
            return streak
        streak += 1
        cursor -= dt.timedelta(days=1)


def mental_value(day, h):
    entry = day.mental
    pp, pi, pn = D(entry.passive_positive_minutes) / 60, D(entry.passive_intermediate_minutes) / 60, D(entry.passive_negative_minutes) / 60
    ai, ap = D(entry.active_intermediate_minutes) / 60, D(entry.active_positive_minutes) / 60
    v_pp = D("0.20") * min(pp, 1) + D("0.05") * min(max(pp - 1, 0), 1) - D("0.20") * max(pp - 4, 0)
    v_pi = -D("0.20") * max(pi - D("0.5"), 0)
    v_pn = -D("0.50") * max(pn - D("0.25"), 0)
    v_ai = D("0.10") * min(ai, D("0.5")) - D("0.30") * max(ai - 1, 0)
    v_ap = D("0.25") * min(ap, 4)
    prior_streak = _prior_glass_streak(day.date)
    if entry.broken_glasses == 0:
        v_glasses, resulting = D("0.20"), prior_streak + 1
    else:
        v_glasses, resulting = -D("0.20") * (entry.broken_glasses + prior_streak), 0
    if entry.prior_streak != prior_streak or entry.resulting_streak != resulting:
        MentalEntry.objects.filter(pk=entry.pk).update(prior_streak=prior_streak, resulting_streak=resulting)
    components = {"passive_positive_h": v_pp, "passive_intermediate_h": v_pi, "passive_negative_h": v_pn, "active_intermediate_h": v_ai, "active_positive_h": v_ap, "glasses_h": v_glasses}
    return q(sum(components.values(), D("0"))), {
        **{key: float(q(value)) for key, value in components.items()},
        "prior_streak": prior_streak, "resulting_streak": resulting,
        "minutes": {"pp": entry.passive_positive_minutes, "pi": entry.passive_intermediate_minutes, "pn": entry.passive_negative_minutes, "ai": entry.active_intermediate_minutes, "ap": entry.active_positive_minutes},
    }


SOCIAL_FIELDS = ("family", "friends", "mixed_friends", "mixed_target", "target_friends")
SOCIAL_RATES = {
    "low": {"family": D(".25"), "friends": D(".25"), "mixed_friends": D(".25"), "mixed_target": D(".50"), "target_friends": D("1")},
    "medium": {"family": D(".25"), "friends": D(".25"), "mixed_friends": D(".50"), "mixed_target": D(".75"), "target_friends": D("1.50")},
    "priority": {"family": D(".25"), "friends": D(".25"), "mixed_friends": D("1"), "mixed_target": D("2"), "target_friends": D("4")},
}


def social_value(day, h):
    entry = day.social
    week_start = day.date - dt.timedelta(days=day.date.weekday())
    prior_days = DayRecord.objects.filter(date__gte=week_start, date__lt=day.date).order_by("date")
    used = {key: D("0") for key in SOCIAL_FIELDS}
    for prior in prior_days:
        previous = (prior.module_breakdowns or {}).get("social", {}).get("rewarded_hours", {})
        for key in SOCIAL_FIELDS:
            used[key] += D(str(previous.get(key, 0)))
    raw = {key: D(getattr(entry, f"{key}_minutes")) / 60 for key in SOCIAL_FIELDS}
    rates = SOCIAL_RATES[day.configuration_snapshot["social_priority"]]
    eligible = {key: min(raw[key], max(D("4") - used[key], 0)) for key in SOCIAL_FIELDS}
    remaining, rewarded = D("2"), {key: D("0") for key in SOCIAL_FIELDS}
    fixed_order = {key: index for index, key in enumerate(SOCIAL_FIELDS)}
    for key in sorted(SOCIAL_FIELDS, key=lambda item: (-rates[item], fixed_order[item])):
        rewarded[key] = min(eligible[key], remaining)
        remaining -= rewarded[key]
        if remaining <= 0:
            break
    base_h = sum((rates[key] * rewarded[key] for key in SOCIAL_FIELDS), D("0"))
    close_penalty_h = mixed_penalty_h = D("0")
    week_raw = {key: raw[key] for key in SOCIAL_FIELDS}
    for prior in prior_days:
        social = getattr(prior, "social", None)
        if social:
            for key in SOCIAL_FIELDS:
                week_raw[key] += D(getattr(social, f"{key}_minutes")) / 60
    if day.date.weekday() == 6:
        close_hours = week_raw["family"] + week_raw["friends"]
        mixed_hours = week_raw["mixed_friends"] + week_raw["mixed_target"] + week_raw["target_friends"]
        close_penalty_h = D("0.25") * max(D("2") - close_hours, 0)
        mixed_rate = {"low": D("0.25"), "medium": D("0.50"), "priority": D("1")}[day.configuration_snapshot["social_priority"]]
        mixed_penalty_h = mixed_rate * max(D("2") - mixed_hours, 0)
    value_h = base_h - close_penalty_h - mixed_penalty_h
    rewarded_json = {key: float(q(value, "0.001")) for key, value in rewarded.items()}
    if entry.rewarded_minutes != {key: int(value * 60) for key, value in rewarded.items()}:
        entry.rewarded_minutes = {key: int(value * 60) for key, value in rewarded.items()}
        entry.save(update_fields=("rewarded_minutes", "updated_at"))
    return q(value_h), {
        "raw_hours": {key: float(q(value, "0.001")) for key, value in raw.items()},
        "rewarded_hours": rewarded_json, "base_h": float(q(base_h)),
        "close_penalty_h": float(q(close_penalty_h)), "mixed_penalty_h": float(q(mixed_penalty_h)),
        "weekly_raw_hours": {key: float(q(value, "0.001")) for key, value in week_raw.items()},
        "weekly_close_hours": float(q(week_raw["family"] + week_raw["friends"], "0.001")),
        "weekly_mixed_hours": float(q(week_raw["mixed_friends"] + week_raw["mixed_target"] + week_raw["target_friends"], "0.001")),
    }


@transaction.atomic
def recalculate_day(day, *, save=True):
    day = DayRecord.objects.select_for_update().get(pk=day.pk)
    states = state_map(day)
    h = day.hour_value_mxn
    values, breakdowns, pending = {}, {}, []

    if day.date < challenge_start_date():
        values = {key: D("0") for key in MODULE_KEYS}
        day.module_values_h = {key: 0.0 for key in MODULE_KEYS}
        day.module_breakdowns = {key: {"excluded_before_challenge": True} for key in MODULE_KEYS}
        day.automatic_value_h = D("0")
        day.adjustment_mxn = D("0")
        day.final_value_h = D("0")
        day.pending_reasons = []
        day.status = DayRecord.Status.PROGRESS
        day.calculated_at = timezone.now()
        if save:
            day.save(update_fields=("module_values_h", "module_breakdowns", "automatic_value_h", "adjustment_mxn", "final_value_h", "pending_reasons", "status", "calculated_at", "updated_at"))
        return day

    values["body"] = D("0")
    body = getattr(day, "body", None)
    breakdowns["body"] = {
        "weight_am_kg": float(body.weight_am_kg) if body and body.weight_am_kg else None,
        "weight_pm_kg": float(body.weight_pm_kg) if body and body.weight_pm_kg else None,
        "abdomen_cm": float(body.abdomen_cm) if body and body.abdomen_cm else None,
        "visual_fat_percent": float(body.visual_fat_percent) if body and body.visual_fat_percent else None,
        "muscularity_rating": float(body.muscularity_rating) if body and body.muscularity_rating else None,
        "body_rating": float(body.body_rating) if body and body.body_rating else None,
        "face_rating": float(body.face_rating) if body and body.face_rating else None,
        "photo_count": body.photos.count() if body else 0,
    }

    calculators = {
        "nutrition": lambda: nutrition_value(day, h),
        "activity": lambda: activity_value(day, h),
        "sleep": lambda: sleep_value(day, h),
        "mental": lambda: mental_value(day, h),
        "social": lambda: social_value(day, h),
    }
    empty_breakdowns = {
        "nutrition": {
            "calories": 0, "protein": 0, "carbs": 0, "fat": 0, "fiber": 0, "alcohol": 0,
            "calorie_goal": day.configuration_snapshot.get("calorie_goal", 0),
            "protein_goal_g": day.configuration_snapshot.get("protein_goal_g", 0), "meal_count": 0,
        },
        "activity": {key: 0 for key, _ in Activity.CATEGORIES} | {"active_kcal": 0, "base_kcal": 0, "total_kcal": 0, "gross_credit_h": 0, "inactivity_penalty_h": 0.20},
        "sleep": {"total_minutes": 0, "deviation_minutes": None, "duration_h": 0, "regularity_h": 0, "rising_penalty_h": 0, "fell_asleep_at": None, "woke_up_at": None, "rising_category": None},
        "mental": {
            "minutes": {"pp": 0, "pi": 0, "pn": 0, "ai": 0, "ap": 0}, "resulting_streak": 0,
            "passive_positive_h": 0, "passive_intermediate_h": 0, "passive_negative_h": 0,
            "active_intermediate_h": 0, "active_positive_h": 0, "glasses_h": 0,
        },
        "social": {
            "raw_hours": {key: 0 for key in SOCIAL_FIELDS}, "rewarded_hours": {key: 0 for key in SOCIAL_FIELDS},
            "base_h": 0, "close_penalty_h": 0, "mixed_penalty_h": 0, "weekly_close_hours": 0, "weekly_mixed_hours": 0,
        },
    }
    relations = {"sleep": "sleep", "mental": "mental", "social": "social"}
    for key, calculator in calculators.items():
        if key == "activity":
            if states[key].captured or day.date == timezone.localdate():
                values[key], breakdowns[key] = calculator()
            else:
                values[key], breakdowns[key] = D("0"), {**empty_breakdowns[key], "not_captured": True}
            if not states[key].captured:
                breakdowns[key]["not_captured"] = True
                pending.append(f"Falta capturar {states[key].get_module_display().lower()}")
            continue
        if not states[key].captured:
            values[key], breakdowns[key] = D("0"), {**empty_breakdowns[key], "not_captured": True}
            pending.append(f"Falta capturar {states[key].get_module_display().lower()}")
            continue
        if key in relations and not hasattr(day, relations[key]):
            values[key], breakdowns[key] = D("0"), {**empty_breakdowns[key], "incomplete": True}
            pending.append(f"Faltan datos de {states[key].get_module_display().lower()}")
            continue
        values[key], breakdowns[key] = calculator()
        if breakdowns[key].get("incomplete"):
            pending.append(f"Faltan datos de {states[key].get_module_display().lower()}")

    if not states["body"].captured:
        pending.append("Falta capturar progreso corporal")
    processing = day.source_submissions.filter(status__in=("sent", "processing", "correction", "error"))
    if processing.exists():
        pending.append("Hay fuentes de IA pendientes o con error")
    if day.date == timezone.localdate():
        pending.append("El día sigue en curso")
    if day.date.weekday() == 6 and day.date >= timezone.localdate():
        pending.append("Los minimos sociales semanales siguen abiertos")

    automatic = sum(values.values(), D("0"))
    final = automatic + day.adjustment_h
    day.module_values_h = {key: float(q(value)) for key, value in values.items()}
    day.module_breakdowns = json_safe(breakdowns)
    day.automatic_value_h = q(automatic)
    day.adjustment_mxn = q(day.adjustment_h * h, "0.01")
    day.final_value_h = q(final)
    day.pending_reasons = list(dict.fromkeys(pending))
    day.status = DayRecord.Status.PENDING if pending and any(s.captured for s in states.values()) else DayRecord.Status.PROGRESS if pending else DayRecord.Status.COMPLETE
    day.calculated_at = timezone.now()
    if save:
        day.save(update_fields=("module_values_h", "module_breakdowns", "automatic_value_h", "adjustment_mxn", "final_value_h", "pending_reasons", "status", "calculated_at", "updated_at"))
    return day


def recalculate_mental_from(date):
    for day in DayRecord.objects.filter(date__gte=date, section_states__module="mental", section_states__captured=True).order_by("date").distinct():
        recalculate_day(day)


def recalculate_social_week(date):
    start = date - dt.timedelta(days=date.weekday())
    end = start + dt.timedelta(days=6)
    for day in DayRecord.objects.filter(date__range=(start, end), section_states__module="social", section_states__captured=True).order_by("date").distinct():
        recalculate_day(day)


def current_streak():
    latest = MentalEntry.objects.filter(day__date__gte=challenge_start_date(), day__section_states__module="mental", day__section_states__captured=True).order_by("-day__date").first()
    return latest.resulting_streak if latest else 0
