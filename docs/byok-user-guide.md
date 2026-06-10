# Using the ratspeak-ai BYOK bot

A public LXMF/Reticulum bot that talks to Venice. You bring your own Venice
API key — every prompt you send is billed to your Venice account, nothing to
the bot operator.

End-to-end encrypted on the mesh. The bot host can't read your messages until
they're forwarded to Venice (which sees them under your account, same as if
you were using the Venice web UI).

---

## What you need

- An LXMF client. The recommended one is the **[Ratspeak app](https://ratspeak.org)** — it ships pre-configured to talk to `1.ratspeak.org`, which is the same hub this bot lives on, so there's no networking setup.
  - Alternatives: [Sideband](https://play.google.com/store/apps/details?id=io.unsigned.sideband) (Android), [Nomadnet](https://github.com/markqvist/nomadnet) (desktop/CLI). Both work but require manually adding the hub.
- A **Venice** account with API access — sign up at <https://venice.ai>. Even
  the free tier gets API access; usage is metered against your Diem balance.

---

## Step 1 — Connect your client to the Ratspeak hub

You and the bot need to share at least one Reticulum hub. The bot lives on `1.ratspeak.org:4242`.

**Ratspeak app:** nothing to do — it ships connected to `1.ratspeak.org` out of the box. Skip to step 2.

**Sideband (Android):**
1. Side menu → **Connectivity**.
2. Enable **"Use TCP tunnel"** (or "Connect via TCP").
3. Host: `1.ratspeak.org` · Port: `4242`. Save.

**Nomadnet / raw RNS:** add a `TCPClientInterface` pointing at `1.ratspeak.org:4242` in your `~/.reticulum/config`.

Any other hub bridged to `1.ratspeak.org` works too.

---

## Step 2 — Add the BYOK bot as a contact

The bot's address:

```
19f0e22660bcc2c6ebde074ecac94a3c
```

**Ratspeak app:** new conversation → paste the address → name it ("ratspeak-ai" works) → done. The app handles path requests automatically.

**Sideband:**
1. Conversations → "+" → **New conversation**.
2. Paste the address.
3. Name it ("ratspeak-ai").
4. Tap **Request Path**. Wait ~10s.

---

## Step 3 — Get a Venice API key

1. Go to <https://venice.ai> and sign in.
2. Top-right menu → **API** → **Keys**.
3. Create a new key. Copy the full string.

Keep it private — anyone with that key can bill your Venice account.

---

## Step 4 — Register your key with the bot

Send this to the bot as a normal message:

```
/setkey <paste_your_venice_key_here>
```

The bot will:

1. Validate the key with a 1-token ping to Venice.
2. Encrypt it at rest on the bot host (Fernet, AES-128).
3. Reply with confirmation, showing only the last 4 chars.

**Then delete your `/setkey` message** from your Sideband conversation so the
key isn't sitting in your local history.

---

## Step 5 — Use it

Just send messages. Each one is a Venice inference call on your account.

Useful commands:

- `/help` — full command list
- `/about` — confirms which key you're billed under
- `/model` — show current model
- `/model <name>` — switch (must be on `/models`)
- `/models` — allowed list
- `/usage` — today's messages + tokens
- `/keystatus` — confirm your key is set
- `/clearkey` — remove your stored key
- `/reset` — clear our conversation history

---

## Cost expectations

`venice-uncensored` (the default) is the cheapest in the Venice catalog —
realistic chat costs are fractions of a cent per turn. Heavier models like
`llama-3.3-70b` cost ~10–20× more but still pennies for normal use.

`/usage` shows your token total for the day so you can spot-check.

---

## Trust model

- **Your messages → bot host → Venice.** Reticulum encrypts the first hop end
  to end. Venice sees the second hop (same as the web UI).
- **Your API key.** Encrypted at rest with a Fernet master key that lives on
  the bot host (mode 0600). Protects against database-only leaks; an attacker
  with root on the host can decrypt — same trust boundary as the bot operator's
  own credentials.
- **No one but you can use your key.** `/setkey`, `/clearkey`, `/keystatus`
  are scoped to your sender address. Other users can't see or use your key.
- If Venice rejects your key (revoked, out of credit), the bot auto-removes
  it and tells you. Run `/setkey` again with a new one.

---

## Troubleshooting

- **No reply after sending.** Your client may not have a path to the bot yet.
  Tap the conversation → **Request Path**, wait 10–30s, try again.
- **"this bot is BYOK-only — set your own Venice key first."** You haven't
  set a key yet. Run `/setkey <your_key>`.
- **"key didn't work."** Venice rejected the key in the validation ping.
  Double-check you copied the full string from venice.ai → API → Keys.
- **Long silence after a prompt.** First inference call after a quiet period
  can take 15–60s while the LXMF path warms up. Subsequent calls are 5–15s.

---

## Source

<https://github.com/jon-tompkins/ratspeak-ai>
