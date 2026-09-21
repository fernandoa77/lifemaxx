import datetime as dt
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from dashboard.views import _calorie_balance
from dashboard.services.pricing import _base_energy


class CalorieBalanceTests(TestCase):
    def test_unspecified_sex_does_not_assume_a_base_expenditure(self):
        day = SimpleNamespace(date=dt.date(2026, 9, 14), configuration_snapshot={
            "body_profile": {"height_cm": "170", "birth_date": "1990-01-01", "biological_sex": "unspecified"},
        })
        self.assertEqual(_base_energy(day, 80), 0)

    def test_deficit_and_surplus_use_total_expenditure(self):
        day = SimpleNamespace(module_breakdowns={
            "nutrition": {"calories": 1800},
            "activity": {"base_kcal": 2000, "active_kcal": 300},
        }, configuration_snapshot={"body_profile": {"height_cm": "170", "birth_date": "1990-01-01", "biological_sex": "male"}})
        with patch("dashboard.views._latest_weight", return_value=80):
            result = _calorie_balance(day)
        self.assertEqual(result["status"], "deficit")
        self.assertEqual(result["difference"], 500)

        day.module_breakdowns["nutrition"]["calories"] = 2500
        with patch("dashboard.views._latest_weight", return_value=80):
            result = _calorie_balance(day)
        self.assertEqual(result["status"], "surplus")
        self.assertEqual(result["difference"], -200)

    def test_missing_base_or_captures_never_claims_a_deficit(self):
        day = SimpleNamespace(module_breakdowns={
            "nutrition": {"calories": 1800},
            "activity": {"base_kcal": 0, "active_kcal": 300},
        }, configuration_snapshot={"body_profile": {"height_cm": "170", "birth_date": "1990-01-01", "biological_sex": "male"}})
        with patch("dashboard.views._latest_weight", return_value=0):
            result = _calorie_balance(day)
        self.assertFalse(result["available"])
        self.assertEqual(result["missing_base_fields"], ["peso AM"])
        day.module_breakdowns["activity"] = {"base_kcal": 2000, "active_kcal": 300, "not_captured": True}
        with patch("dashboard.views._latest_weight", return_value=80):
            self.assertIsNone(_calorie_balance(day)["difference"])
        day.module_breakdowns["activity"].pop("not_captured")
        day.module_breakdowns["nutrition"]["not_captured"] = True
        with patch("dashboard.views._latest_weight", return_value=80):
            self.assertIsNone(_calorie_balance(day)["difference"])


class CalorieBalancePageTests(TestCase):
    def test_balance_is_visible_on_day_and_nutrition_pages(self):
        user = get_user_model().objects.create_user("balance-viewer", password="test-password-123")
        self.client.force_login(user)
        date = "2099-12-30"
        for url in (reverse("dashboard:day", args=(date,)), reverse("dashboard:module", args=(date, "nutrition"))):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "¿Déficit o superávit?")
            self.assertContains(response, "Balance pendiente")
