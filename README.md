# Miyar Trading — Crypto Investment & Trading Platform

A full-stack crypto investment platform: users invest in admin-approved coins
(stablecoins), the platform credits balances automatically, admins issue payouts
that auto-transfer from the platform wallet, users withdraw awards to their own
crypto accounts, a 3-level referral program pays out on every investment, and a
live market monitor tracks real prices. Includes a full admin panel, KYC
verification, and a mobile-friendly PWA (installable on iOS & Android).

## Stack

| Layer     | Tech                                              |
|-----------|---------------------------------------------------|
| Backend   | Django 6 + Django REST Framework + SimpleJWT      |
| DB        | SQLite (dev) — swap `DJANGO_DB` for Postgres in prod |
| Frontend  | React 19 + Vite + React Router + lucide icons     |
| Payments  | Pluggable provider in `api/services.py` (simulate/provider/manual) |
| Mobile    | PWA (`vite-plugin-pwa`) — installable on both stores |

## Project layout

```
backend/                 Django REST API
  api/models.py          Users, Coins, Wallets, Investments, Payouts, Withdrawals,
                         CryptoAccounts, ReferralAwards, KYC, PlatformSettings, Prices
  api/views.py           API endpoints
  api/admin.py           Admin panel (approvals, payouts, KYC, platform settings)
  api/services.py        Crypto transfer provider (auto payouts & withdrawals)
  api/referrals.py       3-level referral award distribution
  api/management/commands/seed.py   Creates settings, sample coins, admin user
frontend/                React SPA + PWA
  src/pages/             Landing, Login, Register, Dashboard, WalletDetail, Market,
                         Invest, Withdraw, Payouts, Referrals, Profile, Legal pages
  src/api/client.js      Axios client with JWT auto-refresh
  src/context/AuthContext.jsx
env/                     Python virtual environment
store/                   App-store submission guides + legal documents
```

## Quick start (Windows / PowerShell)

### Backend

```powershell
cd backend
..\env\Scripts\python.exe -m pip install -r requirements.txt   # first time
..\env\Scripts\python.exe manage.py migrate
..\env\Scripts\python.exe manage.py seed
..\env\Scripts\python.exe manage.py runserver 8001
```

`seed` creates:

- Admin: **admin@miyartrading.com / admin123** → **https://127.0.0.1:8001/admin/**
- Default platform settings (referral %, cooldowns, fees, KYC toggles, payment mode)
- Sample coins: USDT, USDC, DAI, TON, SOL, BTC, …

### Frontend

```powershell
cd frontend
npm install
npm run dev        # http://localhost:5173  (proxies /api to Django)
```

### Go live with real transfers

`api/services.py` runs in three modes (PlatformSetting key `payment_mode`):

- `simulate` (default) — transfers happen instantly with fake tx hashes so the
  entire flow can be exercised end to end.
- `manual` — deposits/withdrawals wait for human confirmation; admins fill in
  the real tx hash in the admin panel.
- `provider` — the coordinator functions call your gateway/RPC
  (`PAYMENT_PROVIDER_URL`, `PAYMENT_PROVIDER_KEY` env vars). Wire each
  `send_platform_to_user` / `receive_from_user` call to your provider.

