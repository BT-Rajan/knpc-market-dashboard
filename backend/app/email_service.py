"""Gmail SMTP sending + {{placeholder}} template rendering."""
import re
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from pathlib import Path

from app.config import SMTP_HOST, SMTP_PORT

_PLACEHOLDER_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")


class EmailSendError(Exception):
    pass


def render_template(text: str, variables: dict) -> str:
    """Replace {{key}} tokens with variables[key]; leaves unknown tokens as-is
    so a typo'd variable name is visible rather than silently blanked."""
    def _sub(match):
        key = match.group(1)
        return str(variables[key]) if key in variables else match.group(0)
    return _PLACEHOLDER_RE.sub(_sub, text)


def send_email(
    gmail_address: str,
    gmail_app_password: str,
    to_address: str,
    subject: str,
    html_body: str,
    attachment_path: str | None = None,
):
    if not gmail_address or not gmail_app_password:
        raise EmailSendError("Gmail sender account is not configured (Admin -> Email -> Gmail Settings).")

    msg = MIMEMultipart()
    msg["From"] = gmail_address
    msg["To"] = to_address
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html"))

    if attachment_path:
        path = Path(attachment_path)
        if path.exists():
            with open(path, "rb") as f:
                part = MIMEApplication(f.read(), Name=path.name)
            part["Content-Disposition"] = f'attachment; filename="{path.name}"'
            msg.attach(part)

    context = ssl.create_default_context()
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
            server.starttls(context=context)
            server.login(gmail_address, gmail_app_password)
            server.sendmail(gmail_address, to_address, msg.as_string())
    except smtplib.SMTPAuthenticationError as exc:
        code = getattr(exc, "smtp_code", None)
        raw = getattr(exc, "smtp_error", b"")
        google_detail = raw.decode(errors="replace").strip() if isinstance(raw, bytes) else str(raw).strip()
        raise EmailSendError(
            f"Gmail rejected the login (SMTP {code}): {google_detail}\n"
            "Common causes: (1) the account password was used instead of a "
            "16-character App Password -- Google Account -> Security -> "
            "2-Step Verification -> App passwords; (2) 2-Step Verification "
            "isn't actually turned on for this account, so App Passwords "
            "were never really available; (3) on a Google Workspace account, "
            "the admin has App Passwords disabled org-wide (Admin console -> "
            "Apps -> Google Workspace -> Gmail -> ... -> allow per-user "
            "application-specific passwords); (4) Google is blocking this "
            "server's IP as a suspicious sign-in -- check for a 'Critical "
            "security alert' email on the account, or sign in as that "
            "account in a browser and visit "
            "https://accounts.google.com/DisplayUnlockCaptcha ."
        ) from exc
    except smtplib.SMTPException as exc:
        raise EmailSendError(str(exc)) from exc
    except OSError as exc:
        # Covers DNS failures, connection refused/timeout, network unreachable --
        # these are not SMTPException subclasses and would otherwise crash the
        # request instead of being logged like every other send failure.
        raise EmailSendError(f"Could not reach {SMTP_HOST}:{SMTP_PORT} -- {exc}") from exc
