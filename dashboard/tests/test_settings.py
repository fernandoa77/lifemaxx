import datetime as dt
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from dashboard.models import AuditRevision, BodyEntry, DayRecord, GlobalConfiguration
from dashboard.services.pricing import _latest_weight, body_profile_for_day, get_or_create_day, recalculate_day
from dashboard.views import _calorie_balance


class UniversalSettingsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("alex", password="a-secure-test-password")
        self.client.force_login(self.user)

    def test_date_inputs_keep_existing_values_visible(self):
        GlobalConfiguration.objects.create(
            challenge_start_date=dt.date(2026, 9, 1),
            birth_date=dt.date(1990, 1, 2),
        )
        response = self.client.get(reverse("dashboard:settings"))
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertIn('value="2026-09-01"', str(form["challenge_start_date"]))
        self.assertIn('value="1990-01-02"', str(form["birth_date"]))

    def test_birth_date_can_be_prefilled_from_configuration_history(self):
        GlobalConfiguration.objects.create(
            effective_from=timezone.now() - dt.timedelta(days=1),
            birth_date=dt.date(1990, 1, 2),
        )
        GlobalConfiguration.objects.create(
            effective_from=timezone.now(),
            birth_date=None,
        )
        response = self.client.get(reverse("dashboard:settings"))
        self.assertIn('value="1990-01-02"', str(response.context["form"]["birth_date"]))

    def test_incomplete_profile_cannot_replace_current_configuration(self):
        current = GlobalConfiguration.objects.create(
            height_cm="180.0", birth_date=dt.date(1990, 1, 1), biological_sex="male",
        )
        response = self.client.post(reverse("dashboard:settings"), {
            "challenge_start_date": current.challenge_start_date.isoformat(),
            "hour_value_mxn": "250.00", "calorie_goal": "2200", "protein_goal_g": "160",
            "fat_priority": "urgent", "muscle_priority": "gain", "social_priority": "priority",
            "height_cm": "", "birth_date": "", "biological_sex": "unspecified",
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(GlobalConfiguration.objects.count(), 1)
        current.refresh_from_db()
        self.assertEqual(current.height_cm, Decimal("180.0"))
        self.assertEqual(current.birth_date, dt.date(1990, 1, 1))
        self.assertEqual(current.biological_sex, "male")
        self.assertFormError(response.context["form"], "height_cm", "Este campo es obligatorio.")
        self.assertFormError(response.context["form"], "birth_date", "Este campo es obligatorio.")
        self.assertFormError(response.context["form"], "biological_sex", "Selecciona masculino o femenino para calcular el gasto energético.")

    def test_new_settings_replace_only_todays_snapshot(self):
        today = timezone.localdate()
        previous_day = get_or_create_day(today - dt.timedelta(days=1))
        current_day = get_or_create_day(today)
        original_configuration_id = current_day.configuration_snapshot["configuration_id"]

        response = self.client.post(reverse("dashboard:settings"), {
            "challenge_start_date": (today - dt.timedelta(days=30)).isoformat(),
            "hour_value_mxn": "375.00",
            "calorie_goal": "2450",
            "protein_goal_g": "190",
            "fat_priority": "lose",
            "muscle_priority": "urgent",
            "social_priority": "medium",
            "height_cm": "180.0",
            "birth_date": "1990-01-01",
            "biological_sex": "male",
        })

        self.assertRedirects(response, reverse("dashboard:settings"))
        new_configuration = GlobalConfiguration.objects.order_by("-effective_from", "-pk").first()
        previous_day.refresh_from_db()
        current_day.refresh_from_db()

        self.assertNotEqual(new_configuration.pk, original_configuration_id)
        self.assertEqual(previous_day.configuration_snapshot["configuration_id"], original_configuration_id)
        self.assertEqual(current_day.configuration_snapshot["configuration_id"], new_configuration.pk)
        self.assertEqual(current_day.configuration_snapshot["hour_value_mxn"], "375.00")
        self.assertEqual(current_day.configuration_snapshot["calorie_goal"], 2450)
        self.assertEqual(new_configuration.challenge_start_date, today - dt.timedelta(days=30))
        self.assertEqual(new_configuration.birth_date, dt.date(1990, 1, 1))
        refreshed_form = self.client.get(reverse("dashboard:settings")).context["form"]
        self.assertIn(f'value="{(today - dt.timedelta(days=30)).isoformat()}"', str(refreshed_form["challenge_start_date"]))
        self.assertIn('value="1990-01-01"', str(refreshed_form["birth_date"]))
        self.assertTrue(AuditRevision.objects.filter(
            day=current_day,
            note="Configuración universal actualizada para el día en curso",
        ).exists())

    def test_existing_day_uses_saved_profile_when_its_snapshot_is_missing_fields(self):
        yesterday = timezone.localdate() - dt.timedelta(days=1)
        day = get_or_create_day(yesterday)
        BodyEntry.objects.create(day=day, weight_am_kg="80.0")
        original_snapshot = day.configuration_snapshot.copy()

        response = self.client.post(reverse("dashboard:settings"), {
            "challenge_start_date": (yesterday - dt.timedelta(days=30)).isoformat(),
            "hour_value_mxn": "250.00", "calorie_goal": "2200", "protein_goal_g": "160",
            "fat_priority": "urgent", "muscle_priority": "gain", "social_priority": "priority",
            "height_cm": "180.0", "birth_date": "1990-01-01", "biological_sex": "male",
        })
        self.assertRedirects(response, reverse("dashboard:settings"))
        day = DayRecord.objects.get(pk=day.pk)
        self.assertEqual(_latest_weight(day), 80)
        self.assertEqual(body_profile_for_day(day)["biological_sex"], "male")
        day = recalculate_day(day)

        self.assertEqual(day.configuration_snapshot, original_snapshot)
        self.assertGreater(day.module_breakdowns["activity"]["base_kcal"], 0)
        self.assertEqual(_calorie_balance(day)["missing_base_fields"], [])
        self.assertTrue(day.module_breakdowns["activity"]["not_captured"])

    def test_recorded_profile_values_are_not_replaced_by_current_settings(self):
        day = get_or_create_day(timezone.localdate() - dt.timedelta(days=1))
        day.configuration_snapshot["body_profile"] = {
            "height_cm": "170", "birth_date": "1985-01-01", "biological_sex": "female",
        }
        GlobalConfiguration.objects.create(height_cm="180", birth_date=dt.date(1990, 1, 1), biological_sex="male")

        self.assertEqual(body_profile_for_day(day), day.configuration_snapshot["body_profile"])
