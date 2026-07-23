"""SMTP email sending — entirely optional.

If `EMAIL_USERNAME`/`EMAIL_PASSWORD`/`EMAIL_TO` aren't all configured
(`Settings.email_enabled` is False), `send_email` logs the subject and
returns without attempting to connect anywhere. The system works fully
with no email configured, matching the "don't require API keys/credentials
unless optional" constraint -- reports are always saved to disk regardless
(see `app.scheduler.jobs`).
"""

from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config.settings import Settings
from app.utils.logging_config import get_logger

logger = get_logger("app")


def send_email(settings: Settings, subject: str, html_body: str) -> bool:
    """Send an HTML email if configured. Returns True iff an email was actually sent."""
    if not settings.email_enabled:
        logger.info("Email not configured; skipping send. Subject: %s", subject)
        return False

    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = settings.email_username
    message["To"] = settings.email_to
    message.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        server.starttls()
        server.login(settings.email_username, settings.email_password)
        server.sendmail(settings.email_username, [settings.email_to], message.as_string())

    logger.info("Email sent: %s", subject)
    return True
