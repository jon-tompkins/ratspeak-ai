from __future__ import annotations

import time
from dataclasses import dataclass

from . import tiers
from .config import Config
from .keystore import Keystore
from .memory import Memory
from .venice import VeniceClient


def _peer_line(cfg: Config) -> str:
    if not cfg.bot.peer_address:
        return ""
    label = cfg.bot.peer_label or "the other ratspeak-ai bot"
    return f"{label}: <{cfg.bot.peer_address}>"


def help_text(cfg: Config) -> str:
    peer = _peer_line(cfg)
    if cfg.bot.byok_only:
        commands = (
            "/help — this message\n\n"
            "/about — what this bot is\n\n"
            "/reset — clear our conversation history\n\n"
            "/model — show your current model\n\n"
            "/model <name> — switch model (must be on /models)\n\n"
            "/models — list allowed models\n\n"
            "/usage — your usage today\n\n"
            "/status — bot info, your model, limits, registration status\n\n"
            "/setkey <venice_api_key> — required before this bot will answer; billed to your account\n\n"
            "/keystatus — show whether your key is set\n\n"
            "/clearkey — remove your stored key\n\n"
            "/owner help — admin commands (owner only)\n\n"
            "anything else is treated as a prompt, once your key is set."
        )
        footer = f"\n\ndon't want to bring your own key? try the shared/subsidized bot instead — {peer}" if peer else ""
    else:
        commands = (
            "/help — this message\n\n"
            "/about — what this bot is and what model it runs (fixed, can't be changed)\n\n"
            "/reset — clear our conversation history\n\n"
            "/badge — check your RATSPEAK badge tier / whitelist status\n\n"
            "/usage — your usage today\n\n"
            "/status — bot info, limits, registration status\n\n"
            "/owner help — admin commands (owner only)\n\n"
            "anything else is treated as a prompt."
        )
        footer = f"\n\nwant to pick your own model or bring your own key? there's a dedicated bot for that — {peer}" if peer else ""
    return f"ratspeak-ai commands\n\n{commands}{footer}"

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


