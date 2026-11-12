#!/bin/sh
# Container start: apply database migrations and collect static files (API container only),
# then run the given command (gunicorn, or the scheduler).
set -e

if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
    python manage.py migrate --noinput
    python manage.py collectstatic --noinput >/dev/null
fi

# Hosts with one container per service and no cheap worker (Render): run the jobs next to the API.
if [ "${RUN_SCHEDULER_IN_PROCESS:-0}" = "1" ]; then
    python manage.py run_scheduler &
fi

exec "$@"
