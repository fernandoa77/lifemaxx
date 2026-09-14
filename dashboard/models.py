from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


def default_pricing_versions():
    return {
        "body": "body-1.0",
        "nutrition": "nutrition-1.0",
        "activity": "activity-1.0",
        "sleep": "sleep-1.0",
        "mental": "mental-1.0",
        "social": "social-1.0",
    }


def default_challenge_start_date():
    return date(2026, 9, 13)


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class GlobalConfiguration(TimestampedModel):
    class FatPriority(models.TextChoices):
        MAINTAIN = "maintain", "Mantener"
        LOSE = "lose", "Bajar"
        URGENT = "urgent", "Bajar urgente"

    class MusclePriority(models.TextChoices):
        MAINTAIN = "maintain", "Mantener"
        GAIN = "gain", "Subir"
        URGENT = "urgent", "Subir urgente"

    class SocialPriority(models.TextChoices):
        LOW = "low", "Baja"
        MEDIUM = "medium", "Media"
        PRIORITY = "priority", "Prioritaria"

    effective_from = models.DateTimeField(default=timezone.now, db_index=True)
    challenge_start_date = models.DateField(default=default_challenge_start_date)
    hour_value_mxn = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("250.00"))
    calorie_goal = models.PositiveIntegerField(default=2200)
    protein_goal_g = models.PositiveIntegerField(default=160)
    fat_priority = models.CharField(max_length=16, choices=FatPriority.choices, default=FatPriority.URGENT)
    muscle_priority = models.CharField(max_length=16, choices=MusclePriority.choices, default=MusclePriority.GAIN)
    social_priority = models.CharField(max_length=16, choices=SocialPriority.choices, default=SocialPriority.PRIORITY)
    pricing_versions = models.JSONField(default=default_pricing_versions)

    # Perfil corporal versionado que alimenta el gasto base reproducible.
    height_cm = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    biological_sex = models.CharField(
        max_length=12,
        choices=(("male", "Masculino"), ("female", "Femenino"), ("unspecified", "Sin especificar")),
        default="unspecified",
    )

    class Meta:
        ordering = ["-effective_from", "-pk"]
        verbose_name = "configuración global"
        verbose_name_plural = "configuraciones globales"

    def snapshot(self):
        return {
            "configuration_id": self.pk,
            "effective_from": self.effective_from.isoformat(),
            "challenge_start_date": self.challenge_start_date.isoformat(),
            "hour_value_mxn": str(self.hour_value_mxn),
            "calorie_goal": self.calorie_goal,
            "protein_goal_g": self.protein_goal_g,
            "fat_priority": self.fat_priority,
            "muscle_priority": self.muscle_priority,
            "social_priority": self.social_priority,
            "pricing_versions": self.pricing_versions,
            "body_profile": {
                "height_cm": str(self.height_cm) if self.height_cm is not None else None,
                "birth_date": self.birth_date.isoformat() if self.birth_date else None,
                "biological_sex": self.biological_sex,
            },
        }

    def __str__(self):
        return f"Configuración desde {timezone.localtime(self.effective_from):%d/%m/%Y %H:%M}"


class DayRecord(TimestampedModel):
    class Status(models.TextChoices):
        PROGRESS = "progress", "En progreso"
        COMPLETE = "complete", "Completo"
        PENDING = "pending", "Con pendientes"

    date = models.DateField(unique=True, db_index=True)
    configuration_snapshot = models.JSONField(default=dict)
    module_values_h = models.JSONField(default=dict)
    module_breakdowns = models.JSONField(default=dict)
    automatic_value_h = models.DecimalField(max_digits=12, decimal_places=4, default=Decimal("0"))
    adjustment_h = models.DecimalField(max_digits=10, decimal_places=4, default=Decimal("0"))
    adjustment_mxn = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    adjustment_justification = models.TextField(blank=True)
    final_value_h = models.DecimalField(max_digits=12, decimal_places=4, default=Decimal("0"))
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PROGRESS)
    pending_reasons = models.JSONField(default=list)
    nutrition_notes = models.TextField(blank=True)
    calculated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-date"]

    @property
    def hour_value_mxn(self):
        return Decimal(str(self.configuration_snapshot.get("hour_value_mxn", "250")))

    @property
    def final_value_mxn(self):
        return (self.final_value_h * self.hour_value_mxn).quantize(Decimal("0.01"))

    def clean(self):
        if self.adjustment_h and not self.adjustment_justification.strip():
            raise ValidationError({"adjustment_justification": "La justificación es obligatoria para un ajuste distinto de cero."})

    def __str__(self):
        return self.date.isoformat()


