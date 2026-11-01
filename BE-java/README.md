# Finance Tracker — Java backend

Spring Boot port of the Django backend in `../BE`. The REST API (`/api/v1/...`) keeps the same
URLs, request fields and JSON responses, so the Angular (`FE/`) and Expo (`mobile/`) apps work
without changes.

## Layout

| Module | What it is |
|---|---|
| `app/` | Modular monolith (Spring Boot 4, Spring Modulith). One deployable with three modules. |
| `gateway/` | "Portal balancer": Spring Cloud Gateway that routes each API area to its backend. |

Modules inside `app/` (`com.financetracker.*`):

- `access` — access manager: register, login (simplejwt-compatible JWTs), email verification,
  password reset, Firebase login, profile and locale preferences, rate limits.
- `notifications` — branded transactional email (SMTP or console) and the in-app inbox
  (`/api/v1/notifications/`).
- `finance` — accounts, transactions, statement import, categories, budgets, savings,
  commitments and schedules, alerts, personal/shared budgets, planning and reports.
- `shared` — config, DRF-compatible errors and request parsing, currency/locale helpers.

Other modules may only use a module's `api` package; `ModularityTest` fails the build otherwise.

## Requirements

JDK 17 or newer. Nothing else: Maven is downloaded by the wrapper.

## Build and test

```powershell
cd BE-java
.\mvnw.cmd verify
```

## Run

```powershell
cd BE-java
.\mvnw.cmd -pl app spring-boot:run          # API on http://localhost:8000
.\mvnw.cmd -pl gateway spring-boot:run      # gateway on http://localhost:8080 -> BACKEND_URL
```

Configuration uses the same environment variable names as Django, and a `.env` file in the
working directory is read automatically. The most important ones:

| Variable | Meaning | Default |
|---|---|---|
| `DJANGO_SECRET_KEY` | Signs JWTs and email/reset links. **Use the Django value** so existing sessions and emailed links keep working. | required unless `DJANGO_DEBUG=1` |
| `DJANGO_DEBUG` | `1` allows every CORS origin and a dev secret | `0` |
| `DATA_STORE` | `jpa` (any SQL database) or `firestore` (`sqlite` = `jpa`) | `jpa` |
| `DATABASE_URL`, `DATABASE_USERNAME`, `DATABASE_PASSWORD` | JDBC database for `jpa` | local H2 file in `./data` |
| `FLYWAY_LOCATIONS` | `classpath:db/migration/mysql` for MySQL | PostgreSQL scripts (also used by H2) |
| `FIREBASE_KEY_PATH` | Service-account key (Firestore mode, Firebase login) | `./finance-tracker-firebase_key.json` |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL` | SMTP; without `EMAIL_HOST` emails are logged | console |
| `FRONTEND_URL`, `API_PUBLIC_URL`, `MOBILE_APP_SCHEME` | Links in emails | as in Django |
| `CORS_ALLOWED_ORIGINS`, `THROTTLE_*`, `JWT_*`, `EXCHANGE_RATES` | as in Django | as in Django |
| `JOBS_ENABLED` | Scheduled jobs (alerts, reminders, plan review, setup nudges). Enable on one instance only. | `true` |

Examples:

```powershell
# PostgreSQL
$env:DATABASE_URL="jdbc:postgresql://localhost:5432/finance"; $env:DATABASE_USERNAME="finance"; $env:DATABASE_PASSWORD="..."

# Existing Firestore data (same collections and fields as the Django code)
$env:DATA_STORE="firestore"; $env:FIREBASE_KEY_PATH="C:\path\to\finance-tracker-firebase_key.json"
```

## Gateway routes

| Path | Variable | Area |
|---|---|---|
| `/api/v1/auth/**`, `/api/v1/meta/**` | `ACCESS_URL` | access manager |
| `/api/v1/notifications/**` | `NOTIFICATIONS_URL` | notifications |
| `/api/v1/budgeting/**` | `FINANCE_URL` | finance |
| everything else | `BACKEND_URL` | default |

All default to `BACKEND_URL` (`http://localhost:8000`). Point an area at Django or at a
separated service by setting its variable.

## Compatibility with the Django backend

- Passwords: Django `pbkdf2_sha256` hashes are verified and written, in both directions.
- JWTs: byte-identical to simplejwt/PyJWT (HS256, same claims); refresh rotation and blacklist.
- Email verification and password-reset links: Django's token algorithm, so links already sent
  stay valid.
- Firestore: same collection names and document fields.
