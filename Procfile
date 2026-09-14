release: python manage.py migrate --noinput && python manage.py collectstatic --noinput
# Railway/Render arrancan el proceso web sin ejecutar necesariamente "release".
# Repetir estos comandos es seguro y garantiza que cada deploy quede listo.
web: python manage.py migrate --noinput && python manage.py collectstatic --noinput --clear && gunicorn lifemaxx.wsgi:application --bind 0.0.0.0:${PORT:-8000} --access-logfile - --error-logfile - --log-level info --timeout 120 --graceful-timeout 30