class SectionState(TimestampedModel):
    MODULES = (
        ("body", "Progreso corporal"),
        ("nutrition", "Nutrición"),
        ("activity", "Actividad física"),
        ("sleep", "Sueño"),
        ("mental", "Mental y digital"),
        ("social", "Vida social"),
    )
    PROCESSING = (
        ("idle", "Sin proceso"),
        ("processing", "Procesando"),
        ("done", "Procesado"),
        ("correction", "Requiere corrección"),
        ("error", "Error"),
    )

    day = models.ForeignKey(DayRecord, on_delete=models.CASCADE, related_name="section_states")
    module = models.CharField(max_length=16, choices=MODULES)
    captured = models.BooleanField(default=False)
    processing_status = models.CharField(max_length=16, choices=PROCESSING, default="idle")
    error_message = models.TextField(blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("day", "module"), name="unique_day_module_state")]


class BodyEntry(TimestampedModel):
    day = models.OneToOneField(DayRecord, on_delete=models.CASCADE, related_name="body")
    weight_am_kg = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    weight_pm_kg = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    abdomen_cm = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    visual_fat_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    muscularity_rating = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    face_rating = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    body_rating = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    llm_description = models.TextField(blank=True)
    analysis_json = models.JSONField(default=dict)


class BodyPhoto(TimestampedModel):
    TYPES = (
        ("body_front", "Cuerpo frontal"),
        ("body_side", "Cuerpo lateral"),
        ("body_back", "Cuerpo posterior"),
        ("face_front", "Rostro frontal"),
        ("face_side", "Rostro lateral"),
    )
    body = models.ForeignKey(BodyEntry, on_delete=models.CASCADE, related_name="photos")
    kind = models.CharField(max_length=20, choices=TYPES)
    image_url = models.URLField(max_length=1000, blank=True)
    image_file_id = models.CharField(max_length=160, blank=True, editable=False)
    captured_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("body", "kind"), name="unique_body_photo_kind")]


class Meal(TimestampedModel):
    day = models.ForeignKey(DayRecord, on_delete=models.CASCADE, related_name="meals")
    eaten_at = models.TimeField(null=True, blank=True)
    description = models.TextField(blank=True)
    photo = models.ImageField(upload_to="meals/%Y/%m/%d/", blank=True)
    foods = models.JSONField(default=list)
    calories = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0"))
    protein_g = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0"))
    carbs_g = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0"))
    fat_g = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0"))
    fiber_g = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0"))
    alcoholic_drink = models.CharField(max_length=120, blank=True)
    beverage_volume_ml = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0"))
    alcohol_abv_percent = models.DecimalField(max_digits=6, decimal_places=3, default=Decimal("0"))
    pure_alcohol_ml = models.DecimalField(max_digits=8, decimal_places=3, default=Decimal("0"))
    corrected_manually = models.BooleanField(default=False)
    ai_result = models.JSONField(default=dict)


class Supplement(TimestampedModel):
    day = models.ForeignKey(DayRecord, on_delete=models.CASCADE, related_name="supplements")
    taken_at = models.TimeField(null=True, blank=True)
    name = models.CharField(max_length=120)
    dose = models.DecimalField(max_digits=9, decimal_places=2, default=Decimal("0"))
    unit = models.CharField(max_length=30, default="mg")
    notes = models.TextField(blank=True)


class Activity(TimestampedModel):
    CATEGORIES = (
        ("steps", "Pasos intencionales"),
        ("pushups", "Lagartijas"),
        ("functional_moderate", "Funcional moderado"),
        ("functional_intense", "Funcional intenso"),
        ("gym", "Gimnasio"),
    )
    UNITS = {"steps": "pasos", "pushups": "repeticiones", "functional_moderate": "minutos", "functional_intense": "minutos", "gym": "minutos"}
    day = models.ForeignKey(DayRecord, on_delete=models.CASCADE, related_name="activities")
    category = models.CharField(max_length=24, choices=CATEGORIES)
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    unit = models.CharField(max_length=20, editable=False)
    description = models.TextField(blank=True)
    coefficient_version = models.CharField(max_length=24, default="energy-1.0")
    estimated_active_kcal = models.DecimalField(max_digits=9, decimal_places=2, default=Decimal("0"))

    def save(self, *args, **kwargs):
        self.unit = self.UNITS[self.category]
        super().save(*args, **kwargs)