def registration_hint(cfg: Config, min_tier: str) -> str:
    return f"register your wallet at {cfg.tiers.badges_url} ({min_tier.title()} tier or higher)."


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
        byok = memory.byok_peer_count()
        return CommandResult(
            f"today: {msgs} msgs, {tokens} tokens, {peers} peers\n\n"
            f"default model: {default}\n\n"
            f"bans: {bans}\n\n"
            f"byok users: {byok}"
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

def about_text(cfg: Config) -> str:
    peer = _peer_line(cfg)
    privacy = (
        "your message is end-to-end encrypted on the mesh, but i forward the text to the model "
        "provider over TLS — they see your prompts.\n\n"
        "don't send anything you wouldn't want a third party to read."
    )
    if cfg.bot.byok_only:
        mode_line = (
            "this is the bring-your-own-key gateway: every reply is billed to your own Venice "
            "account via /setkey, with no shared quota and no bot-side rate limit."
        )
        peer_line = f"\n\nnot ready to bring a key? there's a subsidized bot with a shared quota — {peer}" if peer else ""
    else:
        mode_line = (
            "this is the subsidized gateway: replies come out of a shared bot key, rate-limited "
            "per person. the model is fixed — there's no /model or /setkey here, just check /badge "
            "to see if you're whitelisted and start chatting."
        )
        peer_line = f"\n\nwant to pick your own model or bring your own key? there's a dedicated bot for that — {peer}" if peer else ""
    return (
        "ratspeak-ai is a gateway bot bridging Reticulum/LXMF to a clearnet inference API.\n\n"
        f"{mode_line}\n\n"
        f"{privacy}"
        f"{peer_line}\n\n"
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
    keystore: Keystore,
    bot_address: str = "",
) -> CommandResult | None:
    """Returns a CommandResult if `text` was a slash command, else None."""
    s = text.strip()
    if not s.startswith("/"):
        return None

    parts = s.split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if cmd in ("/help", "/?", "/h"):
        return CommandResult(help_text(cfg))

    if cmd == "/about":
        current = memory.get_model(peer_hash) or memory.get_setting("default_model") or cfg.venice.default_model
        global_default = memory.get_setting("default_model") or cfg.venice.default_model
        key_row = memory.get_peer_api_key(peer_hash)
        if key_row:
            billing = f"billed to: your Venice key (…{key_row[2]})"
        elif cfg.bot.byok_only:
            billing = "billed to: nothing yet — send /setkey to set your Venice key"
        else:
            billing = "billed to: shared bot key (rate-limited)"
        meta = (
            f"\n\nyour model: {current}\n\n"
            f"global default: {global_default}\n\n"
            f"provider: {cfg.venice.base_url}\n\n"
            f"{billing}"
        )
        return CommandResult(about_text(cfg) + meta)

    if cmd == "/reset":
        n = memory.reset(peer_hash)
        return CommandResult(f"Cleared {n} message(s) of history.")

    if cmd in ("/model", "/models") and not cfg.bot.byok_only:
        peer = _peer_line(cfg)
        note = f" try the bring-your-own-key bot instead — {peer}" if peer else ""
        return CommandResult(f"model is fixed on this bot, see /about.{note}")

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

    if cmd == "/badge":
        tier = tiers.registration_tier(peer_hash, cfg.tiers.supabase_url, cfg.tiers.supabase_key)
        if tier:
            return CommandResult(f"RATSPEAK badge: {tier.title()} tier ✅\n\nwhitelisted: yes")
        return CommandResult(
            f"RATSPEAK badge: not registered\n\nwhitelisted: no\n\n{registration_hint(cfg, cfg.tiers.shared_min_tier)}"
        )

    if cmd == "/usage":
        tokens, msgs = memory.usage_today(peer_hash)
        byok_tokens, byok_msgs = memory.byok_usage_today(peer_hash)
        override = memory.get_peer_quota(peer_hash)
        quota = override if override else cfg.ratelimit.daily_token_quota
        shared_str = f"{tokens}/{quota}" if quota else f"{tokens} (unlimited)"
        lines = [f"Today (shared key): {msgs} messages, {shared_str} tokens."]
        if byok_msgs or memory.get_peer_api_key(peer_hash):
            lines.append(f"Today (your key): {byok_msgs} messages, {byok_tokens} tokens (no bot-side quota).")
        return CommandResult("\n\n".join(lines))

    if cmd == "/status":
        current = memory.get_model(peer_hash) or memory.get_setting("default_model") or cfg.venice.default_model
        key_row = memory.get_peer_api_key(peer_hash)
        mode = "BYOK-only" if cfg.bot.byok_only else "subsidized (fixed model)"

        lines = [
            f"{cfg.bot.display_name}" + (f" ({bot_address})" if bot_address else ""),
            f"mode: {mode}\n\nprovider: {cfg.venice.base_url}\n\nyour model: {current}",
        ]

        tier = tiers.registration_tier(peer_hash, cfg.tiers.supabase_url, cfg.tiers.supabase_key)
        if tier:
            lines.append(f"registration: RATSPEAK {tier.title()} tier ✅")
        else:
            lines.append(
                f"registration: not registered\n\n{registration_hint(cfg, cfg.tiers.shared_min_tier)}"
            )

        if key_row:
            lines.append(f"billing: your Venice key (…{key_row[2]})")
        elif not cfg.bot.byok_only:
            window_min = cfg.ratelimit.window_seconds // 60
            override = memory.get_peer_quota(peer_hash)
            quota = override if override else cfg.ratelimit.daily_token_quota
            tokens_today, msgs_today = memory.usage_today(peer_hash)
            quota_str = f"{tokens_today}/{quota} tokens today" if quota else f"{tokens_today} tokens today (unlimited)"
            lines.append(
                f"billing: shared bot key\n\n"
                f"limits: {cfg.ratelimit.messages_per_window} msgs / {window_min} min, "
                f"{quota_str} ({msgs_today} messages sent)\n\n"
                f"requires RATSPEAK {cfg.tiers.shared_min_tier.title()} tier or higher"
            )

        lines.append("see /help for commands")
        return CommandResult("\n\n".join(lines))

    if cmd in ("/setkey", "/clearkey", "/keystatus") and not cfg.bot.byok_only:
        peer = _peer_line(cfg)
        note = f" that's what the bring-your-own-key bot is for — {peer}" if peer else ""
        return CommandResult(f"this bot doesn't support personal keys.{note}")

    if cmd == "/setkey":
        if not arg:
            return CommandResult(
                "usage: /setkey <venice_api_key>\n\n"
                "grab one at venice.ai → API → Keys.\n\n"
                "the key is encrypted at rest on the bot host. inference is billed to your account.\n\n"
                "tip: after the bot confirms, delete your message in Sideband to keep the key out of your local history."
            )
        candidate = arg.strip()
        if len(candidate) < 20:
            return CommandResult("that doesn't look like a Venice key. paste the full string from venice.ai.")
        tier = tiers.registration_tier(peer_hash, cfg.tiers.supabase_url, cfg.tiers.supabase_key)
        if not tiers.meets_min_tier(tier, cfg.tiers.byok_min_tier):
            return CommandResult(
                f"🔒 bring-your-own-key requires RATSPEAK {cfg.tiers.byok_min_tier.title()} tier or higher.\n\n"
                f"{registration_hint(cfg, cfg.tiers.byok_min_tier)}\n\n"
                "then send /setkey again."
            )
        ok, msg = venice.validate_key(candidate)
        if not ok:
            return CommandResult(f"key didn't work: {msg}\n\nnothing saved. try again with /setkey.")
        enc = keystore.encrypt(candidate)
        last4 = candidate[-4:]
        memory.set_peer_api_key(peer_hash, "venice", enc, last4)
        return CommandResult(
            f"key saved (…{last4}). future prompts go through your Venice account.\n\n"
            "the shared bot quota no longer applies to you.\n\n"
            "remove anytime with /clearkey. check with /keystatus.\n\n"
            "now delete your /setkey message in Sideband."
        )

    if cmd == "/clearkey":
        n = memory.clear_peer_api_key(peer_hash)
        if not n:
            return CommandResult("no key was set.")
        return CommandResult("cleared. you're back on the shared bot key (quota applies).")

    if cmd == "/keystatus":
        row = memory.get_peer_api_key(peer_hash)
        if not row:
            return CommandResult("no personal key set. use /setkey to bring your own.")
        provider, _enc, last4, status, last_used = row
        when = "never" if not last_used else f"{int((time.time() - last_used) // 60)} min ago"
        status_str = status or "untested since save"
        return CommandResult(
            f"personal key: {provider} …{last4}\n\n"
            f"last used: {when}\n\n"
            f"last status: {status_str}"
        )

    if cmd == "/owner":
        owner = (cfg.owner.lxmf_addr or "").lower()
        if not owner or peer_hash.lower() != owner:
            return CommandResult("Unknown command. Try /help.")
        return _handle_owner(arg, cfg=cfg, memory=memory)

    return CommandResult(f"Unknown command: {cmd}. Try /help.")
