"""Notifications for buyers and sellers: an in-app inbox, with email delivered from an outbox.

Every notification is first a database row. The worker then emails it, retrying with growing
gaps, so a mail outage delays a message instead of losing it, and a crash cannot send it twice
(a row is claimed before it is sent). A `dedupe_key` makes "remind once per deadline" atomic.

What goes into an email is deliberately plain: a fixed sentence, a product title with any links
removed, and a link to a page on this site. Text that another person wrote (a buyer's or seller's
message) is never copied into an email, so nobody can use Maxx's mail to send a phishing link.
"""

from __future__ import annotations

import logging
import re
import time
import uuid

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError

from maxx import schema, storage
from maxx.config import settings

log = logging.getLogger(__name__)

# kind -> (who it is for, can the person turn its email off?)
KINDS: dict[str, tuple[str, bool]] = {
    # buyers
    "order.won": ("buyer", False),
    "order.address_reminder": ("buyer", False),
    "order.shipped": ("buyer", False),
    "order.out_for_delivery": ("buyer", True),
    "order.delivered": ("buyer", True),
    "order.refunded": ("buyer", False),
    "order.tracking_issue": ("buyer", False),
    "case.reply": ("buyer", False),
    "case.resolved": ("buyer", False),
    "bloc.released": ("buyer", True),
    # sellers
    "seller.status": ("seller", False),
    "seller.identity": ("seller", False),
    "seller.order_new": ("seller", False),
    "seller.order_ready": ("seller", False),
    "seller.ship_reminder": ("seller", False),
    "seller.order_cancelled": ("seller", False),
    "seller.case_opened": ("seller", False),
    "seller.case_reminder": ("seller", False),
    "seller.case_reply": ("seller", False),
    "seller.payout_sent": ("seller", True),
    "seller.payout_failed": ("seller", False),
    "seller.strike": ("seller", False),
    "seller.tracking_issue": ("seller", False),
    "seller.info_required": ("seller", False),
    "seller.bloc_result": ("seller", True),
    "seller.listing": ("seller", False),
}
OPTIONAL = sorted(kind for kind, (_, optional) in KINDS.items() if optional)
LINKS = ("/orders", "/sell", "/my-blocs", "/blocs/", "/account", "/notifications", "/receipts")
_URL = re.compile(r"(https?://|www\.)\S*|[\w.-]+\.(com|net|org|io|co|app|xyz|ru|cn)\b", re.I)


def _engine():
    return storage.get_store().engine


def safe_text(value: str, limit: int = 80) -> str:
    """A product title as it may appear in an email: no links, no control characters."""
    value = re.sub(r"[\x00-\x1f\x7f]", " ", value or "")
    value = _URL.sub("[link removed]", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:limit] + ("…" if len(value) > limit else "")


def notify(
    user_id: str | None,
    kind: str,
    title: str,
    body: str = "",
    link: str = "",
    dedupe_key: str | None = None,
) -> bool:
    """Record a notification for one person. Returns False if it was a duplicate or unknown.

    Never raises: telling someone about an event must not undo the event itself.
    """
    if not user_id or kind not in KINDS or user_id.startswith(("seed-", "demo-buyer-")):
        return False
    if link and not link.startswith(LINKS):
        link = ""
    stamp = int(time.time())
    email = "QUEUED" if _wants_email(user_id, kind) else "SKIPPED"
    try:
        with _engine().begin() as db:
            db.execute(
                schema.notifications.insert().values(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    kind=kind,
                    title=title[:160],
                    body=body[:600],
                    link=link[:300],
                    created_at=stamp,
                    read_at=None,
                    email_status=email,
                    email_attempts=0,
                    email_next_at=stamp,
                    email_error="",
                    dedupe_key=dedupe_key[:160] if dedupe_key else None,
                )
            )
        return True
    except IntegrityError:
        return False  # already sent for this dedupe key
    except Exception:  # noqa: BLE001
        log.exception("Could not record a %s notification", kind)
        return False


def _wants_email(user_id: str, kind: str) -> bool:
    if not KINDS[kind][1]:
        return True  # money, deadlines and account decisions always go by email too
    with _engine().connect() as db:
        value = db.execute(
            select(schema.notification_prefs.c.email).where(
                schema.notification_prefs.c.user_id == user_id,
                schema.notification_prefs.c.kind == kind,
            )
        ).scalar()
    return True if value is None else bool(value)


def preferences(user_id: str) -> dict[str, bool]:
    with _engine().connect() as db:
        rows = dict(
            db.execute(
                select(schema.notification_prefs.c.kind, schema.notification_prefs.c.email).where(
                    schema.notification_prefs.c.user_id == user_id
                )
            ).all()
        )
    return {kind: bool(rows.get(kind, True)) for kind in OPTIONAL}


def set_preferences(user_id: str, values: dict[str, bool]) -> dict[str, bool]:
    from sqlalchemy import delete

    stamp = int(time.time())
    with _engine().begin() as db:
        for kind, email in values.items():
            if kind not in OPTIONAL:
                continue
            db.execute(
                delete(schema.notification_prefs).where(
                    schema.notification_prefs.c.user_id == user_id,
                    schema.notification_prefs.c.kind == kind,
                )
            )
            db.execute(
                schema.notification_prefs.insert().values(
                    user_id=user_id, kind=kind, email=bool(email), updated_at=stamp
                )
            )
    return preferences(user_id)


