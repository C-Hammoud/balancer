# Deploying to the Oracle Cloud server (private beta)

This guide puts the whole app on one Oracle Cloud server (Ubuntu, Ampere ARM):

| Container | What it does |
|---|---|
| `web` (Caddy) | Serves the web app, forwards `/api` to Django, and gets HTTPS automatically once you have a domain |
| `api` | Django API (gunicorn); applies database migrations on every start |
| `scheduler` | Background jobs: alert emails, payment reminders, risk check, support tickets, nightly database backup |
| `db` | PostgreSQL 17, with its data in a Docker volume and not reachable from the internet |
| `redis` | Shared cache for rate limits and alert throttling; not reachable from the internet |

Everything is defined in `deploy/docker-compose.yml`; settings live in `deploy/.env`.

Commands marked **PC** run on your Windows computer; everything else runs on the server over SSH.

---

## 1. Before you start (PC)

1. **Replace the Gmail app password.** The one in `BE/.env` was exposed while debugging.
   1. Google Account → Security → 2-Step Verification → App passwords.
   2. Delete the old password, then create a new one named "Balancer server".
   3. You'll paste it into the server's `deploy/.env` in step 6, and nowhere else.
2. **Put the code in a private Git repository.**
   - Create a **private** repo on GitHub, then commit and push the project folder. The mobile app is a separate repo.
   - Check that these are **not** included: `BE/.env`, `BE/db.sqlite3`, `BE/*firebase_key*.json`, `deploy/.env`.
     They are git-ignored; `git status` should not list them.
3. **Optional: bring your current data.**
   - With the local backend's virtual environment active, in `BE` (**PC**):
     ```
     python manage.py dumpdata --natural-foreign --exclude contenttypes --exclude auth.permission ^
       --exclude admin.logentry --exclude sessions --exclude token_blacklist --indent 2 -o data.json
     ```
   - You'll load `data.json` in step 9. Skip this to start the beta empty.

## 2. Open the ports in the Oracle Cloud console

1. Instance page → **Primary VNIC** → Subnet → **Security Lists** → the default security list → **Add Ingress Rules**.
2. Add two rules:

| Source CIDR | IP protocol | Destination port |
|---|---|---|
| `0.0.0.0/0` | TCP | 80 |
| `0.0.0.0/0` | TCP | 443 |

If your instance uses a Network Security Group instead, add the same two rules there.

## 3. Connect and open the ports in Ubuntu too

Oracle's Ubuntu images have their own firewall (iptables) that blocks everything except SSH. **Both** the console rules
and these are needed. Missing one of them is the usual reason the site doesn't load.

```bash
# PC (PowerShell): connect with the key you downloaded when creating the instance
ssh -i C:\path\to\ssh-key.key ubuntu@<SERVER_IP>
```

```bash
sudo iptables -L INPUT --line-numbers        # note the number of the "REJECT" line, usually 5 or 6
sudo iptables -I INPUT 5 -m state --state NEW -p tcp --dport 80 -j ACCEPT    # use that number
sudo iptables -I INPUT 5 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save               # keep the rules after a reboot
```

Do **not** enable `ufw` as well; it conflicts with these rules.

## 4. Install Docker

```bash
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y ca-certificates curl git
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker ubuntu
exit        # log out and SSH in again so the docker group applies
```

Check it after reconnecting: `docker run --rm hello-world`.

## 5. Get the code

Create a **deploy key** so the server can read your private repo:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/github_deploy -N ""
cat ~/.ssh/github_deploy.pub
```

1. In GitHub, open the repo → Settings → Deploy keys → Add key, paste the key, and leave write access off.
2. Then:

```bash
cat >> ~/.ssh/config <<'EOF'
Host github.com
  IdentityFile ~/.ssh/github_deploy
