"""Small admin commands (Phase 10, 10A). Run from backend/ with the virtual env:

  python -m app.manage seed-known-scams [file]          add the 'scam' rows of a data file to the known-scam memory
                                                        (default: eval/data/collected_sms.csv; duplicates skipped)
  python -m app.manage create-admin <id> [--role owner] make a web admin panel account (asks for the password)
  python -m app.manage reset-admin-password <id>        set a new password and unlock the account (asks for it)
  python -m app.manage list-admins

Passwords are typed here (hidden) and only their hash is stored. Uses DATABASE_URL from .env, like the server."""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

from sqlalchemy import select

from .admin_auth import ROLES, end_all_sessions, hash_password, normalize_username, password_problem
from .checks.known_scams import KnownScamMemory, seed_from_csv
from .config import get_settings
from .db import AdminUser, AuditLog, make_engine, make_sessionmaker

DEFAULT_DATA = Path(__file__).resolve().parent.parent / "eval" / "data" / "collected_sms.csv"


def ask_password() -> str | None:
    """Asks twice (hidden). Returns the password, or None after printing why it is not accepted."""
    first = getpass.getpass("New password: ")
    if problem := password_problem(first):
        print(problem)
        return None
    if getpass.getpass("Repeat password: ") != first:
        print("The two passwords are different.")
        return None
    return first


def main(argv: list[str] | None = None, ask=ask_password) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.manage")
    sub = parser.add_subparsers(dest="cmd", required=True)
    seed = sub.add_parser("seed-known-scams")
    seed.add_argument("file", nargs="?", default=str(DEFAULT_DATA))
    create = sub.add_parser("create-admin")
    create.add_argument("username")
    create.add_argument("--role", choices=ROLES, default="owner")
    sub.add_parser("reset-admin-password").add_argument("username")
    sub.add_parser("list-admins")
    args = parser.parse_args(argv)

    engine = make_engine(get_settings().database_url)
    sessions = make_sessionmaker(engine)
    try:
        with sessions() as db:
            if args.cmd == "seed-known-scams":
                memory = KnownScamMemory(sessions)
                added, skipped = seed_from_csv(db, memory, args.file)
                print(f"known scams: {added} added, {skipped} skipped (too short or already known), "
                      f"{len(memory)} in memory")
                return 0
            if args.cmd == "list-admins":
                for a in db.scalars(select(AdminUser).order_by(AdminUser.id)):
                    print(f"{a.username:24} {a.role:9} {'active' if a.active else 'disabled'}")
                return 0
            name = normalize_username(args.username)
            existing = db.scalar(select(AdminUser).where(AdminUser.username == name))
            if args.cmd == "create-admin" and existing:
                print("That admin ID already exists. Use reset-admin-password to change its password.")
                return 1
            if args.cmd == "reset-admin-password" and not existing:
                print("No admin with that ID.")
                return 1
            password = ask()
            if password is None:
                return 1
            if args.cmd == "create-admin":
                db.add(AdminUser(username=name, password_hash=hash_password(password), role=args.role))
                action = "account_created"
            else:
                existing.password_hash = hash_password(password)
                existing.failed_logins, existing.locked_until, existing.active = 0, None, True
                action = "password_reset"
            db.add(AuditLog(admin_username="(server)", action=action, detail={"account": name}, ip="local"))
            db.commit()
            if existing:
                end_all_sessions(db, existing.id)
            print(f"{name}: done ({args.role if args.cmd == 'create-admin' else 'password reset'}).")
            return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
