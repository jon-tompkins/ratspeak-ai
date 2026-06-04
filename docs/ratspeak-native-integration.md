# Ratspeak-native AI integration (Option 2)

This is the design + code stubs for integrating AI directly into the Ratspeak Tauri client, so a user doesn't have to know the bot's LXMF hash to use it. The bot from this repo is still the substrate — this is the UX layer over it.

The shape is deliberately minimal so it can land as a single PR against `ratspeak/Ratspeak` without rewriting the messaging core.

## UX shape

- A new pseudo-contact `"AI"` (system avatar) pinned to the top of the contact list.
- Opening the AI contact looks like any other 1:1 chat. Same message bubbles, same send box.
- Settings → AI panel:
  - **Mode**: `Community gateway` (default) | `BYO key` | `Custom destination`
  - **Community gateway**: hardcoded LXMF destination hash of the public ratspeak-ai bot (set at build time, swappable from settings). Free, rate-limited, subsidized.
  - **BYO key**: user runs their own `ratspeak-ai-bot` locally (or anywhere), pastes its destination hash + an opaque shared secret used to authenticate `/admin` commands. No quota.
  - **Custom destination**: any LXMF hash. For users pointing at someone else's bot.
- **Slash commands** (`/help`, `/model`, `/reset`, etc.) work as plain text — the bot already handles them. No new UI needed for v0.

## Wire format

Zero new framing. The AI conversation is plain LXMF messages between the client identity and the chosen bot destination. This means:

- Existing message history, search, attachment handling all work for free.
- The AI pseudo-contact is just a contact with a known destination hash and a "system" flag for UI rendering.
- No protocol-level changes to rsLXMF or rsReticulum required.

## Client changes

### 1. `src-tauri/src/ai.rs` — new module

Holds the configured bot destination(s), the active mode, and any per-mode secrets. Persists via Tauri's existing settings store (whatever Ratspeak already uses — looks like `tauri_plugin_store`).

```rust
// src-tauri/src/ai.rs

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "mode", rename_all = "snake_case")]
pub enum AiMode {
    CommunityGateway,
    ByoKey { destination_hex: String },
    Custom { destination_hex: String, label: String },
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AiSettings {
    pub mode: AiMode,
    /// Hex (32 chars). Compiled-in fallback for the community gateway.
    pub community_destination_hex: String,
}

impl Default for AiSettings {
    fn default() -> Self {
        Self {
            mode: AiMode::CommunityGateway,
            community_destination_hex: env!("RATSPEAK_AI_COMMUNITY_DEST").to_string(),
        }
    }
}

impl AiSettings {
    pub fn active_destination(&self) -> &str {
        match &self.mode {
            AiMode::CommunityGateway => &self.community_destination_hex,
            AiMode::ByoKey { destination_hex } => destination_hex,
            AiMode::Custom { destination_hex, .. } => destination_hex,
        }
    }
}
```

### 2. Tauri commands

```rust
// src-tauri/src/commands/ai.rs

use tauri::State;
use crate::ai::{AiMode, AiSettings};
use crate::messaging::MessagingHandle; // existing Ratspeak handle

#[tauri::command]
pub fn ai_settings_get(state: State<'_, AiState>) -> AiSettings {
    state.read().clone()
}

#[tauri::command]
pub fn ai_settings_set(
    state: State<'_, AiState>,
    settings: AiSettings,
) -> Result<(), String> {
    state.write(settings).map_err(|e| e.to_string())
}

/// Send a prompt to whichever destination is configured.
/// Returns the LXMF message id; UI tracks delivery via existing message-state events.
#[tauri::command]
pub async fn ai_send(
    state: State<'_, AiState>,
    messaging: State<'_, MessagingHandle>,
    text: String,
) -> Result<String, String> {
    let settings = state.read();
    let dest_hex = settings.active_destination();
    messaging
        .send_lxmf(dest_hex, &text, /*title=*/ "AI")
        .await
        .map_err(|e| e.to_string())
}
```

### 3. Frontend

A single Svelte/React component (matching whatever Ratspeak's dashboard uses) for the AI pane. Bind `ai_send` to the send box; render the conversation by filtering the existing message store for the active AI destination.

### 4. Discovery

For the **community gateway**, ship the destination hash compiled in via `RATSPEAK_AI_COMMUNITY_DEST`. To allow rotation without a client release, also poll a signed manifest hosted at a stable URL (`https://ratspeak.io/ai-bot.json`?) at startup and prefer that if the signature checks out.

```json
{
  "destination_hex": "ab12...",
  "display_name": "ratspeak-ai",
  "stamp_cost": 8,
  "signed_at": "2026-06-04T05:00:00Z",
  "signature": "..."
}
```

Signed by a key whose public counterpart ships with the client. Same shape as `rsReticulum`'s announce verification — should be a thin reuse.

## Subsidization knobs (for the community gateway)

Free-tier sustainability is mostly a server-side problem the bot already handles:

- `daily_token_quota` per peer (`ratelimit` config, see `config.example.toml`)
- `allowed_models` keeps people off frontier models on the community key
- `messages_per_window` blunts abuse
- The bot operator (initially Jonto / Ratspeak team) sets a hard monthly Venice budget upstream

Once usage clears whatever soft ceiling we pick, options are:
1. Open a tip jar (the bot can reply to `/tip` with payment info; tips are local, no on-chain identity)
2. Rotate to a slower / cheaper default model and bump quotas back up
3. Push BYO-key mode harder — the bot's setup is one-shot anyway

## Open questions for the Ratspeak founder

1. **Settings store.** Does Ratspeak use `tauri-plugin-store` or roll its own? If custom, the persistence shim in `ai.rs` needs to use that.
2. **Send API.** What's the existing Tauri command for sending an LXMF message from the JS side? `ai_send` should delegate to it, not reinvent.
3. **Pseudo-contact rendering.** Is the contact list driven by the LXMF address book, or by a higher-level "conversations" abstraction? Adding the AI entry needs to hook the right one.
4. **Community gateway hosting.** Who runs the default bot? We'd want a non-residential host with a stable Reticulum interface (TCP + RNS public node listed) and enough budget for the Venice tier.

Once those are answered we can land this in 2–3 days of focused work.
