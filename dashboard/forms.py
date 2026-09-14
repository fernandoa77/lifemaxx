from decimal import Decimal

from django import forms
from django.utils import timezone

from .models import Activity, BodyEntry, BodyPhoto, GlobalConfiguration, Meal, MentalEntry, SleepEntry, SocialEntry, Supplement


class StyledModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css = "control"
            if isinstance(field.widget, forms.CheckboxInput):
                css = "checkbox"
            field.widget.attrs.setdefault("class", css)


class BodyForm(StyledModelForm):
    class Meta:
        model = BodyEntry
        fields = ("weight_am_kg", "weight_pm_kg", "abdomen_cm", "visual_fat_percent", "muscularity_rating", "face_rating", "body_rating", "llm_description")
        labels = {
            "weight_am_kg": "Peso AM (kg)", "weight_pm_kg": "Peso PM (kg)", "abdomen_cm": "Panza (cm)",
            "visual_fat_percent": "Grasa visual (%)", "muscularity_rating": "Muscularidad (0-10)",
            "face_rating": "Rating facial (0-10)", "body_rating": "Rating corporal (0-10)",
            "llm_description": "Descripcion del analisis",
        }
        widgets = {"llm_description": forms.Textarea(attrs={"rows": 4})}


class BodyPhotoForm(StyledModelForm):
    class Meta:
        model = BodyPhoto
        fields = ("kind", "image")
        labels = {"kind": "Toma", "image": "Fotografia original"}


class MealForm(StyledModelForm):
    process_with_ai = forms.BooleanField(required=False, initial=False, label="Analizar con IA al guardar")

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


class SleepForm(StyledModelForm):
    class Meta:
        model = SleepEntry
        fields = ("no_sleep", "fell_asleep_at", "woke_up_at", "adjustment_minutes", "rising_category", "description")
        labels = {
            "no_sleep": "No dormi", "fell_asleep_at": "Me dormi", "woke_up_at": "Desperte",
            "adjustment_minutes": "Ajuste firmado (min)", "rising_category": "Tiempo para levantarme",
            "description": "Descripcion personal",
        }
        widgets = {
            "fell_asleep_at": forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}),
            "woke_up_at": forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}),
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["fell_asleep_at"].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["woke_up_at"].input_formats = ["%Y-%m-%dT%H:%M"]

    def clean(self):
        data = super().clean()
        if not data.get("no_sleep") and (not data.get("fell_asleep_at") or not data.get("woke_up_at")):
            raise forms.ValidationError("Captura ambas horas o marca No dormi.")
        return data


class MentalForm(StyledModelForm):
    class Meta:
        model = MentalEntry
        exclude = ("day", "prior_streak", "resulting_streak", "created_at", "updated_at")
        labels = {
            "passive_positive_minutes": "Pasivo positivo (min)", "passive_positive_description": "Contexto pasivo positivo",
            "passive_intermediate_minutes": "Pasivo intermedio (min)", "passive_intermediate_description": "Contexto pasivo intermedio",
            "passive_negative_minutes": "Pasivo negativo (min)", "passive_negative_description": "Contexto pasivo negativo",
            "active_intermediate_minutes": "Activo intermedio (min)", "active_intermediate_description": "Contexto activo intermedio",
            "active_positive_minutes": "Activo positivo (min)", "active_positive_description": "Contexto activo positivo",
            "broken_glasses": "Copas rotas", "elo": "Elo", "solved_problems": "Problemas resueltos",
            "soa_exercises": "Ejercicios SOA", "personal_commits": "Commits personales",
        }
        widgets = {
            "passive_positive_description": forms.Textarea(attrs={"rows": 2}),
            "passive_intermediate_description": forms.Textarea(attrs={"rows": 2}),
            "passive_negative_description": forms.Textarea(attrs={"rows": 2}),
            "active_intermediate_description": forms.Textarea(attrs={"rows": 2}),
            "active_positive_description": forms.Textarea(attrs={"rows": 2}),
        }
        help_texts = {
            "passive_positive_minutes": "Ejemplo: lectura.",
            "passive_intermediate_minutes": "X/Twitter en computadora, YouTube o pelicula valida.",
            "passive_negative_minutes": "Scroll y consumo pasivo negativo.",
            "active_intermediate_minutes": "Ajedrez, puzzles, soroban o investigacion con ChatGPT.",
            "active_positive_minutes": "SOA, programacion personal, marca personal o reuniones constructivas.",
        }


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
            "hour_value_mxn", "calorie_goal", "protein_goal_g", "fat_priority", "muscle_priority", "social_priority",
            "height_cm", "birth_date", "biological_sex",
        )
        labels = {
            "hour_value_mxn": "Valor de H (MXN)", "calorie_goal": "Objetivo calorico", "protein_goal_g": "Objetivo proteico (g)",
            "fat_priority": "Prioridad de grasa", "muscle_priority": "Prioridad de musculo",
            "social_priority": "Prioridad de convivencia target", "height_cm": "Estatura fija (cm)",
            "birth_date": "Fecha de nacimiento", "biological_sex": "Sexo biologico (calculo energetico)",
        }
        widgets = {"birth_date": forms.DateInput(attrs={"type": "date"})}

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
