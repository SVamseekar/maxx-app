"""Account persistence. Uses the application engine; every write is one short transaction."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from sqlalchemy import and_, delete, select, update
from sqlalchemy.exc import IntegrityError

from maxx import schema, storage
from maxx.auth.security import digest, new_token


class EmailTaken(Exception):
    pass


@dataclass(frozen=True)
class User:
    id: str
    email: str
    email_verified: bool
    has_password: bool
    display_name: str
    avatar_url: str | None
    created_at: int
    totp_enabled: bool = False


@dataclass(frozen=True)
class SessionRow:
    """The signed-in browser's session: how it signed in and when it last proved who it is."""

    key: str
    created_at: int
    recent_auth_at: int
    auth_method: str


@dataclass(frozen=True)
class SessionInfo:
    public_id: str
    created_at: int
    last_seen_at: int
    expires_at: int
    user_agent: str


def _user(row) -> User:
    return User(
        id=row.id,
        email=row.email,
        email_verified=bool(row.email_verified),
        has_password=bool(row.password_hash),
        display_name=row.display_name,
        avatar_url=row.avatar_url,
        created_at=row.created_at,
        totp_enabled=bool(row.totp_enabled),
    )


def engine():
    return storage.get_store().engine


def now() -> int:
    return int(time.time())


# --- users ---


def create_user(
    email: str,
    display_name: str,
    password_hash: str | None = None,
    email_verified: bool = False,
    avatar_url: str | None = None,
) -> User:
    user_id, stamp = str(uuid.uuid4()), now()
    try:
        with engine().begin() as db:
            db.execute(
                schema.users.insert().values(
                    id=user_id,
                    email=email,
                    email_verified=email_verified,
                    password_hash=password_hash,
                    display_name=display_name,
                    avatar_url=avatar_url,
                    created_at=stamp,
                    updated_at=stamp,
                )
            )
    except IntegrityError as exc:
        raise EmailTaken(email) from exc
    return get_user(user_id)  # type: ignore[return-value]


def get_user(user_id: str) -> User | None:
    with engine().connect() as db:
        row = db.execute(select(schema.users).where(schema.users.c.id == user_id)).first()
    return _user(row) if row else None


def get_user_by_email(email: str) -> User | None:
    with engine().connect() as db:
        row = db.execute(select(schema.users).where(schema.users.c.email == email)).first()
    return _user(row) if row else None


def password_hash_for(user_id: str) -> str | None:
    with engine().connect() as db:
        return db.execute(
            select(schema.users.c.password_hash).where(schema.users.c.id == user_id)
        ).scalar()


def password_hash_by_email(email: str) -> tuple[str, str | None] | None:
    with engine().connect() as db:
        row = db.execute(
            select(schema.users.c.id, schema.users.c.password_hash).where(
                schema.users.c.email == email
            )
        ).first()
    return (row.id, row.password_hash) if row else None


def update_user(user_id: str, **fields) -> None:
    allowed = {"display_name", "password_hash", "email_verified", "avatar_url", "last_login_at"}
    values = {k: v for k, v in fields.items() if k in allowed}
    with engine().begin() as db:
        db.execute(
            update(schema.users)
            .where(schema.users.c.id == user_id)
            .values(updated_at=now(), **values)
        )


def delete_user(user_id: str) -> None:
    with engine().begin() as db:
        for table in (
            schema.sessions,
            schema.auth_tokens,
            schema.identities,
            schema.recovery_codes,
            schema.passkeys,
            schema.trusted_devices,
            schema.security_events,
            schema.webauthn_challenges,
        ):
            db.execute(delete(table).where(table.c.user_id == user_id))
        db.execute(delete(schema.oauth_states).where(schema.oauth_states.c.link_user_id == user_id))
        db.execute(delete(schema.users).where(schema.users.c.id == user_id))


# --- linked identities ---


def identity_owner(provider: str, subject: str) -> str | None:
    with engine().connect() as db:
        return db.execute(
            select(schema.identities.c.user_id).where(
                and_(
                    schema.identities.c.provider == provider, schema.identities.c.subject == subject
                )
            )
        ).scalar()


