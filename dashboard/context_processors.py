from django.utils import timezone

from .services.pricing import current_streak


def global_context(request):
    return {"today": timezone.localdate(), "global_streak": current_streak()}