class SleepEntry(TimestampedModel):
    RISING = (
        ("quick", "0-1 min"),
        ("medium", "1-15 min"),
        ("slow", "Mas de 15 min"),
        ("na", "No aplica / no dormi"),
    )
    day = models.OneToOneField(DayRecord, on_delete=models.CASCADE, related_name="sleep")
    fell_asleep_at = models.DateTimeField(null=True, blank=True)
    woke_up_at = models.DateTimeField(null=True, blank=True)
    adjustment_minutes = models.IntegerField(default=0)
    rising_category = models.CharField(max_length=10, choices=RISING, default="quick")
    description = models.TextField(blank=True)
    no_sleep = models.BooleanField(default=False)
    total_sleep_minutes = models.IntegerField(default=0)
    midpoint_minute = models.IntegerField(null=True, blank=True)
    circadian_reference_minute = models.IntegerField(null=True, blank=True)
    circadian_deviation_minutes = models.IntegerField(null=True, blank=True)


class MentalEntry(TimestampedModel):
    day = models.OneToOneField(DayRecord, on_delete=models.CASCADE, related_name="mental")
    passive_positive_minutes = models.PositiveIntegerField(default=0)
    passive_positive_description = models.TextField(blank=True)
    passive_intermediate_minutes = models.PositiveIntegerField(default=0)
    passive_intermediate_description = models.TextField(blank=True)
    passive_negative_minutes = models.PositiveIntegerField(default=0)
    passive_negative_description = models.TextField(blank=True)
    active_intermediate_minutes = models.PositiveIntegerField(default=0)
    active_intermediate_description = models.TextField(blank=True)
    active_positive_minutes = models.PositiveIntegerField(default=0)
    active_positive_description = models.TextField(blank=True)
    broken_glasses = models.PositiveIntegerField(default=0)
    elo = models.IntegerField(null=True, blank=True)
    solved_problems = models.PositiveIntegerField(default=0)
    soa_exercises = models.PositiveIntegerField(default=0)
    personal_commits = models.PositiveIntegerField(default=0)
    prior_streak = models.PositiveIntegerField(default=0)
    resulting_streak = models.PositiveIntegerField(default=0)


class SocialEntry(TimestampedModel):
    day = models.OneToOneField(DayRecord, on_delete=models.CASCADE, related_name="social")
    family_minutes = models.PositiveIntegerField(default=0)
    friends_minutes = models.PositiveIntegerField(default=0)
    mixed_friends_minutes = models.PositiveIntegerField(default=0)
    mixed_target_minutes = models.PositiveIntegerField(default=0)
    target_friends_minutes = models.PositiveIntegerField(default=0)
    journal = models.TextField(blank=True)
    rewarded_minutes = models.JSONField(default=dict)


class SourceSubmission(TimestampedModel):
    STATUSES = (
        ("draft", "Borrador"),
        ("sent", "Enviado"),
        ("processing", "Procesando"),
        ("processed", "Procesado"),
        ("correction", "Requiere correccion"),
        ("error", "Error"),
    )
    day = models.ForeignKey(DayRecord, on_delete=models.CASCADE, related_name="source_submissions")
    module = models.CharField(max_length=16, choices=SectionState.MODULES)
    source_text = models.TextField(blank=True)
    source_file = models.FileField(upload_to="sources/%Y/%m/%d/", blank=True)
    status = models.CharField(max_length=16, choices=STATUSES, default="draft")
    prompt_version = models.CharField(max_length=32, default="1.0")
    model_used = models.CharField(max_length=160, blank=True)
    result_json = models.JSONField(default=dict)
    correction_json = models.JSONField(default=dict)
    error_message = models.TextField(blank=True)


class AuditRevision(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    day = models.ForeignKey(DayRecord, on_delete=models.CASCADE, related_name="revisions")
    object_type = models.CharField(max_length=60)
    object_id = models.PositiveBigIntegerField(null=True, blank=True)
    action = models.CharField(max_length=20, default="update")
    previous_data = models.JSONField(default=dict)
    new_data = models.JSONField(default=dict)
    note = models.CharField(max_length=240, blank=True)

    class Meta:
        ordering = ["-created_at"]
