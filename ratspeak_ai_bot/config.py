from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


@dataclass
class BotConfig:
    display_name: str = "ratspeak-ai"
    storage_dir: str = "./state"
    announce_interval: int = 21600
    stamp_cost: int = 8
    reticulum_configdir: str = ""


@dataclass
class VeniceConfig:
    base_url: str = "https://api.venice.ai/api/v1"
    api_key: str = ""
    default_model: str = "venice-uncensored"
    allowed_models: list[str] = field(default_factory=lambda: ["venice-uncensored"])
    max_tokens: int = 800
    temperature: float = 0.7
    system_prompt: str = "You are a helpful AI assistant reached over Reticulum/LXMF. Be concise."


@dataclass
class MemoryConfig:
    history_turns: int = 8
    db_path: str = "./state/conversations.sqlite"


@dataclass
class RateLimitConfig:
    messages_per_window: int = 20
    window_seconds: int = 3600
    daily_token_quota: int = 50000


@dataclass
class LoggingConfig:
    level: str = "info"


@dataclass
class Config:
    bot: BotConfig = field(default_factory=BotConfig)
    venice: VeniceConfig = field(default_factory=VeniceConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    ratelimit: RateLimitConfig = field(default_factory=RateLimitConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


def load(path: str | os.PathLike[str]) -> Config:
    raw: dict = {}
    p = Path(path)
    if p.is_file():
        with p.open("rb") as fh:
            raw = tomllib.load(fh)

    cfg = Config(
        bot=BotConfig(**raw.get("bot", {})),
        venice=VeniceConfig(**raw.get("venice", {})),
        memory=MemoryConfig(**raw.get("memory", {})),
        ratelimit=RateLimitConfig(**raw.get("ratelimit", {})),
        logging=LoggingConfig(**raw.get("logging", {})),
    )

    api_key = os.environ.get("VENICE_API_KEY", "").strip()
    if api_key:
        cfg.venice.api_key = api_key

    return cfg
