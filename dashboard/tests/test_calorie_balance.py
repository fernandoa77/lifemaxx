from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from dashboard.views import _calorie_balance


class CalorieBalanceTests(SimpleTestCase):
    def test_deficit_and_surplus_use_total_expenditure(self):
        day = SimpleNamespace(module_breakdowns={
            "nutrition": {"calories": 1800},
            "activity": {"base_kcal": 2000, "active_kcal": 300},
        })
        result = _calorie_balance(day)
        self.assertEqual(result["status"], "deficit")
        self.assertEqual(result["difference"], 500)

        day.module_breakdowns["nutrition"]["calories"] = 2500
        result = _calorie_balance(day)
        self.assertEqual(result["status"], "surplus")
        self.assertEqual(result["difference"], -200)

    def test_missing_base_or_captures_never_claims_a_deficit(self):
        day = SimpleNamespace(module_breakdowns={
            "nutrition": {"calories": 1800},
            "activity": {"base_kcal": 0, "active_kcal": 300},
        })
        self.assertFalse(_calorie_balance(day)["available"])
        day.module_breakdowns["activity"] = {"base_kcal": 2000, "active_kcal": 300, "not_captured": True}
        self.assertIsNone(_calorie_balance(day)["difference"])
        day.module_breakdowns["activity"].pop("not_captured")
        day.module_breakdowns["nutrition"]["not_captured"] = True
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
