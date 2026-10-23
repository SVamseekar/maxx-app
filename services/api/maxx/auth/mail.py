"""Transactional email. `log` mode writes the message to the server log for local development."""

from __future__ import annotations

import asyncio
import logging
import smtplib
from email.message import EmailMessage

from maxx.config import settings

log = logging.getLogger("maxx.mail")
if not log.handlers:  # visible under uvicorn, whose default config silences application loggers
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(levelname)s:     %(message)s"))
    log.addHandler(_handler)
    log.setLevel(logging.INFO)
    log.propagate = False

# Tests replace this to capture outgoing mail without a network.
outbox: list[dict] = []


def _send_smtp(message: EmailMessage) -> None:
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
        smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(message)


async def send(to: str, subject: str, text: str) -> None:
    outbox.append({"to": to, "subject": subject, "text": text})
    del outbox[:-50]
    if settings.email_mode == "smtp" and settings.smtp_host:
        message = EmailMessage()
        message["From"], message["To"], message["Subject"] = settings.email_from, to, subject
        message.set_content(text)
        try:
            await asyncio.to_thread(_send_smtp, message)
        except (OSError, smtplib.SMTPException):
            # Delivery failure must not reveal whether the account exists.
            log.warning("Email delivery failed for a %s message.", subject)
        return
    # Local development: the full message, including its single-use link, goes to the log only.
    log.info("EMAIL (log mode) to=%s subject=%s\n%s", to, subject, text)


def link(path: str, token: str) -> str:
    return f"{settings.public_base_url.rstrip('/')}{path}?token={token}"


async def send_verification(to: str, name: str, token: str) -> None:
    await send(
        to,
        "Confirm your Maxx email",
        f"Hi {name},\n\nConfirm your email to finish setting up your Maxx account:\n"
        f"{link('/verify-email', token)}\n\nThis link works once and expires in 48 hours. "
        "If you did not create an account, ignore this message.\n",
    )


async def send_reset(to: str, name: str, token: str) -> None:
    await send(
        to,
        "Reset your Maxx password",
        f"Hi {name},\n\nUse this link to choose a new password:\n"
        f"{link('/reset-password', token)}\n\nThis link works once and expires in 1 hour. "
        "If you did not ask for it, ignore this message; your password has not changed.\n",
    )


async def send_alert(to: str, name: str, headline: str, detail: str) -> None:
    """A short security notice. It never contains a link that signs anyone in."""
    await send(
        to,
        f"Maxx security alert: {headline}",
        f"Hi {name},\n\n{headline}.\n\n{detail}\n\n"
        f"If this was you, nothing more is needed. If it was not, sign in at "
        f"{settings.public_base_url.rstrip('/')}/account to change your password, and review "
        "your devices and security activity.\n",
    )


async def send_signup_link(to: str, token: str) -> None:
    await send(
        to,
        "Finish creating your Maxx account",
        "Welcome to Maxx.\n\nOpen this link to confirm your email and choose how you sign in:\n"
        f"{link('/complete-signup', token)}\n\nThis link works once and expires in 24 hours. "
        "If you did not ask for an account, ignore this message and nothing will be created.\n",
    )


async def send_already_registered(to: str) -> None:
    base = settings.public_base_url.rstrip("/")
    await send(
        to,
        "You already have a Maxx account",
        "Someone (hopefully you) tried to create a Maxx account with this address, but one "
        f"already exists.\n\nSign in: {base}/login\n"
        f"Forgot how you sign in? {base}/forgot-password\n\n"
        "If this was not you, you can ignore this message; your account is unchanged.\n",
    )


async def send_signin_link(to: str, name: str, token: str) -> None:
    await send(
        to,
        "Your Maxx sign-in link",
        f"Hi {name},\n\nOpen this link to sign in:\n{link('/signin-link', token)}\n\n"
        "It works once and expires in 15 minutes. If you did not ask for it, ignore this "
        "message; nobody can sign in without it.\n",
    )


async def send_code(to: str, name: str, code: str) -> None:
    await send(
        to,
        "Your Maxx confirmation code",
        f"Hi {name},\n\nYour confirmation code is {code}. It expires in 10 minutes.\n"
        "Maxx staff never ask for this code. If you did not request it, ignore this message.\n",
    )