def link_identity(provider: str, subject: str, user_id: str, email: str | None) -> None:
    try:
        with engine().begin() as db:
            db.execute(
                schema.identities.insert().values(
                    provider=provider,
                    subject=subject,
                    user_id=user_id,
                    email=email,
                    created_at=now(),
                )
            )
    except IntegrityError as exc:
        raise EmailTaken(provider) from exc


def list_identities(user_id: str) -> list[str]:
    with engine().connect() as db:
        rows = db.execute(
            select(schema.identities.c.provider)
            .where(schema.identities.c.user_id == user_id)
            .order_by(schema.identities.c.provider)
        )
        return [r[0] for r in rows]


def unlink_identity(user_id: str, provider: str) -> bool:
    with engine().begin() as db:
        result = db.execute(
            delete(schema.identities).where(
                and_(
                    schema.identities.c.user_id == user_id, schema.identities.c.provider == provider
                )
            )
        )
    return result.rowcount > 0


# --- sessions ---


def purge_stale(db, stamp: int) -> None:
    """Opportunistic housekeeping keeps tables small without a scheduler."""
    db.execute(delete(schema.sessions).where(schema.sessions.c.expires_at < stamp))
    db.execute(delete(schema.oauth_states).where(schema.oauth_states.c.expires_at < stamp))
    db.execute(delete(schema.auth_tokens).where(schema.auth_tokens.c.expires_at < stamp - 86400))
    db.execute(
        delete(schema.webauthn_challenges).where(schema.webauthn_challenges.c.expires_at < stamp)
    )
    db.execute(delete(schema.trusted_devices).where(schema.trusted_devices.c.expires_at < stamp))
    db.execute(
        delete(schema.security_events).where(
            schema.security_events.c.created_at < stamp - 400 * 86400
        )
    )
    # Sign-ups that never confirmed their email within a week leave nothing behind.
    stale = select(schema.users.c.id).where(
        schema.users.c.email_verified.is_(False),
        schema.users.c.password_hash.is_(None),
        schema.users.c.created_at < stamp - 7 * 86400,
    )
    ids = [r[0] for r in db.execute(stale)]
    for user_id in ids:
        for table in (schema.auth_tokens, schema.identities, schema.sessions):
            db.execute(delete(table).where(table.c.user_id == user_id))
        db.execute(delete(schema.users).where(schema.users.c.id == user_id))


def create_session(user_id: str, user_agent: str, days: int, method: str = "") -> str:
    """A new sign-in. Its lifetime is absolute; only inactivity can end it sooner."""
    token, stamp = new_token(), now()
    with engine().begin() as db:
        db.execute(
            schema.sessions.insert().values(
                id=digest(token),
                user_id=user_id,
                created_at=stamp,
                last_seen_at=stamp,
                expires_at=stamp + days * 86400,
                user_agent=user_agent[:200],
                recent_auth_at=stamp,
                auth_method=method[:30],
            )
        )
        purge_stale(db, stamp)
    return token


def session_user(token: str, idle_days: int) -> tuple[User, SessionRow] | None:
    """Resolve a session cookie. Expired, or idle for too long, means signed out."""
    key, stamp = digest(token), now()
    with engine().begin() as db:
        row = db.execute(
            select(schema.sessions).where(
                schema.sessions.c.id == key, schema.sessions.c.expires_at > stamp
            )
        ).first()
        if row is None:
            return None
        if stamp - row.last_seen_at > idle_days * 86400:
            db.execute(delete(schema.sessions).where(schema.sessions.c.id == key))
            return None
        if stamp - row.last_seen_at > 600:  # bound the write rate of busy sessions
            db.execute(
                update(schema.sessions)
                .where(schema.sessions.c.id == key)
                .values(last_seen_at=stamp)
            )
        user = db.execute(select(schema.users).where(schema.users.c.id == row.user_id)).first()
    if user is None:
        return None
    return _user(user), SessionRow(key, row.created_at, row.recent_auth_at, row.auth_method)