In production set the env overrides documented in `backend/backend/settings.py`
(`DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, e-mail).

## Deploy with Docker

The repo ships a ready-to-run container stack:

| Service  | Source                             | Role                                  |
|----------|------------------------------------|---------------------------------------|
| `db`     | `postgres:16-alpine`               | Application database                  |
| `redis`  | `redis:7-alpine`                   | Cache / throttling                    |
| `api`    | `backend/Dockerfile`               | Django REST + gunicorn (`:8000`)      |
| `main`   | `frontend/Dockerfile`              | Vite build + nginx (`:80`, proxies `/api`) |
| `payram` | `docker-compose.payram.yml`        | Self-hosted PayRam gateway (optional) |

```bash
# 1) configure (edit to real values, generate secrets)
cp .env.docker.example .env

# 2) build & start everything including PayRam (testnet by default)
docker compose -f docker-compose.yml -f docker-compose.payram.yml up -d --build

# 3) operations
docker compose ps
docker compose logs -f api main payram
docker compose down
```

- First boot runs `migrate`, seeds platform settings + sample coins, collects
  static files and — when `DJANGO_SUPERUSER_EMAIL/PASSWORD` are set — creates
  the admin account. In production never rely on the dev `seed` defaults.
- Static files & media are written by `api` into shared named volumes and served
  directly by nginx (`/static/`, `/media/`).
- Containers bind to the **host loopback only** (`main` → `127.0.0.1:8080`,
  `api` → `127.0.0.1:8000`, `payram` → `127.0.0.1:8081`) so the host nginx owns
  ports 80/443 and terminates TLS.

### Host nginx + TLS

Drop-in vhosts for three names are in `deploy/nginx/miyartrading.conf`:

| Hostname                    | Proxied to         |
|-----------------------------|--------------------|
| `miyartrading.com` / `www`  | `127.0.0.1:8080` (app; `/api` handled internally) |
| `api.miyartrading.com`      | `127.0.0.1:8000` (Django REST + `/admin/`) |
| `payram.miyartrading.com`   | `127.0.0.1:8081` (PayRam dashboard) |

```bash
sudo cp deploy/nginx/miyartrading.conf /etc/nginx/sites-available/miyartrading.conf
sudo ln -sf /etc/nginx/sites-available/miyartrading.conf /etc/nginx/sites-enabled/miyartrading.conf
sudo mkdir -p /var/www/certbot
sudo certbot certonly --nginx -d miyartrading.com -d www.miyartrading.com \
  -d api.miyartrading.com -d payram.miyartrading.com
sudo nginx -t && sudo systemctl reload nginx
```

Set `DJANGO_ALLOWED_HOSTS=miyartrading.com,www.miyartrading.com,api.miyartrading.com`
and keep `CORS_ALLOWED_ORIGINS` empty (the frontend calls `/api` same-origin).
- After PayRam is up, open **`https://payram.miyartrading.com`**, register the
  webhook `<your-app>/api/gateway/webhook/`, then enter the PayRam BASE_URL +
  project API key in **Admin → Payments** (or `PAYRAM_*` env vars) and hit
  **Test connection**.

## Features

- Register with optional invite code; JWT auth with refresh + blacklist logout
- Personal profile: photo, name, email, phone, change password, delete account
- KYC verification with document upload; admin toggles whether it is required
  before investing / withdrawing
- Coins managed by the admin (stablecoin flag, chain, min invest, icon)
- Investing: user picks a coin and pays from their own crypto account; the
  platform confirms receipt and credits the **invested balance** automatically
- Balances: click any wallet to see its full history (investments, withdrawals,
  payouts, referral awards)
- Withdrawals from the **withdrawable balance** (awards + payouts) to the user's
  own crypto account, with admin-controlled cooldown, min amount, and fee
- Admin payouts auto-transferred from the platform wallet to the user's account
- Referrals: 3 levels, each with an admin-set % of every confirmed investment,
  credited to the inviter's withdrawable balance
- Live market monitor from CoinGecko with 24h change
- Installable PWA for phones; legal pages hosted on the site

## Legal & stores

Publishing a financial app on the App Store / Play Store requires a privacy
policy URL, compliant terms, and often applicable licenses for financial
services / crypto activities. See `store/` for:

- `APP_STORE_SUBMISSION.md` and `PLAY_STORE_SUBMISSION.md` — steps, data-safety
  answers, category suggestions
- `PRIVACY_POLICY.md`, `TERMS_OF_SERVICE.md`, `AML_KYC_POLICY.md` — the same
  documents served on the web (also linked in the app footer)

**Disclaimer:** these documents are templates. Have them reviewed by a lawyer
qualified in the jurisdictions where you operate before launch.# Zevra
