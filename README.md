# LifeMax

Life Dashboard personal en Django. El MVP implementa captura diaria, pricing marginal en unidades de `H`, historial inmutable de configuracion, calendario, analisis por periodo y procesamiento estructurado mediante OpenRouter.

## Arranque local (Windows / PowerShell)

```powershell
.\venv\Scripts\Activate.ps1
Copy-Item .env.example .env
python manage.py migrate
python manage.py runserver
```

Abre `http://127.0.0.1:8000/`. La primera visita crea la configuracion inicial (`H = $250 MXN`) y la fotografia de configuracion del dia.

## OpenRouter

Configura en `.env`:

```env
OPENROUTER_API_KEY=tu-clave
OPENROUTER_MODEL=proveedor/modelo-compatible-con-json-schema
OPENROUTER_FALLBACK_MODELS=
```

Toda integracion de IA pasa por `dashboard/services/ai.py::request_structured_json`. La funcion acepta prompt, contexto, imagenes y un JSON Schema por modulo; solicita `response_format=json_schema` con modo estricto y bloquea propiedades adicionales. Nutricion y progreso corporal ya la reutilizan.

## Estructura

- `lifemax/`: settings, URLs y entradas WSGI/ASGI siguiendo el patron de Studio Green.
- `dashboard/models.py`: configuracion versionada, fotografia diaria, seis modulos, evidencia, fuentes IA y auditoria.
- `dashboard/services/pricing.py`: formulas deterministas y recalculo historico con snapshot original.
- `dashboard/services/ai.py`: cliente transversal de OpenRouter y schemas estructurados.
- `dashboard/views.py`: las cinco superficies del MVP y operaciones de captura.
- `templates/dashboard/`: dia, modulo unificado, calendario, dashboard y configuracion.
- `static/`: interfaz responsive y autosave.

## Despliegue

El `Procfile` ejecuta migraciones y `collectstatic` en release y sirve la aplicacion con Gunicorn. `DATABASE_URL` cambia automaticamente de SQLite local a PostgreSQL; WhiteNoise sirve los archivos estaticos. Los uploads viven en `MEDIA_ROOT`, por lo que en produccion deben conectarse a almacenamiento persistente.

## Reglas historicas

- Cada `DayRecord` guarda su copia de `H`, metas, prioridades, perfil corporal y versiones de formulas.
- Cambiar Configuracion crea una fila nueva con vigencia hacia adelante.
- Corregir un dia recalcula usando su propia copia historica.
- Los valores anteriores y nuevos quedan en `AuditRevision`.
- El ajuste manual se muestra y almacena separado del resultado automatico.
