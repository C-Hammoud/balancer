# Budgeting Application (BRD v1.0) — updated for finance merge, utilization & alerts

This module implements the **Budgeting Application** from the Business Requirements Document (Chadi M. Hammoud, Feb 10, 2026). It is a Django app (`budgeting`) that now **merges** with the expenses finance-tracking app for actuals, alerts, and dashboard widgets.

## Data store: Firebase (Firestore)

**All budgeting data is stored in Firestore**, not in local SQL. Collections:

- `budgeting_groups` — Category groups (e.g. Home, Food)
- `budgeting_categories` — Categories with `group_id`, `include_in_reports`
- `budgeting_transactions` — Transactions (user_id, date, category_id, amount, direction, …)
- `budgeting_merchant_links` — Keyword → category_id for auto-classification
- `budgeting_budgets` — Forecast per user/category/year/month
- `budgeting_savings` — Monthly target/actual/goal_status per user
- `budgeting_commitments` — Loans; `budgeting_commitment_schedule_lines` — schedule lines
- `budgeting_financial_standings` — Assets/liabilities snapshots
- `budgeting_upload_templates` — (optional) column mappings
- `budgeting_type_category_maps` — Expense `consumption_type` → budgeting `category_id` (global + per-user)
- `budgeting_thresholds` — Warn/critical utilization % and email toggle (global or per category)
- `budgeting_alerts` — Open/resolved WARN/CRITICAL alerts (deduped by fingerprint; email once)

Django models in `budgeting.models` remain for reference; **views and services use `budgeting.firestore_models`**.

## Unified actuals (finance merge)

Budget actuals automatically include:

1. Budgeting `TransactionFS` expenses for the month
2. Expenses-app `ConsumptionFS` for the month that are **not** already mirrored as transactions (`external_id = consumption:<id>`)

Consumptions are mapped to budgeting categories via **Type maps** (Config → Type maps). Defaults are seeded (`market→Groceries`, `food→Restaurants`, `transport→Fuel`, `other→Other`). Manual “copy expense → transaction” remains available but is **not required** for dashboard accuracy.

## Utilization & alerts

