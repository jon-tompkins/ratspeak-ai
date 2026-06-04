# ratspeak-ai

AI access on the [Reticulum](https://reticulum.network) mesh, via LXMF.

Two integration patterns, shipping easiest first:

1. **`ratspeak_ai_bot/`** — an LXMF destination you DM like any other contact. The bot bridges to a privacy-aligned inference provider ([Venice](https://venice.ai) by default) and replies on the mesh. Works today with any LXMF client: Sideband, Nomad Network, rsLXMF/Ratspeak.
2. **`docs/ratspeak-native-integration.md`** — design + Tauri command stubs for in-client AI in [Ratspeak](https://github.com/ratspeak/Ratspeak). BYO-key by default, community gateway as fallback. (Implementation TBD with the Ratspeak founder.)

Long-term: local edge inference on networking nodes (small models on Pis hanging off Reticulum interfaces). Parked.

---

## Quickstart — run the bot

```bash
# 1. Install
pip install -e .

# 2. Set your Venice key
export VENICE_API_KEY=...

# 3. Copy config, edit display name + any model overrides
cp config.example.toml config.toml

# 4. Run
ratspeak-ai-bot --config config.toml
```

First boot prints the bot's LXMF address (32 hex chars). Hand that to a user — they add it as a contact in Sideband/Ratspeak and start chatting.

If you have no Reticulum interface configured, the bot will only be reachable on the local box. To join the public mesh, add an interface to `~/.reticulum/config` — the [Reticulum manual](https://reticulum.network/manual/) has presets.

## Architecture

```
┌──────────────────┐    LXMF    ┌─────────────────┐   HTTPS    ┌─────────┐
│ User (Sideband / │ ─────────► │ ratspeak-ai-bot │ ─────────► │ Venice  │
│ Ratspeak / etc)  │ ◄───────── │  (this repo)    │ ◄───────── │  API    │
└──────────────────┘            └─────────────────┘            └─────────┘
       on mesh                       gateway                     clearnet
```

The bot is a **gateway**, not a peer. Inbound messages on the mesh are end-to-end encrypted to the bot's identity; from the bot to Venice the conversation is normal TLS to a clearnet API. **This is not end-to-end private with the model provider.** See [`docs/trust-model.md`](docs/trust-model.md) for what is and isn't protected.

## Features

- LXMF direct, opportunistic, and propagated delivery
- Per-peer conversation memory in SQLite (rolling window, configurable)
- Slash commands: `/help`, `/about`, `/reset`, `/model`, `/models`, `/usage`
- Per-peer rate limiting + daily token quota (subsidize a free tier without bleeding)
- Configurable system prompt
- Allowed-models list (so a free tier can't run a $20/Mtok frontier model)
- Graceful shutdown, persistent identity, automatic announce on startup

## Files

- `ratspeak_ai_bot/bot.py` — LXMF router setup, inbound/outbound, lifecycle
- `ratspeak_ai_bot/venice.py` — Venice client wrapper (OpenAI-compatible)
- `ratspeak_ai_bot/config.py` — TOML config loader
- `ratspeak_ai_bot/memory.py` — per-peer conversation store (SQLite)
- `ratspeak_ai_bot/commands.py` — slash command dispatch
- `ratspeak_ai_bot/ratelimit.py` — token-bucket + daily quota
- `config.example.toml` — annotated config
- `systemd/ratspeak-ai-bot.service` — drop-in unit file
- `scripts/install.sh` — one-shot installer for a fresh box

## License

AGPL-3.0-or-later, matching the rest of the Ratspeak family.
