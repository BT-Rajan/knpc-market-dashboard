import logging
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from app.db import SessionLocal
from app.models import ScrapeSetting
from app.scraper.runner import run_full_scrape
from app.config import (
    DEFAULT_SCRAPE_FREQUENCY_MINUTES, KUWAIT_TZ,
    DAILY_SCRAPE_HOUR_KWT, DAILY_SCRAPE_MINUTE_KWT,
)

logger = logging.getLogger("knpc.scheduler")

_scheduler = BackgroundScheduler()
_JOB_ID = "scrape_all"
_DAILY_JOB_ID = "scrape_all_daily_kwt"


def _job():
    db = SessionLocal()
    try:
        run_full_scrape(db)
    finally:
        db.close()


def _current_frequency_minutes() -> int:
    db = SessionLocal()
    try:
        setting = db.query(ScrapeSetting).first()
        return setting.frequency_minutes if setting else DEFAULT_SCRAPE_FREQUENCY_MINUTES
    finally:
        db.close()


def start():
    if _scheduler.running:
        return
    minutes = _current_frequency_minutes()
    _scheduler.add_job(
        _job, IntervalTrigger(minutes=minutes), id=_JOB_ID,
        replace_existing=True,
    )
    # Fixed daily run pinned to Kuwait wall-clock time, independent of the
    # admin-configurable interval job above -- this is the guaranteed "once a
    # day, same real-world time" reading the dashboard/date views and reports
    # are built around, regardless of what the interval is set to or when the
    # process happened to start. Scraping is append-only (see
    # app/scraper/runner.py) so this never clobbers a reading the interval
    # job already took today; it just adds one.
    _scheduler.add_job(
        _job,
        CronTrigger(hour=DAILY_SCRAPE_HOUR_KWT, minute=DAILY_SCRAPE_MINUTE_KWT, timezone=ZoneInfo(KUWAIT_TZ)),
        id=_DAILY_JOB_ID, replace_existing=True,
    )
    _scheduler.start()
    logger.info(
        "Scheduler started: interval=%s minutes, daily fixed run=%02d:%02d %s",
        minutes, DAILY_SCRAPE_HOUR_KWT, DAILY_SCRAPE_MINUTE_KWT, KUWAIT_TZ,
    )


def reschedule(minutes: int):
    """Called by the admin panel when the scrape frequency is changed."""
    if _scheduler.get_job(_JOB_ID):
        _scheduler.reschedule_job(_JOB_ID, trigger=IntervalTrigger(minutes=minutes))
    else:
        _scheduler.add_job(_job, IntervalTrigger(minutes=minutes), id=_JOB_ID, replace_existing=True)
    logger.info("Scheduler rescheduled, interval=%s minutes", minutes)


def trigger_now():
    """Manual 'scrape now' from the admin panel — runs in the caller's thread."""
    _job()
