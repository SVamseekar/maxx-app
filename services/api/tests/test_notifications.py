"""Notifications: the inbox, the email outbox, preferences and what may appear in an email."""

import asyncio

from fastapi.testclient import TestClient

from maxx.auth import mail
from maxx.config import settings
from maxx.main import app
from maxx.notify import service as notify
from tests.conftest import sign_up


def test_a_notification_lands_in_the_inbox_once_and_only_for_its_owner():
    with TestClient(app) as me, TestClient(app) as other:
        user = sign_up(me, "me@example.com")
        sign_up(other, "other@example.com")
        assert notify.notify(
            user["id"], "order.shipped", "Your parcel shipped", "", "/orders", "k1"
        )
        assert not notify.notify(user["id"], "order.shipped", "Again", "", "/orders", "k1")
        assert not notify.notify(user["id"], "no.such.kind", "x")
        assert not notify.notify("seed-123", "order.shipped", "x")  # simulated buyers get nothing
        mine = me.get("/notifications").json()
        assert mine["unread"] == 1 and mine["items"][0]["title"] == "Your parcel shipped"
        assert other.get("/notifications").json() == {"unread": 0, "items": []}
        item = mine["items"][0]["id"]
        assert other.post("/notifications/read", json={"ids": [item]}).json()["marked"] == 0
        assert me.post("/notifications/read", json={"ids": [item]}).json()["marked"] == 1
        assert me.get("/notifications/unread").json()["unread"] == 0


def test_links_must_point_inside_the_site():
    with TestClient(app) as me:
        user = sign_up(me, "me@example.com")
        notify.notify(user["id"], "order.shipped", "x", "", "https://evil.example/login")
        assert me.get("/notifications").json()["items"][0]["link"] == ""


def test_emails_are_sent_from_the_outbox_and_retried_after_a_failure(monkeypatch):
    with TestClient(app) as me:
        user = sign_up(me, "me@example.com", "Mo")
    notify.notify(user["id"], "order.refunded", "Refunded: $10 for Lamp", "Body.", "/orders")
    calls = {"n": 0}
    real = mail.deliver

    async def flaky(to, subject, text):
        calls["n"] += 1
        if calls["n"] == 1:
            raise mail.DeliveryError("SMTPServerDisconnected")
        await real(to, subject, text)

    monkeypatch.setattr(mail, "deliver", flaky)
    assert asyncio.run(notify.deliver_due())["retry"] == 1
    assert asyncio.run(notify.deliver_due())["sent"] == 0  # waits out the back-off
    from sqlalchemy import update

    from maxx import schema, storage

    with storage.get_store().engine.begin() as db:
        db.execute(update(schema.notifications).values(email_next_at=0))
    assert asyncio.run(notify.deliver_due())["sent"] == 1
    sent = [m for m in mail.outbox if m["subject"] == "Maxx: Refunded: $10 for Lamp"]
    assert (
        sent and "/orders" in sent[0]["text"] and "never asks for your password" in sent[0]["text"]
    )
    assert asyncio.run(notify.deliver_due())["sent"] == 0  # never twice


def test_an_email_that_keeps_failing_stops_after_the_limit(monkeypatch):
    monkeypatch.setattr(settings, "email_max_attempts", 2)
    with TestClient(app) as me:
        user = sign_up(me, "me@example.com")
    notify.notify(user["id"], "order.refunded", "Refunded")

    async def broken(to, subject, text):
        raise mail.DeliveryError("refused")

    monkeypatch.setattr(mail, "deliver", broken)
    from sqlalchemy import update

    from maxx import schema, storage

    results = []
    for _ in range(3):
        results.append(asyncio.run(notify.deliver_due()))
        with storage.get_store().engine.begin() as db:
            db.execute(update(schema.notifications).values(email_next_at=0))
    assert (
        results[0]["retry"] == 1
        and results[1]["failed"] == 1
        and results[2]
        == {
            "sent": 0,
            "failed": 0,
            "retry": 0,
        }
    )
    assert notify.outbox_health().get("failed") == 1


def test_only_optional_updates_can_be_switched_off():
    with TestClient(app) as me:
        user = sign_up(me, "me@example.com")
        prefs = me.get("/notifications/preferences").json()
        assert "order.delivered" in prefs["email"] and "order.refunded" in prefs["always"]
        saved = me.post(
            "/notifications/preferences",
            json={"email": {"order.delivered": False, "order.refunded": False}},
        ).json()
        assert saved["email"]["order.delivered"] is False
        assert "order.refunded" not in saved["email"]  # money updates cannot be turned off
    notify.notify(user["id"], "order.delivered", "Delivered")
    notify.notify(user["id"], "order.refunded", "Refunded")
    from sqlalchemy import select

    from maxx import schema, storage

    with storage.get_store().engine.connect() as db:
        rows = dict(
            db.execute(
                select(schema.notifications.c.kind, schema.notifications.c.email_status)
            ).all()
        )
    assert rows == {"order.delivered": "SKIPPED", "order.refunded": "QUEUED"}


def test_text_from_other_people_never_carries_a_link_into_an_email():
    assert notify.safe_text("Lamp https://evil.example/x now") == "Lamp [link removed] now"
    assert "evil" not in notify.safe_text("Visit www.evil.com today")
    assert notify.safe_text("Paypal-login.com deal") == "[link removed] deal"
    assert notify.safe_text("a\x00b\nc") == "a b c"
    assert len(notify.safe_text("x" * 500)) <= 81


def test_closing_an_account_deletes_its_notifications(monkeypatch):
    with TestClient(app) as me:
        user = sign_up(me, "me@example.com")
        notify.notify(user["id"], "order.shipped", "Shipped")
        assert me.post("/auth/me/delete", json={"confirm": "delete my account"}).status_code == 204
    assert notify.inbox(user["id"])["items"] == []