- `budget_utilization_report()` returns per-category forecast/actual/remaining/utilization % and status (`ok|warn|critical|over`).
- Default thresholds: **80% warn**, **100% critical** (configurable under Config → Thresholds).
- `evaluate_budget_alerts()` creates/updates Firestore alerts and sends email once per fingerprint when email is enabled and the user has an email address.
- Evaluation runs on budgeting dashboard / alerts page, after expense CRUD, and after transaction/budget saves.
- **Background email (no UI):** run `python manage.py process_budget_alerts` on a schedule (cron / Windows Task Scheduler, e.g. every 30 minutes). Re-evaluates alerts for all users and sends branded emails for any new open alert (`email_sent=False`).
- **After CSV import:** `TransactionUploadView` re-evaluates every month present in the file, then calls `process_budget_alerts(user=request.user)` so new alerts email immediately (response includes `alerts_emails_sent`).
- Commitment payment reminders: `python manage.py send_commitment_reminders` (separate job).
- Email uses Django `send_mail`. With `DEBUG` / no `EMAIL_HOST`, mail goes to the **console** backend. Set `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `DEFAULT_FROM_EMAIL` for SMTP.

## Risk management (debt & liquidity)

`budgeting/risk.py` scores each user from 0 to 100 (higher is safer) using six checks.
Thresholds are percentages unless noted; each one can be overridden per user in Risk settings.

| Check | Measures | Warn / high (defaults) |
|---|---|---|
| Debt payments vs income | installments due this month ÷ expected monthly income | 36% / 50% |
| Overdue installments | outstanding installments past their due date | any → high |
| Upcoming balloon payments | balloons due in the next 6 months ÷ liquid balance | 50% / 100% |
| Debt vs assets | (Net worth liabilities + credit-card debt) ÷ assets (or liquid balance) | 50% / 80% |
| Emergency fund | liquid balance ÷ average monthly spending (last 3 months) | below 3 / below 1 month |
| This month's cash flow | liquid balance + income still expected − installments, planned bills and spending pace left this month | below 10% of income / below 0 |

- **Score:** ok = 100, warn = 60, high = 20 points per check. Debt-to-income and the emergency fund count double. 70+ is low risk, 40–69 medium, below 40 high.
- **Unknown checks** (data missing) are left out of the score; the report says what to add.
- **Expected income:** active income streams plus recurring planned income. If there are none, the average actual income of the last 3 months is used.
- **Liquid balance:** active bank, wallet and other accounts, or the accounts chosen in Risk settings. It is unknown until money has entered an account at least once (an income, e.g. the opening balance, or an incoming transfer). Otherwise the balances would only measure spending.
- **Alerts:** each check in warn/high raises one `alert_type="risk"` alert (`category_id="risk:<check>"`). It is resolved automatically when the check recovers or risk alerts are turned off, and emailed once when Risk settings allow email and the profile's *Low balance* notification is on. The utilization evaluator never touches risk alerts.
- **History:** one score per user per day (`RiskSnapshot`), shown as a 90-day chart.

Supporting data added with it:

- **Server-side account balances** (`budgeting/balances.py`): all transactions, per account and per currency, plus a total converted to the report currency.
- **One-row transfers:** a transfer may carry `to_account_id`. It then takes the money out of `account_id` and puts it into the destination, with no category. Older two-row transfers keep the description rule ("Transfer from …" adds money).
- **Pending status** (`settled` | `pending`): pending expenses count right away; pending income counts only once it is settled.
- **Planned items:** expected money in or out (once, weekly, every two weeks, monthly, yearly). Monthly dates keep their day, clamped to the end of shorter months.

| API (under `/api/v1/`) | Purpose |
|---|---|
| `GET risk/?refresh=1` | Report; `refresh=1` also re-evaluates risk alerts |
| `GET risk/history/?days=90` | Daily scores |
| `GET`/`PATCH risk/settings/` | Threshold overrides (`null` = default), cash accounts, alert/email switches |
| `GET budgeting/config/accounts/balances/?report_currency=` | Account balances |
| `GET`/`POST budgeting/planned-items/`, `GET`/`PATCH`/`DELETE budgeting/planned-items/<id>/` | Planned items |

Risk alerts are also re-evaluated with the other alerts (at most every 15 minutes per user, `RISK_ALERT_TTL_SECONDS`). For a daily check and history point without anyone opening the app, run `python manage.py evaluate_risk`.

## Plans and sub-budgets

**Structure:**
- **Main budget:** the plan's available money (income − installments due that month).
- **Everyday:** the category group lines.
- **Sub-budgets:** trips or projects (personal budgets with `in_plan = true`).
- **Savings:** what is left.

**Reserving money:**
- A sub-budget reserves its `total_amount` in one month or spread over `funding_months` months from `funding_start`.
- The last month takes the rounding remainder.
- **Default window:** from the month it joins the plan until the month before its `start_date` (1 month if the trip starts this month).
- The plan shows the reserved lines (`sub_budgets`, `reserved_total`), and savings shrink by that amount.
- If sub-budgets need more than the month has available, the plan warns but does not block.
- Accepting the plan sets the reduced savings target and turns draft sub-budgets active.

**Counting:**
- An expense tagged to a sub-budget (`budget_id`) counts **only in the sub-budget**: not in category utilization, alerts, the spending history used by the spending-based plan, or the overspending check.
- Removing the budget from the plan makes those expenses count in the category budgets again.

**Rules:**
- Only the owner can attach a budget, and only an active or draft one.
- A budget shared with you never affects your plan, and the owner's sub-budget never affects a member's utilization.

**Default budget:**
- The automatic default "Monthly Expenses" budget is no longer created, because the plan's main budget replaces it.
- An existing one is archived the next time the user opens their budgets, and its transactions are untagged.
- `python manage.py retire_default_budgets` does this for everyone at once.

**Risk:** a sub-budget taking place in the rest of this month adds its unspent amount to the cash-flow check's planned outflows.

| API | Purpose |
|---|---|
| `GET budgeting/personal-budgets/?in_plan=1\|0` | Sub-budgets / budgets that can join the plan |
| `POST budgeting/personal-budgets/` with `in_plan: true`, `funding_months` | Create a sub-budget |
| `PATCH budgeting/personal-budgets/<id>/` `{in_plan, funding_months, funding_start}` | Add to / remove from the plan, change the spread |
| Plan endpoints (`plans/preview/`, `plans/`, `plans/<id>/`) | Include `sub_budgets` and `reserved_total` |

## Admin & customer support

**Roles:**
- **Support admin:** `user.is_staff`. Can use the web **Admin** menu and the `/api/v1/admin/...` endpoints.
- **Superuser:** `user.is_superuser`. Can also grant or remove the admin role. Superusers are always admins.

**Setting roles:**
- Make the first admin from the command line:
  ```
  python manage.py set_admin <username or email> --superuser   # first admin
  python manage.py set_admin <username or email>               # support admin
  python manage.py set_admin <username or email> --remove      # back to a normal user
  ```
- After that, superusers grant or remove the role from **Admin → Users → (user) → Make admin**.
- Safety rules: you can't change your own role or deactivate yourself, and the last active superuser can't be deactivated.

**What staff can do (web Admin menu):**
- **Overview:** counts of users, new sign-ups, unverified users, setup not finished, failed emails, deactivated accounts and open tickets.
- **Users:** search, filter by status or problem, and open a user's support view: account facts, problems, account balances, the last 20 transactions, open alerts, risk score, emails sent to them, and their tickets.
- **Actions:**
  - resend the verification email, or mark the email verified;
  - send a password-reset link (staff never see or set passwords);
  - deactivate (signs the user out everywhere) or reactivate.
- **Tickets:** tabs **My tickets / Pool / All**; take a pool ticket, reply, mark resolved, set priority; superusers reassign.
- **Support settings:** assignment mode, reminder and auto-close days, admin emails (superusers edit, admins read).
- **Audit log:** every time staff open a user, and every action, with who did it and when.

**Problem flags:**

| Flag | Raised when |
|---|---|
| `email_unverified` | not verified 24 hours after sign-up |
| `setup_stuck` | setup not finished after 3 days |
| `email_failed` | an email to the user failed in the last 7 days |
| `no_activity` | no transactions after 7 days |
| `high_risk` | latest risk level is high |
| `open_ticket` | a ticket is waiting for support |
| `deactivated` | the account is deactivated |

**Tickets:**
- Users report problems from **Help & support** (web `/support`, mobile Profile → Help & support).
- **Lifecycle:**
  ```
  user opens ─► assigned to an admin (or the pool) ─► OPEN
  OPEN ── admin replies ──► WAITING_USER ── user replies ──► OPEN
  OPEN ── admin "Send & mark resolved" ──► RESOLVED (the user is asked "is it fixed?")
  RESOLVED ── user "Yes, it's fixed" ──► CLOSED (confirmed)  ─┐ both the user and the assigned
           ── no answer for N days ───► CLOSED (automatic)  ─┘ admin get a "Closed" email
           ── user "Still not fixed" ─► OPEN (same admin is notified)
  ```
  A user reply on a closed ticket reopens it for the same admin.
- **Who can act:** any admin can read any ticket; only the assigned admin or a superuser can reply, resolve or change priority. Only superusers reassign. Status changes happen only through these actions.
- **Assignment** (Admin → Support settings; superusers only):

  | Mode | New tickets go to |
  |---|---|
  | `least_busy` (default) | the admin with the fewest unfinished tickets; ties go to whoever was assigned least recently |
  | `round_robin` | each admin in turn |
  | `pool` | the pool, until an admin clicks **Take it** |

  With no active admin, tickets wait in the pool and are handed out by the hourly job as soon as an admin exists. When an admin is deactivated or loses the role, their unfinished tickets move to another admin.
- **Reminder and auto-close:** a resolved ticket gets one reminder after *reminder days* and closes after *auto-close days* (defaults 3 and 7; 0 turns either off).
- **Defaults** until a superuser saves the settings page come from `.env`: `SUPPORT_ASSIGNMENT_MODE`, `SUPPORT_REMINDER_DAYS`, `SUPPORT_AUTO_CLOSE_DAYS`, `SUPPORT_EMAIL_ADMINS`.
- **Emails:** all ticket emails are account emails, so they're sent even with `NOTIFICATION_EMAILS_ENABLED=0`: reply, "is it fixed?", reminder, and closed (to user and admin). "Assigned to you" and "still not fixed" emails to admins can be turned off in the settings; the in-app notifications always appear.
- **Job:** run `python manage.py process_support_tickets` hourly (reminders, auto-close, pool assignment).

**Tracking:** every email attempt is recorded in `EmailLog` (sent, failed or printed to the console), and `user.last_login` is updated at each sign-in.

## Features

- **Dashboard** (`/budgeting/`) — Budget vs actual, progress bars, remaining, open-alert banner (includes expense consumptions)
- **Alerts** (`/budgeting/alerts/`) — Open/resolved list, resolve action; navbar badge
- **Transactions** — List, add, edit, CSV upload; optional expense bridge
- **Budgets / Savings / Commitments / Financial standing** — as before
- **Config** — Categories, merchant links, **type maps**, **thresholds**
- **Expenses dashboard** — Budget utilization widget + open alerts for the current month

## Setup

1. **Firebase**: Configure `firebase_client.py` / service account as for the expenses app.
2. **Seed** groups, categories, and global type maps:
   ```bash
   python manage.py seed_firestore_budgeting
   ```
3. Optionally set thresholds and type-map overrides in the UI; configure SMTP env vars for real alert emails.

## URLs (under `/budgeting/`)

| Path | Purpose |
|------|--------|
| `/budgeting/` | Dashboard |
| `/budgeting/alerts/` | Alert center |
| `/budgeting/transactions/` | Transaction list |
| `/budgeting/budgets/` | Budget list |
| `/budgeting/config/type-maps/` | Expense type → category |
| `/budgeting/config/thresholds/` | Utilization thresholds |
| … | Savings, commitments, financial standing, merchant links (unchanged) |

## Out of scope (per BRD Phase 2)

- Investment analytics, Open Banking, push notifications, Celery/cron (evaluation is request-triggered)

## Configuration and operations (v2.0 hardening)

### Required environment variables

| Variable | Local dev | Production |
|---|---|---|
| `DJANGO_DEBUG` | `1` | unset (or `0`) |
| `DJANGO_SECRET_KEY` | any value | **required**: the server refuses to start without it when debug is off |
| `DJANGO_ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS` | optional | your domains |

With debug off the API also turns on HTTPS redirect, HSTS and secure cookies
(`DJANGO_SECURE_SSL_REDIRECT=0` disables the redirect if your proxy already does it).

Optional: `EXCHANGE_RATES` (JSON, value of 1 unit in USD, e.g. `{"LBP": 0.0000112}`),
`EXCHANGE_RATES_AS_OF` (date shown in `/api/v1/meta/`), `THROTTLE_AUTH_LOGIN` (default `10/min`),
`THROTTLE_AUTH_REGISTER` (`5/hour`), `THROTTLE_AUTH_EMAIL` (`5/hour`), `THROTTLE_USER_LOOKUP` (`30/hour`),
`TRANSACTION_IMPORT_MAX_BYTES` (5 MB), `TRANSACTION_IMPORT_MAX_ROWS` (5000), `LOG_LEVEL`.

Rate limits use Django's cache. The default in-memory cache is per process; with several
workers configure a shared cache (e.g. Redis) so limits apply across them.

### After pulling these changes

```
pip install -r requirements.txt   # adds openpyxl (Excel import)
python manage.py migrate          # alert snooze/resolution, category owners, token blacklist
```

Categories created before this change have no owner, so they become **shared defaults**
(read-only except for staff users). On a single-user install, give them to your account:

```
python manage.py claim_shared_categories --username <you>
```

### Production server

The production setup is in `deploy/` (Docker Compose: Caddy + Django/gunicorn + PostgreSQL + Redis + scheduler).
The step-by-step guide for the Oracle Cloud server is `docs/deploy/oracle.md`. To host on Render instead, see
`docs/deploy/render.md` and `render.yaml`.

| Setting | Effect |
|---|---|
| `DATABASE_URL=postgres://…` | Use PostgreSQL (unset: the local `db.sqlite3`) |
| `DATA_STORE=postgres` | Same store as `sqlite`, i.e. the Django database; any of `sqlite`, `sql`, `postgres` |
| `REDIS_URL=redis://…` | Shared cache for rate limits and alert throttling (unset: per-process memory) |
| `DJANGO_SECURE_SSL_REDIRECT` / `DJANGO_HSTS_SECONDS` | HTTPS switches. Keep both at `0` while the server has no domain; secure-only cookies follow the redirect switch |

### Scheduled jobs (production)

`python manage.py run_scheduler` runs every job on its own interval; this is the `scheduler` container.
`--once` runs each job a single time.

| Command | Default interval |
|---|---|
| `python manage.py process_budget_alerts` | 30 min |
| `python manage.py send_setup_nudges` | 30 min |
| `python manage.py process_support_tickets` | hourly |
| `python manage.py evaluate_risk` | daily |
| `python manage.py send_commitment_reminders` | daily |
| `python manage.py review_budget_plans` | daily |
| database backup (`pg_dump` into `BACKUP_DIR`, keeps `BACKUP_KEEP`) | daily |

Override an interval with `SCHEDULE_<JOB>_MINUTES`, e.g. `SCHEDULE_BUDGET_ALERTS_MINUTES=15`.
`/healthz/` has no side effects, so uptime pings don't trigger jobs.

### Tests

```
pip install pytest pytest-django
pytest
```

Tests always run on SQLite with Django's in-memory email backend (no real emails).
