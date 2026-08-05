from __future__ import annotations

import json
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import LibraryItem, LibraryItemCreate


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=10, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _initialize(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS cache (
                    cache_key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL,
                    expires_at INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS library_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL,
                    external_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    UNIQUE(kind, external_id)
                );
                CREATE INDEX IF NOT EXISTS idx_library_kind ON library_items(kind);
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL UNIQUE,
                    role TEXT NOT NULL DEFAULT 'user',
                    created_at TEXT NOT NULL,
                    trial_ends_at TEXT,
                    stripe_customer_id TEXT,
                    stripe_subscription_id TEXT,
                    subscription_status TEXT NOT NULL DEFAULT 'none',
                    subscription_expires_at TEXT,
                    last_login_at TEXT
                );
                CREATE TABLE IF NOT EXISTS auth_codes (
                    email TEXT PRIMARY KEY,
                    code_hash TEXT NOT NULL,
                    expires_at INTEGER NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS complimentary_grants (
                    email TEXT PRIMARY KEY,
                    expires_at TEXT,
                    reason TEXT NOT NULL DEFAULT '',
                    granted_by INTEGER,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS usage_daily (
                    user_id INTEGER NOT NULL,
                    feature TEXT NOT NULL,
                    day TEXT NOT NULL,
                    quantity INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(user_id, feature, day)
                );
                CREATE TABLE IF NOT EXISTS processed_webhooks (
                    event_id TEXT PRIMARY KEY,
                    processed_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner_id INTEGER NOT NULL DEFAULT 0,
                    name TEXT NOT NULL,
                    research_question TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_projects_owner
                    ON projects(owner_id, status, updated_at);
                CREATE TABLE IF NOT EXISTS search_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner_id INTEGER NOT NULL DEFAULT 0,
                    project_id INTEGER,
                    request_json TEXT NOT NULL,
                    result_count INTEGER NOT NULL,
                    source_status_json TEXT NOT NULL,
                    cache_hit INTEGER NOT NULL DEFAULT 0,
                    elapsed_ms INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL
                );
                CREATE INDEX IF NOT EXISTS idx_search_runs_owner
                    ON search_runs(owner_id, project_id, created_at);
                CREATE TABLE IF NOT EXISTS policy_candidates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id TEXT NOT NULL,
                    external_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    issuer TEXT NOT NULL,
                    published_at TEXT NOT NULL DEFAULT '',
                    url TEXT NOT NULL,
                    summary TEXT NOT NULL DEFAULT '',
                    signals_json TEXT NOT NULL DEFAULT '[]',
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    content_hash TEXT NOT NULL,
                    raw_json TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'pending',
                    discovered_at TEXT NOT NULL,
                    reviewed_at TEXT,
                    reviewed_by INTEGER,
                    UNIQUE(source_id, external_id)
                );
                CREATE INDEX IF NOT EXISTS idx_policy_candidates_status
                    ON policy_candidates(status, discovered_at);
                CREATE TABLE IF NOT EXISTS policy_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    candidate_id INTEGER NOT NULL,
                    content_hash TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    discovered_at TEXT NOT NULL,
                    UNIQUE(candidate_id, content_hash),
                    FOREIGN KEY(candidate_id) REFERENCES policy_candidates(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS policy_sync_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    discovered INTEGER NOT NULL DEFAULT 0,
                    changed INTEGER NOT NULL DEFAULT 0,
                    error TEXT NOT NULL DEFAULT '',
                    started_at TEXT NOT NULL,
                    completed_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_policy_sync_source
                    ON policy_sync_runs(source_id, completed_at);
                CREATE TABLE IF NOT EXISTS llm_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner_id INTEGER NOT NULL DEFAULT 0,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    task TEXT NOT NULL,
                    input_tokens INTEGER NOT NULL DEFAULT 0,
                    output_tokens INTEGER NOT NULL DEFAULT 0,
                    cache_hit_tokens INTEGER NOT NULL DEFAULT 0,
                    cache_miss_tokens INTEGER NOT NULL DEFAULT 0,
                    reasoning_tokens INTEGER NOT NULL DEFAULT 0,
                    latency_ms INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_llm_runs_owner
                    ON llm_runs(owner_id, created_at);
                CREATE TABLE IF NOT EXISTS provider_credentials (
                    owner_id INTEGER NOT NULL DEFAULT 0,
                    provider_id TEXT NOT NULL,
                    encrypted_api_key TEXT NOT NULL,
                    key_hint TEXT NOT NULL DEFAULT '',
                    base_url TEXT NOT NULL,
                    fast_model TEXT NOT NULL,
                    quality_model TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    priority INTEGER NOT NULL DEFAULT 100,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(owner_id, provider_id)
                );
                CREATE INDEX IF NOT EXISTS idx_provider_credentials_owner
                    ON provider_credentials(owner_id, enabled, priority);
                CREATE TABLE IF NOT EXISTS model_routing (
                    owner_id INTEGER PRIMARY KEY,
                    mode TEXT NOT NULL DEFAULT 'balanced',
                    primary_provider TEXT NOT NULL DEFAULT '',
                    fallback_enabled INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT NOT NULL
                );
                """
            )
            columns = {row[1] for row in conn.execute("PRAGMA table_info(library_items)")}
            if "owner_id" not in columns:
                conn.executescript(
                    """
                    ALTER TABLE library_items RENAME TO library_items_legacy;
                    CREATE TABLE library_items (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        owner_id INTEGER NOT NULL DEFAULT 0,
                        kind TEXT NOT NULL,
                        external_id TEXT NOT NULL,
                        title TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        note TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL,
                        UNIQUE(owner_id, kind, external_id)
                    );
                    INSERT INTO library_items(id,owner_id,kind,external_id,title,payload_json,note,created_at)
                    SELECT id,0,kind,external_id,title,payload_json,note,created_at
                    FROM library_items_legacy;
                    DROP TABLE library_items_legacy;
                    CREATE INDEX idx_library_kind ON library_items(owner_id,kind);
                    """
                )
            columns = {row[1] for row in conn.execute("PRAGMA table_info(library_items)")}
            if "project_id" not in columns:
                conn.execute("ALTER TABLE library_items ADD COLUMN project_id INTEGER")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_library_project "
                "ON library_items(owner_id, project_id, kind)"
            )

    def get_cache(self, key: str) -> Optional[Dict[str, Any]]:
        now = int(time.time())
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT value_json FROM cache WHERE cache_key=? AND expires_at>?", (key, now)
            ).fetchone()
            if row is None:
                conn.execute("DELETE FROM cache WHERE cache_key=?", (key,))
                return None
            return json.loads(row["value_json"])

    def set_cache(self, key: str, value: Dict[str, Any], ttl_seconds: int) -> None:
        now = datetime.now(timezone.utc).isoformat()
        expires_at = int(time.time()) + ttl_seconds
        payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO cache(cache_key,value_json,expires_at,created_at)
                VALUES(?,?,?,?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    value_json=excluded.value_json,
                    expires_at=excluded.expires_at,
                    created_at=excluded.created_at
                """,
                (key, payload, expires_at, now),
            )

    def add_library_item(self, item: LibraryItemCreate, owner_id: int = 0) -> LibraryItem:
        created_at = datetime.now(timezone.utc).isoformat()
        payload = json.dumps(item.payload, ensure_ascii=False)
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO library_items(
                    owner_id,kind,external_id,title,payload_json,note,created_at,project_id
                )
                VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(owner_id,kind,external_id) DO UPDATE SET
                    title=excluded.title,payload_json=excluded.payload_json,note=excluded.note,
                    project_id=excluded.project_id
                """,
                (
                    owner_id,
                    item.kind,
                    item.external_id,
                    item.title,
                    payload,
                    item.note,
                    created_at,
                    item.project_id,
                ),
            )
            row = conn.execute(
                "SELECT * FROM library_items WHERE owner_id=? AND kind=? AND external_id=?",
                (owner_id, item.kind, item.external_id),
            ).fetchone()
            if item.project_id:
                conn.execute(
                    "UPDATE projects SET updated_at=? WHERE id=? AND owner_id=?",
                    (created_at, item.project_id, owner_id),
                )
        return self._row_to_library(row)

    def list_library_items(
        self,
        kind: Optional[str] = None,
        owner_id: int = 0,
        project_id: Optional[int] = None,
    ) -> List[LibraryItem]:
        sql = "SELECT * FROM library_items WHERE owner_id=?"
        args: List[Any] = [owner_id]
        if kind:
            sql += " AND kind=?"
            args.append(kind)
        if project_id is not None:
            sql += " AND project_id=?"
            args.append(project_id)
        sql += " ORDER BY created_at DESC, id DESC"
        with self._lock, self._connect() as conn:
            rows = conn.execute(sql, tuple(args)).fetchall()
        return [self._row_to_library(row) for row in rows]

    def update_library_note(self, item_id: int, owner_id: int, note: str) -> bool:
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                "UPDATE library_items SET note=? WHERE id=? AND owner_id=?",
                (note, item_id, owner_id),
            )
            return cursor.rowcount > 0

    def delete_library_item(self, item_id: int, owner_id: int = 0) -> bool:
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM library_items WHERE id=? AND owner_id=?", (item_id, owner_id)
            )
            return cursor.rowcount > 0

    def count_library_items(self, owner_id: int) -> int:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS total FROM library_items WHERE owner_id=?", (owner_id,)
            ).fetchone()
        return int(row["total"])

    def get_or_create_user(self, email: str, trial_days: int, is_admin: bool = False) -> dict:
        now = datetime.now(timezone.utc)
        trial_end = (now + timedelta(days=max(0, trial_days))).isoformat()
        role = "admin" if is_admin else "user"
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO users(email,role,created_at,trial_ends_at,last_login_at)
                VALUES(?,?,?,?,?)
                ON CONFLICT(email) DO UPDATE SET
                    role=CASE WHEN excluded.role='admin' THEN 'admin' ELSE users.role END,
                    last_login_at=excluded.last_login_at
                """,
                (email, role, now.isoformat(), trial_end, now.isoformat()),
            )
            row = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        return dict(row)

    def get_user_by_id(self, user_id: int) -> Optional[dict]:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        return dict(row) if row else None

    def get_user_by_email(self, email: str) -> Optional[dict]:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        return dict(row) if row else None

    def save_auth_code(self, email: str, code_hash: str, expires_at: int) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO auth_codes(email,code_hash,expires_at,attempts,created_at)
                VALUES(?,?,?,0,?)
                ON CONFLICT(email) DO UPDATE SET code_hash=excluded.code_hash,
                    expires_at=excluded.expires_at,attempts=0,created_at=excluded.created_at
                """,
                (email, code_hash, expires_at, now),
            )

    def get_auth_code(self, email: str) -> Optional[dict]:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM auth_codes WHERE email=?", (email,)).fetchone()
        return dict(row) if row else None

    def fail_auth_code(self, email: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("UPDATE auth_codes SET attempts=attempts+1 WHERE email=?", (email,))

    def consume_auth_code(self, email: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM auth_codes WHERE email=?", (email,))

    def upsert_grant(
        self, email: str, expires_at: Optional[str], reason: str, granted_by: int
    ) -> dict:
        created_at = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO complimentary_grants(email,expires_at,reason,granted_by,created_at)
                VALUES(?,?,?,?,?)
                ON CONFLICT(email) DO UPDATE SET expires_at=excluded.expires_at,
                    reason=excluded.reason,granted_by=excluded.granted_by,
                    created_at=excluded.created_at
                """,
                (email, expires_at, reason, granted_by, created_at),
            )
            row = conn.execute(
                "SELECT * FROM complimentary_grants WHERE email=?", (email,)
            ).fetchone()
        return dict(row)

    def list_grants(self) -> List[dict]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM complimentary_grants ORDER BY created_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def get_grant(self, email: str) -> Optional[dict]:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM complimentary_grants WHERE email=?", (email,)
            ).fetchone()
        return dict(row) if row else None

    def delete_grant(self, email: str) -> bool:
        with self._lock, self._connect() as conn:
            cursor = conn.execute("DELETE FROM complimentary_grants WHERE email=?", (email,))
        return cursor.rowcount > 0

    def create_project(
        self,
        owner_id: int,
        name: str,
        research_question: str = "",
        description: str = "",
    ) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO projects(
                    owner_id,name,research_question,description,status,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?)
                """,
                (owner_id, name, research_question, description, "active", now, now),
            )
            row = conn.execute("SELECT * FROM projects WHERE id=?", (cursor.lastrowid,)).fetchone()
        return self._project_with_counts(dict(row), owner_id)

    def list_projects(self, owner_id: int, include_archived: bool = False) -> List[dict]:
        sql = "SELECT * FROM projects WHERE owner_id=?"
        args: tuple = (owner_id,)
        if not include_archived:
            sql += " AND status!='archived'"
        sql += " ORDER BY updated_at DESC,id DESC"
        with self._lock, self._connect() as conn:
            rows = conn.execute(sql, args).fetchall()
        return [self._project_with_counts(dict(row), owner_id) for row in rows]

    def get_project(self, project_id: int, owner_id: int) -> Optional[dict]:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM projects WHERE id=? AND owner_id=?", (project_id, owner_id)
            ).fetchone()
        return self._project_with_counts(dict(row), owner_id) if row else None

    def update_project(self, project_id: int, owner_id: int, changes: Dict[str, Any]) -> Optional[dict]:
        allowed = {"name", "research_question", "description", "status"}
        clean = {key: value for key, value in changes.items() if key in allowed and value is not None}
        if clean:
            clean["updated_at"] = datetime.now(timezone.utc).isoformat()
            assignments = ",".join(f"{key}=?" for key in clean)
            with self._lock, self._connect() as conn:
                conn.execute(
                    f"UPDATE projects SET {assignments} WHERE id=? AND owner_id=?",
                    (*clean.values(), project_id, owner_id),
                )
        return self.get_project(project_id, owner_id)

    def delete_project(self, project_id: int, owner_id: int) -> bool:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM projects WHERE id=? AND owner_id=?", (project_id, owner_id)
            ).fetchone()
            if not row:
                return False
            conn.execute(
                "UPDATE library_items SET project_id=NULL WHERE owner_id=? AND project_id=?",
                (owner_id, project_id),
            )
            conn.execute(
                "UPDATE search_runs SET project_id=NULL WHERE owner_id=? AND project_id=?",
                (owner_id, project_id),
            )
            conn.execute("DELETE FROM projects WHERE id=? AND owner_id=?", (project_id, owner_id))
        return True

    def _project_with_counts(self, project: dict, owner_id: int) -> dict:
        with self._lock, self._connect() as conn:
            evidence = conn.execute(
                "SELECT COUNT(*) AS total FROM library_items WHERE owner_id=? AND project_id=?",
                (owner_id, project["id"]),
            ).fetchone()["total"]
            searches = conn.execute(
                "SELECT COUNT(*) AS total FROM search_runs WHERE owner_id=? AND project_id=?",
                (owner_id, project["id"]),
            ).fetchone()["total"]
        return {**project, "evidence_count": int(evidence), "search_count": int(searches)}

    def record_search(
        self,
        owner_id: int,
        request: Dict[str, Any],
        result_count: int,
        source_status: Dict[str, str],
        cache_hit: bool,
        elapsed_ms: int,
    ) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        project_id = request.get("project_id")
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO search_runs(
                    owner_id,project_id,request_json,result_count,source_status_json,
                    cache_hit,elapsed_ms,created_at
                ) VALUES(?,?,?,?,?,?,?,?)
                """,
                (
                    owner_id,
                    project_id,
                    json.dumps(request, ensure_ascii=False),
                    result_count,
                    json.dumps(source_status, ensure_ascii=False),
                    int(cache_hit),
                    elapsed_ms,
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM search_runs WHERE id=?", (cursor.lastrowid,)).fetchone()
            if project_id:
                conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (now, project_id))
        return self._row_to_search_run(row)

    def list_search_runs(
        self, owner_id: int, project_id: Optional[int] = None, limit: int = 50
    ) -> List[dict]:
        sql = "SELECT * FROM search_runs WHERE owner_id=?"
        args: List[Any] = [owner_id]
        if project_id is not None:
            sql += " AND project_id=?"
            args.append(project_id)
        sql += " ORDER BY created_at DESC,id DESC LIMIT ?"
        args.append(limit)
        with self._lock, self._connect() as conn:
            rows = conn.execute(sql, tuple(args)).fetchall()
        return [self._row_to_search_run(row) for row in rows]

    def delete_search_run(self, run_id: int, owner_id: int) -> bool:
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM search_runs WHERE id=? AND owner_id=?", (run_id, owner_id)
            )
        return cursor.rowcount > 0

    def record_llm_run(self, owner_id: int, usage: Dict[str, Any]) -> None:
        if not usage.get("provider"):
            return
        now = datetime.now(timezone.utc).isoformat()
        values = (
            owner_id,
            str(usage.get("provider", "unknown"))[:80],
            str(usage.get("model", "unknown"))[:160],
            str(usage.get("task", "general"))[:80],
            int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0),
            int(usage.get("output_tokens") or usage.get("completion_tokens") or 0),
            int(usage.get("cache_hit_tokens") or 0),
            int(usage.get("cache_miss_tokens") or 0),
            int(usage.get("reasoning_tokens") or 0),
            int(usage.get("latency_ms") or 0),
            now,
        )
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO llm_runs(
                    owner_id,provider,model,task,input_tokens,output_tokens,
                    cache_hit_tokens,cache_miss_tokens,reasoning_tokens,latency_ms,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                """,
                values,
            )

    def llm_usage_summary(self, owner_id: int, days: int = 30) -> dict:
        since = (datetime.now(timezone.utc) - timedelta(days=max(1, days))).isoformat()
        with self._lock, self._connect() as conn:
            total = conn.execute(
                """
                SELECT COUNT(*) AS calls,
                    COALESCE(SUM(input_tokens),0) AS input_tokens,
                    COALESCE(SUM(output_tokens),0) AS output_tokens,
                    COALESCE(SUM(cache_hit_tokens),0) AS cache_hit_tokens,
                    COALESCE(SUM(reasoning_tokens),0) AS reasoning_tokens,
                    COALESCE(AVG(latency_ms),0) AS average_latency_ms
                FROM llm_runs WHERE owner_id=? AND created_at>=?
                """,
                (owner_id, since),
            ).fetchone()
            recent = conn.execute(
                """
                SELECT provider,model,task,input_tokens,output_tokens,cache_hit_tokens,
                    reasoning_tokens,latency_ms,created_at
                FROM llm_runs WHERE owner_id=? AND created_at>=?
                ORDER BY created_at DESC,id DESC LIMIT 12
                """,
                (owner_id, since),
            ).fetchall()
        return {
            "days": max(1, days),
            "calls": int(total["calls"]),
            "input_tokens": int(total["input_tokens"]),
            "output_tokens": int(total["output_tokens"]),
            "cache_hit_tokens": int(total["cache_hit_tokens"]),
            "reasoning_tokens": int(total["reasoning_tokens"]),
            "average_latency_ms": int(total["average_latency_ms"]),
            "recent": [dict(row) for row in recent],
        }

    def upsert_provider_credential(
        self,
        owner_id: int,
        provider_id: str,
        encrypted_api_key: str,
        key_hint: str,
        base_url: str,
        fast_model: str,
        quality_model: str,
        enabled: bool,
        priority: int,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO provider_credentials(
                    owner_id,provider_id,encrypted_api_key,key_hint,base_url,fast_model,
                    quality_model,enabled,priority,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(owner_id,provider_id) DO UPDATE SET
                    encrypted_api_key=excluded.encrypted_api_key,
                    key_hint=excluded.key_hint,
                    base_url=excluded.base_url,
                    fast_model=excluded.fast_model,
                    quality_model=excluded.quality_model,
                    enabled=excluded.enabled,
                    priority=excluded.priority,
                    updated_at=excluded.updated_at
                """,
                (
                    owner_id,
                    provider_id,
                    encrypted_api_key,
                    key_hint,
                    base_url,
                    fast_model,
                    quality_model,
                    int(enabled),
                    max(1, min(int(priority), 999)),
                    now,
                    now,
                ),
            )

    def get_provider_credential(self, owner_id: int, provider_id: str) -> Optional[dict]:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM provider_credentials WHERE owner_id=? AND provider_id=?",
                (owner_id, provider_id),
            ).fetchone()
        return dict(row) if row else None

    def list_provider_credentials(
        self, owner_id: int, enabled_only: bool = False
    ) -> List[dict]:
        sql = "SELECT * FROM provider_credentials WHERE owner_id=?"
        args: List[Any] = [owner_id]
        if enabled_only:
            sql += " AND enabled=1"
        sql += " ORDER BY priority,provider_id"
        with self._lock, self._connect() as conn:
            rows = conn.execute(sql, tuple(args)).fetchall()
        return [dict(row) for row in rows]

    def delete_provider_credential(self, owner_id: int, provider_id: str) -> bool:
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM provider_credentials WHERE owner_id=? AND provider_id=?",
                (owner_id, provider_id),
            )
            conn.execute(
                "UPDATE model_routing SET primary_provider='',updated_at=? "
                "WHERE owner_id=? AND primary_provider=?",
                (datetime.now(timezone.utc).isoformat(), owner_id, provider_id),
            )
        return cursor.rowcount > 0

    def get_model_routing(self, owner_id: int) -> Optional[dict]:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM model_routing WHERE owner_id=?", (owner_id,)
            ).fetchone()
        if not row:
            return None
        value = dict(row)
        value["fallback_enabled"] = bool(value["fallback_enabled"])
        return value

    def upsert_model_routing(
        self, owner_id: int, mode: str, primary_provider: str, fallback_enabled: bool
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO model_routing(
                    owner_id,mode,primary_provider,fallback_enabled,updated_at
                ) VALUES(?,?,?,?,?)
                ON CONFLICT(owner_id) DO UPDATE SET
                    mode=excluded.mode,
                    primary_provider=excluded.primary_provider,
                    fallback_enabled=excluded.fallback_enabled,
                    updated_at=excluded.updated_at
                """,
                (owner_id, mode, primary_provider, int(fallback_enabled), now),
            )

    def upsert_policy_candidate(self, candidate: Dict[str, Any]) -> str:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            existing = conn.execute(
                "SELECT * FROM policy_candidates WHERE source_id=? AND external_id=?",
                (candidate["source_id"], candidate["external_id"]),
            ).fetchone()
            state = "new"
            if existing:
                if existing["content_hash"] == candidate["content_hash"]:
                    return "unchanged"
                state = "changed"
                conn.execute(
                    """
                    UPDATE policy_candidates SET title=?,issuer=?,published_at=?,url=?,summary=?,
                        signals_json=?,tags_json=?,content_hash=?,raw_json=?,status='pending',
                        discovered_at=?,reviewed_at=NULL,reviewed_by=NULL
                    WHERE id=?
                    """,
                    (
                        candidate["title"],
                        candidate["issuer"],
                        candidate.get("published_at", ""),
                        candidate["url"],
                        candidate.get("summary", ""),
                        json.dumps(candidate.get("signals", []), ensure_ascii=False),
                        json.dumps(candidate.get("tags", []), ensure_ascii=False),
                        candidate["content_hash"],
                        json.dumps(candidate.get("raw", {}), ensure_ascii=False),
                        now,
                        existing["id"],
                    ),
                )
                candidate_id = existing["id"]
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO policy_candidates(
                        source_id,external_id,title,issuer,published_at,url,summary,signals_json,
                        tags_json,content_hash,raw_json,status,discovered_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,'pending',?)
                    """,
                    (
                        candidate["source_id"],
                        candidate["external_id"],
                        candidate["title"],
                        candidate["issuer"],
                        candidate.get("published_at", ""),
                        candidate["url"],
                        candidate.get("summary", ""),
                        json.dumps(candidate.get("signals", []), ensure_ascii=False),
                        json.dumps(candidate.get("tags", []), ensure_ascii=False),
                        candidate["content_hash"],
                        json.dumps(candidate.get("raw", {}), ensure_ascii=False),
                        now,
                    ),
                )
                candidate_id = int(cursor.lastrowid)
            version_record = {**candidate, "discovered_at": now}
            conn.execute(
                """
                INSERT OR IGNORE INTO policy_versions(
                    candidate_id,content_hash,record_json,discovered_at
                ) VALUES(?,?,?,?)
                """,
                (
                    candidate_id,
                    candidate["content_hash"],
                    json.dumps(version_record, ensure_ascii=False),
                    now,
                ),
            )
        return state

    def list_policy_candidates(self, status: str = "pending", limit: int = 100) -> List[dict]:
        sql = "SELECT * FROM policy_candidates"
        args: List[Any] = []
        if status:
            sql += " WHERE status=?"
            args.append(status)
        sql += " ORDER BY discovered_at DESC,id DESC LIMIT ?"
        args.append(limit)
        with self._lock, self._connect() as conn:
            rows = conn.execute(sql, tuple(args)).fetchall()
        return [self._row_to_policy_candidate(row) for row in rows]

    def get_policy_candidate(self, candidate_id: int) -> Optional[dict]:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM policy_candidates WHERE id=?", (candidate_id,)
            ).fetchone()
        return self._row_to_policy_candidate(row) if row else None

    def review_policy_candidate(
        self, candidate_id: int, action: str, record: Dict[str, Any], reviewer_id: int
    ) -> Optional[dict]:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            existing = conn.execute(
                "SELECT * FROM policy_candidates WHERE id=?", (candidate_id,)
            ).fetchone()
            if not existing:
                return None
            if action == "reject":
                conn.execute(
                    "UPDATE policy_candidates SET status='rejected',reviewed_at=?,reviewed_by=? "
                    "WHERE id=?",
                    (now, reviewer_id, candidate_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE policy_candidates SET title=?,issuer=?,published_at=?,url=?,summary=?,
                        signals_json=?,tags_json=?,status='approved',reviewed_at=?,reviewed_by=?
                    WHERE id=?
                    """,
                    (
                        record["title"],
                        record["issuer"],
                        record["published_at"],
                        record["url"],
                        record["summary"],
                        json.dumps(record.get("signals", []), ensure_ascii=False),
                        json.dumps(record.get("tags", []), ensure_ascii=False),
                        now,
                        reviewer_id,
                        candidate_id,
                    ),
                )
            row = conn.execute(
                "SELECT * FROM policy_candidates WHERE id=?", (candidate_id,)
            ).fetchone()
        return self._row_to_policy_candidate(row)

    def approved_policies(self) -> List[dict]:
        return self.list_policy_candidates("approved", 1000)

    def add_policy_sync_run(
        self,
        source_id: str,
        status: str,
        discovered: int,
        changed: int,
        error: str,
        started_at: str,
    ) -> dict:
        completed_at = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO policy_sync_runs(
                    source_id,status,discovered,changed,error,started_at,completed_at
                ) VALUES(?,?,?,?,?,?,?)
                """,
                (source_id, status, discovered, changed, error[:1000], started_at, completed_at),
            )
            row = conn.execute(
                "SELECT * FROM policy_sync_runs WHERE id=?", (cursor.lastrowid,)
            ).fetchone()
        return dict(row)

    def policy_sync_status(self) -> dict:
        with self._lock, self._connect() as conn:
            pending = conn.execute(
                "SELECT COUNT(*) AS total FROM policy_candidates WHERE status='pending'"
            ).fetchone()["total"]
            approved = conn.execute(
                "SELECT COUNT(*) AS total FROM policy_candidates WHERE status='approved'"
            ).fetchone()["total"]
            last = conn.execute(
                "SELECT * FROM policy_sync_runs ORDER BY completed_at DESC,id DESC LIMIT 1"
            ).fetchone()
            recent = conn.execute(
                "SELECT * FROM policy_sync_runs ORDER BY completed_at DESC,id DESC LIMIT 20"
            ).fetchall()
        return {
            "pending": int(pending),
            "approved_dynamic": int(approved),
            "last_run": dict(last) if last else None,
            "recent_runs": [dict(row) for row in recent],
        }

    @staticmethod
    def _row_to_policy_candidate(row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "source_id": row["source_id"],
            "external_id": row["external_id"],
            "title": row["title"],
            "issuer": row["issuer"],
            "published_at": row["published_at"],
            "url": row["url"],
            "summary": row["summary"],
            "signals": json.loads(row["signals_json"]),
            "tags": json.loads(row["tags_json"]),
            "content_hash": row["content_hash"],
            "raw": json.loads(row["raw_json"]),
            "status": row["status"],
            "discovered_at": row["discovered_at"],
            "reviewed_at": row["reviewed_at"],
            "reviewed_by": row["reviewed_by"],
        }

    @staticmethod
    def _row_to_search_run(row: sqlite3.Row) -> dict:
        request = json.loads(row["request_json"])
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "query": request.get("query", ""),
            "sources": request.get("sources", []),
            "year_from": request.get("year_from"),
            "year_to": request.get("year_to"),
            "english_query": request.get("english_query", ""),
            "language": request.get("language", "any"),
            "has_abstract": request.get("has_abstract"),
            "open_access_only": bool(request.get("open_access_only", False)),
            "min_citations": int(request.get("min_citations", 0)),
            "sort_by": request.get("sort_by", "relevance"),
            "requested_limit": request.get("limit", 20),
            "result_count": row["result_count"],
            "source_status": json.loads(row["source_status_json"]),
            "cache_hit": bool(row["cache_hit"]),
            "elapsed_ms": row["elapsed_ms"],
            "created_at": row["created_at"],
        }

    def usage(self, user_id: int, feature: str, day: Optional[str] = None) -> int:
        day = day or datetime.now(timezone.utc).date().isoformat()
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT quantity FROM usage_daily WHERE user_id=? AND feature=? AND day=?",
                (user_id, feature, day),
            ).fetchone()
        return int(row["quantity"]) if row else 0

    def add_usage(self, user_id: int, feature: str, quantity: int = 1) -> int:
        day = datetime.now(timezone.utc).date().isoformat()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO usage_daily(user_id,feature,day,quantity) VALUES(?,?,?,?)
                ON CONFLICT(user_id,feature,day) DO UPDATE SET
                    quantity=usage_daily.quantity+excluded.quantity
                """,
                (user_id, feature, day, quantity),
            )
            row = conn.execute(
                "SELECT quantity FROM usage_daily WHERE user_id=? AND feature=? AND day=?",
                (user_id, feature, day),
            ).fetchone()
        return int(row["quantity"])

    def update_subscription(
        self,
        user_id: Optional[int] = None,
        customer_id: str = "",
        subscription_id: str = "",
        status: str = "none",
        expires_at: Optional[str] = None,
    ) -> bool:
        where = "id=?" if user_id is not None else "stripe_customer_id=?"
        value: Any = user_id if user_id is not None else customer_id
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                f"""
                UPDATE users SET
                    stripe_customer_id=CASE WHEN ?!='' THEN ? ELSE stripe_customer_id END,
                    stripe_subscription_id=CASE WHEN ?!='' THEN ? ELSE stripe_subscription_id END,
                    subscription_status=?,subscription_expires_at=? WHERE {where}
                """,
                (
                    customer_id,
                    customer_id,
                    subscription_id,
                    subscription_id,
                    status,
                    expires_at,
                    value,
                ),
            )
        return cursor.rowcount > 0

    def webhook_seen(self, event_id: str) -> bool:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM processed_webhooks WHERE event_id=?", (event_id,)
            ).fetchone()
        return row is not None

    def mark_webhook(self, event_id: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO processed_webhooks(event_id,processed_at) VALUES(?,?)",
                (event_id, datetime.now(timezone.utc).isoformat()),
            )

    @staticmethod
    def _row_to_library(row: sqlite3.Row) -> LibraryItem:
        return LibraryItem(
            id=row["id"],
            kind=row["kind"],
            external_id=row["external_id"],
            title=row["title"],
            payload=json.loads(row["payload_json"]),
            note=row["note"],
            project_id=row["project_id"],
            created_at=row["created_at"],
        )
