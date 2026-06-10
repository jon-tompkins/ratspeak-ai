from __future__ import annotations

import logging
import signal
import threading
import time
from pathlib import Path

import LXMF
import RNS

from .commands import handle_command
from .config import Config
from .keystore import Keystore
from .memory import Memory
from .ratelimit import RateLimiter
from .venice import InferenceAuthError, VeniceClient

log = logging.getLogger(__name__)


# Hard cap on a single LXMF reply payload. LXMF supports arbitrary size, but huge replies
# fragment badly over the mesh; keep things friendly.
MAX_REPLY_CHARS = 6000


class Bot:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._stop = threading.Event()

        storage = Path(cfg.bot.storage_dir).expanduser().resolve()
        storage.mkdir(parents=True, exist_ok=True)
        self._storage = storage
        self._identity_path = storage / "identity"
        self._lxmf_storage = storage / "lxmf"
        self._lxmf_storage.mkdir(parents=True, exist_ok=True)

        # --- Reticulum ---
        configdir = cfg.bot.reticulum_configdir or None
        self._rns = RNS.Reticulum(configdir=configdir)

        # --- Identity (persistent) ---
        if self._identity_path.is_file():
            self._identity = RNS.Identity.from_file(str(self._identity_path))
            log.info("loaded existing identity")
        else:
            self._identity = RNS.Identity()
            self._identity.to_file(str(self._identity_path))
            log.info("generated new identity at %s", self._identity_path)

        # --- LXMF router ---
        self._router = LXMF.LXMRouter(
            identity=self._identity,
            storagepath=str(self._lxmf_storage),
            enforce_stamps=False,
        )
        self._dest = self._router.register_delivery_identity(
            self._identity,
            display_name=cfg.bot.display_name,
            stamp_cost=cfg.bot.stamp_cost,
        )
        self._router.register_delivery_callback(self._on_message)

        # --- Subsystems ---
        self._memory = Memory(cfg.memory.db_path, cfg.memory.history_turns)
        self._ratelimit = RateLimiter(
            cfg.ratelimit.messages_per_window,
            cfg.ratelimit.window_seconds,
            cfg.ratelimit.daily_token_quota,
        )
        self._venice = VeniceClient(
            cfg.venice.base_url, cfg.venice.api_key, cfg.venice.default_model
        )
        self._keystore = Keystore(storage / "keystore.key")

        log.info("bot LXMF address: %s", RNS.prettyhexrep(self._dest.hash))
        log.info("display name: %s", cfg.bot.display_name)

    # ---------------------------------------------------------------- lifecycle

    def run(self) -> None:
        signal.signal(signal.SIGINT, self._signal)
        signal.signal(signal.SIGTERM, self._signal)

        # Announce once on start, then on the configured interval.
        last_announce = 0.0
        try:
            while not self._stop.is_set():
                now = time.monotonic()
                if now - last_announce >= self.cfg.bot.announce_interval:
                    try:
                        self._router.announce(self._dest.hash)
                        log.info("announced %s", RNS.prettyhexrep(self._dest.hash))
                    except Exception as exc:  # pragma: no cover — RNS internal errors
                        log.warning("announce failed: %s", exc)
                    last_announce = now
                self._stop.wait(timeout=5)
        finally:
            log.info("shutting down")

    def _signal(self, signum, _frame):  # pragma: no cover
        log.info("signal %s, stopping", signum)
        self._stop.set()

    # ----------------------------------------------------------- message handler

    def _on_message(self, message: "LXMF.LXMessage") -> None:
        """Dispatched by LXMRouter on inbound delivery. Runs on the router thread; offload
        the slow Venice call to a worker so the router keeps moving."""
        try:
            body = (message.content_as_string() or "").strip()
            title = message.title_as_string() or ""
            source_identity = message.source
            source_hash = message.source_hash
        except Exception as exc:
            log.exception("failed to read inbound message: %s", exc)
            return

        if not body:
            return

        peer_hex = RNS.hexrep(source_hash, delimit=False)
        display_name = title if title else None
        log.info("inbound from %s (%d chars)", peer_hex, len(body))

        t = threading.Thread(
            target=self._handle_message,
            args=(peer_hex, source_identity, source_hash, body, display_name),
            daemon=True,
        )
        t.start()

    def _handle_message(
        self,
        peer_hex: str,
        source_identity,
        source_hash: bytes,
        body: str,
        display_name: str | None,
    ) -> None:
        self._memory.touch_peer(peer_hex, display_name)

        is_owner = bool(self.cfg.owner.lxmf_addr) and peer_hex.lower() == self.cfg.owner.lxmf_addr.lower()

        # Ban check (owner is never banned)
        if not is_owner and self._memory.is_banned(peer_hex):
            log.info("dropped inbound from banned peer %s", peer_hex)
            return

        # Slash command? Short-circuit before hitting rate limit, since these are cheap.
        cmd_result = handle_command(
            body,
            peer_hash=peer_hex,
            cfg=self.cfg,
            memory=self._memory,
            venice=self._venice,
            keystore=self._keystore,
        )
        if cmd_result is not None:
            self._send_reply(source_identity or source_hash, cmd_result.reply)
            return

        # BYOK: if peer has a personal key, decrypt it and skip the shared quota.
        key_row = self._memory.get_peer_api_key(peer_hex)
        byok_key: str | None = None
        if key_row:
            byok_key = self._keystore.decrypt(key_row[1])
            if byok_key is None:
                log.warning("could not decrypt stored key for %s; dropping it", peer_hex)
                self._memory.clear_peer_api_key(peer_hex)

        if not byok_key:
            if self.cfg.bot.byok_only:
                self._send_reply(
                    source_identity or source_hash,
                    "this bot is BYOK-only — set your own Venice key first.\n\n"
                    "1. grab one at venice.ai → API → Keys\n\n"
                    "2. send: /setkey <your_key>\n\n"
                    "then prompt as normal. see /help for more.",
                )
                return
            # Rate / quota (per-peer override > global) — only applies to shared key.
            tokens_today, _ = self._memory.usage_today(peer_hex)
            peer_quota = self._memory.get_peer_quota(peer_hex)
            decision = self._ratelimit.check(peer_hex, tokens_today, quota_override=peer_quota)
            if not decision.allowed:
                self._send_reply(source_identity or source_hash, decision.reason)
                return

        # Build chat context
        history = self._memory.recent_turns(peer_hex)
        messages = [{"role": "system", "content": self.cfg.venice.system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": body})

        global_default = self._memory.get_setting("default_model") or self.cfg.venice.default_model
        chosen_model = self._memory.get_model(peer_hex) or global_default
        if chosen_model not in self.cfg.venice.allowed_models:
            chosen_model = global_default

        try:
            result = self._venice.chat(
                messages,
                model=chosen_model,
                max_tokens=self.cfg.venice.max_tokens,
                temperature=self.cfg.venice.temperature,
                api_key=byok_key,
            )
        except InferenceAuthError as exc:
            log.warning("auth error for %s (byok=%s): %s", peer_hex, bool(byok_key), exc)
            if byok_key:
                self._memory.touch_peer_api_key(peer_hex, "auth_failed")
                self._memory.clear_peer_api_key(peer_hex)
                self._send_reply(
                    source_identity or source_hash,
                    "your Venice key was rejected — i've removed it. "
                    "check venice.ai → API → Keys and try /setkey again.",
                )
            else:
                self._send_reply(
                    source_identity or source_hash,
                    "the shared bot key was rejected by the provider. owner has been notified.",
                )
            return
        except Exception as exc:
            log.exception("inference failed: %s", exc)
            self._send_reply(
                source_identity or source_hash,
                "Sorry — the model call failed. Try again, or /reset if it keeps happening.",
            )
            return

        reply = result.text or "(empty reply)"
        if len(reply) > MAX_REPLY_CHARS:
            reply = reply[: MAX_REPLY_CHARS - 16] + "\n…[truncated]"

        # Persist turn + usage (shared vs BYOK accounted separately)
        self._memory.append_turn(peer_hex, "user", body)
        self._memory.append_turn(peer_hex, "assistant", reply)
        if byok_key:
            self._memory.add_byok_usage(peer_hex, result.total_tokens)
            self._memory.touch_peer_api_key(peer_hex, "ok")
        else:
            self._memory.add_usage(peer_hex, result.total_tokens)

        log.info(
            "reply to %s: model=%s tokens=%d/%d",
            peer_hex,
            result.model,
            result.prompt_tokens,
            result.completion_tokens,
        )
        self._send_reply(source_identity or source_hash, reply, title="Re: " + (display_name or "chat"))

    # ----------------------------------------------------------------- outbound

    def _send_reply(
        self, source_identity, text: str, *, title: str = "Re: chat"
    ) -> None:
        try:
            identity = source_identity
            identity_hash = None
            if isinstance(identity, RNS.Destination):
                identity_hash = identity.hash
                identity = identity.identity
            elif isinstance(identity, (bytes, bytearray)):
                identity_hash = bytes(identity)
                identity = RNS.Identity.recall(identity_hash)
            if not isinstance(identity, RNS.Identity):
                if identity_hash is not None:
                    RNS.Transport.request_path(identity_hash)
                    log.warning("no identity for %s, requested path; reply dropped", RNS.hexrep(identity_hash, delimit=False))
                else:
                    log.warning("no identity available for reply; dropped (type=%s)", type(source_identity).__name__)
                return
            dest = RNS.Destination(
                identity,
                RNS.Destination.OUT,
                RNS.Destination.SINGLE,
                "lxmf",
                "delivery",
            )
            lxm = LXMF.LXMessage(
                dest,
                self._dest,
                text,
                title=title,
                desired_method=LXMF.LXMessage.DIRECT,
                include_ticket=True,
            )
            self._router.handle_outbound(lxm)
        except Exception as exc:
            log.exception("send failed: %s", exc)
