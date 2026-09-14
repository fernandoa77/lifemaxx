from decimal import Decimal

from django import forms
from django.utils import timezone

from .models import Activity, BodyEntry, BodyPhoto, DayRecord, GlobalConfiguration, Meal, MentalEntry, SleepEntry, SocialEntry, Supplement


class StyledModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css = "control"
            if isinstance(field.widget, forms.CheckboxInput):
                css = "checkbox"
            field.widget.attrs.setdefault("class", css)


class BodyMeasurementsForm(StyledModelForm):
    class Meta:
        model = BodyEntry
        fields = ("weight_am_kg", "weight_pm_kg", "abdomen_cm")
        labels = {
            "weight_am_kg": "Peso AM (kg)", "weight_pm_kg": "Peso PM (kg)", "abdomen_cm": "Panza (cm)",
        }


class BodyAnalysisForm(StyledModelForm):
    class Meta:
        model = BodyEntry
        fields = ("visual_fat_percent", "muscularity_rating", "face_rating", "body_rating", "llm_description")
        labels = {
            "visual_fat_percent": "Grasa visual (%)", "muscularity_rating": "Muscularidad (0-10)",
            "face_rating": "Rating facial (0-10)", "body_rating": "Rating corporal (0-10)",
            "llm_description": "Descripcion del analisis",
        }
        widgets = {"llm_description": forms.Textarea(attrs={"rows": 4})}


class BodyPhotoPackageForm(forms.Form):
    body_front = forms.ImageField(label="Cuerpo frontal")
    body_side = forms.ImageField(label="Cuerpo lateral")
    body_back = forms.ImageField(label="Cuerpo posterior")
    face_front = forms.ImageField(label="Rostro frontal")
    face_side = forms.ImageField(label="Rostro lateral")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.widget.attrs.update({"class": "photo-package-input", "accept": "image/*", "data-photo-kind": name})


class BodySinglePhotoForm(forms.Form):
    kind = forms.ChoiceField(choices=BodyPhoto.TYPES)
    photo = forms.ImageField()


class MealForm(StyledModelForm):
    foods_json = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = Meal
        fields = (
            "eaten_at", "description", "photo", "calories", "protein_g", "carbs_g", "fat_g", "fiber_g",
            "alcoholic_drink", "beverage_volume_ml", "alcohol_abv_percent", "pure_alcohol_ml",
        )
        labels = {
            "eaten_at": "Hora", "description": "Descripcion libre", "photo": "Foto",
            "calories": "Calorias", "protein_g": "Proteina (g)", "carbs_g": "Carbohidratos (g)",
            "fat_g": "Grasas (g)", "fiber_g": "Fibra (g)", "alcoholic_drink": "Bebida alcoholica",
            "beverage_volume_ml": "Volumen (ml)", "alcohol_abv_percent": "Graduacion (%)",
            "pure_alcohol_ml": "Alcohol puro (ml)",
        }
        widgets = {"eaten_at": forms.TimeInput(attrs={"type": "time"}), "description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("calories", "protein_g", "carbs_g", "fat_g", "fiber_g", "beverage_volume_ml", "alcohol_abv_percent", "pure_alcohol_ml"):
            self.fields[name].min_value = Decimal("0")
        if not self.is_bound and not self.instance.pk:
            self.fields["eaten_at"].initial = timezone.localtime().strftime("%H:%M")
        if not self.is_bound and self.instance.pk:
            import json
            self.fields["foods_json"].initial = json.dumps(self.instance.foods, ensure_ascii=False)


class NutritionNotesForm(StyledModelForm):
    class Meta:
        model = DayRecord
        fields = ("nutrition_notes",)
        labels = {"nutrition_notes": "Notas del dia"}
        widgets = {"nutrition_notes": forms.Textarea(attrs={"rows": 3, "placeholder": "Notas generales de nutricion"})}


class ActivityForm(StyledModelForm):
    class Meta:
        model = Activity
        fields = ("category", "amount", "description")
        labels = {"category": "Categoria", "amount": "Tiempo o cantidad", "description": "Descripcion opcional"}
        widgets = {"description": forms.Textarea(attrs={"rows": 2})}


class SupplementForm(StyledModelForm):
    class Meta:
        model = Supplement
        fields = ("taken_at", "name", "dose", "unit", "notes")
        labels = {"taken_at": "Hora", "name": "Suplemento", "dose": "Dosis", "unit": "Unidad", "notes": "Notas"}
        widgets = {"taken_at": forms.TimeInput(attrs={"type": "time"}), "notes": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.fields["taken_at"].initial = timezone.localtime().strftime("%H:%M")


class SleepForm(StyledModelForm):
    class Meta:
        model = SleepEntry
        fields = ("no_sleep", "fell_asleep_at", "woke_up_at", "adjustment_minutes", "rising_category", "description")
        labels = {
            "no_sleep": "No dormí", "fell_asleep_at": "Me dormí", "woke_up_at": "Desperté",
            "adjustment_minutes": "Ajuste por siestas y despertares (min)", "rising_category": "Tiempo para levantarme hoy",
            "description": "Descripcion personal",
        }
        widgets = {
            "fell_asleep_at": forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}),
            "woke_up_at": forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}),
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, rising_blocked=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["fell_asleep_at"].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["woke_up_at"].input_formats = ["%Y-%m-%dT%H:%M"]
        self.order_fields([
            "rising_category", "no_sleep", "fell_asleep_at", "woke_up_at",
            "adjustment_minutes", "description",
        ])
        self.rising_blocked = rising_blocked
        if rising_blocked:
            self.initial["rising_category"] = "na"
            self.fields["rising_category"].disabled = True

    def clean(self):
        data = super().clean()
        if self.rising_blocked:
            data["rising_category"] = "na"
        start, end = data.get("fell_asleep_at"), data.get("woke_up_at")
        if bool(start) != bool(end):
            raise forms.ValidationError("Las horas de dormir y despertar se guardan juntas.")
        if data.get("no_sleep"):
            data["fell_asleep_at"] = None
            data["woke_up_at"] = None
            data["adjustment_minutes"] = 0
        return data


