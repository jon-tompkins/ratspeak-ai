from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS peers (
    peer_hash    TEXT PRIMARY KEY,
    display_name TEXT,
    model        TEXT,
    created_at   INTEGER NOT NULL,
    updated_at   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS turns (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    peer_hash  TEXT NOT NULL,
    role       TEXT NOT NULL,
    content    TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS turns_peer_idx ON turns (peer_hash, id);

CREATE TABLE IF NOT EXISTS usage (
    peer_hash TEXT NOT NULL,
    day       TEXT NOT NULL,
    tokens    INTEGER NOT NULL DEFAULT 0,
    messages  INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (peer_hash, day)
);

CREATE TABLE IF NOT EXISTS bans (
    peer_hash  TEXT PRIMARY KEY,
    reason     TEXT,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS peer_quotas (
    peer_hash TEXT PRIMARY KEY,
    tokens    INTEGER NOT NULL
);
"""


class Memory:
    def __init__(self, db_path: str, history_turns: int):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, isolation_level=None, check_same_thread=False)
        self._conn.executescript(SCHEMA)
        self._history_turns = history_turns

    # ---- peers ----
    def touch_peer(self, peer_hash: str, display_name: str | None) -> None:
        now = int(time.time())
        self._conn.execute(
            """
            INSERT INTO peers (peer_hash, display_name, model, created_at, updated_at)
            VALUES (?, ?, NULL, ?, ?)
            ON CONFLICT(peer_hash) DO UPDATE SET
                display_name = COALESCE(excluded.display_name, peers.display_name),
                updated_at   = excluded.updated_at
            """,
            (peer_hash, display_name, now, now),
        )

    def get_model(self, peer_hash: str) -> str | None:
        row = self._conn.execute(
            "SELECT model FROM peers WHERE peer_hash = ?", (peer_hash,)
        ).fetchone()
        return row[0] if row else None

    def set_model(self, peer_hash: str, model: str) -> None:
        self._conn.execute(
            "UPDATE peers SET model = ?, updated_at = ? WHERE peer_hash = ?",
            (model, int(time.time()), peer_hash),
        )

    # ---- turns ----
    def append_turn(self, peer_hash: str, role: str, content: str) -> None:
        if self._history_turns <= 0:
            return
        self._conn.execute(
            "INSERT INTO turns (peer_hash, role, content, created_at) VALUES (?, ?, ?, ?)",
            (peer_hash, role, content, int(time.time())),
        )

    def recent_turns(self, peer_hash: str) -> list[dict[str, str]]:
        if self._history_turns <= 0:
            return []
        # A "turn" is one user + one assistant message, so fetch 2x rows.
        rows = self._conn.execute(
            """
            SELECT role, content FROM turns
            WHERE peer_hash = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (peer_hash, self._history_turns * 2),
        ).fetchall()
        return [{"role": role, "content": content} for role, content in reversed(rows)]

    def reset(self, peer_hash: str) -> int:
        cur = self._conn.execute("DELETE FROM turns WHERE peer_hash = ?", (peer_hash,))
        return cur.rowcount

    # ---- usage ----
    def add_usage(self, peer_hash: str, tokens: int) -> None:
        day = time.strftime("%Y-%m-%d", time.gmtime())
        self._conn.execute(
            """
            INSERT INTO usage (peer_hash, day, tokens, messages)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(peer_hash, day) DO UPDATE SET
                tokens   = usage.tokens + excluded.tokens,
                messages = usage.messages + 1
            """,
            (peer_hash, day, tokens),
        )

    def usage_today(self, peer_hash: str) -> tuple[int, int]:
        day = time.strftime("%Y-%m-%d", time.gmtime())
        row = self._conn.execute(
            "SELECT tokens, messages FROM usage WHERE peer_hash = ? AND day = ?",
            (peer_hash, day),
        ).fetchone()
        if not row:
            return 0, 0
        return int(row[0]), int(row[1])

    # ---- owner-facing ----
    def global_usage_today(self) -> tuple[int, int, int]:
        day = time.strftime("%Y-%m-%d", time.gmtime())
        row = self._conn.execute(
            "SELECT COALESCE(SUM(tokens),0), COALESCE(SUM(messages),0), COUNT(DISTINCT peer_hash) "
            "FROM usage WHERE day = ?",
            (day,),
        ).fetchone()
        return int(row[0]), int(row[1]), int(row[2])

    def peer_summaries(self, limit: int = 20) -> list[tuple[str, str | None, int, int, int]]:
        day = time.strftime("%Y-%m-%d", time.gmtime())
        rows = self._conn.execute(
            """
            SELECT p.peer_hash, p.display_name, p.updated_at,
                   COALESCE(u.tokens, 0), COALESCE(u.messages, 0)
            FROM peers p
            LEFT JOIN usage u ON u.peer_hash = p.peer_hash AND u.day = ?
            ORDER BY p.updated_at DESC
            LIMIT ?
            """,
            (day, limit),
        ).fetchall()
        return [(r[0], r[1], int(r[2]), int(r[3]), int(r[4])) for r in rows]

    def set_banned(self, peer_hash: str, reason: str | None) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO bans (peer_hash, reason, created_at) VALUES (?, ?, ?)",
            (peer_hash, reason, int(time.time())),
        )

    def unban(self, peer_hash: str) -> int:
        cur = self._conn.execute("DELETE FROM bans WHERE peer_hash = ?", (peer_hash,))
        return cur.rowcount

    def is_banned(self, peer_hash: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM bans WHERE peer_hash = ? LIMIT 1", (peer_hash,)
        ).fetchone()
        return row is not None

    def list_bans(self) -> list[tuple[str, str | None]]:
        return [
            (r[0], r[1])
            for r in self._conn.execute(
                "SELECT peer_hash, reason FROM bans ORDER BY created_at DESC"
            ).fetchall()
        ]

    def get_setting(self, key: str) -> str | None:
        row = self._conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return row[0] if row else None

    def set_setting(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value)
        )

    def set_peer_quota(self, peer_hash: str, tokens: int) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO peer_quotas (peer_hash, tokens) VALUES (?, ?)",
            (peer_hash, tokens),
        )

    def get_peer_quota(self, peer_hash: str) -> int | None:
        row = self._conn.execute(
            "SELECT tokens FROM peer_quotas WHERE peer_hash = ?", (peer_hash,)
        ).fetchone()
        return int(row[0]) if row else None
