import re
from datetime import datetime, timezone

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.auth import get_current_admin
from app.models import EmailRecipient, EmailTemplate, EmailLog, ScheduledEmail
from app.schemas import (
    EmailRecipientOut, EmailRecipientCreate, EmailRecipientUpdate,
    EmailTemplateOut, EmailTemplateCreate, EmailTemplateUpdate,
    EmailCredentialsOut, EmailCredentialsUpdate,
    EmailSendRequest, EmailSendResponse, EmailSendResult,
    EmailLogOut, ScheduledEmailCreate, ScheduledEmailOut,
)
from app.services import get_email_credentials_row, resolve_email_credentials
from app.email_batch import send_batch
from app.crypto import encrypt
from app.config import REPORTS_DIR

router = APIRouter(prefix="/api/admin/email", tags=["email"], dependencies=[Depends(get_current_admin)])


def _normalize_app_password(raw: str) -> str:
    """Google displays app passwords grouped like 'abcd efgh ijkl mnop'.
    Strip every whitespace character (not just leading/trailing -- a plain
    .strip() leaves internal spaces untouched) plus zero-width characters
    that can survive a copy-paste and look identical to a real space."""
    cleaned = re.sub(r"[\s\u200b\u200c\u200d\ufeff]+", "", raw)
    return cleaned


# --- Distribution list ---

@router.get("/recipients", response_model=List[EmailRecipientOut])
def list_recipients(db: Session = Depends(get_db)):
    return db.query(EmailRecipient).order_by(EmailRecipient.email).all()


@router.post("/recipients", response_model=EmailRecipientOut)
def add_recipient(body: EmailRecipientCreate, db: Session = Depends(get_db)):
    if db.query(EmailRecipient).filter(EmailRecipient.email == body.email).first():
        raise HTTPException(status_code=409, detail="That email is already on the distribution list")
    recipient = EmailRecipient(**body.model_dump())
    db.add(recipient)
    db.commit()
    db.refresh(recipient)
    return recipient


@router.patch("/recipients/{recipient_id}", response_model=EmailRecipientOut)
def update_recipient(recipient_id: int, body: EmailRecipientUpdate, db: Session = Depends(get_db)):
    recipient = db.get(EmailRecipient, recipient_id)
    if not recipient:
        raise HTTPException(status_code=404, detail="Recipient not found")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(recipient, key, value)
    db.commit()
    db.refresh(recipient)
    return recipient


@router.delete("/recipients/{recipient_id}")
def delete_recipient(recipient_id: int, db: Session = Depends(get_db)):
    recipient = db.get(EmailRecipient, recipient_id)
    if not recipient:
        raise HTTPException(status_code=404, detail="Recipient not found")
    db.delete(recipient)
    db.commit()
    return {"ok": True}


# --- Templates ---

@router.get("/templates", response_model=List[EmailTemplateOut])
def list_templates(db: Session = Depends(get_db)):
    return db.query(EmailTemplate).order_by(EmailTemplate.name).all()


@router.post("/templates", response_model=EmailTemplateOut)
def create_template(body: EmailTemplateCreate, db: Session = Depends(get_db)):
    if db.query(EmailTemplate).filter(EmailTemplate.name == body.name).first():
        raise HTTPException(status_code=409, detail="A template with that name already exists")
    template = EmailTemplate(**body.model_dump())
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


@router.patch("/templates/{template_id}", response_model=EmailTemplateOut)
def update_template(template_id: int, body: EmailTemplateUpdate, db: Session = Depends(get_db)):
    template = db.get(EmailTemplate, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(template, key, value)
    db.commit()
    db.refresh(template)
    return template


@router.delete("/templates/{template_id}")
def delete_template(template_id: int, db: Session = Depends(get_db)):
    template = db.get(EmailTemplate, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    db.delete(template)
    db.commit()
    return {"ok": True}


# --- Gmail sender credentials ---

def _credentials_out(row) -> "EmailCredentialsOut":
    return EmailCredentialsOut(
        configured=bool(row.gmail_address and row.gmail_app_password_encrypted),
        gmail_address=row.gmail_address,
        last_success_at=row.last_success_at,
        last_failure_at=row.last_failure_at,
        last_failure_message=row.last_failure_message,
        consecutive_failures=row.consecutive_failures or 0,
    )


@router.get("/credentials", response_model=EmailCredentialsOut)
def get_credentials(db: Session = Depends(get_db)):
    row = get_email_credentials_row(db)
    return _credentials_out(row)


@router.put("/credentials", response_model=EmailCredentialsOut)
def update_credentials(body: EmailCredentialsUpdate, db: Session = Depends(get_db)):
    row = get_email_credentials_row(db)
    if body.gmail_address is not None:
        row.gmail_address = body.gmail_address.strip() or None
    if body.gmail_app_password is not None:
        cleaned = _normalize_app_password(body.gmail_app_password)
        if cleaned and len(cleaned) != 16:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"That's {len(cleaned)} characters after removing spaces -- a Gmail "
                    "App Password is always 16 characters. Generate one at Google Account "
                    "-> Security -> 2-Step Verification -> App passwords, and paste it "
                    "in as-is (spaces are stripped automatically)."
                ),
            )
        row.gmail_app_password_encrypted = encrypt(cleaned) if cleaned else None
        # A newly entered credential deserves a clean slate -- otherwise a
        # stale failure streak from the old (bad) credential keeps showing
        # even though this is untested and might well work.
        row.consecutive_failures = 0
        row.last_failure_at = None
        row.last_failure_message = None
    db.commit()
    db.refresh(row)
    return _credentials_out(row)


