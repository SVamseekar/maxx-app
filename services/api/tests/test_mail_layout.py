"""Email layout: both parts say the same thing, people's text is escaped, inboxes get both parts."""

import asyncio

import pytest

from maxx.auth import mail, mail_layout
from maxx.auth.mail_layout import Email
from maxx.config import settings

pytestmark = pytest.mark.unit

SIGN_IN = Email(
    subject="Your Maxx sign-in link",
    heading="Sign in to Maxx",
    preheader="Works once.",
    greeting="Hi Mo,",
    lines=("Use this link to sign in.",),
    action=("Sign in", "https://maxx.example/signin-link?token=abc"),
    fallback=True,
    note="This link works once and expires in 15 minutes.",
)


def test_the_text_part_carries_everything_the_html_part_says():
    text = mail_layout.text(SIGN_IN)
    page = mail_layout.html(SIGN_IN, "https://maxx.example")
    for part in ("Sign in to Maxx", "Hi Mo,", "Use this link to sign in.", "expires in 15 minutes"):
        assert part in text and part in page
    assert "Sign in:\nhttps://maxx.example/signin-link?token=abc" in text
    assert page.count('href="https://maxx.example/signin-link?token=abc"') == 2  # button + fallback


def test_names_and_notification_text_cannot_inject_markup():
    hostile = Email(
        subject="x",
        heading="<b>Lamp</b>",
        preheader="x",
        greeting='Hi <img src=x onerror="alert(1)">,',
        facts=(("Browser", "<script>alert(1)</script>"),),
    )
    page = mail_layout.html(hostile, "https://maxx.example")
    assert "<img" not in page and "<script" not in page and "<b>Lamp" not in page
    assert "&lt;img src=x" in page


def test_a_link_cannot_break_out_of_its_attribute():
    message = Email(subject="x", heading="x", preheader="x", action=("Go", 'https://a.example/"x'))
    assert 'href="https://a.example/&quot;x"' in mail_layout.html(message, "https://maxx.example")


def test_the_code_email_shows_the_code_in_both_parts():
    message = Email(subject="x", heading="Your confirmation code", preheader="x", code="123456")
    assert "Your confirmation code is 123456." in mail_layout.text(message)
    assert ">123456</td>" in mail_layout.html(message, "https://maxx.example")


def test_messages_go_out_as_text_with_an_html_alternative(monkeypatch):
    monkeypatch.setattr(settings, "email_from", "Maxx <no-reply@maxx.example>")
    message = mail.compose("me@example.com", "Hi", "plain", "<p>rich</p>")
    assert message.get_content_type() == "multipart/alternative"
    assert [part.get_content_type() for part in message.iter_parts()] == [
        "text/plain",
        "text/html",
    ]
    assert message["Message-ID"].endswith("@maxx.example>") and message["Date"]
    assert mail.compose("me@example.com", "Hi", "plain").get_content_type() == "text/plain"


def test_every_sign_in_email_is_sent_with_both_parts():
    mail.outbox.clear()
    asyncio.run(mail.send_signin_link("judge@judges.maxx.invalid", "Mo", "tok"))
    sent = mail.outbox[-1]
    assert "/signin-link?token=tok" in sent["text"] and "/signin-link?token=tok" in sent["html"]
    assert sent["html"].startswith("<!DOCTYPE html>")


def test_links_without_a_token_get_no_paste_this_link_block():
    message = Email(subject="x", heading="x", preheader="x", action=("Open", "https://a.example/o"))
    assert "paste this link" not in mail_layout.html(message, "https://maxx.example")


def test_the_footer_link_reads_as_part_of_its_sentence():
    message = Email(
        subject="x",
        heading="x",
        preheader="x",
        footer="Choose updates in your",
        footer_link=("notification settings", "https://a.example/n"),
    )
    assert "Choose updates in your notification settings: https://a.example/n" in mail_layout.text(
        message
    )
    assert "notification settings</a>." in mail_layout.html(message, "https://maxx.example")


@pytest.mark.parametrize(
    ("agent", "name"),
    [
        (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
            "(KHTML, like Gecko) Version/18.0 Safari/605.1.15",
            "Safari on macOS",
        ),
        (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/130.0 Safari/537.36 Edg/130.0",
            "Edge on Windows",
        ),
        ("Mozilla/5.0 (Linux; Android 14) Chrome/130.0 Mobile Safari/537.36", "Chrome on Android"),
        ("curl/8.0", "Unknown device"),
    ],
)
def test_security_alerts_name_the_device_in_words(agent, name):
    from maxx.auth.events import describe_agent

    assert describe_agent(agent) == name
