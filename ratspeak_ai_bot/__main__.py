from __future__ import annotations

import argparse
import logging
import sys

from . import __version__
from .bot import Bot
from .config import load as load_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ratspeak-ai-bot")
    parser.add_argument("--config", default="config.toml", help="Path to TOML config.")
    parser.add_argument("--version", action="version", version=f"ratspeak-ai-bot {__version__}")
    parser.add_argument(
        "--print-address",
        action="store_true",
        help="Boot, print LXMF address, exit. Useful for setup scripts.",
    )
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    logging.basicConfig(
        level=getattr(logging, cfg.logging.level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )

    if not cfg.venice.api_key:
        print(
            "ERROR: VENICE_API_KEY is not set. Export it before starting the bot.",
            file=sys.stderr,
        )
        return 2

    bot = Bot(cfg)
    if args.print_address:
        # Bot's __init__ already logged the address. Done.
        return 0

    try:
        bot.run()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
