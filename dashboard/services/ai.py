import base64
import json
import mimetypes
import time
import urllib.error
import urllib.request
from pathlib import Path

from django.conf import settings


class AIUnavailable(RuntimeError):
    pass


def _data_url(path):
    file_path = Path(path)
    mime = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    encoded = base64.b64encode(file_path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _uploaded_data_url(uploaded):
    mime = getattr(uploaded, "content_type", None) or mimetypes.guess_type(uploaded.name)[0] or "application/octet-stream"
    uploaded.seek(0)
    encoded = base64.b64encode(uploaded.read()).decode("ascii")
    uploaded.seek(0)
    return f"data:{mime};base64,{encoded}"


def request_structured_json(
    *,
    system_prompt,
    user_content,
    schema,
    schema_name,
    images=None,
    image_files=None,
    image_urls=None,
    model=None,
    context=None,
):
    """Punto unico de comunicacion con IA para cualquier modulo.

    La garantia tiene dos capas: instruccion explicita de salida JSON y
    ``response_format=json_schema`` estricto exigido al proveedor.
    """
    api_key = settings.OPENROUTER_API_KEY
    selected_model = model or settings.OPENROUTER_MODEL
    if not api_key or not selected_model:
        raise AIUnavailable("OpenRouter no esta configurado. Agrega OPENROUTER_API_KEY y OPENROUTER_MODEL.")

    system = (
        "Eres el motor de extraccion estructurada de LifeMax. "
        "Conserva la incertidumbre: no inventes alimentos, cantidades ni mediciones. "
        "Tu respuesta DEBE ser unicamente un objeto JSON valido que cumpla exactamente "
        "el JSON Schema recibido: sin markdown, explicaciones ni propiedades extra. "
        f"Tarea del modulo: {system_prompt}"
    )
    if context:
        system += f" Contexto verificable: {json.dumps(context, ensure_ascii=False)}"

    content = [{"type": "text", "text": str(user_content or "Analiza la evidencia adjunta.")}]
    for image_path in images or []:
        content.append({"type": "image_url", "image_url": {"url": _data_url(image_path)}})
    for image_file in image_files or []:
        content.append({"type": "image_url", "image_url": {"url": _uploaded_data_url(image_file)}})
    for image_url in image_urls or []:
        content.append({"type": "image_url", "image_url": {"url": image_url}})
    payload = {
        "model": selected_model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": schema_name, "strict": True, "schema": schema},
        },
        "provider": {
            "allow_fallbacks": True,
            "require_parameters": True,
            "data_collection": "deny",
        },
        "temperature": 0,
    }
    fallbacks = list(settings.OPENROUTER_FALLBACK_MODELS)
    if fallbacks:
        payload["models"] = [selected_model, *fallbacks]

    request = urllib.request.Request(
        f"{settings.OPENROUTER_BASE_URL.rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": settings.OPENROUTER_HTTP_REFERER,
            "X-OpenRouter-Title": settings.OPENROUTER_APP_TITLE,
        },
        method="POST",
    )
    retryable = {408, 409, 425, 429, 500, 502, 503, 504}
    attempts = max(1, settings.OPENROUTER_RETRIES)
    body = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=settings.OPENROUTER_TIMEOUT) as response:
                body = json.loads(response.read().decode("utf-8"))
                break
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:600]
            if exc.code in retryable and attempt < attempts - 1:
                time.sleep(2 * (attempt + 1))
                continue
            raise AIUnavailable(f"OpenRouter rechazo la solicitud ({exc.code}): {detail}") from exc
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            if attempt < attempts - 1:
                time.sleep(2 * (attempt + 1))
                continue
            raise AIUnavailable(f"OpenRouter no respondio: {exc}") from exc

    try:
        message = body["choices"][0]["message"]
        raw = message["content"]
        if isinstance(raw, list):
            raw = "".join(part.get("text", "") for part in raw if isinstance(part, dict))
        data = json.loads(raw) if isinstance(raw, str) else raw
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise AIUnavailable("OpenRouter devolvio una salida que no es JSON valido.") from exc
    if not isinstance(data, dict):
        raise AIUnavailable("La salida estructurada no es un objeto JSON.")
    return {"data": data, "model": body.get("model", selected_model), "provider": body.get("provider", "openrouter")}


MEAL_SCHEMA = {
    "type": "object",
    "properties": {
        "foods": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "quantity": {"type": "number"},
                    "unit": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["name", "quantity", "unit", "confidence"],
                "additionalProperties": False,
            },
        },
        "calories": {"type": "number", "minimum": 0},
        "protein_g": {"type": "number", "minimum": 0},
        "carbs_g": {"type": "number", "minimum": 0},
        "fat_g": {"type": "number", "minimum": 0},
        "fiber_g": {"type": "number", "minimum": 0},
        "alcoholic_drink": {"type": "string"},
        "beverage_volume_ml": {"type": "number", "minimum": 0},
        "alcohol_abv_percent": {"type": "number", "minimum": 0, "maximum": 100},
        "pure_alcohol_ml": {"type": "number", "minimum": 0},
        "notes": {"type": "string"},
    },
    "required": ["foods", "calories", "protein_g", "carbs_g", "fat_g", "fiber_g", "alcoholic_drink", "beverage_volume_ml", "alcohol_abv_percent", "pure_alcohol_ml", "notes"],
    "additionalProperties": False,
}


BODY_SCHEMA = {
    "type": "object",
    "properties": {
        "visual_fat_percent": {"type": ["number", "null"], "minimum": 0, "maximum": 70},
        "muscularity_rating": {"type": ["number", "null"], "minimum": 0, "maximum": 10},
        "face_rating": {"type": ["number", "null"], "minimum": 0, "maximum": 10},
        "body_rating": {"type": ["number", "null"], "minimum": 0, "maximum": 10},
        "description": {"type": "string"},
        "quality_warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["visual_fat_percent", "muscularity_rating", "face_rating", "body_rating", "description", "quality_warnings"],
    "additionalProperties": False,
}
