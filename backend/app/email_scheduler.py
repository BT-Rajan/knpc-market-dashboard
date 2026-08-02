"""Fires scheduled emails once their scheduled_at time arrives. Runs as its
own lightweight BackgroundScheduler (separate from the scrape scheduler in
app/scraper/scheduler.py) checking every minute for due, still-pending
rows."""
import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.db import SessionLocal
from app.models import ScheduledEmail, EmailTemplate, EmailRecipient
from app.services import get_email_credentials_row, resolve_email_credentials
from app.email_batch import send_batch
from app.config import REPORTS_DIR

logger = logging.getLogger("knpc.email_scheduler")

_scheduler = BackgroundScheduler()
_JOB_ID = "dispatch_scheduled_emails"


def _dispatch(db, sched: ScheduledEmail):
    template = db.get(EmailTemplate, sched.template_id)
    if not template:
        sched.status = "failed"
        sched.result_summary = "Template no longer exists"
        sched.sent_at = datetime.utcnow()
        db.commit()
        logger.warning("Scheduled email %s: template %s missing", sched.id, sched.template_id)
        return

    recipients = (
        db.query(EmailRecipient)
        .filter(EmailRecipient.id.in_(sched.recipient_ids or []), EmailRecipient.active == True)  # noqa: E712
        .all()
    )
    if not recipients:
        sched.status = "failed"
        sched.result_summary = "No active recipients (removed or disabled since this was scheduled)"
        sched.sent_at = datetime.utcnow()
        db.commit()
        logger.warning("Scheduled email %s: no active recipients left", sched.id)
        return

    attachment_path = None
    if sched.attach_report_filename:
        candidate = REPORTS_DIR / sched.attach_report_filename
        if candidate.exists():
            attachment_path = str(candidate)

    gmail_address, gmail_app_password = resolve_email_credentials(db)
    credentials_row = get_email_credentials_row(db)

    sent, failed, _results = send_batch(
        db, template, recipients, sched.variables or {}, attachment_path,
        gmail_address, gmail_app_password, credentials_row,
    )

    sched.status = "sent" if failed == 0 else ("partially_failed" if sent > 0 else "failed")
    sched.sent_at = datetime.utcnow()
    sched.result_summary = f"{sent} sent, {failed} failed"
    db.commit()
    logger.info("Scheduled email %s dispatched: %s", sched.id, sched.result_summary)


def _job():
    db = SessionLocal()
    try:
        due = (
            db.query(ScheduledEmail)
            .filter(ScheduledEmail.status == "pending", ScheduledEmail.scheduled_at <= datetime.utcnow())
            .all()
        )
        for sched in due:
            _dispatch(db, sched)
    finally:
        db.close()


def start():
    if _scheduler.running:
        return
    _scheduler.add_job(_job, IntervalTrigger(minutes=1), id=_JOB_ID, replace_existing=True)
    _scheduler.start()
    logger.info("Email scheduler started, checking for due sends every minute")
