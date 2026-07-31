# KNPC Market Intelligence Dashboard

FastAPI + React monolith. Replaces the old Streamlit/FastAPI-mixed repo
(`knpc-dashboard`, now archived) — this is the single, current codebase.

## Layout
```
backend/    FastAPI app, SQLAlchemy models, scraper, report/email generation
frontend/   React + TypeScript (Vite)
scripts/    One-shot installers (Linux/macOS + Windows)
docs/archive/  Historical dev-session notes -- not current documentation
```

## Stack
- Backend: FastAPI, SQLAlchemy, MySQL (pymysql)
- Frontend: React + TypeScript (Vite), served by the backend as static files in prod
- Scheduler: APScheduler, configurable interval (default 30 min)

## Roles
Two fixed accounts, no self-signup: `admin` (full access — sources,
scrape settings, reports, email) and `user` (viewer — dashboard, ticker,
news, reports). Credentials are bcrypt hashes set via environment.

## Setup
Either run `scripts/install.sh` (Linux/macOS) or `scripts/install.bat`
(Windows) — both create the venv, write `backend/.env` (prompting for DB
and admin credentials, generating `SESSION_SECRET`/`ENCRYPTION_KEY`/password
hashes), and build the frontend.

Or manually:
```
cd backend
cp .env.example .env
# fill in DB_*, SESSION_SECRET, ENCRYPTION_KEY, ADMIN_PASSWORD_HASH, USER_PASSWORD_HASH
# (see the generator commands in .env.example for each)
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python run.py

cd ../frontend
npm install
npm run build   # outputs to frontend/dist, served by the backend
```

Gmail sending (distribution-list emails) is configured separately, from
the app itself: Admin → Email → Gmail Settings, using a Gmail App
Password. It's stored encrypted in the DB, not in `.env`.

## What it does
- Scrapes configurable sources (per item, with fallback priority) on a
  timer, default every 30 minutes — admin can change the interval and
  add/disable sources without a redeploy.
- Stores prices and news in MySQL, shown live on a ticker dashboard.
- Tracks a news feed per tracked item plus an independent general
  market-news feed.
- Generates quarterly reports from the collected data.
- Sends templated emails (Admin → Email) to an admin-managed distribution
  list — multiple reusable templates, multi-recipient send, per-recipient
  delivery log.

See `docs/archive/` for historical build/feature notes from earlier in
development — not current documentation.
