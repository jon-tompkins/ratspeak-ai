from __future__ import annotations

from dataclasses import dataclass

from .config import Config
from .memory import Memory
from .venice import VeniceClient


HELP_TEXT = (
    "ratspeak-ai commands\n\n"
    "/help — this message\n\n"
    "/about — what this bot is, and your current model\n\n"
    "/reset — clear our conversation history\n\n"
    "/model — show your current model\n\n"
    "/model <name> — switch model (must be on /models)\n\n"
    "/models — list allowed models\n\n"
    "/usage — your usage today\n\n"
    "/owner help — admin commands (owner only)\n\n"
    "anything else is treated as a prompt."
)

OWNER_HELP_TEXT = (
    "owner commands\n\n"
    "/owner stats — global usage today + peer count\n\n"
    "/owner peers [n] — recent peers (default 20)\n\n"
    "/owner setdefault <model> — change global default model\n\n"
    "/owner ban <peer> [reason] — block a peer hash\n\n"
    "/owner unban <peer> — unblock a peer\n\n"
    "/owner bans — list current bans\n\n"
    "/owner quota <peer> <tokens> — per-peer daily token override (0 = remove)\n\n"
    "/owner help — this message"
)


def _short(peer: str) -> str:
    return peer[:10] + "…" if len(peer) > 12 else peer


def _handle_owner(
    arg: str, *, cfg: Config, memory: Memory
) -> CommandResult:
    parts = arg.split(maxsplit=2) if arg else []
    sub = parts[0].lower() if parts else "help"
    rest = parts[1:] if len(parts) > 1 else []

    if sub in ("help", "?", ""):
        return CommandResult(OWNER_HELP_TEXT)

    if sub == "stats":
        tokens, msgs, peers = memory.global_usage_today()
        default = memory.get_setting("default_model") or cfg.venice.default_model
        bans = len(memory.list_bans())
        return CommandResult(
            f"today: {msgs} msgs, {tokens} tokens, {peers} peers\n\n"
            f"default model: {default}\n\n"
            f"bans: {bans}"
        )

    if sub == "peers":
        n = int(rest[0]) if rest and rest[0].isdigit() else 20
        rows = memory.peer_summaries(limit=n)
        if not rows:
            return CommandResult("no peers yet.")
        lines = [f"recent peers (top {len(rows)})"]
        for peer, name, updated, tokens, msgs in rows:
            tag = name or "—"
            lines.append(f"• {_short(peer)} · {tag} · {msgs}m/{tokens}t today")
        return CommandResult("\n\n".join(lines))

    if sub == "setdefault":
        if not rest:
            return CommandResult("usage: /owner setdefault <model>")
        model = rest[0]
        if model not in cfg.venice.allowed_models:
            return CommandResult(f"'{model}' not in allowed_models.")
        memory.set_setting("default_model", model)
        cfg.venice.default_model = model
        return CommandResult(f"default model now {model}.")

    if sub == "ban":
        if not rest:
            return CommandResult("usage: /owner ban <peer_hash> [reason]")
        peer = rest[0].lower()
        reason = rest[1] if len(rest) > 1 else None
        memory.set_banned(peer, reason)
        return CommandResult(f"banned {_short(peer)}.")

    if sub == "unban":
        if not rest:
            return CommandResult("usage: /owner unban <peer_hash>")
        n = memory.unban(rest[0].lower())
        return CommandResult(f"unbanned ({n} row).")

    if sub == "bans":
        bans = memory.list_bans()
        if not bans:
            return CommandResult("no bans.")
        return CommandResult(
            "\n\n".join(f"• {_short(p)}{(' · ' + r) if r else ''}" for p, r in bans)
        )

    if sub == "quota":
        if len(rest) < 2 or not rest[1].lstrip("-").isdigit():
            return CommandResult("usage: /owner quota <peer> <tokens>  (0 to clear)")
        peer = rest[0].lower()
        tokens = int(rest[1])
        if tokens <= 0:
            memory.set_peer_quota(peer, 0)
            return CommandResult(f"cleared quota override for {_short(peer)}.")
        memory.set_peer_quota(peer, tokens)
        return CommandResult(f"quota for {_short(peer)} set to {tokens} tokens/day.")

    return CommandResult(f"unknown owner subcommand: {sub}. try /owner help")

ABOUT_TEXT = (
    "ratspeak-ai is a gateway bot bridging Reticulum/LXMF to a clearnet inference API.\n\n"
    "your message is end-to-end encrypted on the mesh, but i forward the text to the model "
    "provider over TLS — they see your prompts.\n\n"
    "don't send anything you wouldn't want a third party to read.\n\n"
    "source: github.com/jon-tompkins/ratspeak-ai"
)


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
        current = memory.get_model(peer_hash) or memory.get_setting("default_model") or cfg.venice.default_model
        global_default = memory.get_setting("default_model") or cfg.venice.default_model
        meta = (
            f"\n\nyour model: {current}\n\n"
            f"global default: {global_default}\n\n"
            f"provider: {cfg.venice.base_url}"
        )
        return CommandResult(ABOUT_TEXT + meta)

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
        models = "\n\n".join(f"• {m}" for m in cfg.venice.allowed_models)
        return CommandResult(f"allowed models\n\n{models}")

    if cmd == "/usage":
        tokens, msgs = memory.usage_today(peer_hash)
        override = memory.get_peer_quota(peer_hash)
        quota = override if override else cfg.ratelimit.daily_token_quota
        quota_str = f"{tokens}/{quota}" if quota else f"{tokens} (unlimited)"
        return CommandResult(f"Today: {msgs} messages, {quota_str} tokens.")

    if cmd == "/owner":
        owner = (cfg.owner.lxmf_addr or "").lower()
        if not owner or peer_hash.lower() != owner:
            return CommandResult("Unknown command. Try /help.")
        return _handle_owner(arg, cfg=cfg, memory=memory)

    return CommandResult(f"Unknown command: {cmd}. Try /help.")
