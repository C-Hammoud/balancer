#!/bin/sh
# Container start: apply database migrations and collect static files (API container only),
# then run the given command (gunicorn, or the scheduler).
set -e

if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
    python manage.py migrate --noinput
    python manage.py collectstatic --noinput >/dev/null
fi

exec "$@"
