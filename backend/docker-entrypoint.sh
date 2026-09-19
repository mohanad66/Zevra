#!/bin/sh
set -e

# ---------------------------------------------------------------------------
# Miyar Trading — Django API container entrypoint
# - waits for PostgreSQL
# - applies migrations
# - seeds platform settings + coins (never creates the default admin123 user
#   unless explicit DJANGO_SUPERUSER_EMAIL/PASSWORD are provided)
# - collects static files
# - runs gunicorn (WSGI) as the app user
# ---------------------------------------------------------------------------

if [ "$1" = "manage" ]; then
  shift
  exec python manage.py "$@"
fi

# --- Wait for the database ------------------------------------------------
if [ -n "$DB_HOST" ]; then
  python - <<'PY'
import os, time
import psycopg
host = os.environ["DB_HOST"]
port = int(os.environ.get("DB_PORT", "5432"))
name = os.environ["DB_NAME"]
user = os.environ["DB_USER"]
password = os.environ.get("DB_PASSWORD", "")
for attempt in range(60):
    try:
        conn = psycopg.connect(
            host=host, port=port, dbname=name, user=user, password=password,
            connect_timeout=3,
        )
        conn.close()
        break
    except Exception:
        if attempt == 59:
            raise SystemExit("Database is not reachable. Aborting startup.")
        time.sleep(1)
PY
fi

# --- Migrate --------------------------------------------------------------
echo "> applying migrations"
python manage.py migrate --noinput

# --- Seed settings + coins; create superuser only if credentials given ------
if [ -n "$DJANGO_SUPERUSER_EMAIL" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
  echo "> seeding settings/coins and creating superuser"
  python manage.py seed \
    --admin-email "$DJANGO_SUPERUSER_EMAIL" \
    --admin-password "$DJANGO_SUPERUSER_PASSWORD"
else
  echo "> seeding settings/coins (no superuser, credentials not set)"
  python manage.py shell -c '
from api.admin import DEFAULT_PLATFORM_SETTINGS
from api.models import Coin, PlatformSettings
for key, value, label in DEFAULT_PLATFORM_SETTINGS:
    PlatformSettings.objects.get_or_create(key=key, defaults={"value": value, "label": label})
for name, symbol, chain, price, stable in [
    ("Tether USD", "USDT", "TRC20", "1.0", True),
    ("USD Coin", "USDC", "TRC20", "1.0", True),
    ("USD", "USD", "TRC20", "1.0", True),
    ("Dai", "DAI", "ERC20", "1.0", True),
    ("Toncoin", "TON", "TON", "5.5", False),
    ("Solana", "SOL", "SOL", "140.0", False),
    ("Bitcoin", "BTC", "ERC20", "64000.0", False),
]:
    Coin.objects.update_or_create(
        symbol=symbol,
        defaults={"name": name, "chain": chain, "reference_price": price, "is_stable": stable},
    )
print("seeded settings + coins (no superuser created)")
'
fi

# --- Static files ---------------------------------------------------------
echo "> collecting static files"
python manage.py collectstatic --noinput

# --- Run ------------------------------------------------------------------
echo "> starting gunicorn on :8000"
GUNICORN_WORKERS=${GUNICORN_WORKERS:-3}
GUNICORN_THREADS=${GUNICORN_THREADS:-4}
exec gunicorn backend.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers "$GUNICORN_WORKERS" \
  --worker-class gthread \
  --threads "$GUNICORN_THREADS" \
  --access-logfile - \
  --error-logfile - \
  --timeout 60 \
  --graceful-timeout 30