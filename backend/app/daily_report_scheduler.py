"""Sends the "Daily Price Movement Report" email once a day at a fixed
Kuwait wall-clock time to every active recipient in the distribution list.
Runs as its own lightweight BackgroundScheduler, separate from both the
scrape scheduler (app/scraper/scheduler.py) and the one-off scheduled-email
dispatcher (app/email_scheduler.py) -- this one is always-on and not tied to
any admin-created ScheduledEmail row.
"""
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.db import SessionLocal
from app.models import EmailTemplate, EmailRecipient
from app.services import (
    daily_price_movement_rows,
    render_daily_price_movement_table_html,
    get_email_credentials_row,
    resolve_email_credentials,
)
from app.email_batch import send_batch
from app.config import KUWAIT_TZ, DAILY_PRICE_EMAIL_HOUR_KWT, DAILY_PRICE_EMAIL_MINUTE_KWT

logger = logging.getLogger("knpc.daily_report_scheduler")

_scheduler = BackgroundScheduler()
_JOB_ID = "daily_price_movement_email"
TEMPLATE_NAME = "Daily Price Movement Report"


def send_daily_price_movement_report(db=None) -> dict:
    """Builds and sends today's price-movement table to every active
    recipient. Returns a small summary dict; safe to call directly (e.g. for
    an admin "send now" button or a manual test) as well as from the cron
    job. Skips quietly (with a log line) if there's no template, no active
    recipients, or no Gmail sender configured yet, rather than raising --a
    misconfigured deployment shouldn't crash the scheduler thread."""
    owns_session = db is None
    db = db or SessionLocal()
    try:
        template = db.query(EmailTemplate).filter(EmailTemplate.name == TEMPLATE_NAME).first()
        if not template:
            logger.warning("Daily price movement report: template '%s' not found -- skipping", TEMPLATE_NAME)
            return {"status": "skipped", "reason": "template_missing"}

        recipients = db.query(EmailRecipient).filter(EmailRecipient.active == True).all()  # noqa: E712
        if not recipients:
            logger.info("Daily price movement report: no active recipients configured -- skipping")
            return {"status": "skipped", "reason": "no_recipients"}

        gmail_address, gmail_app_password = resolve_email_credentials(db)
        if not gmail_address or not gmail_app_password:
            logger.warning("Daily price movement report: Gmail sender not configured -- skipping")
            return {"status": "skipped", "reason": "no_sender_configured"}

        now_kwt = datetime.now(ZoneInfo(KUWAIT_TZ))
        rows = daily_price_movement_rows(db)
        variables = {
            "report_date": now_kwt.strftime("%d %b %Y"),
            "report_time": now_kwt.strftime("%H:%M"),
            "price_table": render_daily_price_movement_table_html(rows),
        }

        credentials_row = get_email_credentials_row(db)
        sent, failed, results = send_batch(
            db, template, recipients, variables, None,
            gmail_address, gmail_app_password, credentials_row,
        )
        logger.info("Daily price movement report: %s sent, %s failed", sent, failed)
        return {"status": "sent", "sent": sent, "failed": failed, "results": results}
    finally:
        if owns_session:
            db.close()


def _job():
    send_daily_price_movement_report()


def start():
    if _scheduler.running:
        return
    _scheduler.add_job(
        _job,
        CronTrigger(hour=DAILY_PRICE_EMAIL_HOUR_KWT, minute=DAILY_PRICE_EMAIL_MINUTE_KWT, timezone=ZoneInfo(KUWAIT_TZ)),
        id=_JOB_ID, replace_existing=True,
    )
    _scheduler.start()
    logger.info(
        "Daily price movement report scheduler started: %02d:%02d %s",
        DAILY_PRICE_EMAIL_HOUR_KWT, DAILY_PRICE_EMAIL_MINUTE_KWT, KUWAIT_TZ,
    )
