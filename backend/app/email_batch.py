"""Shared per-recipient render+send+log logic. Used by both the manual
'send now' endpoint and the scheduled-email dispatcher so the two paths
can't quietly drift apart from each other."""
import re
from datetime import datetime

from app.models import EmailLog
from app.email_service import send_email, render_template, EmailSendError


def send_batch(db, template, recipients, variables, attachment_path,
                gmail_address, gmail_app_password, credentials_row):
    """Sends `template` to each of `recipients`, rendering `variables` (plus
    recipient_name) into it. Returns (sent, failed, results); results is a
    list of dicts: {"recipient", "status", "message"}. Commits per
    recipient so a mid-batch crash doesn't lose progress already made."""
    results = []
    sent, failed = 0, 0
    for recipient in recipients:
        merged_vars = {**variables, "recipient_name": recipient.name or recipient.email}
        subject = render_template(template.subject, merged_vars)
        body_html = render_template(template.body_html, merged_vars)
        unfilled = sorted(set(re.findall(r"\{\{\s*(\w+)\s*\}\}", subject + " " + body_html)))
        unfilled_note = f"unfilled placeholders: {', '.join(unfilled)}" if unfilled else None
        try:
            send_email(gmail_address, gmail_app_password, recipient.email, subject, body_html, attachment_path)
            db.add(EmailLog(template_name=template.name, recipient=recipient.email, status="success", message=unfilled_note))
            results.append({"recipient": recipient.email, "status": "success", "message": unfilled_note})
            credentials_row.last_success_at = datetime.utcnow()
            credentials_row.consecutive_failures = 0
            sent += 1
        except EmailSendError as exc:
            db.add(EmailLog(template_name=template.name, recipient=recipient.email, status="error", message=str(exc)))
            results.append({"recipient": recipient.email, "status": "error", "message": str(exc)})
            credentials_row.last_failure_at = datetime.utcnow()
            credentials_row.last_failure_message = str(exc)
            credentials_row.consecutive_failures = (credentials_row.consecutive_failures or 0) + 1
            failed += 1
        db.commit()
    return sent, failed, results
