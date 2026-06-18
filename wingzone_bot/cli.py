from __future__ import annotations

import argparse
import asyncio
import logging

from .config import Settings
from .scheduler import WingZoneApp
from .storage import Storage


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Wing Zone Telegram editorial bot")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db", help="Initialize local SQLite database")

    once = subparsers.add_parser("once", help="Fetch news and create drafts once")
    once.add_argument("--dry-run", action="store_true", help="Print drafts without Telegram calls")

    subparsers.add_parser("worker", help="Run continuous polling worker")

    send_test = subparsers.add_parser("send-test", help="Send a test message to review chat")
    send_test.add_argument("text", nargs="?", default="Wing Zone bot is alive.")

    return parser


async def async_main() -> None:
    args = build_parser().parse_args()
    settings = Settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.command == "init-db":
        Storage(settings.database_path).initialize()
        print(f"Initialized {settings.database_path}")
        return

    app = WingZoneApp(settings)

    if args.command == "once":
        await app.run_once(dry_run=args.dry_run)
        return

    if args.command == "worker":
        await app.run_worker()
        return

    if args.command == "send-test":
        await app.send_test(args.text)
        return


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
