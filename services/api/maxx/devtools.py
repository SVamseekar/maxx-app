"""Development helpers. Refuse to run in production.

uv run python -m maxx.devtools account you@example.com 'a long passphrase' --admin
"""

import argparse
import sys

from maxx.auth import store
from maxx.auth.security import hash_password, normalize_email, password_problem, valid_email
from maxx.config import settings


def create_account(email: str, password: str, name: str = "") -> store.User:
    email = normalize_email(email)
    if not valid_email(email):
        raise SystemExit("Not a valid email address.")
    problem = password_problem(password, email)
    if problem:
        raise SystemExit(problem)
    existing = store.get_user_by_email(email)
    digest = hash_password(password)
    if existing:
        store.update_user(existing.id, password_hash=digest, email_verified=True)
        return store.get_user(existing.id)  # type: ignore[return-value]
    return store.create_user(email, name or email.split("@")[0], digest, True)


def main(argv: list[str] | None = None) -> None:
    if settings.environment == "production":
        raise SystemExit("Development tools are disabled in production.")
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    account = sub.add_parser("account", help="Create or reset a verified account (skips email).")
    account.add_argument("email")
    account.add_argument("password")
    account.add_argument("--name", default="")
    args = parser.parse_args(argv)
    user = create_account(args.email, args.password, args.name)
    print(f"Ready: {user.email} (verified, password set). Add it to ADMIN_EMAILS to reset demos.")


if __name__ == "__main__":
    sys.exit(main())