EOF
sudo mkdir -p /opt/balancer && sudo chown ubuntu:ubuntu /opt/balancer
git clone git@github.com:C-Hammoud/balancer.git /opt/balancer
cd /opt/balancer
```

## 6. Configure

```bash
cd /opt/balancer
cp deploy/.env.example deploy/.env
openssl rand -hex 32     # run twice: one value for DJANGO_SECRET_KEY, one for POSTGRES_PASSWORD
nano deploy/.env
```

Set at least the following (the file explains each line):

| Setting | Value |
|---|---|
| `DJANGO_SECRET_KEY`, `POSTGRES_PASSWORD` | The two random values |
| `DJANGO_ALLOWED_HOSTS` | `<SERVER_IP>` |
| `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS`, `FRONTEND_URL` | `http://<SERVER_IP>` |
| `API_PUBLIC_URL` | `http://<SERVER_IP>/api/v1` |
| `EMAIL_HOST_USER`, `DEFAULT_FROM_EMAIL` | Your Gmail address |
| `EMAIL_HOST_PASSWORD` | The **new** app password |
| `SITE_ADDRESS`, `DJANGO_SECURE_SSL_REDIRECT`, `DJANGO_HSTS_SECONDS` | Leave `SITE_ADDRESS=:80` and the two HTTPS switches at `0` until you have a domain |

Save with Ctrl+O, Enter, Ctrl+X.

## 7. Create the database and start everything

```bash
mkdir -p deploy/backups
docker compose -f deploy/docker-compose.yml up -d --build
```

The first build takes a few minutes on ARM. What happens:
- **PostgreSQL** creates the database `balancer` and the user `balancer` (with `POSTGRES_PASSWORD`) on its first start.
- **The API** waits for the database, then creates all the tables (Django migrations).
- **The scheduler** starts a minute later, and **Caddy** starts once the API is healthy.

To look inside the database at any time:

```bash
docker compose -f deploy/docker-compose.yml exec db psql -U balancer balancer
#   \dt          list tables
#   \q           quit
```

Tip: `alias dc='docker compose -f /opt/balancer/deploy/docker-compose.yml'` (add it to `~/.bashrc`) shortens the
commands below to `dc ps`, `dc logs api`, and so on.

## 8. Check that it works

```bash
docker compose -f deploy/docker-compose.yml ps          # every service "running" / "healthy"
curl http://localhost/healthz/                          # {"status":"ok"}
docker compose -f deploy/docker-compose.yml logs --tail=50 api scheduler
```

Then open `http://<SERVER_IP>` in your browser and register.

## 9. Your data and your admin account

If you made `data.json` in step 1, copy it up (**PC**) and load it right away, before anyone registers:

```powershell
scp -i C:\path\to\ssh-key.key BE\data.json ubuntu@<SERVER_IP>:/opt/balancer/
```

```bash
cd /opt/balancer
docker compose -f deploy/docker-compose.yml cp data.json api:/tmp/data.json
docker compose -f deploy/docker-compose.yml exec api python manage.py loaddata /tmp/data.json
rm data.json
```

Make yourself the admin (the Admin menu appears after you reload the web app):

```bash
docker compose -f deploy/docker-compose.yml exec api python manage.py set_admin <your username or email> --superuser
```

## 10. Backups

The scheduler writes a compressed copy of the database to `/opt/balancer/deploy/backups/` every night and keeps the last
14 (`BACKUP_KEEP`). The files are on the same server, so copy them somewhere else regularly (**PC**):

```powershell
scp -i C:\path\to\ssh-key.key "ubuntu@<SERVER_IP>:/opt/balancer/deploy/backups/*.sql.gz" D:\Backups\balancer\
```

**Test a restore once** into a scratch database, so you know it works:

```bash
cd /opt/balancer
F=$(ls -t deploy/backups/*.sql.gz | head -1)
docker compose -f deploy/docker-compose.yml exec db createdb -U balancer restore_test
gunzip -c "$F" | docker compose -f deploy/docker-compose.yml exec -T db psql -q -U balancer -d restore_test
docker compose -f deploy/docker-compose.yml exec db psql -U balancer -d restore_test -c "select count(*) from auth_user;"
docker compose -f deploy/docker-compose.yml exec db dropdb -U balancer restore_test
```

