from __future__ import annotations

from dataclasses import dataclass

from .config import Config
from .memory import Memory
from .venice import VeniceClient


HELP_TEXT = """\
ratspeak-ai commands:

  /help            Show this message.
  /about           What this bot is and isn't.
  /reset           Clear our conversation history.
  /model           Show your current model.
  /model <name>    Switch model (must be on the allowed list).
  /models          List allowed models.
  /usage           Your usage today.

Anything else is treated as a prompt.\
"""

ABOUT_TEXT = """\
You're talking to ratspeak-ai, a gateway bot that bridges Reticulum/LXMF to a \
clearnet inference API. Your message to me is end-to-end encrypted on the mesh, \
but I forward the text to the model provider over TLS — they see your prompts. \
Don't send anything you wouldn't want a third party to read. \
Source: github.com/ratspeak (or wherever this bot is hosted).\
"""


@dataclass
class CommandResult:
    reply: str
    handled: bool = True


def handle_command(
    text: str,
    *,
    peer_hash: str,
    cfg: Config,
    memory: Memory,
    venice: VeniceClient,
) -> CommandResult | None:
    """Returns a CommandResult if `text` was a slash command, else None."""
    s = text.strip()
    if not s.startswith("/"):
        return None

    parts = s.split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if cmd in ("/help", "/?", "/h"):
        return CommandResult(HELP_TEXT)

    if cmd == "/about":
        return CommandResult(ABOUT_TEXT)

    if cmd == "/reset":
        n = memory.reset(peer_hash)
        return CommandResult(f"Cleared {n} message(s) of history.")

    if cmd == "/model":
        if not arg:
            current = memory.get_model(peer_hash) or cfg.venice.default_model
            return CommandResult(f"Current model: {current}\nUse /models to see options.")
        if arg not in cfg.venice.allowed_models:
            return CommandResult(
                f"'{arg}' is not on the allowed list. Try /models."
            )
        memory.set_model(peer_hash, arg)
        return CommandResult(f"Model set to {arg}.")

    if cmd == "/models":
        models = "\n".join(f"  - {m}" for m in cfg.venice.allowed_models)
        return CommandResult(f"Allowed models:\n{models}")

    if cmd == "/usage":
        tokens, msgs = memory.usage_today(peer_hash)
        quota = cfg.ratelimit.daily_token_quota
        quota_str = f"{tokens}/{quota}" if quota else f"{tokens} (unlimited)"
        return CommandResult(f"Today: {msgs} messages, {quota_str} tokens.")

    return CommandResult(f"Unknown command: {cmd}. Try /help.")
