# LifeMaxx

Life Dashboard personal en Django. El MVP implementa captura diaria, pricing marginal en unidades de `H`, historial inmutable de configuracion, calendario, analisis por periodo y procesamiento estructurado mediante OpenRouter.

## Arranque local (Windows / PowerShell)

```powershell
.\venv\Scripts\Activate.ps1
Copy-Item .env.example .env
python manage.py migrate
python manage.py runserver
```

Antes del primer acceso crea un usuario administrador:

```powershell
python manage.py createsuperuser
```

Abre `http://127.0.0.1:8000/` e inicia sesión con ese usuario. La sesión se conserva durante 30 días, incluso al cerrar el navegador, y se renueva con cada uso; se puede cambiar con `SESSION_COOKIE_DAYS` en `.env` o cerrar manualmente desde la app. La primera visita autenticada crea la configuración inicial (`H = $250 MXN`) y la fotografía de configuración del día. El acceso se bloquea durante 30 minutos después de 5 intentos fallidos por usuario e IP; ambos valores se pueden ajustar en `.env` con `AXES_FAILURE_LIMIT` y `AXES_COOLOFF_MINUTES`.

## OpenRouter

Configura en `.env`:

```env
OPENROUTER_API_KEY=tu-clave
OPENROUTER_MODEL=proveedor/modelo-compatible-con-json-schema
OPENROUTER_FALLBACK_MODELS=
```

La extracción estructurada pasa por `dashboard/services/ai.py::request_structured_json`. La funcion acepta prompt, contexto, imagenes y un JSON Schema por modulo; solicita `response_format=json_schema` con modo estricto y bloquea propiedades adicionales. Nutricion y progreso corporal ya la reutilizan.

En **Nueva comida → Generar con IA** puedes escribir, dictar una receta o adjuntar una imagen. El dictado usa `transcribe_audio` con Whisper por el endpoint `/audio/transcriptions` de OpenRouter y la misma `OPENROUTER_API_KEY`. El modelo se puede configurar con `OPENROUTER_TRANSCRIPTION_MODEL` (por defecto `openai/whisper-large-v3`). No requiere otra clave ni instalar Whisper en el servidor.

El micrófono requiere HTTPS (o localhost), permiso del navegador y soporte de MediaRecorder. Cada grabación dura hasta 3 minutos; el servidor acepta hasta 10 MB. Al detenerla, el texto se agrega a la descripción para revisarlo y luego generar la vista previa nutricional con el modelo `OPENROUTER_MODEL` (debe admitir imágenes para analizar fotos). El audio no se guarda en los modelos ni en el almacenamiento de medios; si falla la transcripción se conserva temporalmente en el navegador para reintentar. La comida solo se guarda al confirmar **Agregar comida**.

Contrato del proveedor: [Speech-to-Text de OpenRouter](https://openrouter.ai/docs/guides/overview/multimodal/stt).

## Fotografias corporales en ImageKit

El paquete estandarizado de cinco tomas se sube con el mismo SDK de Jacob Web (`imagekitio`). Configura:

```env
IMAGEKIT_PRIVATE_KEY=private_xxx
IMAGEKIT_URL_ENDPOINT=https://ik.imagekit.io/tu_id
IMAGEKIT_FOLDER=/lifemaxx/body
```

Cada foto se almacena en la base como URL y `file_id`. La imagen conserva el encuadre completo, normaliza la orientacion EXIF y se convierte a WebP con un maximo de 1800 px. ImageKit crea la ruta configurada al recibir la primera subida; tambien puedes crear manualmente la carpeta `/lifemaxx/body` desde el Media Library.

## Estructura

- `lifemaxx/`: settings, URLs y entradas WSGI/ASGI siguiendo el patron de Studio Green.
- `dashboard/models.py`: configuracion versionada, fotografia diaria, seis modulos, evidencia, fuentes IA y auditoria.
- `dashboard/services/pricing.py`: formulas deterministas y recalculo historico con snapshot original.
- `dashboard/services/ai.py`: cliente transversal de OpenRouter y schemas estructurados.
- `dashboard/views.py`: las cinco superficies del MVP y operaciones de captura.
- `templates/dashboard/`: dia, modulo unificado, calendario, dashboard y configuracion.
- `static/`: interfaz responsive y autosave.

## Despliegue

El `Procfile` ejecuta migraciones y `collectstatic` en release y sirve la aplicacion con Gunicorn. `DATABASE_URL` cambia automaticamente de SQLite local a PostgreSQL; WhiteNoise sirve los archivos estaticos. Los uploads viven en `MEDIA_ROOT`, por lo que en produccion deben conectarse a almacenamiento persistente.

En Railway, `railway.json` ejecuta `collectstatic` durante el build, las migraciones antes del deploy y luego inicia Gunicorn. Esto evita que un Start Command autodetectado omita la generacion de `staticfiles/`.

Configura estas variables en el panel del proveedor (Railway, Render, etc.):

```env
DEBUG=False
ENVIRONMENT=production
SECRET_KEY=una-clave-larga-y-aleatoria
ALLOWED_HOSTS=tu-dominio-del-proveedor
CSRF_TRUSTED_ORIGINS=https://tu-dominio-del-proveedor
DATABASE_URL=postgresql://...
```

`ALLOWED_HOSTS` no lleva `https://`; `CSRF_TRUSTED_ORIGINS` sí. El proceso web escucha el puerto que el proveedor asigne mediante `PORT` y los errores 500 se registran en los logs de Gunicorn/Django sin exponer el traceback en el navegador.

## Reglas historicas

- Cada `DayRecord` guarda su copia de `H`, metas, prioridades, perfil corporal y versiones de formulas.
- Cambiar Configuracion crea una fila nueva con vigencia hacia adelante.
- Corregir un dia recalcula usando su propia copia historica.
- Los valores anteriores y nuevos quedan en `AuditRevision`.
- El ajuste manual se muestra y almacena separado del resultado automatico.
