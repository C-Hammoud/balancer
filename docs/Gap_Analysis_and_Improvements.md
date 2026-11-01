# Finance Tracker — Gap Analysis and Improvement Plan

| | |
|---|---|
| **Compares** | PRD — Finance Tracker v1.0 (2026-10-18) against the current code in `Finance_tracker_cloned` (`BE/`, `FE/`, `mobile/`) |
| **Owner** | Chadi M. Hammoud |
| **Date** | 2026-10-18 |
| **Status** | Draft for review |

---

## Contents

1. [Summary](#1-summary)
2. [What changed since the PRD](#2-what-changed-since-the-prd)
3. [Status of the PRD's known gaps (K1–K12)](#3-status-of-the-prds-known-gaps-k1k12)
4. [Weaknesses in the new implementation](#4-weaknesses-in-the-new-implementation)
5. [Features lost from the PRD scope](#5-features-lost-from-the-prd-scope)
6. [Improvements and new features to add](#6-improvements-and-new-features-to-add)
7. [Proposed roadmap](#7-proposed-roadmap)
8. [PRD updates needed](#8-prd-updates-needed)
9. [Review scope](#9-review-scope)

---

## 1. Summary

The new implementation is a real step forward. It moves from server-rendered Django pages to a clean **REST API (`/api/v1`) + Angular 19 web app + Expo (iOS/Android) mobile app**, and it closes several of the PRD's most important gaps: commitment payment schedules are now generated and payable in the app (K1), categories can be managed (K2), transactions carry a currency with report-currency conversion (K3), and transfers are accepted by the API (K10). It also adds features beyond the PRD: budget alerts with thresholds and email, shared budgets (owner / editor / viewer), accounts, email verification, password reset and onboarding.

The main weaknesses are:

- **Security and production readiness have not moved.** The secret key is still hard-coded, `DEBUG = True`, CORS is fully open in debug, there is no rate limiting on sign-in or email endpoints, and **any signed-in user can rename or delete the shared categories everyone uses**.
- **Data correctness issues** in the money logic: savings mix currencies, marking a loan payment as "paid" makes it disappear from savings, regenerating a schedule deletes payment history, and CSV dates are parsed US-style (M/D) for users in Lebanon and Saudi Arabia.
- **Scalability limits remain (K5).** Transaction queries still cap at 1,000 per user and filter by month in Python; background jobs scan whole collections.
- **Regressions against the PRD**: the fast multi-line expense entry, the PDF reports and the full data import/export (backup and restore) no longer exist in the new stack.
- **Still no automated tests (K9)** and still hard-coded exchange rates (K4).

## 2. What changed since the PRD

| Area | PRD (as built) | New implementation |
|---|---|---|
| Architecture | Django pages + partial React SPA | Django REST API only (Swagger at `/api/docs/`); Angular web app (`FE/`); Expo mobile app (`mobile/`) |
| Data store | Firestore only | Firestore or SQLite, switched by `DATA_STORE` (`finance_tracker/data_store.py`) |
| Expense capture | Separate "consumptions" tracker with USD conversion | Folded into transactions; `/expenses` routes redirect to transactions |
| Categories | Read-only, admin-managed | Full CRUD via `/budgeting/config/groups/` and `/config/categories/` |
| Commitments | Schedule must be entered in Firebase console | Schedule generated from term/frequency/payment/balloon; pay / unpay / edit lines; reminder emails |
| Currency | Expenses only; transactions have none | Transactions have `currency`; reports convert to the user's `default_currency` |
| New | — | Budget alerts (warn/critical thresholds, email), shared personal budgets with invites and notifications, accounts / income sources, type maps, email verification, password reset, onboarding nudges, Hijri date support on mobile |

## 3. Status of the PRD's known gaps (K1–K12)

| # | Gap | Status | Notes |
|---|---|---|---|
| K1 | Payment schedules can't be created in app | **Fixed** | `budgeting/commitment_schedule.py`. New issues found — see W-D2, W-D3. |
| K2 | Categories can't be managed | **Partly fixed** | CRUD exists, but categories are still **global**, and now any user can change them (W-S1). Q1 is still open. |
| K3 | Transactions have no currency | **Mostly fixed** | Currency stored and converted in reports; savings still mixes currencies (W-D1). |
| K4 | Exchange rates out of date and hard-coded | **Open** | `settings.EXCHANGE_RATES` still has `LBP: 0.01`. Now worse, because report conversion depends on it everywhere. |
| K5 | Query limits silently drop data | **Open** | `TransactionFS.list_by_user` reads at most 1,000 docs, then filters by month in Python (W-P1). |
| K6 | Year picker hard-coded | Not verified | Old Django pages are retired; check the Angular/mobile pickers. |
| K7 | Hard-coded `SECRET_KEY`, `DEBUG = True`, DEBUG logging | **Open** | Unchanged in `finance_tracker/settings.py` (W-S2). |
| K8 | Upload page over-promises | **Improved** | Header aliases are detected automatically. Still CSV only, though `sample_data/` contains an `.xlsx`. |
| K9 | No automated tests | **Open** | `expenses/tests.py` is the empty template; no API, Angular or mobile tests. |
| K10 | Transfers inconsistent | **Fixed** | API serializer accepts every `Direction` choice. |
| K11 | Two partial UIs | **Resolved differently** | Django pages retired; Angular + mobile are now the two UIs to keep in step. |
| K12 | No product analytics | **Open** | — |

## 4. Weaknesses in the new implementation

Severity: **Critical** = fix before any real users · **High** = fix in the next release · **Medium** · **Low**.

### 4.1 Security and privacy

| ID | Weakness | Evidence | Impact | Fix | Severity |
|---|---|---|---|---|---|
| W-S1 | **Any signed-in user can create, rename or delete the global categories and groups.** | `GroupListCreateView`, `GroupDetailView`, `CategoryListCreateView`, `CategoryDetailView` in `api/views/budgeting.py` only require `IsAuthenticated`. Deleting a category also deletes every type map pointing to it, for all users. | One user can break every other user's budgets, reports and auto-categorisation. | Make categories per-user (or "shared defaults + personal"), and restrict global ones to `IsAdminUser`. | **Critical** |
| W-S2 | Hard-coded `SECRET_KEY`, `DEBUG = True`, `ALLOWED_HOSTS` gets `*` and `CORS_ALLOW_ALL_ORIGINS = True` while debug is on, root logger at DEBUG. | `finance_tracker/settings.py` | Anyone with the key can forge sessions/password-reset tokens; debug pages leak settings; logs leak request data. | Read `SECRET_KEY`, `DEBUG`, hosts and CORS from env; fail fast if missing in production; run `manage.py check --deploy`. | **Critical** |
| W-S3 | **Email-verification links carry a token that also resets the password.** | Both flows use `default_token_generator` (`api/email_verification.py`, `api/views/auth.py`). | Whoever sees a verification link (forwarded email, proxy/server logs, since it's a GET URL) can set a new password for that account. | Use a separate token generator subclass for email verification (different `key_salt`), and shorter expiry. | **High** |
| W-S4 | No rate limiting on login, register, password reset, verification resend or user lookup. | No DRF throttles configured. | Password guessing; email bombing a victim through reset/resend; spam account creation. | Add `AnonRateThrottle`/`ScopedRateThrottle` to auth endpoints; add CAPTCHA on register if public. | **High** |
| W-S5 | Any signed-in user can look up any email and get the account's **name, username and id**. | `PersonalBudgetUserLookupView` → `lookup_user_by_email`. | Account enumeration and personal-data leak. | Don't return identity; just "invite sent". Let the invitee accept. | **High** |
| W-S6 | The unauthenticated `/healthz/` endpoint **sends setup-nudge emails** as a side effect. | `HealthView.get` → `process_setup_nudges()`. | Every uptime ping or anonymous request triggers DB writes and email sends. | Move to a management command run by a scheduler. | Medium |
| W-S7 | Refresh tokens can't be revoked. | `ROTATE_REFRESH_TOKENS=True` without `rest_framework_simplejwt.token_blacklist`. | Sign-out doesn't end the session; a stolen refresh token works for 7 days. | Install the blacklist app; blacklist on logout and after rotation. | Medium |
| W-S8 | Web app stores JWTs in `localStorage`. | `FE/src/app/core/auth.service.ts` | Any XSS steals tokens. | Short access lifetime + refresh in an HttpOnly cookie, plus a strict CSP. | Medium |
| W-S9 | Firebase service-account key and `db.sqlite3` sit in `BE/` and are **not** covered by `.gitignore` (it only ignores `/resources/...`). `BE/` isn't a git repo yet, so nothing has leaked. | `BE/.gitignore` | Committing the folder would publish the key and user data. | Add `finance-tracker-firebase_key.json`, `*firebase*key*.json`, `db.sqlite3`, `venv/` to `.gitignore` before `git init`. | Medium |
| W-S10 | Email isn't unique; if `REQUIRE_EMAIL_VERIFICATION=0`, pending budget invites are granted on registration without proving ownership of the email. | `RegisterView`, `accept_pending_budget_invites` | Someone can register with an invited email and get access to a shared budget. | Enforce unique emails; only accept invites after verification. | Medium |
| W-S11 | No upload size limit on CSV import. | `TransactionUploadView` reads the whole file into memory. | Memory exhaustion with a large file. | Set `DATA_UPLOAD_MAX_MEMORY_SIZE`/`FILE_UPLOAD_MAX_MEMORY_SIZE` and a row limit. | Low |

### 4.2 Data correctness

| ID | Weakness | Evidence | Impact | Fix | Severity |
|---|---|---|---|---|---|
| W-D1 | **Savings add up amounts in different currencies.** | `savings_actual()` in `budgeting/services.py` calls the income/expense totals without `report_currency`; commitment lines aren't converted either. | A month with SAR income and USD expenses gives a meaningless savings figure. | Pass the user's report currency through every total, including commitments. | **High** |
| W-D2 | **Marking a schedule line "paid" removes it from savings without recording an expense.** | `CommitmentSchedulePayView` → `mark_line_paid()` only flips the status; `sum_amount_due_in_month` counts only *outstanding* lines. Creating a transaction with `commitment_id` is a separate path. | Paying a loan instalment makes savings go **up** by the instalment amount. | Make "pay" always create (or link) the expense transaction, in one operation. Same for "unpay" (remove/unlink it). | **High** |
| W-D3 | **"Regenerate schedule" deletes paid lines.** | `CommitmentRegenerateScheduleView` → `generate_schedule_lines(replace=True)` deletes all lines. | Payment history lost; transactions keep a `schedule_line_id` that no longer exists. | Keep paid lines; regenerate only the outstanding remainder. Require confirmation. | **High** |
| W-D4 | **CSV dates are parsed US-style (M/D/YYYY) first.** | `_parse_csv_date()` comment: "Prefer US M/D/YYYY". | Lebanese and Saudi banks export D/M/YYYY. `03/04/2026` is imported as 4 March, not 3 April; transactions land in the wrong month. | Default to D/M for LB/SA users, or let the user choose the date format on import (and remember it). | **High** |
| W-D5 | Exchange rates hard-coded and stale (K4). | `settings.EXCHANGE_RATES`, `LBP: 0.01`. | Every converted total involving LBP is ~900× too high. | Rates table with effective dates, admin-editable; optional daily feed. Store the rate used on each transaction. | **High** |
| W-D6 | CSV import ignores currency. | Imported `TransactionFS` rows have no currency → default `USD`. | A SAR bank statement is treated as USD. | Ask for the statement currency (or take it from the selected account). | **High** |
| W-D7 | Import dedupe drops genuine repeated transactions. | Key = `date|amount|first 100 chars of description`. | Two identical coffees on the same day: the second is skipped, even within the same file. | Add the row's position/occurrence count to the key, or a bank reference column when present. | Medium |
| W-D8 | Latin-1 fallback is broken. | `f.read()` is called again after the first read failed, so it returns empty bytes. | Non-UTF-8 files import as "0 rows" with no error. | Read bytes once, then try decodings on that buffer. | Medium |
| W-D9 | "Remaining principal" is really "remaining payments". | `schedule_progress()` sums outstanding instalments. | Includes interest; overstates the loan liability. | Rename the label, or add interest rate and compute an amortisation schedule. | Low |
| W-D10 | Multi-step writes aren't atomic. | CSV import, pay + transaction, schedule regenerate do many separate Firestore writes. | A failure halfway leaves partial data. | Use Firestore batched writes/transactions (and `transaction.atomic` on SQLite). | Medium |

### 4.3 Performance and scalability

| ID | Weakness | Evidence | Fix | Severity |
|---|---|---|---|---|
| W-P1 | Transactions capped at 1,000 per user, filtered by month in Python, and the list endpoint returns everything with no pagination. | `TransactionFS.list_by_user`; `TransactionListCreateView.get` | Query by `user_id + month` with a composite index; cursor pagination in the API. | **High** |
| W-P2 | The same month's transactions are fetched several times per request (dashboard, income, expense, savings, utilization each call `list_by_user`). | `budgeting/services.py` | Load once per request and pass the list down, or cache per request. | Medium |
| W-P3 | Background jobs scan whole collections (`list_all(limit=5000)` on commitments, transactions, alerts) and silently stop at 5,000. | `budgeting/alerts.py::_users_for_alert_processing` | Iterate users, or query only open/changed items; page through results. | Medium |
| W-P4 | N+1 queries: monthly commitment total loads every commitment, then every schedule line. Global categories use `list_all(limit=500)` many times per request. | `sum_amount_due_in_month`; category views | Store `user_id` and `due_month` on schedule lines; cache reference data. | Medium |
| W-P5 | Alert re-evaluation runs synchronously on many writes (and emails are sent inside the CSV upload request). | `trigger_budget_alerts`, `TransactionUploadView` | Queue the work (Celery/RQ or Cloud Tasks) and return immediately. | Medium |

### 4.4 Code health and operations

| ID | Weakness | Evidence | Fix | Severity |
|---|---|---|---|---|
| W-C1 | **No automated tests** anywhere (K9). | `BE/expenses/tests.py` empty; no Angular specs beyond the generated one; none in `mobile/`. | Start with pytest tests for money logic (utilization, savings, schedule, CSV parse/dedupe, currency) and API permission tests. | **High** |
| W-C2 | Two storage back-ends with the same API (`firestore_models.py` ~39 KB and `store/sqlite.py` ~64 KB). | `budgeting/store/__init__.py` | Every feature must be written twice and can drift. Pick one for production, or run the same test suite against both. | Medium |
| W-C3 | Large amount of dead code: `expenses` app is not in `INSTALLED_APPS`, `budgeting/views.py` (~46 KB) and all Django templates are no longer routed. | `settings.py`, `finance_tracker/urls.py` | Remove or archive; it confuses the next developer and any code search. | Medium |
| W-C4 | Errors are silently swallowed (`except Exception: pass`) in alert triggering and Firebase user sync. | `api/utils.py::trigger_budget_alerts`, `FirebaseLoginView` | At least log with stack trace; add error tracking (e.g. Sentry). | Medium |
| W-C5 | Very large view modules (`api/views/budgeting.py` ~68 KB, Angular `transactions.component.ts` ~32 KB). | — | Split by resource; move logic into services; use DRF serializers/ViewSets. | Low |
| W-C6 | No CI, no Dockerfile, no deployment docs, no pinned versions for most Python packages. | `requirements.txt` uses `>=` | Add GitHub Actions (lint, tests, build), a Dockerfile, and a lock file. | Medium |
| W-C7 | No scheduler is defined for `process_budget_alerts` and `send_commitment_reminders`. | README says "run on a schedule (cron / Task Scheduler)" | Define it in deployment (Cloud Scheduler, cron container, or Celery beat). | Medium |
| W-C8 | Mobile app: some forms still need raw ids typed in; `@expo/ngrok` is a runtime dependency. | `mobile/README.md` notes | Replace id fields with pickers; move ngrok to devDependencies. | Low |

## 5. Features lost from the PRD scope

These are in the PRD as **Live** but have no equivalent in the new API or apps.

| PRD ref | Feature | Current state | Recommendation |
|---|---|---|---|
| EX-1, G1 | Fast **multi-line expense entry** (several items, one date) — the core "under 30 seconds" goal | Single transaction form only | Add a "quick add" sheet on mobile (amount → category → save, with a "+ another" row) and a batch create endpoint. |
| EX-2 | Default country from timezone | Replaced by user preferences (timezone/country/currency) | Fine — update the PRD. |
| EX-8 | **PDF report** (month / year / selected months, charts by country) | Gone (`reportlab`, `matplotlib` still in requirements) | Re-implement as `GET /api/v1/reports/pdf?...`, or CSV/XLSX export; share sheet on mobile. |
| §6.10 DT-1..4 | **Data import/export** (backup, merge/replace, preview) | Gone | Re-add: JSON export per period, import with preview. Important for user trust and for moving between Firestore and SQLite. |
| §6.5 BR-1..4 | Expense → transaction bridge | No longer needed (expenses are transactions now) | Remove from PRD; plan a one-off migration of old `consumptions` into transactions. |
| EX-6 | Soft delete with audit trail | Transactions are hard-deleted | Add `deleted_at` (soft delete) and "undo" in the UI. |

## 6. Improvements and new features to add

### 6.1 Must-have (correctness and trust)

1. **Per-user categories** with shared defaults seeded at sign-up (answers PRD Q1). Lock global categories to admins.
2. **Exchange-rate service**: rates table with effective dates, admin screen, optional daily feed; store `rate` and `amount_report` on each transaction at save time so history doesn't change when rates do.
3. **Import wizard**: choose account, currency and date format; preview rows before saving; support XLSX (the sample file already exists) and saved column mappings (`budgeting_upload_templates` is already in the model, unused).
4. **One payment flow for loans**: "Mark paid" creates the expense transaction; "Unpay" reverses it; regenerate keeps paid history.
5. **Backup and restore** (JSON) and **CSV/XLSX export** of transactions.
6. **Test suite + CI** covering money logic and access control.

### 6.2 High-value features

| Feature | Why it matters | Notes |
|---|---|---|
| **Recurring transactions** (salary, rent, subscriptions) | Removes repetitive entry; makes forecasts realistic | Auto-create on schedule, or prompt "Salary arrived?" |
| **Copy last month's budget / budget templates** | Already on the PRD 1.2 roadmap; most users budget the same each month | `PersonalBudgetCloneView` exists — expose "start next month from this one" |
| **Account balances and transfers between accounts** | Accounts exist, and `notify_low_balance` exists, but no running balance is shown | Opening balance + transactions = current balance; transfer moves money between two accounts without affecting income/expense |
| **Savings goals with target date** (e.g. "Car — 20,000 SAR by Dec 2027") | Monthly savings target alone doesn't motivate | Progress bar, required monthly contribution |
| **Net worth from data** | Financial standing is still manual snapshots | Pre-fill assets from account balances and liabilities from commitments; chart over time |
| **Receipt photo capture** | Proof of purchase and faster entry on mobile | Attach image to transaction (Firebase Storage is already initialised); later OCR for amount/merchant |
| **Push notifications** | Alerts are email-only today; push nudges are only logged | Expo push tokens; budget 80%/100%, loan due, weekly summary (`notify_weekly_summaries` already exists) |
| **Smarter auto-categorisation** | Merchant keyword links need manual upkeep | Learn from user corrections ("always categorise X as Y?"); suggest rules after import (partly there via `unmatched`) |
| **Search and filters** on transactions | Only month filter today | Text search, category, account, amount range, direction |
| **Insights** | Turn data into advice | Month-over-month change per category, top merchants, "you usually spend X on groceries" |
| **Offline entry on mobile** | Cash spending often happens with poor signal | Queue new transactions locally and sync |
| **Biometric app lock** | Finance data on a phone | Face ID / fingerprint via `expo-local-authentication` |
| **Arabic and RTL support** | Target users are in Lebanon and Saudi Arabia; Hijri dates already supported | i18n in Angular and mobile; Arabic number formatting |
| **Account deletion and data-privacy controls** | Required by app stores (Apple/Google) and good practice | Delete account + all data; export before deletion |
| **Product analytics** (K12) | Needed to measure PRD §3.3 targets | Privacy-respecting events: transaction added, budget set, import completed |

### 6.3 Platform and operations

- Production settings module (`settings/prod.py`) with HTTPS, HSTS, secure cookies, strict CORS, INFO-level structured logging.
- Background worker for alerts, reminders, imports and emails.
- Error monitoring (Sentry) for API, Angular and mobile.
- API versioning and OpenAPI-generated TypeScript clients, shared by Angular and mobile so the two UIs can't drift.
- Firestore security rules that deny all direct client access (all access goes through the API), and composite indexes checked into the repo.
- Daily automated Firestore backups.

## 7. Proposed roadmap

### Phase 2.0 — Harden (2–3 weeks)

- W-S1 lock categories; W-S2 production settings; W-S3 separate verification tokens; W-S4 throttling; W-S5 remove identity from lookup; W-S6 move nudges out of health check; W-S9 `.gitignore`.
- W-D1 savings currency; W-D2 pay creates transaction; W-D3 keep paid lines; W-D4 date format; W-D8 decoding bug.
- W-C1 first test suite + CI.

### Phase 2.1 — Correct and scale (3–4 weeks)

- Exchange-rate service (W-D5) and currency on import (W-D6).
- Indexed, paginated transaction queries (W-P1, W-P2, W-P4).
- Background worker for alerts/emails (W-P3, W-P5, W-C7).
- Per-user categories; remove dead code (W-C3).

### Phase 2.2 — Restore and delight (4–6 weeks)

- Quick multi-line entry; PDF/CSV export; backup/restore.
- Import wizard with XLSX and saved mappings.
- Recurring transactions; copy last month's budget; account balances.
- Push notifications; biometric lock.

### Phase 3 — Grow

- Receipt capture and OCR, insights, savings goals, net worth from data, Arabic/RTL, offline mode, analytics, Open Banking (from the BRD's Phase 2).

## 8. PRD updates needed

The PRD should be revised to v2.0 so it describes what is actually built:

- **§1, §5, §6.11** — architecture is now REST API + Angular + Expo mobile; Django pages are retired.
- **§3.2 Non-goals** — "native mobile apps" and "shared accounts" are now in scope (Expo app; shared personal budgets).
- **§6.2 / §6.5** — expense tracking merged into transactions; bridge removed. Decide whether multi-line entry and PDF reports return.
- **§6.8** — CM-5 is done; document generate / pay / unpay / edit / regenerate and reminders.
- **New sections** — alerts and thresholds, shared budgets and invites, accounts, email verification and password reset, onboarding, user preferences.
- **§7 Data model** — add `budgeting_alerts`, `budgeting_thresholds`, `budgeting_type_category_maps`, `budgeting_income_sources`, personal budget collections, user preferences; add `currency` to transactions.
- **§10** — replace K1–K12 with the open items from this document.
- **§12 Open questions** — Q2 and Q4 are answered (Angular + mobile; expenses are transactions). Add: which data store is the production one (Firestore vs SQLite/Postgres)?

## 9. Review scope

This review read the backend settings, URL map, auth, budgeting and shared-budget views, services, alerts, commitment schedule, Firestore models and store selection, plus the Angular core services/routes and the mobile API client, auth storage and config. Individual screen components were not reviewed line by line, so UI-level issues (e.g. K6 year pickers) should be checked separately. Findings reference file paths so each can be turned into a tracked issue.
