"""Append-only audit trail for money and trust decisions, plus the payments emergency brake."""

from __future__ import annotations

import logging
import time

from sqlalchemy import select

from maxx import schema, storage
from maxx.config import settings

log = logging.getLogger("maxx.audit")


def record(actor: str, action: str, subject: str = "", detail: str = "") -> None:
    """Never raises: an audit failure must not undo a payment that already happened."""
    try:
        with storage.get_store().engine.begin() as db:
            db.execute(
                schema.audit_log.insert().values(
                    at=int(time.time()),
                    actor=actor[:40],
                    action=action[:40],
                    subject=subject[:80],
                    detail=detail[:300],
                )
            )
    except Exception:  # noqa: BLE001
        log.exception("Could not write audit entry %s", action)
    log.info("audit actor=%s action=%s subject=%s", actor, action, subject)


def recent(limit: int = 100, action_prefix: str = "") -> list[dict]:
    query = select(schema.audit_log).order_by(schema.audit_log.c.id.desc()).limit(limit)
    if action_prefix:
        query = query.where(schema.audit_log.c.action.like(action_prefix + "%"))
    with storage.get_store().engine.connect() as db:
        return [dict(r._mapping) for r in db.execute(query)]


def flag(key: str) -> str | None:
    with storage.get_store().engine.connect() as db:
        return db.execute(
            select(schema.system_flags.c.value).where(schema.system_flags.c.key == key)
        ).scalar()


def set_flag(key: str, value: str) -> None:
    from sqlalchemy import delete

    with storage.get_store().engine.begin() as db:
        db.execute(delete(schema.system_flags).where(schema.system_flags.c.key == key))
        db.execute(
            schema.system_flags.insert().values(key=key, value=value, updated_at=int(time.time()))
        )


def payments_frozen() -> bool:
    """True when new money movement is paused, by configuration or by an administrator."""
    return settings.payments_frozen or flag("payments_frozen") == "1"