**A real restore** (replaces all data):
1. Stop `api`, `scheduler` and `web`.
2. Drop and recreate `balancer`, then load the file the same way.
3. Start everything again.

## 11. Updating to a new version

```bash
cd /opt/balancer
git pull
docker compose -f deploy/docker-compose.yml up -d --build
```

Database migrations run automatically when the API restarts. Check `ps` and the logs afterwards (step 8).

## 12. Later: a domain and HTTPS

1. Buy a domain and add an **A record** (e.g. `app.example.com`) pointing to `<SERVER_IP>`. Wait until
   `nslookup app.example.com` shows the IP.
2. In `deploy/.env`:
   - `SITE_ADDRESS=app.example.com` and `ACME_EMAIL=<your email>`;
   - every `http://<SERVER_IP>` becomes `https://app.example.com`, and `DJANGO_ALLOWED_HOSTS=app.example.com`;
   - `DJANGO_SECURE_SSL_REDIRECT=1` and `DJANGO_HSTS_SECONDS=3600`. Raise it to `31536000` after a week without
     problems; browsers remember it, so start small.
3. Run `docker compose -f deploy/docker-compose.yml up -d`. Caddy gets the certificate within a minute and renews it
   by itself.

## 13. Mobile app (beta testers using Expo Go)

In the mobile project set `EXPO_PUBLIC_API_URL=http://<SERVER_IP>/api/v1` (or `https://app.example.com/api/v1`), then
`npx expo start`. Expo Go accepts plain HTTP. App-store builds need the domain and HTTPS first.

## Background jobs

| Job | Every | Interval setting |
|---|---|---|
| Budget alert emails | 30 min | `SCHEDULE_BUDGET_ALERTS_MINUTES` |
| Setup reminder emails | 30 min | `SCHEDULE_SETUP_NUDGES_MINUTES` |
| Support tickets: reminders, auto-close, pool assignment | 60 min | `SCHEDULE_SUPPORT_TICKETS_MINUTES` |
| Risk check (score history and risk alerts) | daily | `SCHEDULE_RISK_MINUTES` |
| Commitment payment reminders | daily | `SCHEDULE_COMMITMENT_REMINDERS_MINUTES` |
| Budget plan suggestions | daily | `SCHEDULE_BUDGET_PLANS_MINUTES` |
| Database backup | daily | `SCHEDULE_BACKUP_MINUTES` |

Each run is logged: `docker compose -f deploy/docker-compose.yml logs -f scheduler`. A failing job is logged and
retried at its next turn.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Page doesn't load at all | Ports: step 2 **and** step 3 |
| "Bad Request (400)" | `DJANGO_ALLOWED_HOSTS` must contain exactly the IP or domain you type in the browser |
| Browser jumps to `https://` and fails | `DJANGO_SECURE_SSL_REDIRECT=0` and `DJANGO_HSTS_SECONDS=0` while there's no domain, then restart. Clear the browser's HSTS entry: `chrome://net-internals/#hsts` → delete the IP |
| No emails arrive | `docker compose … logs api` for SMTP errors; check the app password. Admin → Users → (user) also lists every email and its result |
| A service keeps restarting | `docker compose … logs <service>`; usually a missing or wrong value in `deploy/.env` |
| Gmail limits | A personal Gmail account sends about 500 emails a day: enough for a beta, not for a public launch |

## Before inviting beta users

- [ ] Register a test user and receive the verification email; reset its password.
- [ ] Add income, an account, a few transactions (one transfer, one pending).
- [ ] Create a plan with a trip sub-budget; tag an expense to the trip.
- [ ] Check the risk card on the dashboard.
- [ ] Open a support ticket as the test user; answer and resolve it as admin; confirm it as the user. Both closing
      emails arrive.
- [ ] A backup file appears in `deploy/backups` the next day, and the restore test works.
- [ ] Decide whether alert and reminder emails go out during the beta (`NOTIFICATION_EMAILS_ENABLED`).

**Known limits of the beta:**
- no error monitoring service (read the logs);
- no "export / delete my account" yet (needed before a public launch);
- app-store releases need a domain and HTTPS first.
