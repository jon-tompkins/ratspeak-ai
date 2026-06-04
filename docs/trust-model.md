# Trust model

This bot is a **gateway**. That word matters.

## What's protected

- **User → bot, on the mesh.** LXMF messages between a peer and this bot are encrypted end-to-end with Reticulum identity keys. Nobody on the mesh (transit nodes, propagation nodes, anyone snooping a radio link) sees the plaintext of your prompt or the reply.
- **Forward secrecy on the link leg.** When delivery uses `DIRECT` (the default), each session establishes a fresh ephemeral link key. Past traffic stays private if a long-term key later leaks.
- **Identity decoupling.** A peer's LXMF address is a hash of an identity key, not a phone number or email. The bot never sees a real-world identifier unless the user types one into a prompt.

## What's NOT protected

- **Bot → model provider.** The bot decrypts your prompt to send it to Venice (or whichever provider). That hop is TLS to a clearnet API. The provider sees your prompt and reply in cleartext.
- **The operator of the bot.** Whoever runs the bot can read the plaintext of every conversation that passes through it. Same trust posture as any matrix bridge, Telegram bot, or email relay.
- **Side-channel metadata.** The mesh sees that "peer X is exchanging messages with destination Y at this time." That fact is unavoidable on any addressed network.

## Reasonable inferences

- Don't send anything you wouldn't want the bot operator and the model provider to read.
- Treat conversation history (`/reset`, the SQLite store) as locally controlled but not zero-knowledge — the bot operator can read it.
- If you self-host the bot and BYO Venice key, your trust surface is just Venice + your own ops.

## How to harden further

- **Run your own bot.** The whole point of the architecture is that anyone can spin one up. The default community bot is convenient; a self-hosted bot is private to you.
- **BYO key.** Don't share an inference key with strangers; rate-limit and quota per peer.
- **Local inference, eventually.** The long-term plan (parked for now) is small models running directly on Reticulum nodes — Pi-class hardware with `llama.cpp`. That collapses the trust surface to "the operator of the node you're talking to" with no clearnet hop.