def touch_recent_auth(token: str) -> None:
    """The person just proved who they are again; sensitive actions are allowed for a while."""
    with engine().begin() as db:
        db.execute(
            update(schema.sessions)
            .where(schema.sessions.c.id == digest(token))
            .values(recent_auth_at=now())
        )


def rotate_session(old_token: str, user_agent: str, days: int, method: str) -> str:
    """Swap the session id (after a privilege change) so any copy of the old one stops working."""
    new = create_session(_owner_of(old_token), user_agent, days, method)
    delete_session(old_token)
    return new


def _owner_of(token: str) -> str:
    with engine().connect() as db:
        return db.execute(
            select(schema.sessions.c.user_id).where(schema.sessions.c.id == digest(token))
        ).scalar_one()


def list_sessions(user_id: str) -> list[SessionInfo]:
    with engine().connect() as db:
        rows = db.execute(
            select(schema.sessions)
            .where(schema.sessions.c.user_id == user_id, schema.sessions.c.expires_at > now())
            .order_by(schema.sessions.c.last_seen_at.desc())
        )
        return [
            SessionInfo(r.id[:16], r.created_at, r.last_seen_at, r.expires_at, r.user_agent)
            for r in rows
        ]


def current_public_id(token: str) -> str:
    return digest(token)[:16]


def revoke_session(user_id: str, public_id: str) -> bool:
    with engine().begin() as db:
        result = db.execute(
            delete(schema.sessions).where(
                schema.sessions.c.user_id == user_id, schema.sessions.c.id.like(public_id + "%")
            )
        )
    return result.rowcount > 0


def delete_session(token: str) -> None:
    with engine().begin() as db:
        db.execute(delete(schema.sessions).where(schema.sessions.c.id == digest(token)))


def revoke_other_sessions(user_id: str, keep_token: str | None) -> int:
    condition = schema.sessions.c.user_id == user_id
    if keep_token:
        condition = and_(condition, schema.sessions.c.id != digest(keep_token))
    with engine().begin() as db:
        return db.execute(delete(schema.sessions).where(condition)).rowcount


# --- one-time tokens ---


def issue_token(user_id: str, purpose: str, email: str, ttl_seconds: int) -> str:
    token, stamp = new_token(), now()
    with engine().begin() as db:
        # A new request supersedes earlier unused links for the same purpose.
        db.execute(
            delete(schema.auth_tokens).where(
                schema.auth_tokens.c.user_id == user_id, schema.auth_tokens.c.purpose == purpose
            )
        )
        db.execute(
            schema.auth_tokens.insert().values(
                id=digest(token),
                user_id=user_id,
                purpose=purpose,
                email=email,
                created_at=stamp,
                expires_at=stamp + ttl_seconds,
            )
        )
    return token


def issue_custom_token(user_id: str, purpose: str, email: str, raw: str, ttl_seconds: int) -> None:
    """Like issue_token, but the secret is chosen by the caller (short email codes)."""
    stamp = now()
    with engine().begin() as db:
        db.execute(
            delete(schema.auth_tokens).where(
                schema.auth_tokens.c.user_id == user_id, schema.auth_tokens.c.purpose == purpose
            )
        )
        db.execute(
            schema.auth_tokens.insert().values(
                id=digest(raw),
                user_id=user_id,
                purpose=purpose,
                email=email,
                created_at=stamp,
                expires_at=stamp + ttl_seconds,
            )
        )


def peek_token(token: str, purpose: str) -> tuple[str, str] | None:
    """Check a token without using it, so a rejected form submission does not burn the link."""
    with engine().connect() as db:
        row = db.execute(
            select(schema.auth_tokens).where(
                schema.auth_tokens.c.id == digest(token),
                schema.auth_tokens.c.purpose == purpose,
                schema.auth_tokens.c.used_at.is_(None),
                schema.auth_tokens.c.expires_at > now(),
            )
        ).first()
    return (row.user_id, row.email) if row else None


