"""Ratspeak Badges tier lookups, shared across shared-key and BYOK modes.

Mirrors the tier ranking in ratspeak-tools/lib/tiers.ts, alert_gateway/commands.py,
and propagation/propagation_node.py — keep in sync if a tier is added/removed there.
"""
from __future__ import annotations

import json
import logging
import urllib.request

log = logging.getLogger(__name__)

TIER_RANK = {"bronze": 1, "silver": 2, "gold": 3, "diamond": 4}


def registration_tier(peer_hash: str, supabase_url: str, supabase_key: str) -> str | None:
    """Return the holder's badge tier if registered with a real tier, else None."""
    if not supabase_url or not supabase_key:
        log.warning("tier lookup skipped: Supabase creds not configured")
        return None
    addr = peer_hash.lower()
    url = (
        f"{supabase_url.rstrip('/')}/rest/v1/rs_registrations"
        f"?select=tier&ratspeak_address=eq.{addr}&tier=neq.none"
    )
    try:
        req = urllib.request.Request(
            url,
            headers={"apikey": supabase_key, "Authorization": f"Bearer {supabase_key}"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            rows = json.loads(resp.read())
        if rows:
            return rows[0].get("tier")
    except Exception:
        log.exception("registration lookup failed for %s", addr)
    return None


def meets_min_tier(tier: str | None, min_tier: str) -> bool:
    """True if `tier` is registered and ranks at or above `min_tier`."""
    if tier is None:
        return False
    return TIER_RANK.get(tier, 0) >= TIER_RANK.get(min_tier, 0)
