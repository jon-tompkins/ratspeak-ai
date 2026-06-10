# Bring Your Own Key (BYOK)

Anyone with a Venice API key can route their own inference through the bot,
paying for their own usage and bypassing the shared-key rate limits.

## End-to-end flow for a new user

1. **Install a Reticulum client** (Sideband on Android, Nomadnet on desktop, or
   the Ratspeak client). Connect it to a public Reticulum hub the bot is also
   on — `1.ratspeak.org:4242` works.

2. **Add the bot as a contact.** Address:
   `9b1ba11be311f7e72546890d2f8267da` (for this deployment; substitute your
   own bot's hash). In Sideband, paste the hash, "Request Path", wait for
   resolution.

3. **Optional: ask `/help`** to see the command list, or `/about` to confirm
   you're talking to ratspeak-ai.

4. **Get a Venice key.** Sign in at https://venice.ai → API → Keys → create one.
   Keep it private.

5. **Send `/setkey <your_key>`** to the bot. The bot will:
   - Validate the key with a one-token ping against Venice.
   - On success: encrypt the key with Fernet (key lives on the bot host at
     `state/keystore.key`, mode 0600) and store it against your LXMF address.
   - Reply confirming, showing only the last 4 chars.

6. **Delete your `/setkey` message** in your client so it isn't sitting in your
   local message history.

7. **Chat normally.** Every prompt now bills your Venice account, not the
   shared bot key. The daily token quota that applies to shared-key users is
   skipped for you. Per-conversation rate-limit (messages-per-window) still
   applies as a basic abuse guard.

## Managing your key

- `/keystatus` — show whether a personal key is set, its last 4 chars,
  last-used time, and last-status (`ok` / `auth_failed`).
- `/clearkey` — remove your stored key. You go back on the shared bot key
  (with its quota).
- `/usage` — shows shared-key usage today and your-key usage today separately.
- `/about` — confirms which key is currently billing you.

If Venice ever rejects your key mid-session (revoked, out of credit), the bot
auto-clears it and tells you. Set a new one with `/setkey`.

## Trust model

- **Plaintext key never touches disk in cleartext.** The `/setkey` message
  arrives over Reticulum's end-to-end encryption, gets encrypted in memory
  before SQLite insert.
- **Encryption is symmetric (Fernet, AES-128-CBC + HMAC).** The encryption
  key lives in `state/keystore.key` next to the bot's identity. An attacker
  with full root on the bot host can decrypt — the same trust boundary as
  the bot's own provider key. This protects against DB-only exfiltration,
  not against host compromise.
- **Venice still sees your prompts.** BYOK changes *who pays*, not *who
  reads*. Don't send anything you wouldn't paste into the Venice web UI.

## Owner notes

- `/owner stats` includes a `byok users` count.
- BYOK usage is tracked in a separate `byok_usage` table; the global
  `usage` totals you see in stats only reflect shared-key traffic.
- Backup `state/keystore.key` along with `state/conversations.sqlite`. Losing
  the key file invalidates every stored BYOK credential; users would need to
  re-run `/setkey`.