def consume_token(token: str, purpose: str) -> tuple[str, str] | None:
    """Atomically mark a token used. Returns (user_id, email) once, then None."""
    key, stamp = digest(token), now()
    with engine().begin() as db:
        row = db.execute(
            select(schema.auth_tokens).where(
                schema.auth_tokens.c.id == key,
                schema.auth_tokens.c.purpose == purpose,
                schema.auth_tokens.c.used_at.is_(None),
                schema.auth_tokens.c.expires_at > stamp,
            )
        ).first()
        if row is None:
            return None
        claimed = db.execute(
            update(schema.auth_tokens)
            .where(schema.auth_tokens.c.id == key, schema.auth_tokens.c.used_at.is_(None))
            .values(used_at=stamp)
        )
        if claimed.rowcount != 1:
            return None
    return row.user_id, row.email


# --- OAuth state ---


def put_oauth_state(
    state: str,
    provider: str,
    verifier: str,
    next_path: str,
    link_user_id: str | None,
    nonce: str | None = None,
) -> None:
    with engine().begin() as db:
        db.execute(
            schema.oauth_states.insert().values(
                state=state,
                provider=provider,
                verifier=verifier,
                next_path=next_path,
                link_user_id=link_user_id,
                nonce=nonce,
                expires_at=now() + 600,
            )
        )


def pop_oauth_state(state: str, provider: str):
    with engine().begin() as db:
        row = db.execute(
            select(schema.oauth_states).where(schema.oauth_states.c.state == state)
        ).first()
        if row is None:
            return None
        db.execute(delete(schema.oauth_states).where(schema.oauth_states.c.state == state))
    if row.provider != provider or row.expires_at < now():
        return None
    return row


# --- two-step verification (TOTP) and recovery codes ---


def set_totp_pending(user_id: str, encrypted_seed: str) -> None:
    with engine().begin() as db:
        db.execute(
            update(schema.users)
            .where(schema.users.c.id == user_id)
            .values(totp_pending_enc=encrypted_seed, updated_at=now())
        )


def totp_material(user_id: str) -> tuple[str | None, str | None, bool]:
    """(active seed, pending seed, enabled) as stored, still encrypted."""
    with engine().connect() as db:
        row = db.execute(
            select(
                schema.users.c.totp_secret_enc,
                schema.users.c.totp_pending_enc,
                schema.users.c.totp_enabled,
            ).where(schema.users.c.id == user_id)
        ).first()
    return (row[0], row[1], bool(row[2])) if row else (None, None, False)


def enable_totp(user_id: str, step: int) -> bool:
    """Promote the pending seed to active, recording the step that proved it. Atomic."""
    with engine().begin() as db:
        result = db.execute(
            update(schema.users)
            .where(schema.users.c.id == user_id, schema.users.c.totp_pending_enc.is_not(None))
            .values(
                totp_secret_enc=schema.users.c.totp_pending_enc,
                totp_pending_enc=None,
                totp_enabled=True,
                totp_last_step=step,
                updated_at=now(),
            )
        )
    return result.rowcount == 1


def claim_totp_step(user_id: str, step: int) -> bool:
    """Accept a code only if its time step is newer than any already used (replay defence)."""
    with engine().begin() as db:
        result = db.execute(
            update(schema.users)
            .where(
                schema.users.c.id == user_id,
                schema.users.c.totp_enabled.is_(True),
                (schema.users.c.totp_last_step.is_(None)) | (schema.users.c.totp_last_step < step),
            )
            .values(totp_last_step=step)
        )
    return result.rowcount == 1


def disable_totp(user_id: str) -> None:
    with engine().begin() as db:
        db.execute(
            update(schema.users)
            .where(schema.users.c.id == user_id)
            .values(
                totp_secret_enc=None,
                totp_pending_enc=None,
                totp_enabled=False,
                totp_last_step=None,
                updated_at=now(),
            )
        )
        db.execute(delete(schema.recovery_codes).where(schema.recovery_codes.c.user_id == user_id))
        db.execute(
            delete(schema.trusted_devices).where(schema.trusted_devices.c.user_id == user_id)
        )


