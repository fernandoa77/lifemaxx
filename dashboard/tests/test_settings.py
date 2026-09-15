import datetime as dt

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from dashboard.models import AuditRevision, DayRecord, GlobalConfiguration
from dashboard.services.pricing import get_or_create_day


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
