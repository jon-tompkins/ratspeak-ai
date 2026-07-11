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
    byok_only: bool = False
    # LXMF address + label of the sibling bot (BYOK <-> subsidized), so /about and /help
    # can point users at the other mode instead of duplicating it here.
    peer_address: str = ""
    peer_label: str = ""


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
class OwnerConfig:
    lxmf_addr: str = ""


@dataclass
class TiersConfig:
    supabase_url: str = ""
    supabase_key: str = ""
    # Min Ratspeak Badges tier required to use the shared (bot-billed) key.
    shared_min_tier: str = "gold"
    # Min tier required to register a personal key via /setkey.
    byok_min_tier: str = "bronze"
    # Where unregistered peers are told to go to register a wallet.
    badges_url: str = "https://ratspeak-badges.vercel.app/register"


@dataclass
class Config:
    bot: BotConfig = field(default_factory=BotConfig)
    venice: VeniceConfig = field(default_factory=VeniceConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    ratelimit: RateLimitConfig = field(default_factory=RateLimitConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    owner: OwnerConfig = field(default_factory=OwnerConfig)
    tiers: TiersConfig = field(default_factory=TiersConfig)


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
        owner=OwnerConfig(**raw.get("owner", {})),
        tiers=TiersConfig(**raw.get("tiers", {})),
    )

    api_key = os.environ.get("VENICE_API_KEY", "").strip()
    if api_key:
        cfg.venice.api_key = api_key

    owner_addr = os.environ.get("OWNER_LXMF_ADDR", "").strip().lower()
    if owner_addr:
        cfg.owner.lxmf_addr = owner_addr

    supabase_url = os.environ.get("SUPABASE_URL", "").strip()
    if supabase_url:
        cfg.tiers.supabase_url = supabase_url

    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if supabase_key:
        cfg.tiers.supabase_key = supabase_key

    return cfg