# --- Send ---

@router.post("/send", response_model=EmailSendResponse)
def send_to_distribution_list(body: EmailSendRequest, db: Session = Depends(get_db)):
    template = db.get(EmailTemplate, body.template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    recipients = (
        db.query(EmailRecipient)
        .filter(EmailRecipient.id.in_(body.recipient_ids), EmailRecipient.active == True)  # noqa: E712
        .all()
    )
    if not recipients:
        raise HTTPException(status_code=400, detail="No active recipients selected")

    gmail_address, gmail_app_password = resolve_email_credentials(db)
    credentials_row = get_email_credentials_row(db)

    attachment_path = None
    if body.attach_report_filename:
        candidate = REPORTS_DIR / body.attach_report_filename
        if candidate.exists():
            attachment_path = str(candidate)
        else:
            raise HTTPException(status_code=404, detail=f"Report not found: {body.attach_report_filename}")

    sent, failed, results = send_batch(
        db, template, recipients, body.variables, attachment_path,
        gmail_address, gmail_app_password, credentials_row,
    )
    return EmailSendResponse(sent=sent, failed=failed, results=[EmailSendResult(**r) for r in results])


# --- Scheduled sends ---

def _normalize_to_naive_utc(dt: datetime) -> datetime:
    """Every timestamp column in this app is naive-but-UTC; a tz-aware value
    from the client (e.g. an ISO string with a 'Z' or offset) needs the
    offset applied and then the tzinfo stripped, or comparisons against
    datetime.utcnow() elsewhere would be silently wrong."""
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


@router.post("/schedule", response_model=ScheduledEmailOut)
def create_scheduled_email(body: ScheduledEmailCreate, db: Session = Depends(get_db)):
    template = db.get(EmailTemplate, body.template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    recipients = db.query(EmailRecipient).filter(EmailRecipient.id.in_(body.recipient_ids)).all()
    if not recipients:
        raise HTTPException(status_code=400, detail="No recipients selected")

    scheduled_at = _normalize_to_naive_utc(body.scheduled_at)
    if scheduled_at <= datetime.utcnow():
        raise HTTPException(status_code=422, detail="Scheduled time must be in the future")

    if body.attach_report_filename:
        candidate = REPORTS_DIR / body.attach_report_filename
        if not candidate.exists():
            raise HTTPException(status_code=404, detail=f"Report not found: {body.attach_report_filename}")

    sched = ScheduledEmail(
        template_id=template.id,
        template_name=template.name,
        recipient_ids=body.recipient_ids,
        variables=body.variables,
        attach_report_filename=body.attach_report_filename,
        scheduled_at=scheduled_at,
        status="pending",
    )
    db.add(sched)
    db.commit()
    db.refresh(sched)
    return sched


@router.get("/schedule", response_model=List[ScheduledEmailOut])
def list_scheduled_emails(db: Session = Depends(get_db)):
    return db.query(ScheduledEmail).order_by(ScheduledEmail.scheduled_at.desc()).all()


@router.delete("/schedule/{schedule_id}")
def cancel_scheduled_email(schedule_id: int, db: Session = Depends(get_db)):
    sched = db.get(ScheduledEmail, schedule_id)
    if not sched:
        raise HTTPException(status_code=404, detail="Scheduled email not found")
    if sched.status != "pending":
        raise HTTPException(status_code=409, detail=f"Can't cancel -- already {sched.status}")
    sched.status = "cancelled"
    db.commit()
    return {"ok": True}


@router.get("/logs", response_model=List[EmailLogOut])
def list_email_logs(limit: int = 200, db: Session = Depends(get_db)):
    return (
        db.query(EmailLog)
        .order_by(EmailLog.sent_at.desc())
        .limit(limit)
        .all()
    )
