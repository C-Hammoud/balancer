# Deploying to Render (private beta)

[`render.yaml`](../../render.yaml) in the repo root describes everything, so Render creates it in one go:

| Service | What it is | Plan | Rough cost |
|---|---|---|---|
| `balancer-web` | The Angular web app (static site) | Free | $0 |
| `balancer-api` | Django API, plus the background jobs in the same service | `0.5c-512mb` | ~$7/month |
| `balancer-db` | PostgreSQL 17 | `0.1c-256mb` | ~$6/month + storage |

Render shows the exact total before you confirm. Everything is in Frankfurt; to change that, edit `region` in
`render.yaml` (in both the database and the API) **before** the first deploy, because it can't be changed later.

HTTPS is included from the first minute on the `onrender.com` addresses.

## Why not the free plans?

The API and the database both have free plans, but they don't work for real users:

- **No email:** free services can't connect to mail servers, so sign-up verification emails never arrive.
- **The database is deleted:** a free database expires after 30 days, and its data is deleted 14 days later.
- **It sleeps:** after 15 minutes without visitors the API stops. The next visitor waits about a minute, and the
  background jobs (alerts, reminders, ticket auto-close) don't run while it sleeps.

## 1. Before you start

1. **Replace the Gmail app password** if you haven't yet. Google Account → Security → App passwords: delete the old
   one and create a new one.
2. **Push the code to GitHub.** Render builds from the repo, so `render.yaml` must be on `main`.
3. Check that the GitHub "tests" run passes (repo → **Actions**).

## 2. Create everything

1. Sign up at [render.com](https://render.com) with your GitHub account and add a payment card.
2. Dashboard → **New** → **Blueprint**.
3. Connect GitHub and allow access to the `C-Hammoud/balancer` repo, then select it.
4. Render reads `render.yaml` and lists the three resources. Fill in the values it asks for:
   - `EMAIL_HOST_USER`: your Gmail address
   - `EMAIL_HOST_PASSWORD`: the **new** app password
   - `DEFAULT_FROM_EMAIL`: your Gmail address
5. Check the cost and click **Apply** (or **Deploy Blueprint**).

The first deploy takes about 5–10 minutes. The API creates the database tables itself when it starts.

## 3. Check the addresses

Open each service in the dashboard and look at the address under its name.

- If they are `https://balancer-api.onrender.com` and `https://balancer-web.onrender.com`, nothing needs changing.
- If Render added something (for example `balancer-api-x7k2.onrender.com` because the name was taken), correct them:
  - in `balancer-api` → **Environment**: `API_PUBLIC_URL`, `FRONTEND_URL`, `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS`;
  - in `balancer-web` → **Environment**: `API_URL`, then **Manual Deploy** so the web app is rebuilt;
  - in `render.yaml`: the same values, so the next sync doesn't undo them. Commit and push.

Then check:

- `https://balancer-api.onrender.com/healthz/` answers.
- `https://balancer-web.onrender.com` shows the sign-in page.
- You can sign up and the verification email arrives. If it doesn't, look at `balancer-api` → **Logs** for `SMTP` errors.

## 4. Make yourself admin

Sign up on the site and verify your email. Then in `balancer-api` → **Shell**:

```bash
python manage.py set_admin <your email> --superuser
```

## 5. (Optional) Load your existing data

Do this **before** anyone starts using the site, on an empty database, so skip the sign-up in step 4 until afterwards.
Only services inside Render can reach the database, so let your PC in for a moment.

1. In `BE`, with your normal local settings, export the data:

   ```powershell
   python manage.py dumpdata --natural-foreign --exclude contenttypes --exclude auth.permission --exclude admin.logentry --exclude sessions -o data.json
   ```

2. `balancer-db` → **Info** → access control: add your IP address. Copy the **External Database URL**.
3. Still in `BE`, in the same PowerShell window (these settings only last for this window):

   ```powershell
   $env:DATA_STORE = "postgres"
   $env:DATABASE_URL = "<External Database URL>"
   python manage.py loaddata data.json
   Remove-Item Env:DATABASE_URL, Env:DATA_STORE
   ```

4. Remove your IP from the access control list, and delete `data.json`.
5. Run the `set_admin` command from step 4 with your existing account.

## 6. Backups

Paid Render databases are backed up automatically. Check what your plan includes in `balancer-db` → **Recovery**, and
try a restore once before inviting people. The app's own nightly `pg_dump` is switched off here (`BACKUP_ENABLED=0`)
because a Render service's disk is erased on every deploy.

For a copy outside Render, from your PC (with your IP allowed as in step 5):

```powershell
pg_dump --no-owner --dbname "<External Database URL>" -f balancer-backup.sql
```

## 7. Updating

Push to `main`. Render rebuilds only what changed (`BE/**` the API, `FE/**` the web app), and migrations run when the
API starts. If a new version fails its health check, Render keeps the old one running.

## 8. Later

- **Your own domain:** service → **Settings** → **Custom Domains**, then add it at your domain provider as Render
  describes. Update the four API addresses and `API_URL` from step 3. Render handles the certificate.
- **Longer HTTPS lock-in:** once a domain is stable, raise `DJANGO_HSTS_SECONDS` to `31536000`.
- **Mobile app:** set `EXPO_PUBLIC_API_URL=https://balancer-api.onrender.com/api/v1`. It's already HTTPS, which store builds require.
- **More traffic:** a bigger plan for the API, a separate `worker` service for `python manage.py run_scheduler`
  (then set `RUN_SCHEDULER_IN_PROCESS=0`), and a Key Value (Redis) service for `REDIS_URL`, so rate limits are shared
  between processes.

## Troubleshooting

| Problem | Likely cause and fix |
|---|---|
| Blueprint rejected because of a plan name | Render changes plan names now and then. Pick the matching plan on the form or update `plan:` in `render.yaml`. |
| API deploy fails or restarts | `balancer-api` → **Logs**. "Out of memory": set `WEB_CONCURRENCY=1` or move to a bigger plan. |
| Web app shows network errors or CORS errors in the browser console | The addresses from step 3 don't match. `CORS_ALLOWED_ORIGINS` must be exactly the web app's address, with no trailing `/`. |
| "Bad Request (400)" from the API | The request used a host Django doesn't know. For a custom domain, add it to `DJANGO_ALLOWED_HOSTS`. |
| Verification email never arrives | Logs show a timeout: check the service isn't on the free plan. Logs show an authentication error: re-create the Gmail app password. |
| Page refresh gives a 404 | The `/* → /index.html` rewrite is missing on `balancer-web` → **Redirects/Rewrites**. |

## Before inviting beta users

Same as the checklist in [oracle.md](oracle.md#before-inviting-beta-users): click through as a normal user and as
admin. Check the background jobs in `balancer-api` → **Logs** by searching for `scheduler`.
