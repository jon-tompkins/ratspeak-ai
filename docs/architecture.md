# Architecture

```
                         ╔══════════════════════════════════════╗
                         ║          ratspeak-ai-bot             ║
                         ║                                      ║
                         ║   ┌──────────┐    ┌──────────────┐   ║
   LXMF (encrypted) ───► ║   │ LXMRouter│───►│ bot.Bot      │   ║
   ◄─────────────── LXMF ║   │  (Rx)    │    │  on_message  │   ║
                         ║   └──────────┘    └─────┬────────┘   ║
                         ║                         │            ║
                         ║                         ▼            ║
                         ║   ┌──────────┐    ┌──────────────┐   ║
                         ║   │ memory   │◄──►│ commands     │   ║
                         ║   │ (SQLite) │    │  /help /reset│   ║
                         ║   └──────────┘    └─────┬────────┘   ║
                         ║                         │            ║
                         ║                         ▼            ║
                         ║   ┌──────────┐    ┌──────────────┐   ║
                         ║   │ratelimit │───►│ VeniceClient │───╫───► api.venice.ai
                         ║   └──────────┘    └──────────────┘   ║         (TLS)
                         ╚══════════════════════════════════════╝
```

## Threads

- **Main thread** — boots Reticulum, spins up LXMRouter, runs the announce loop, waits for SIGTERM.
- **Router thread (LXMF internal)** — calls `_on_message` for each inbound delivery. We do the bare minimum here (parse, log) and dispatch a worker thread.
- **Worker thread (per inbound)** — handles slash commands or hits Venice, persists to SQLite, sends the reply via `LXMRouter.handle_outbound`. Threads are short-lived; we don't pool because the rate-limiter already bounds concurrency per peer.

The SQLite handle is opened with `check_same_thread=False` because workers come from multiple threads. All writes go through single SQL statements (no multi-statement transactions), so the GIL plus `isolation_level=None` is enough — no explicit lock needed.

## Failure modes

- **Venice API down** → reply with a polite error, no retention of the failed turn. User can `/reset` if context gets weird.
- **Path not yet established** to a new peer's identity → `handle_outbound` queues; LXMF retries on its own schedule. We don't need to poll.
- **SIGINT/SIGTERM** → set the stop event, the main loop falls through. Worker threads are daemon-flagged so an unsent reply on shutdown will drop. Acceptable for v0; if we ever want guaranteed delivery on shutdown, switch workers to a join-on-shutdown queue.
- **Identity file lost** → bot's destination hash changes. All existing peers' contact entries point at the dead address. Treat `state/identity` like a key file: back it up.

## What's not here (intentionally)

- **No global LLM context.** Each peer has its own rolling window; we never co-mingle.
- **No multi-bot orchestration.** One bot, one Venice key, one destination. If you want a different persona or model pool, run a second bot with a different storage dir.
- **No web admin.** Configuration is files. Operational signals are logs + `/usage` for peers and SQLite for operators.
