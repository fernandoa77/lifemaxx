release: python manage.py migrate --noinput && python manage.py collectstatic --noinput
web: gunicorn lifemaxx.wsgi:application --timeout 120 --graceful-timeout 30
