import datetime as dt
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from dashboard.models import BodyEntry, MentalEntry, SectionState, SleepEntry, SocialEntry
from dashboard.services.pricing import get_or_create_day


class InlineEditTests(TestCase):
    date = dt.date(2099, 12, 30)

    def setUp(self):
        self.day = get_or_create_day(self.date)

    def save(self, module, field, value):
        return self.client.post(
            reverse("dashboard:module", args=(self.date.isoformat(), module)),
            {"action": "inline-save", "field": field, "value": value},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    def test_body_edit_updates_only_selected_field(self):
        body = BodyEntry.objects.create(day=self.day, weight_am_kg=Decimal("80"), weight_pm_kg=Decimal("81"))
        response = self.save("body", "weight_am_kg", "79.50")
        body.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body.weight_am_kg, Decimal("79.50"))
        self.assertEqual(body.weight_pm_kg, Decimal("81"))

    def test_nutrition_notes_save_without_capturing_module(self):
        response = self.save("nutrition", "nutrition_notes", "Más agua")
        self.day.refresh_from_db()
        state = SectionState.objects.get(day=self.day, module="nutrition")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.day.nutrition_notes, "Más agua")
        self.assertFalse(state.captured)

    def test_sleep_fields_save_independently_and_no_sleep_clears_times(self):
        self.assertEqual(self.save("sleep", "fell_asleep_at", "2099-12-30T23:15").status_code, 200)
        self.assertEqual(self.save("sleep", "woke_up_at", "2099-12-31T07:00").status_code, 200)
        response = self.save("sleep", "no_sleep", "true")
        sleep = SleepEntry.objects.get(day=self.day)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(sleep.no_sleep)
        self.assertIsNone(sleep.fell_asleep_at)
        self.assertIsNone(sleep.woke_up_at)

    def test_choice_returns_human_display(self):
        response = self.save("sleep", "rising_category", "medium")
        self.assertEqual(response.json()["display"], "1-15 min")

    def test_mental_minutes_reject_more_than_three_digits(self):
        response = self.save("mental", "passive_positive_minutes", "1000")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(MentalEntry.objects.get(day=self.day).passive_positive_minutes, 0)

    def test_social_inline_text_does_not_overwrite_minutes(self):
        social = SocialEntry.objects.create(day=self.day, family_minutes=45)
        response = self.save("social", "journal", "Cena familiar")
        social.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(social.journal, "Cena familiar")
        self.assertEqual(social.family_minutes, 45)

    def test_unapproved_field_is_rejected(self):
        response = self.save("mental", "solved_problems", "3")
        self.assertEqual(response.status_code, 422)
