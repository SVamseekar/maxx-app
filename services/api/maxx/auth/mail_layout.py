"""One layout for every Maxx email: a plain-text part and a matching HTML part.

The HTML follows what inboxes actually render: nested tables, inline styles, system fonts and no
images, scripts or web fonts. Every value that came from a person (names, notification text) is
escaped, and the only link in a message is the one Maxx built for it.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape

# The app's light theme (apps/web/app/design.css), so an email looks like the product it came from.
PAGE = "#f6f7f2"
PANEL = "#ffffff"
RAISED = "#e9ede5"
INK = "#202b24"
MUTED = "#536359"
SUBTLE = "#627368"
ACCENT = "#256c65"
ACCENT_INK = "#ffffff"
MINT = "#3f6a36"
LINE = "#dfe3dc"
FONT = (
    "Manrope, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
)
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace"


@dataclass(frozen=True)
class Email:
    """What one message says. Both parts are rendered from it, so they never disagree."""

    subject: str
    heading: str
    preheader: str
    greeting: str = ""
    lines: tuple[str, ...] = ()
    action: tuple[str, str] | None = None  # (button label, absolute URL)
    fallback: bool = False  # also print the action's URL: for one-time links a client might break
    code: str = ""
    facts: tuple[tuple[str, str], ...] = ()  # (label, value) rows, such as the browser of a sign-in
    note: str = ""  # what the link or code does, and when it expires
    secondary: tuple[str, str] | None = None  # a quieter second link under the note
    footer: str = "If you did not ask for this, ignore this email; nothing changes."
    footer_link: tuple[str, str] | None = None  # link text that ends the footer sentence


def text(message: Email) -> str:
    parts = [message.heading] + ([message.greeting] if message.greeting else [])
    parts += list(message.lines)
    if message.code:
        parts.append(f"Your confirmation code is {message.code}.")
    if message.facts:
        parts.append("\n".join(f"{label}: {value}" for label, value in message.facts))
    if message.action:
        parts.append(f"{message.action[0]}:\n{message.action[1]}")
    if message.note:
        parts.append(message.note)
    if message.secondary:
        parts.append(f"{message.secondary[0]}:\n{message.secondary[1]}")
    if (
        message.footer_link
    ):  # the footer reads on into its link: "... in your notification settings."
        parts.append(f"{message.footer} {message.footer_link[0]}: {message.footer_link[1]}")
    elif message.footer:
        parts.append(message.footer)
    return "\n\n".join(parts) + "\n"


def html(message: Email, base_url: str) -> str:
    body = []
    if message.greeting:
        body.append(_paragraph(message.greeting))
    body += [_paragraph(line) for line in message.lines]
    if message.code:
        body.append(_code(message.code))
    if message.facts:
        body.append(_facts(message.facts))
    if message.action:
        body.append(_button(*message.action))
    if message.note:
        body.append(_paragraph(message.note, size=13, color=MUTED, bottom=0))
    if message.secondary:
        body.append(_secondary(*message.secondary))
    if message.action and message.fallback:
        body.append(_fallback(message.action[1]))
    footer = escape(message.footer)
    if message.footer_link:
        label, url = message.footer_link
        footer += (
            f' <a href="{escape(url, quote=True)}" target="_blank" '
            f'style="color:{SUBTLE};text-decoration:underline;">{escape(label)}</a>.'
        )
    site = base_url.rstrip("/")
    host = site.split("://", 1)[-1]
    return _PAGE.format(
        subject=escape(message.subject),
        preheader=escape(message.preheader),
        heading=escape(message.heading),
        body="".join(body),
        footer=footer,
        site=escape(site, quote=True),
        host=escape(host),
        font=FONT,
        page=PAGE,
        panel=PANEL,
        ink=INK,
        subtle=SUBTLE,
        mint=MINT,
        line=LINE,
    )


def _paragraph(value: str, size: int = 15, color: str = INK, bottom: int = 16) -> str:
    return (
        f'<p style="margin:0 0 {bottom}px;font-family:{FONT};font-size:{size}px;line-height:1.6;'
        f'color:{color};">{escape(value)}</p>'
    )


def _button(label: str, url: str) -> str:
    # A padded link inside a coloured cell: the whole button is clickable in every client.
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
        'style="margin:8px 0 24px;"><tr>'
        f'<td bgcolor="{ACCENT}" style="border-radius:10px;background:{ACCENT};">'
        f'<a href="{escape(url, quote=True)}" target="_blank" style="display:inline-block;'
        f"padding:13px 24px;font-family:{FONT};font-size:15px;font-weight:600;line-height:1.2;"
        f'color:{ACCENT_INK};text-decoration:none;border-radius:10px;">{escape(label)}</a>'
        "</td></tr></table>"
    )


def _code(code: str) -> str:
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        'style="margin:8px 0 24px;"><tr>'
        f'<td align="center" bgcolor="{RAISED}" style="background:{RAISED};border-radius:10px;'
        f"padding:22px 16px;font-family:{MONO};font-size:30px;font-weight:600;"
        f'letter-spacing:8px;color:{INK};">{escape(code)}</td></tr></table>'
    )


def _facts(rows: tuple[tuple[str, str], ...]) -> str:
    cells = "".join(
        f'<tr><td style="padding:6px 16px 6px 0;font-family:{FONT};font-size:13px;color:{MUTED};'
        f'vertical-align:top;white-space:nowrap;">{escape(label)}</td>'
        f'<td style="padding:6px 0;font-family:{FONT};font-size:13px;color:{INK};'
        f'word-break:break-word;">{escape(value)}</td></tr>'
        for label, value in rows
    )
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="margin:0 0 20px;border-top:1px solid {LINE};border-bottom:1px solid {LINE};">'
        f"{cells}</table>"
    )


def _secondary(label: str, url: str) -> str:
    return (
        f'<p style="margin:12px 0 0;font-family:{FONT};font-size:13px;line-height:1.6;">'
        f'<a href="{escape(url, quote=True)}" target="_blank" style="color:{ACCENT};'
        f'text-decoration:underline;">{escape(label)}</a></p>'
    )


def _fallback(url: str) -> str:
    safe = escape(url, quote=True)
    return (
        f'<p style="margin:20px 0 0;padding-top:20px;border-top:1px solid {LINE};'
        f'font-family:{FONT};font-size:12px;line-height:1.6;color:{SUBTLE};">'
        "If the button does not work, paste this link into your browser:<br>"
        f'<a href="{safe}" target="_blank" style="color:{ACCENT};word-break:break-all;">'
        f"{escape(url)}</a></p>"
    )


_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="x-apple-disable-message-reformatting">
<meta name="color-scheme" content="light">
<meta name="supported-color-schemes" content="light">
<title>{subject}</title>
</head>
<body style="margin:0;padding:0;background:{page};-webkit-text-size-adjust:100%;">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;">{preheader}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="{page}" style="background:{page};">
<tr><td align="center" style="padding:40px 16px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:560px;">
<tr><td style="padding:0 4px 20px;font-family:{font};font-size:26px;font-weight:800;letter-spacing:-1.5px;line-height:1;color:{ink};">maxx<span style="display:inline-block;width:6px;height:6px;margin-left:2px;border-radius:3px;background:{mint};"></span></td></tr>
<tr><td bgcolor="{panel}" style="background:{panel};border:1px solid {line};border-radius:12px;padding:36px 32px 32px;">
<h1 style="margin:0 0 20px;font-family:{font};font-size:22px;font-weight:700;line-height:1.3;letter-spacing:-0.4px;color:{ink};">{heading}</h1>
{body}
</td></tr>
<tr><td style="padding:20px 4px 0;font-family:{font};font-size:12px;line-height:1.6;color:{subtle};">
{footer}<br>
Maxx &middot; <a href="{site}" target="_blank" style="color:{subtle};text-decoration:underline;">{host}</a>
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>
"""  # noqa: E501