def inbox(user_id: str, limit: int = 50, before: int | None = None) -> dict:
    n = schema.notifications.c
    query = select(schema.notifications).where(n.user_id == user_id)
    if before:
        query = query.where(n.created_at < before)
    with _engine().connect() as db:
        rows = [
            dict(r._mapping)
            for r in db.execute(query.order_by(n.created_at.desc(), n.id).limit(limit))
        ]
        unread = db.execute(
            select(func.count()).where(n.user_id == user_id, n.read_at.is_(None))
        ).scalar()
    return {
        "unread": int(unread or 0),
        "items": [
            {
                "id": r["id"],
                "kind": r["kind"],
                "title": r["title"],
                "body": r["body"],
                "link": r["link"],
                "created_at": r["created_at"],
                "read": r["read_at"] is not None,
            }
            for r in rows
        ],
    }


def unread_count(user_id: str) -> int:
    n = schema.notifications.c
    with _engine().connect() as db:
        return int(
            db.execute(
                select(func.count()).where(n.user_id == user_id, n.read_at.is_(None))
            ).scalar()
            or 0
        )


def mark_read(user_id: str, ids: list[str] | None) -> int:
    n = schema.notifications.c
    condition = (n.user_id == user_id) & n.read_at.is_(None)
    if ids is not None:
        condition = condition & n.id.in_(ids[:200])
    with _engine().begin() as db:
        return db.execute(
            update(schema.notifications).where(condition).values(read_at=int(time.time()))
        ).rowcount


def delete_for_user(user_id: str) -> None:
    from sqlalchemy import delete

    with _engine().begin() as db:
        db.execute(delete(schema.notifications).where(schema.notifications.c.user_id == user_id))
        db.execute(
            delete(schema.notification_prefs).where(schema.notification_prefs.c.user_id == user_id)
        )


# ---- the outbox --------------------------------------------------------------------------------


def _email_text(name: str, row: dict) -> str:
    base = settings.public_base_url.rstrip("/")
    link = f"\n\nOpen it on Maxx: {base}{row['link']}" if row["link"] else ""
    return (
        f"Hi {name},\n\n{row['title']}\n\n{row['body']}{link}\n\n"
        "You get this email because it is about your own order, payment or seller account. "
        f"Choose which optional updates you receive at {base}/notifications.\n"
        "Maxx never asks for your password or a sign-in code by email.\n"
    )


async def deliver_due(limit: int = 50) -> dict:
    """Email queued notifications. Safe to run from several workers and after a crash."""
    from maxx.auth import mail
    from maxx.auth import store as accounts

    n = schema.notifications.c
    now = int(time.time())
    done = {"sent": 0, "failed": 0, "retry": 0}
    with _engine().begin() as db:
        # A sender that crashed mid-send leaves SENDING rows; give them back after ten minutes.
        db.execute(
            update(schema.notifications)
            .where(n.email_status == "SENDING", n.email_next_at < now - 600)
            .values(email_status="QUEUED")
        )
        due = [
            dict(r._mapping)
            for r in db.execute(
                select(schema.notifications)
                .where(n.email_status == "QUEUED", n.email_next_at <= now)
                .order_by(n.email_next_at)
                .limit(limit)
            )
        ]
    for row in due:
        with _engine().begin() as db:
            claimed = db.execute(
                update(schema.notifications)
                .where(n.id == row["id"], n.email_status == "QUEUED")
                .values(email_status="SENDING", email_next_at=now)
            ).rowcount
        if not claimed:
            continue
        user = accounts.get_user(row["user_id"])
        if user is None:
            _finish(row["id"], "SKIPPED", row["email_attempts"], "no account")
            continue
        try:
            await mail.deliver(
                user.email, f"Maxx: {row['title']}"[:150], _email_text(user.display_name, row)
            )
        except mail.DeliveryError as exc:
            attempts = row["email_attempts"] + 1
            if attempts >= settings.email_max_attempts:
                _finish(row["id"], "FAILED", attempts, str(exc))
                done["failed"] += 1
            else:
                delay = min(6 * 3600, 30 * 2**attempts)
                _finish(row["id"], "QUEUED", attempts, str(exc), now + delay)
                done["retry"] += 1
            continue
        _finish(row["id"], "SENT", row["email_attempts"] + 1, "")
        done["sent"] += 1
    return done


def _finish(row_id: str, status: str, attempts: int, error: str, next_at: int = 0) -> None:
    with _engine().begin() as db:
        db.execute(
            update(schema.notifications)
            .where(schema.notifications.c.id == row_id)
            .values(
                email_status=status,
                email_attempts=attempts,
                email_error=error[:120],
                email_next_at=next_at,
            )
        )


def outbox_health() -> dict:
    n = schema.notifications.c
    with _engine().connect() as db:
        rows = dict(
            db.execute(
                select(n.email_status, func.count())
                .where(or_(n.email_status != "SENT", n.created_at > int(time.time()) - 86400))
                .group_by(n.email_status)
            ).all()
        )
    return {status.lower(): int(count) for status, count in rows.items()}
