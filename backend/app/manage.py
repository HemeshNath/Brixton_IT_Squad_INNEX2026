"""Small admin commands (Phase 10). Run from backend/ with the virtual env:

  python -m app.manage seed-known-scams [file]   add the 'scam' rows of a data file to the known-scam memory
                                                 (default: eval/data/collected_sms.csv; duplicates are skipped)
  python -m app.manage make-admin <email>        let a signed-in user review reports (they must have signed in once)
  python -m app.manage remove-admin <email>

Uses DATABASE_URL from .env, like the server."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import func, select

from .checks.known_scams import KnownScamMemory, seed_from_csv
from .config import get_settings
from .db import Profile, make_engine, make_sessionmaker

DEFAULT_DATA = Path(__file__).resolve().parent.parent / "eval" / "data" / "collected_sms.csv"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.manage")
    sub = parser.add_subparsers(dest="cmd", required=True)
    seed = sub.add_parser("seed-known-scams")
    seed.add_argument("file", nargs="?", default=str(DEFAULT_DATA))
    for name in ("make-admin", "remove-admin"):
        sub.add_parser(name).add_argument("email")
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
            users = db.scalars(select(Profile).where(func.lower(Profile.email) == args.email.strip().lower())).all()
            if not users:
                print("No user with that email. They must sign in to the app once first.")
                return 1
            for u in users:
                u.is_admin = args.cmd == "make-admin"
            db.commit()
            print(f"{args.email}: admin = {args.cmd == 'make-admin'}")
            return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
