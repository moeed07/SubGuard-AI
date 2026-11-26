"""SMTP email sender for delivering subscription renewal reminders to the user's Gmail."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

from app.config import Settings

REMINDER_LABELS = {
    "five_days": "5 days before renewal",
    "one_day": "1 day before renewal",
    "default": "1 day before renewal",
    "one_minute": "1-minute test reminder",
}


def send_reminder_email(
    settings: Settings,
    to_email: str,
    subscription_key: str,
    target_date: str,
    reminder_type: str,
) -> bool:
    """Send a reminder email via SMTP if SMTP credentials are configured."""
    if not settings.smtp_configured or not to_email or "@" not in to_email:
        return False

    label = REMINDER_LABELS.get(reminder_type, reminder_type)
    msg = EmailMessage()
    msg["Subject"] = f"SubGuard AI Reminder: {subscription_key} charge on {target_date} ({label})"
    msg["From"] = settings.smtp_email
    msg["To"] = to_email
    msg.set_content(
        f"Hello,\n\n"
        f"This is your automated SubGuard AI reminder ({label}).\n\n"
        f"Subscription: {subscription_key}\n"
        f"Upcoming charge / renewal date: {target_date}\n\n"
        f"If you no longer wish to continue this subscription, please cancel it before {target_date}.\n\n"
        f"— SubGuard AI\n"
    )

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=12) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(settings.smtp_email, settings.smtp_app_password.replace(" ", ""))
            server.send_message(msg)
        return True
    except Exception:
        return False
