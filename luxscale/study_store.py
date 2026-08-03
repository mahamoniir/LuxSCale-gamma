"""
luxscale/study_store.py — persistent storage for calculated study payloads.

WHY THIS EXISTS
----------------
Studies were saved as flat JSON files under api/data/studies/<token>.json.
On Railway (Procfile / Nixpacks deployment, no Dockerfile + no attached
Volume), the container filesystem is EPHEMERAL: every restart, redeploy, or
crash-restart wipes it. If more than one replica is ever run, a token saved
by one instance may not exist on the instance that later reads it. Either
case produces exactly the error you're seeing:

    404 Not Found: Study not found: <token>

THE FIX
-------
Store studies in Postgres (Railway's managed Postgres add-on, reachable via
the DATABASE_URL env var it auto-injects) so records survive restarts,
redeploys, and are visible to every replica. Falls back to the old
local-file behavior ONLY when DATABASE_URL is not set — so local dev without
a database still works unchanged.

DROP-IN USAGE (replaces the old file read/write blocks in app.py):
    from luxscale.study_store import save_study, load_study, storage_backend

    token   = save_study(payload_dict)      # -> hex token string (32 chars)
    payload = load_study(token)             # -> dict | None
    storage_backend()                       # -> "postgres" | "local-file (ephemeral)"

SETUP ON RAILWAY (one-time)
----------------------------
1. In your Railway project: New -> Database -> Add PostgreSQL.
2. Railway auto-injects DATABASE_URL into any service in the same project
   that you link it to (or it's shared project-wide, depending on your
   Railway setup — check the Variables tab of your web service to confirm
   DATABASE_URL is present).
3. Add `psycopg2-binary` to requirements.txt and redeploy.
4. No manual migration needed — the table is created automatically on first
   use (see _ensure_schema below).
"""

from __future__ import annotations

import json
import os
import secrets
import time
from pathlib import Path
from typing import Optional

_DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

# Some providers hand out "postgres://" — psycopg2 accepts it, but normalize
# to "postgresql://" since some tooling (SQLAlchemy etc.) insists on it.
if _DATABASE_URL.startswith("postgres://"):
    _DATABASE_URL = _DATABASE_URL.replace("postgres://", "postgresql://", 1)

_ROOT_DIR = Path(__file__).resolve().parent
_FILE_STUDIES_DIR = _ROOT_DIR / "api" / "data" / "studies"

_pool = None  # lazy psycopg2 SimpleConnectionPool, created on first DB use


def _using_db() -> bool:
    return bool(_DATABASE_URL)


def _get_pool():
    global _pool
    if _pool is None:
        import psycopg2
        from psycopg2.pool import SimpleConnectionPool

        _pool = SimpleConnectionPool(1, 5, _DATABASE_URL)
        _ensure_schema()
    return _pool


def _ensure_schema() -> None:
    conn = _pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS studies (
                    token    TEXT PRIMARY KEY,
                    payload  JSONB NOT NULL,
                    saved_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
    finally:
        _pool.putconn(conn)


# ── Postgres-backed implementation ──────────────────────────────────────────
def _db_save(token: str, payload: dict) -> None:
    pool = _get_pool()
    conn = pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO studies (token, payload) VALUES (%s, %s)
                ON CONFLICT (token) DO UPDATE SET payload = EXCLUDED.payload
                """,
                (token, json.dumps(payload)),
            )
    finally:
        pool.putconn(conn)


def _db_load(token: str) -> Optional[dict]:
    pool = _get_pool()
    conn = pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT payload FROM studies WHERE token = %s", (token,))
            row = cur.fetchone()
            return row[0] if row else None
    finally:
        pool.putconn(conn)


# ── Local-file fallback (dev only — identical to the old behavior) ─────────
def _file_save(token: str, payload: dict) -> None:
    _FILE_STUDIES_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "token": token,
        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "payload": payload,
    }
    path = _FILE_STUDIES_DIR / f"{token}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False)


def _file_load(token: str) -> Optional[dict]:
    path = _FILE_STUDIES_DIR / f"{token}.json"
    if not path.is_file():
        return None
    with open(path, encoding="utf-8") as f:
        record = json.load(f)
    return record.get("payload", record)


# ── Public API ───────────────────────────────────────────────────────────────
def save_study(payload: dict, token: Optional[str] = None) -> str:
    """Persist a study payload and return its token (creates one if not given)."""
    token = token or secrets.token_hex(16)
    if _using_db():
        _db_save(token, payload)
    else:
        _file_save(token, payload)
    return token


def load_study(token: str) -> Optional[dict]:
    """Return the study payload for a token, or None if it doesn't exist."""
    if _using_db():
        return _db_load(token)
    return _file_load(token)


def storage_backend() -> str:
    """Diagnostics: which backend is currently active."""
    return "postgres" if _using_db() else "local-file (ephemeral — unsafe on Railway)"
