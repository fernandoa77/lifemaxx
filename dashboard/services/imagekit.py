import logging
import uuid
from dataclasses import dataclass
from io import BytesIO

from django.conf import settings
from imagekitio import ImageKit
from PIL import Image, ImageOps


logger = logging.getLogger(__name__)
MAX_PHOTO_SIZE = (1800, 1800)


class ImageKitError(RuntimeError):
    pass


@dataclass(frozen=True)
class UploadedImage:
    url: str
    file_id: str


def _client():
    if not settings.IMAGEKIT_PRIVATE_KEY:
        raise ImageKitError("Falta configurar IMAGEKIT_PRIVATE_KEY.")
    return ImageKit(private_key=settings.IMAGEKIT_PRIVATE_KEY)


def _normalize_photo(file) -> bytes:
    """Normaliza orientacion y peso sin recortar el encuadre estandarizado."""
    try:
        file.seek(0)
        with Image.open(file) as original:
            image = ImageOps.exif_transpose(original)
            if image.mode in ("RGBA", "LA"):
                background = Image.new("RGB", image.size, "white")
                background.paste(image, mask=image.getchannel("A"))
                image = background
            else:
                image = image.convert("RGB")
            image.thumbnail(MAX_PHOTO_SIZE, Image.Resampling.LANCZOS)
            output = BytesIO()
            image.save(output, format="WEBP", quality=88, method=6)
            return output.getvalue()
    except Exception as exc:
        raise ImageKitError("No se pudo procesar una de las fotografias.") from exc
    finally:
        file.seek(0)


def upload_body_photo(file, *, date, kind) -> UploadedImage:
    filename = f"{date.isoformat()}-{kind}-{uuid.uuid4().hex[:12]}.webp"
    try:
        response = _client().files.upload(
            file=_normalize_photo(file),
            file_name=filename,
            folder=settings.IMAGEKIT_FOLDER,
            use_unique_file_name=False,
            tags=["lifemax", "body", kind, date.isoformat()],
            timeout=30,
        )
        url = response.url
        if settings.IMAGEKIT_URL_ENDPOINT:
            url = f"{settings.IMAGEKIT_URL_ENDPOINT}/{response.file_path.lstrip('/')}"
        return UploadedImage(url=url, file_id=response.file_id)
    except ImageKitError:
        raise
    except Exception as exc:
        logger.exception("ImageKit rechazo una fotografia corporal.")
        raise ImageKitError("No fue posible subir el paquete fotografico.") from exc


def delete_photo(file_id):
    if not file_id:
        return True
    try:
        _client().files.delete(file_id, timeout=15)
        return True
    except Exception:
        logger.exception("No se pudo borrar de ImageKit el archivo %s.", file_id)
        return False
