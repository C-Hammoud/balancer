# Finance Tracker UI (Angular)

Angular 19 frontend for the Finance Tracker Django REST API.

## Setup

```bash
cd FE
npm install
npm start
```

App runs at **http://localhost:4200** and proxies API calls to `http://127.0.0.1:8000/api/v1`.

**Phone / tablet on the same Wi‑Fi:** open `http://<your-computer-ip>:4200` (e.g. `http://192.168.1.10:4200`). The dev server listens on all interfaces (`--host 0.0.0.0`) and proxies `/api` to Django on your PC.

Start the backend separately:

```bash
# from repo root, with venv active
python manage.py runserver
```

## Features

- JWT login / register (tokens stored in `localStorage`)
- Auto token refresh on 401
- Dashboard (expense summary + budget utilization + alerts)
- Expenses list / add / delete
- Budgeting dashboard (utilization bars, edit forecast, transactions)
- Alerts center (open / resolve)

## Config

Edit `src/environments/environment.ts`:

```ts
apiUrl: '/api/v1'  // proxied to Django in dev (see proxy.conf.json)
```

Production build uses `environment.prod.ts` (`apiUrl: '/api/v1'` for same-origin deploy).

Ensure Django CORS allows Angular:

```env
CORS_ALLOWED_ORIGINS=http://localhost:4200
```
