"""Per-peer API key encryption.

Stored keys are encrypted with a Fernet symmetric key that lives on disk next
to the bot's identity (mode 0600). Threat model: protects against casual DB
exfiltration; an attacker with full filesystem access on the bot host can
decrypt — which is the same trust boundary as the bot's own provider key.
"""
from __future__ import annotations

import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


class Keystore:
    def __init__(self, key_path: str | os.PathLike[str]):
        p = Path(key_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.is_file():
            data = p.read_bytes().strip()
        else:
            data = Fernet.generate_key()
            p.write_bytes(data)
            try:
                os.chmod(p, 0o600)
            except OSError:
                pass
        self._fernet = Fernet(data)

    def encrypt(self, plaintext: str) -> bytes:
        return self._fernet.encrypt(plaintext.encode("utf-8"))

    def decrypt(self, token: bytes) -> str | None:
        try:
            return self._fernet.decrypt(token).decode("utf-8")
        except (InvalidToken, ValueError):
            return None
