"""Transactional email. `log` mode writes the message to the server log for local development."""

from __future__ import annotations

import asyncio
import logging
import smtplib
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr

from maxx.auth import mail_layout
from maxx.auth.mail_layout import Email
from maxx.config import settings

log = logging.getLogger("maxx.mail")
if not log.handlers:  # visible under uvicorn, whose default config silences application loggers
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(levelname)s:     %(message)s"))
    log.addHandler(_handler)
    log.setLevel(logging.INFO)
    log.propagate = False

# Guest judge accounts (see auth.routes.judge_entry) live under a reserved, undeliverable domain.
JUDGE_DOMAIN = "@judges.maxx.invalid"

# Tests replace this to capture outgoing mail without a network.
outbox: list[dict] = []


def _send_smtp(message: EmailMessage) -> None:
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
        smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(message)


class DeliveryError(Exception):
    """The mail server did not accept the message."""


def compose(to: str, subject: str, text: str, html: str = "") -> EmailMessage:
    """A plain-text message, with the HTML version as the preferred alternative if there is one."""
    message = EmailMessage()
    message["From"], message["To"], message["Subject"] = settings.email_from, to, subject
    message["Date"] = formatdate()
    domain = parseaddr(settings.email_from)[1].rpartition("@")[2] or None
    message["Message-ID"] = make_msgid(domain=domain)
    message.set_content(text)
    if html:
        message.add_alternative(html, subtype="html")
    return message


async def deliver(to: str, subject: str, text: str, html: str = "") -> None:
    """Send one message, raising DeliveryError if the mail server refuses it. The notification
    outbox uses this so it can retry; sign-in mail uses `send`, which never reveals a failure."""
    outbox.append({"to": to, "subject": subject, "text": text, "html": html})
    del outbox[:-50]
    if to.lower().endswith(JUDGE_DOMAIN):
        return  # judge guest accounts have no mailbox; their inbox is the in-app one
    if settings.email_mode == "smtp" and settings.smtp_host:
        try:
            await asyncio.to_thread(_send_smtp, compose(to, subject, text, html))
        except (OSError, smtplib.SMTPException) as exc:
            raise DeliveryError(type(exc).__name__) from exc
        return
    # Local development: the full message, including its single-use link, goes to the log only.
    log.info("EMAIL (log mode) to=%s subject=%s\n%s", to, subject, text)


async def deliver_email(to: str, message: Email) -> None:
    await deliver(
        to,
        message.subject,
        mail_layout.text(message),
        mail_layout.html(message, settings.public_base_url),
    )


async def send(to: str, message: Email) -> None:
    try:
        await deliver_email(to, message)
    except DeliveryError:
        # Delivery failure must not reveal whether the account exists.
        log.warning("Email delivery failed for a %s message.", message.subject)


def link(path: str, token: str) -> str:
    return f"{settings.public_base_url.rstrip('/')}{path}?token={token}"


async def send_verification(to: str, name: str, token: str) -> None:
    await send(
        to,
        Email(
            subject="Confirm your Maxx email",
            heading="Confirm your email",
            preheader="Confirm your email to finish setting up your Maxx account.",
            greeting=f"Hi {name},",
            lines=("Confirm your email to finish setting up your Maxx account.",),
            action=("Confirm email", link("/verify-email", token)),
            fallback=True,
            note="This link works once and expires in 48 hours.",
            footer="If you did not create an account, ignore this email.",
        ),
    )


async def send_reset(to: str, name: str, token: str) -> None:
    await send(
        to,
        Email(
            subject="Reset your Maxx password",
            heading="Reset your password",
            preheader="Choose a new password for your Maxx account.",
            greeting=f"Hi {name},",
            lines=("Choose a new password for your Maxx account.",),
            action=("Choose a new password", link("/reset-password", token)),
            fallback=True,
            note="This link works once and expires in 1 hour.",
            footer="If you did not ask for this, ignore this email; your password has not changed.",
        ),
    )


async def send_alert(
    to: str, name: str, headline: str, detail: str = "", facts: tuple[tuple[str, str], ...] = ()
) -> None:
    """A short security notice. It never contains a link that signs anyone in."""
    await send(
        to,
        Email(
            subject=f"Maxx security alert: {headline}",
            heading=headline,
            preheader="If this was you, nothing more is needed.",
            greeting=f"Hi {name},",
            lines=tuple(line for line in (detail,) if line)
            + (
                "If this was you, nothing more is needed. If it was not, change your password "
                "and review your devices and security activity.",
            ),
            facts=facts,
            action=("Review your account", f"{settings.public_base_url.rstrip('/')}/account"),
            footer="You get this email because it is about the security of your Maxx account.",
        ),
    )


async def send_signup_link(to: str, token: str) -> None:
    await send(
        to,
        Email(
            subject="Finish creating your Maxx account",
            heading="Finish creating your account",
            preheader="Confirm your email and choose how you sign in.",
            lines=("Welcome to Maxx. Confirm your email and choose how you sign in.",),
            action=("Finish sign-up", link("/complete-signup", token)),
            fallback=True,
            note="This link works once and expires in 24 hours.",
            footer="If you did not ask for an account, ignore this email and nothing is created.",
        ),
    )


async def send_already_registered(to: str) -> None:
    base = settings.public_base_url.rstrip("/")
    await send(
        to,
        Email(
            subject="You already have a Maxx account",
            heading="You already have an account",
            preheader="Someone tried to create a Maxx account with this address.",
            lines=(
                "Someone (hopefully you) tried to create a Maxx account with this address, but "
                "one already exists.",
            ),
            action=("Sign in", f"{base}/login"),
            secondary=("Forgot how you sign in? Reset it", f"{base}/forgot-password"),
            footer="If this was not you, ignore this email; your account is unchanged.",
        ),
    )


async def send_signin_link(to: str, name: str, token: str) -> None:
    await send(
        to,
        Email(
            subject="Your Maxx sign-in link",
            heading="Sign in to Maxx",
            preheader="Your sign-in link works once and expires in 15 minutes.",
            greeting=f"Hi {name},",
            lines=("Use this link to sign in to your Maxx account.",),
            action=("Sign in", link("/signin-link", token)),
            fallback=True,
            note="This link works once and expires in 15 minutes.",
            footer="If you did not ask for it, ignore this email; nobody can sign in without it.",
        ),
    )


async def send_code(to: str, name: str, code: str) -> None:
    await send(
        to,
        Email(
            subject="Your Maxx confirmation code",
            heading="Your confirmation code",
            preheader="Your confirmation code expires in 10 minutes.",
            greeting=f"Hi {name},",
            code=code,
            note="It expires in 10 minutes. Maxx staff never ask for this code.",
            footer="If you did not request it, ignore this email.",
        ),
    )