def replace_recovery_codes(user_id: str, hashes: list[str]) -> None:
    with engine().begin() as db:
        db.execute(delete(schema.recovery_codes).where(schema.recovery_codes.c.user_id == user_id))
        db.execute(
            schema.recovery_codes.insert(),
            [{"user_id": user_id, "code_hash": h, "used_at": None} for h in hashes],
        )


def use_recovery_code(user_id: str, code_hash: str) -> bool:
    with engine().begin() as db:
        result = db.execute(
            update(schema.recovery_codes)
            .where(
                schema.recovery_codes.c.user_id == user_id,
                schema.recovery_codes.c.code_hash == code_hash,
                schema.recovery_codes.c.used_at.is_(None),
            )
            .values(used_at=now())
        )
    return result.rowcount == 1


def recovery_codes_left(user_id: str) -> int:
    with engine().connect() as db:
        rows = db.execute(
            select(schema.recovery_codes.c.code_hash).where(
                schema.recovery_codes.c.user_id == user_id,
                schema.recovery_codes.c.used_at.is_(None),
            )
        )
        return len(list(rows))


# --- trusted devices ("remember this browser") ---


def add_trusted_device(user_id: str, user_agent: str, days: int) -> str:
    token, stamp = new_token(), now()
    with engine().begin() as db:
        db.execute(
            schema.trusted_devices.insert().values(
                id=digest(token),
                user_id=user_id,
                user_agent=user_agent[:200],
                created_at=stamp,
                last_used_at=stamp,
                expires_at=stamp + days * 86400,
            )
        )
    return token


def trusted_device_ok(token: str, user_id: str) -> bool:
    key, stamp = digest(token), now()
    with engine().begin() as db:
        row = db.execute(
            select(schema.trusted_devices.c.user_id).where(
                schema.trusted_devices.c.id == key, schema.trusted_devices.c.expires_at > stamp
            )
        ).first()
        if row is None or row[0] != user_id:
            return False
        db.execute(
            update(schema.trusted_devices)
            .where(schema.trusted_devices.c.id == key)
            .values(last_used_at=stamp)
        )
    return True


def revoke_trusted_devices(user_id: str) -> int:
    with engine().begin() as db:
        return db.execute(
            delete(schema.trusted_devices).where(schema.trusted_devices.c.user_id == user_id)
        ).rowcount


def count_trusted_devices(user_id: str) -> int:
    with engine().connect() as db:
        rows = db.execute(
            select(schema.trusted_devices.c.id).where(
                schema.trusted_devices.c.user_id == user_id,
                schema.trusted_devices.c.expires_at > now(),
            )
        )
        return len(list(rows))


# --- passkeys (WebAuthn) ---


@dataclass(frozen=True)
class Passkey:
    id: str
    user_id: str
    public_key: str
    sign_count: int
    name: str
    transports: str
    backup_eligible: bool
    backup_state: bool
    created_at: int
    last_used_at: int | None


def _passkey(row) -> Passkey:
    return Passkey(
        row.id, row.user_id, row.public_key, row.sign_count, row.name, row.transports,
        bool(row.backup_eligible), bool(row.backup_state), row.created_at, row.last_used_at,
    )  # fmt: skip


def add_passkey(
    credential_id: str,
    user_id: str,
    public_key: str,
    sign_count: int,
    name: str,
    transports: str,
    aaguid: str,
    backup_eligible: bool,
    backup_state: bool,
) -> None:
    try:
        with engine().begin() as db:
            db.execute(
                schema.passkeys.insert().values(
                    id=credential_id,
                    user_id=user_id,
                    public_key=public_key,
                    sign_count=sign_count,
                    name=name[:80],
                    transports=transports[:120],
                    aaguid=aaguid[:40],
                    backup_eligible=backup_eligible,
                    backup_state=backup_state,
                    created_at=now(),
                )
            )
    except IntegrityError as exc:
        raise EmailTaken(credential_id) from exc


