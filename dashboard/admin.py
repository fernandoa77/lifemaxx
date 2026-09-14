from django.contrib import admin

from .models import (
    Activity, AuditRevision, BodyEntry, BodyPhoto, DayRecord, GlobalConfiguration,
    Meal, MentalEntry, SectionState, SleepEntry, SocialEntry, SourceSubmission, Supplement,
)


@admin.register(GlobalConfiguration)
class ConfigurationAdmin(admin.ModelAdmin):
    list_display = ("effective_from", "hour_value_mxn", "calorie_goal", "protein_goal_g", "fat_priority", "muscle_priority", "social_priority")
    readonly_fields = ("created_at", "updated_at")


@admin.register(DayRecord)
class DayRecordAdmin(admin.ModelAdmin):
    list_display = ("date", "status", "automatic_value_h", "adjustment_h", "final_value_h", "calculated_at")
    list_filter = ("status",)
    search_fields = ("date",)
    readonly_fields = ("configuration_snapshot", "module_values_h", "module_breakdowns", "calculated_at", "created_at", "updated_at")


admin.site.register([SectionState, BodyEntry, BodyPhoto, Meal, Supplement, Activity, SleepEntry, MentalEntry, SocialEntry, SourceSubmission, AuditRevision])
