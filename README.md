# KNPC Market Intelligence Dashboard

FastAPI + React monolith. Replaces the old Streamlit/FastAPI-mixed repo
(`knpc-dashboard`, now archived) — this is the single, current codebase.

## Stack
- Backend: FastAPI, SQLAlchemy, MySQL (pymysql)
- Frontend: React + TypeScript (Vite), served by the backend as static files in prod
- Scheduler: APScheduler, configurable interval (default 30 min)

## Roles
Two fixed accounts, no self-signup: `admin` (full access — sources,
scrape settings, reports) and `user` (viewer — dashboard, ticker, news, reports).
Credentials are bcrypt hashes set via environment — see `backend/.env.example`.

## Setup
```
cd backend
cp .env.example .env
# fill in DB_*, SESSION_SECRET, ADMIN_PASSWORD_HASH, USER_PASSWORD_HASH
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python run.py

cd ../frontend
npm install
npm run build   # outputs to frontend/dist, served by the backend
```

## What it does
- Scrapes configurable sources (per item, with fallback priority) on a
  timer, default every 30 minutes — admin can change the interval and
  add/disable sources without a redeploy.
- Stores prices and news in MySQL, shown live on a ticker dashboard.
- Tracks a news feed per tracked item.
- Generates quarterly reports from the collected data.

See `BUILD_REPORT.md` and `FEATURE_UPDATES.md` for build verification and
feature history carried over from the rebuild branch.