def get_passkey(credential_id: str) -> Passkey | None:
    with engine().connect() as db:
        row = db.execute(
            select(schema.passkeys).where(schema.passkeys.c.id == credential_id)
        ).first()
    return _passkey(row) if row else None


def list_passkeys(user_id: str) -> list[Passkey]:
    with engine().connect() as db:
        rows = db.execute(
            select(schema.passkeys)
            .where(schema.passkeys.c.user_id == user_id)
            .order_by(schema.passkeys.c.created_at)
        )
        return [_passkey(r) for r in rows]


def passkey_used(credential_id: str, sign_count: int, backup_state: bool) -> None:
    with engine().begin() as db:
        db.execute(
            update(schema.passkeys)
            .where(schema.passkeys.c.id == credential_id)
            .values(sign_count=sign_count, backup_state=backup_state, last_used_at=now())
        )


def rename_passkey(user_id: str, credential_id: str, name: str) -> bool:
    with engine().begin() as db:
        result = db.execute(
            update(schema.passkeys)
            .where(schema.passkeys.c.id == credential_id, schema.passkeys.c.user_id == user_id)
            .values(name=name[:80])
        )
    return result.rowcount == 1


def delete_passkey(user_id: str, credential_id: str) -> bool:
    with engine().begin() as db:
        result = db.execute(
            delete(schema.passkeys).where(
                schema.passkeys.c.id == credential_id, schema.passkeys.c.user_id == user_id
            )
        )
    return result.rowcount == 1


def put_challenge(purpose: str, user_id: str | None, challenge: str, ttl: int = 300) -> str:
    challenge_id = new_token()[:48]
    with engine().begin() as db:
        db.execute(
            schema.webauthn_challenges.insert().values(
                id=challenge_id,
                purpose=purpose,
                user_id=user_id,
                challenge=challenge,
                expires_at=now() + ttl,
            )
        )
    return challenge_id


def pop_challenge(challenge_id: str, purpose: str):
    """Single use: a challenge is deleted the moment it is read, valid or not."""
    with engine().begin() as db:
        row = db.execute(
            select(schema.webauthn_challenges).where(
                schema.webauthn_challenges.c.id == challenge_id
            )
        ).first()
        if row is None:
            return None
        db.execute(
            delete(schema.webauthn_challenges).where(
                schema.webauthn_challenges.c.id == challenge_id
            )
        )
    if row.purpose != purpose or row.expires_at < now():
        return None
    return row


# --- security activity ---


@dataclass(frozen=True)
class SecurityEvent:
    id: str
    kind: str
    created_at: int
    ip_prefix: str
    user_agent: str
    detail: str


def add_event(user_id: str, kind: str, ip_prefix: str, user_agent: str, detail: str = "") -> None:
    with engine().begin() as db:
        db.execute(
            schema.security_events.insert().values(
                id=str(uuid.uuid4()),
                user_id=user_id,
                kind=kind,
                created_at=now(),
                ip_prefix=ip_prefix[:64],
                user_agent=user_agent[:200],
                detail=detail[:300],
            )
        )


def list_events(user_id: str, limit: int = 50) -> list[SecurityEvent]:
    with engine().connect() as db:
        rows = db.execute(
            select(schema.security_events)
            .where(schema.security_events.c.user_id == user_id)
            .order_by(schema.security_events.c.created_at.desc())
            .limit(limit)
        )
        return [
            SecurityEvent(r.id, r.kind, r.created_at, r.ip_prefix, r.user_agent, r.detail)
            for r in rows
        ]


def seen_before(user_id: str, ip_prefix: str, user_agent: str) -> bool:
    """Has this account signed in from this browser family and network before?"""
    with engine().connect() as db:
        row = db.execute(
            select(schema.security_events.c.id)
            .where(
                schema.security_events.c.user_id == user_id,
                schema.security_events.c.kind.in_(
                    ("signup", "login", "login_mfa", "login_passkey", "login_link", "login_oauth")
                ),
                schema.security_events.c.ip_prefix == ip_prefix,
                schema.security_events.c.user_agent == user_agent[:200],
            )
            .limit(1)
        ).first()
    return row is not None
