"""Transactional local store. Tenant scope is explicit on every data access.

SQLite supports development and tests. This is not a production RLS substitute.
"""

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def now():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def new_id():
    return str(uuid4())


SCHEMA = """
CREATE TABLE IF NOT EXISTS tenants (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, jurisdiction_id TEXT NOT NULL,
    profile TEXT NOT NULL, profile_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS memberships (
    tenant_id TEXT NOT NULL REFERENCES tenants(id), user_id TEXT NOT NULL REFERENCES users(id),
    role TEXT NOT NULL CHECK(role IN ('owner','reviewer')), PRIMARY KEY(tenant_id,user_id)
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, tenant_id TEXT NOT NULL, expires_at TEXT NOT NULL,
    FOREIGN KEY(tenant_id,user_id) REFERENCES memberships(tenant_id,user_id)
);
CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id),
    payload TEXT NOT NULL, content_hash TEXT NOT NULL, created_at TEXT NOT NULL,
    UNIQUE(tenant_id,id), UNIQUE(tenant_id,content_hash)
);
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id),
    payload TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(tenant_id,id)
);
CREATE TABLE IF NOT EXISTS run_sources (
    tenant_id TEXT NOT NULL, run_id TEXT NOT NULL, source_id TEXT NOT NULL,
    PRIMARY KEY(tenant_id,run_id,source_id),
    FOREIGN KEY(tenant_id,run_id) REFERENCES runs(tenant_id,id),
    FOREIGN KEY(tenant_id,source_id) REFERENCES sources(tenant_id,id)
);
CREATE TABLE IF NOT EXISTS findings (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, run_id TEXT NOT NULL,
    instrument_source_id TEXT NOT NULL, external_source_id TEXT NOT NULL,
    payload TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(tenant_id,id),
    FOREIGN KEY(tenant_id,run_id) REFERENCES runs(tenant_id,id),
    FOREIGN KEY(tenant_id,instrument_source_id) REFERENCES sources(tenant_id,id),
    FOREIGN KEY(tenant_id,external_source_id) REFERENCES sources(tenant_id,id)
);
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT NOT NULL REFERENCES tenants(id),
    actor_id TEXT NOT NULL REFERENCES users(id), actor_name TEXT NOT NULL,
    action TEXT NOT NULL, entity_type TEXT NOT NULL, entity_id TEXT NOT NULL,
    details TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS sources_tenant ON sources(tenant_id);
CREATE INDEX IF NOT EXISTS runs_tenant ON runs(tenant_id);
CREATE INDEX IF NOT EXISTS findings_run ON findings(tenant_id,run_id);
CREATE INDEX IF NOT EXISTS audit_tenant ON audit(tenant_id,id);
CREATE TABLE IF NOT EXISTS preferences (
    tenant_id TEXT NOT NULL, user_id TEXT NOT NULL,
    view_mode TEXT NOT NULL CHECK(view_mode IN ('simple','advanced')),
    PRIMARY KEY(tenant_id,user_id),
    FOREIGN KEY(tenant_id,user_id) REFERENCES memberships(tenant_id,user_id)
);
CREATE TABLE IF NOT EXISTS workspace_settings (
    tenant_id TEXT PRIMARY KEY REFERENCES tenants(id), payload TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS workspace_context (
    tenant_id TEXT PRIMARY KEY REFERENCES tenants(id), payload TEXT NOT NULL, updated_at TEXT NOT NULL
);
"""


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path, timeout=10) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(SCHEMA)

    @contextmanager
    def connect(self, write=False):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            # A read snapshot keeps exported findings and audit events consistent
            # when another request records a decision during the export.
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()


def source_dict(row):
    return {**json.loads(row["payload"]), "id": row["id"], "hash": row["content_hash"], "created_at": row["created_at"]}


def item_dict(row):
    return {**json.loads(row["payload"]), "id": row["id"], "created_at": row["created_at"]}


def audit(db, actor, action, entity_type, entity_id, details):
    db.execute(
        "INSERT INTO audit(tenant_id,actor_id,actor_name,action,entity_type,entity_id,details,created_at) VALUES(?,?,?,?,?,?,?,?)",
        (actor["tenant_id"], actor["id"], actor["name"], action, entity_type, entity_id, canonical(details), now()),
    )


def audit_dict(row):
    return {**dict(row), "details": json.loads(row["details"])}