class MentalForm(StyledModelForm):
    class Meta:
        model = MentalEntry
        fields = (
            "passive_positive_minutes", "passive_positive_description",
            "passive_intermediate_minutes", "passive_intermediate_description",
            "passive_negative_minutes", "passive_negative_description",
            "active_intermediate_minutes", "active_intermediate_description",
            "active_positive_minutes", "active_positive_description",
            "broken_glasses", "elo", "soa_exercises", "personal_commits",
        )
        labels = {
            "passive_positive_minutes": "Min", "passive_positive_description": "Contexto",
            "passive_intermediate_minutes": "Min", "passive_intermediate_description": "Contexto",
            "passive_negative_minutes": "Min", "passive_negative_description": "Contexto",
            "active_intermediate_minutes": "Min", "active_intermediate_description": "Contexto",
            "active_positive_minutes": "Min", "active_positive_description": "Contexto",
            "broken_glasses": "Copas rotas", "elo": "Cambio ELO",
            "soa_exercises": "Ejercicios SOA", "personal_commits": "Commits personales",
        }
        widgets = {
            "passive_positive_description": forms.Textarea(attrs={"rows": 2}),
            "passive_intermediate_description": forms.Textarea(attrs={"rows": 2}),
            "passive_negative_description": forms.Textarea(attrs={"rows": 2}),
            "active_intermediate_description": forms.Textarea(attrs={"rows": 2}),
            "active_positive_description": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in (
            "passive_positive_minutes", "passive_intermediate_minutes", "passive_negative_minutes",
            "active_intermediate_minutes", "active_positive_minutes",
        ):
            self.fields[name].max_value = 999
            self.fields[name].widget.attrs.update({"max": "999", "inputmode": "numeric"})


class SocialForm(StyledModelForm):
    class Meta:
        model = SocialEntry
        exclude = ("day", "rewarded_minutes", "created_at", "updated_at")
        labels = {
            "family_minutes": "Familia (min)", "friends_minutes": "Amigos (min)",
            "mixed_friends_minutes": "Mixto / amigas (min)", "mixed_target_minutes": "Mixto target (min)",
            "target_friends_minutes": "Amigas target (min)", "journal": "Journal social",
        }
        widgets = {"journal": forms.Textarea(attrs={"rows": 4})}


class ConfigurationForm(StyledModelForm):
    class Meta:
        model = GlobalConfiguration
        fields = (
            "challenge_start_date", "hour_value_mxn", "calorie_goal", "protein_goal_g", "fat_priority", "muscle_priority", "social_priority",
            "height_cm", "birth_date", "biological_sex",
        )
        labels = {
            "challenge_start_date": "Fecha de inicio del reto", "hour_value_mxn": "Valor de H (MXN)", "calorie_goal": "Objetivo calorico", "protein_goal_g": "Objetivo proteico (g)",
            "fat_priority": "Prioridad de grasa", "muscle_priority": "Prioridad de musculo",
            "social_priority": "Prioridad de convivencia target", "height_cm": "Estatura fija (cm)",
            "birth_date": "Fecha de nacimiento", "biological_sex": "Sexo biologico (calculo energetico)",
        }
        widgets = {"challenge_start_date": forms.DateInput(attrs={"type": "date"}), "birth_date": forms.DateInput(attrs={"type": "date"})}

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.pk = None
        instance.effective_from = timezone.now()
        current = GlobalConfiguration.objects.order_by("-effective_from", "-pk").first()
        if current:
            instance.pricing_versions = current.pricing_versions.copy()
        if commit:
            instance.save()
        return instance


class AdjustmentForm(forms.Form):
    adjustment_h = forms.DecimalField(max_digits=10, decimal_places=4, label="Ajuste firmado (H)", widget=forms.NumberInput(attrs={"class": "control", "step": "0.01"}))
    adjustment_justification = forms.CharField(required=False, label="Justificacion", widget=forms.Textarea(attrs={"class": "control", "rows": 3}))

    def clean(self):
        data = super().clean()
        if data.get("adjustment_h", Decimal("0")) != 0 and not (data.get("adjustment_justification") or "").strip():
            self.add_error("adjustment_justification", "Es obligatoria cuando el ajuste es distinto de cero.")
        return data
