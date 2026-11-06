"""Durable, tenant-scoped local analysis jobs and in-app monitoring notices.

This module never approves a finding, modifies an instrument, or sends a message
outside COMPASS. Source snapshots, settings and context are frozen for every job.
"""

import json
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from statistics import median
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from . import __version__
from .analysis import ENGINE_VERSION, analyze
from .configuration import get_context, get_settings
from .store import audit, audit_dict, canonical, digest, item_dict, new_id, now, source_dict


MAX_ATTEMPTS = 3
LEASE_SECONDS = 300
SCHEMA = """
CREATE TABLE IF NOT EXISTS monitoring_jobs (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id),
    basis_hash TEXT NOT NULL, state TEXT NOT NULL
      CHECK(state IN ('queued','running','succeeded','failed','cancelled')),
    attempts INTEGER NOT NULL DEFAULT 0, payload TEXT NOT NULL,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL, available_at TEXT NOT NULL,
    lease_expires_at TEXT, lease_token TEXT, last_error TEXT,
    run_id TEXT, analysis_id TEXT, UNIQUE(tenant_id,basis_hash),
    FOREIGN KEY(tenant_id,run_id) REFERENCES runs(tenant_id,id)
);
CREATE INDEX IF NOT EXISTS monitoring_job_queue ON monitoring_jobs(state,available_at);
CREATE TABLE IF NOT EXISTS analysis_reports (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, run_id TEXT NOT NULL,
    basis_hash TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL,
    UNIQUE(tenant_id,run_id,basis_hash),
    FOREIGN KEY(tenant_id,run_id) REFERENCES runs(tenant_id,id)
);
CREATE INDEX IF NOT EXISTS analysis_reports_tenant ON analysis_reports(tenant_id,created_at);
CREATE INDEX IF NOT EXISTS analysis_reports_basis ON analysis_reports(tenant_id,basis_hash,created_at);
CREATE TABLE IF NOT EXISTS monitoring_state (
    tenant_id TEXT PRIMARY KEY REFERENCES tenants(id),
    last_check TEXT, last_successful_check TEXT, last_scheduled_at TEXT,
    last_effective_date TEXT, last_digest TEXT
);
CREATE TABLE IF NOT EXISTS inapp_notices (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id),
    dedupe_key TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL,
    read_at TEXT, UNIQUE(tenant_id,dedupe_key)
);
"""


CAPABILITIES = {
    "external_database": False,
    "language_model": False,
    "rule_based_analysis": True,
    "email": False,
    "local_triggers": True,
    "local_rules_analysis": True,
    "source_change_triggers": True,
    "effective_date_triggers": True,
    "scheduled_checks": True,
    "in_app_digests": True,
    "external_database_connected": False,
    "external_monitoring": False,
    "email_delivery": False,
    "llm_analysis": False,
    "automatic_policy_approval": False,
    "amendment_drafting": False,
}


def _utc(value=None):
    if value is None:
        return datetime.now(timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _local_date(settings):
    return datetime.now(ZoneInfo(settings["monitoring"]["timezone"])).date().isoformat()


def _job(row):
    data = dict(row)
    snapshot = json.loads(data.pop("payload"))
    data.pop("lease_token", None)
    data.update({"trigger": snapshot["trigger"], "status": data["state"], "max_attempts": MAX_ATTEMPTS})
    data["retry_history"] = snapshot.get("retry_history", [])
    data["retry_batches"] = len(data["retry_history"]) + 1
    data["attempts_total"] = snapshot.get("attempts_total_offset", 0) + data["attempts"]
    data["as_of"] = snapshot["snapshot"]["as_of"]
    data["source_count"] = len(snapshot["snapshot"]["sources"])
    return data


def _report(row):
    return {**json.loads(row["payload"]), "id": row["id"], "run_id": row["run_id"], "created_at": row["created_at"]}


def _notice(row):
    return {**json.loads(row["payload"]), "id": row["id"], "created_at": row["created_at"], "read_at": row["read_at"], "read": row["read_at"] is not None}


def _latest_sources(sources):
    """Use declared identities/replacements, never infer identity from a title."""
    ordered = sorted(sources, key=lambda s: (s["created_at"], s["id"]))
    replaced = {s.get("replaces_source_id") for s in ordered if s.get("replaces_source_id")}
    latest_keys = {}
    for source in ordered:
        if source.get("source_key"):
            latest_keys[(source["kind"], source["jurisdiction_id"], source["source_key"])] = source["id"]
    return [
        source for source in ordered
        if source["id"] not in replaced
        and (not source.get("source_key") or latest_keys[(source["kind"], source["jurisdiction_id"], source["source_key"])] == source["id"])
    ]


def _basis(snapshot):
    return digest({
        "tenant_id": snapshot["tenant_id"],
        "sources": sorted((s["id"], s["hash"]) for s in snapshot["sources"]),
        "profile_hash": snapshot["profile_hash"],
        "settings": snapshot["settings"], "context": snapshot["context"],
        "workflow": digest({"findings": snapshot["findings"], "audit": snapshot["workflow_audit"]}),
        "as_of": snapshot["as_of"], "engine_version": ENGINE_VERSION,
    })


class MonitoringService:
    def __init__(self, store):
        self.store = store
        with store.connect(write=True) as db:
            db.executescript(SCHEMA)

    def _tenant(self, db, tenant_id):
        row = db.execute("SELECT * FROM tenants WHERE id=?", (tenant_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Workspace not found")
        return row

    def _actor(self, db, tenant_id, actor=None):
        if actor and actor.get("tenant_id") != tenant_id:
            raise HTTPException(403, "Actor does not belong to this workspace")
        if actor:
            row = db.execute(
                "SELECT u.id,u.name,m.role FROM users u JOIN memberships m ON m.user_id=u.id WHERE m.tenant_id=? AND u.id=?",
                (tenant_id, actor["id"]),
            ).fetchone()
        else:
            row = db.execute(
                "SELECT u.id,u.name,m.role FROM users u JOIN memberships m ON m.user_id=u.id WHERE m.tenant_id=? AND m.role='owner' ORDER BY u.id LIMIT 1",
                (tenant_id,),
            ).fetchone()
        if row is None:
            raise HTTPException(403, "An authorized workspace member is required")
        return {**dict(row), "tenant_id": tenant_id}

    def _snapshot(self, db, tenant_id, as_of=None, source_ids=None, run=None):
        tenant = self._tenant(db, tenant_id)
        settings = get_settings(db, tenant_id)
        context = get_context(db, tenant_id)
        historical_cutoff = run.get("created_at") if run else None
        history = [source_dict(row) for row in db.execute(
            "SELECT * FROM sources WHERE tenant_id=? ORDER BY created_at,id", (tenant_id,)
        ) if historical_cutoff is None or row["created_at"] <= historical_cutoff]
        by_id = {s["id"]: s for s in history}
        if source_ids is not None:
            if len(set(source_ids)) != len(source_ids):
                raise HTTPException(422, "Select each source once")
            if any(key not in by_id for key in source_ids):
                raise HTTPException(404, "Source not found in this workspace or historical review")
            sources = [by_id[key] for key in source_ids]
        else:
            sources = _latest_sources(history)
        profile = run["profile"] if run else json.loads(tenant["profile"])
        profile_hash = run["profile_hash"] if run else tenant["profile_hash"]
        findings, events = self._analysis_inputs(db, tenant_id)
        workflow_events = [event for event in events if event["action"] in {
            "finding.created", "finding.assigned", "decision.recorded", "applicability.reviewed",
        }]
        return {
            "tenant_id": tenant_id, "jurisdiction_id": tenant["jurisdiction_id"],
            "as_of": str(as_of or _local_date(settings)), "settings": settings, "context": context,
            "profile": profile, "profile_hash": profile_hash, "sources": sources, "history": history,
            "findings": findings, "workflow_audit": workflow_events,
            "snapshot_at": now(),
        }

    def enqueue(self, tenant_id, actor, trigger, as_of=None, source_ids=None, db=None):
        with (nullcontext(db) if db is not None else self.store.connect(write=True)) as db:
            actor = self._actor(db, tenant_id, actor)
            snapshot = self._snapshot(db, tenant_id, as_of, source_ids)
            monitoring = snapshot["settings"]["monitoring"]
            if trigger in {"scheduled", "effective_date", "digest"} and not monitoring["enabled"]:
                return None
            if trigger == "source_changed" and not monitoring["source_changes"]:
                return None
            if trigger in {"context_changed", "settings_changed", "profile_changed", "workflow_changed"} and not monitoring["context_changes"]:
                return None
            if trigger == "effective_date" and not monitoring["effective_dates"]:
                return None
            if {s["kind"] for s in snapshot["sources"]} != {"instrument", "external"}:
                return None
            basis_hash = _basis(snapshot)
            existing = db.execute("SELECT * FROM monitoring_jobs WHERE tenant_id=? AND basis_hash=?", (tenant_id, basis_hash)).fetchone()
            if existing:
                if existing["state"] == "cancelled" and existing["attempts"] < MAX_ATTEMPTS:
                    db.execute("UPDATE monitoring_jobs SET state='queued',available_at=?,updated_at=?,last_error=NULL WHERE tenant_id=? AND id=?", (now(), now(), tenant_id, existing["id"]))
                    existing = db.execute("SELECT * FROM monitoring_jobs WHERE tenant_id=? AND id=?", (tenant_id, existing["id"])).fetchone()
                return _job(existing)
            job_id, stamp = new_id(), now()
            payload = {"trigger": trigger, "actor": actor, "snapshot": snapshot}
            db.execute(
                "INSERT INTO monitoring_jobs(id,tenant_id,basis_hash,state,attempts,payload,created_at,updated_at,available_at) VALUES(?,?,?,'queued',0,?,?,?,?)",
                (job_id, tenant_id, basis_hash, canonical(payload), stamp, stamp, stamp),
            )
            audit(db, actor, "monitoring.queued", "monitoring_job", job_id, {"trigger": trigger, "basis_hash": basis_hash, "automated": trigger != "manual"})
            return _job(db.execute("SELECT * FROM monitoring_jobs WHERE tenant_id=? AND id=?", (tenant_id, job_id)).fetchone())

    def _create_run(self, db, job, payload):
        if job["run_id"]:
            row = db.execute("SELECT * FROM runs WHERE tenant_id=? AND id=?", (job["tenant_id"], job["run_id"])).fetchone()
            if row:
                return item_dict(row)
        snapshot = payload["snapshot"]
        run_id, stamp = new_id(), now()
        data = {
            "title": f"Policy review · {snapshot['as_of']}", "as_of": snapshot["as_of"],
            "profile": snapshot["profile"], "profile_hash": snapshot["profile_hash"],
            "source_ids": [s["id"] for s in snapshot["sources"]],
            "analysis_method": ENGINE_VERSION, "coverage_status": "unverified", "code_version": __version__,
            "coverage_note": "Local supplied sources only. Rule-based indicators require owner review; external source coverage is unverified.",
            "trigger": payload["trigger"],
        }
        db.execute("INSERT INTO runs VALUES(?,?,?,?)", (run_id, job["tenant_id"], canonical(data), stamp))
        for source_id in data["source_ids"]:
            db.execute("INSERT INTO run_sources VALUES(?,?,?)", (job["tenant_id"], run_id, source_id))
        db.execute("UPDATE monitoring_jobs SET run_id=? WHERE tenant_id=? AND id=?", (run_id, job["tenant_id"], job["id"]))
        audit(db, payload["actor"], "run.created", "run", run_id, {"trigger": payload["trigger"], "automated_analysis": True, "policy_approval": False, "job_id": job["id"]})
        return {**data, "id": run_id, "created_at": stamp}

    def _compute(self, snapshot):
        result = analyze(
            snapshot["sources"], snapshot["history"], snapshot["settings"], snapshot["context"],
            snapshot["as_of"], snapshot["findings"], snapshot["workflow_audit"], snapshot["jurisdiction_id"],
        )
        evidence_ids = {s["id"] for s in snapshot["sources"]}
        for feature in result.get("features", {}).values():
            for item in feature.get("items", []):
                evidence_ids.update(item.get("source_ids", []))
                evidence_ids.update(e["source_id"] for e in item.get("evidence", []) if e.get("source_id"))
        evidence_sources = [s for s in snapshot["history"] if s["id"] in evidence_ids]
        return {
            **result, "basis_hash": _basis(snapshot), "engine_version": ENGINE_VERSION,
            "settings_snapshot": snapshot["settings"], "context_snapshot": snapshot["context"],
            "findings_snapshot": snapshot["findings"], "audit_snapshot": snapshot["workflow_audit"],
            "profile_snapshot": snapshot["profile"], "profile_hash": snapshot["profile_hash"],
            "source_ids": [s["id"] for s in snapshot["sources"]], "evidence_sources": evidence_sources,
            "snapshot_at": snapshot["snapshot_at"], "capabilities": CAPABILITIES,
            "coverage_status": "unverified", "policy_approval": False,
        }

    def _analysis_inputs(self, db, tenant_id):
        findings = [item_dict(row) for row in db.execute("SELECT * FROM findings WHERE tenant_id=? ORDER BY created_at,id", (tenant_id,))]
        events = [audit_dict(row) for row in db.execute("SELECT * FROM audit WHERE tenant_id=? ORDER BY id", (tenant_id,))]
        return findings, events

    def _save_report(self, db, tenant_id, run_id, data, actor):
        existing = db.execute("SELECT * FROM analysis_reports WHERE tenant_id=? AND run_id=? AND basis_hash=?", (tenant_id, run_id, data["basis_hash"])).fetchone()
        if existing:
            return _report(existing)
        report_id, stamp = new_id(), now()
        db.execute("INSERT INTO analysis_reports VALUES(?,?,?,?,?,?)", (report_id, tenant_id, run_id, data["basis_hash"], canonical(data), stamp))
        audit(db, actor, "analysis.completed", "run", run_id, {"analysis_id": report_id, "engine_version": ENGINE_VERSION, "policy_approval": False})
        return {**data, "id": report_id, "run_id": run_id, "created_at": stamp}

    def _add_notice(self, db, tenant_id, key, data):
        notice_id, stamp = new_id(), now()
        db.execute("INSERT OR IGNORE INTO inapp_notices VALUES(?,?,?,?,?,NULL)", (notice_id, tenant_id, key, canonical(data), stamp))

    def process(self, job_id=None, tenant_id=None):
        stamp = now()
        with self.store.connect(write=True) as db:
            filters, values = [], []
            if tenant_id is not None:
                filters.append("tenant_id=?")
                values.append(tenant_id)
            if job_id is not None:
                filters.append("id=?")
                values.append(job_id)
            clause = " AND " + " AND ".join(filters) if filters else ""
            # A crashed worker's lease can be reclaimed without duplicating a run.
            expired = db.execute("SELECT * FROM monitoring_jobs WHERE state='running' AND lease_expires_at<=?" + clause, [stamp, *values]).fetchall()
            for old in expired:
                state = "queued" if old["attempts"] < MAX_ATTEMPTS else "failed"
                db.execute("UPDATE monitoring_jobs SET state=?,available_at=?,lease_expires_at=NULL,lease_token=NULL,last_error=?,updated_at=? WHERE tenant_id=? AND id=?", (state, stamp, "Worker lease expired; the previous attempt did not finish.", stamp, old["tenant_id"], old["id"]))
            # Failed attempts become eligible after their persisted backoff.
            # Explicit retry can bring that time forward, but never resets the
            # attempt counter or exceeds MAX_ATTEMPTS.
            db.execute("UPDATE monitoring_jobs SET state='queued',updated_at=? WHERE state='failed' AND attempts<? AND available_at<=?" + clause, [stamp, MAX_ATTEMPTS, stamp, *values])
            row = db.execute("SELECT * FROM monitoring_jobs WHERE state='queued' AND attempts<? AND available_at<=?" + clause + " ORDER BY available_at,created_at,id LIMIT 1", [MAX_ATTEMPTS, stamp, *values]).fetchone()
            if row is None:
                if job_id is not None:
                    found = db.execute("SELECT * FROM monitoring_jobs WHERE id=?" + (" AND tenant_id=?" if tenant_id else ""), (job_id, tenant_id) if tenant_id else (job_id,)).fetchone()
                    return _job(found) if found else None
                return None
            token = new_id()
            expires = (datetime.now(timezone.utc) + timedelta(seconds=LEASE_SECONDS)).isoformat()
            db.execute("UPDATE monitoring_jobs SET state='running',attempts=attempts+1,updated_at=?,lease_expires_at=?,lease_token=? WHERE tenant_id=? AND id=?", (stamp, expires, token, row["tenant_id"], row["id"]))
            job = dict(db.execute("SELECT * FROM monitoring_jobs WHERE tenant_id=? AND id=?", (row["tenant_id"], row["id"])).fetchone())
            payload = json.loads(job["payload"])
            run = self._create_run(db, job, payload)
            db.execute("INSERT INTO monitoring_state(tenant_id,last_check) VALUES(?,?) ON CONFLICT(tenant_id) DO UPDATE SET last_check=excluded.last_check", (job["tenant_id"], stamp))
        try:
            data = self._compute(payload["snapshot"])
            with self.store.connect(write=True) as db:
                current = db.execute("SELECT * FROM monitoring_jobs WHERE tenant_id=? AND id=?", (job["tenant_id"], job["id"])).fetchone()
                if current["lease_token"] != token or current["state"] != "running":
                    return _job(current)
                report = self._save_report(db, job["tenant_id"], run["id"], data, payload["actor"])
                finished = now()
                db.execute("UPDATE monitoring_jobs SET state='succeeded',analysis_id=?,last_error=NULL,updated_at=?,lease_expires_at=NULL,lease_token=NULL WHERE tenant_id=? AND id=?", (report["id"], finished, job["tenant_id"], job["id"]))
                db.execute("UPDATE monitoring_state SET last_successful_check=? WHERE tenant_id=?", (finished, job["tenant_id"]))
                count = data.get("summary", {}).get("attention_count", 0)
                urgent = any(item.get("severity") == "urgent" for feature in data.get("features", {}).values() for item in feature.get("items", []))
                self._add_notice(db, job["tenant_id"], f"analysis:{report['id']}", {
                    "kind": "review_ready", "title": "Review ready", "severity": "urgent" if urgent else "info",
                    "message": f"{count} analysis indicators need attention. Policy-owner review is still required; source coverage is unverified.",
                    "run_id": run["id"], "analysis_id": report["id"], "attention_count": count,
                })
                return _job(db.execute("SELECT * FROM monitoring_jobs WHERE tenant_id=? AND id=?", (job["tenant_id"], job["id"])).fetchone())
        except Exception as error:
            # Persist a bounded diagnostic, not source text or credentials.
            message = f"{type(error).__name__}: analysis did not complete. Retry or inspect the local service logs."
            with self.store.connect(write=True) as db:
                current = db.execute("SELECT * FROM monitoring_jobs WHERE tenant_id=? AND id=?", (job["tenant_id"], job["id"])).fetchone()
                if current["lease_token"] != token:
                    return _job(current)
                retry_at = (datetime.now(timezone.utc) + timedelta(seconds=min(60 * 2 ** (current["attempts"] - 1), 300))).isoformat()
                db.execute("UPDATE monitoring_jobs SET state='failed',last_error=?,available_at=?,updated_at=?,lease_expires_at=NULL,lease_token=NULL WHERE tenant_id=? AND id=?", (message, retry_at, now(), job["tenant_id"], job["id"]))
                audit(db, payload["actor"], "monitoring.failed", "monitoring_job", job["id"], {"trigger": payload["trigger"], "attempt": current["attempts"], "error_type": type(error).__name__, "policy_approval": False})
                return _job(db.execute("SELECT * FROM monitoring_jobs WHERE tenant_id=? AND id=?", (job["tenant_id"], job["id"])).fetchone())

    def check(self, tenant_id, actor):
        job = self.enqueue(tenant_id, actor, "manual")
        if job is None:
            raise HTTPException(409, "Import at least one internal instrument and one external reference before running a check")
        if job["state"] == "failed" and job["attempts"] < MAX_ATTEMPTS:
            job = self.retry(tenant_id, actor, job["id"])
        job = self.process(job["id"], tenant_id) or job
        with self.store.connect() as db:
            row = db.execute("SELECT * FROM analysis_reports WHERE tenant_id=? AND id=?", (tenant_id, job["analysis_id"])).fetchone() if job["analysis_id"] else None
            return {"job": job, "analysis": _report(row) if row else None, "run_id": job["run_id"]}

    def analyze_run(self, tenant_id, actor, run_id):
        with self.store.connect() as db:
            actor = self._actor(db, tenant_id, actor)
            row = db.execute("SELECT * FROM runs WHERE tenant_id=? AND id=?", (tenant_id, run_id)).fetchone()
            if row is None:
                raise HTTPException(404, "Review not found")
            run = item_dict(row)
            snapshot = self._snapshot(db, tenant_id, run["as_of"], run["source_ids"], run)
            existing = db.execute("SELECT * FROM analysis_reports WHERE tenant_id=? AND run_id=? AND basis_hash=?", (tenant_id, run_id, _basis(snapshot))).fetchone()
            if existing:
                return _report(existing)
        data = self._compute(snapshot)
        with self.store.connect(write=True) as db:
            return self._save_report(db, tenant_id, run_id, data, actor)

    def analyses_for_run(self, tenant_id, run_id, db=None):
        with (nullcontext(db) if db is not None else self.store.connect()) as db:
            if db.execute("SELECT 1 FROM runs WHERE tenant_id=? AND id=?", (tenant_id, run_id)).fetchone() is None:
                raise HTTPException(404, "Review not found")
            return [_report(row) for row in db.execute("SELECT * FROM analysis_reports WHERE tenant_id=? AND run_id=? ORDER BY created_at,id", (tenant_id, run_id))]

    def _workload(self, db, tenant_id):
        findings, events = self._analysis_inputs(db, tenant_id)
        counts = {key: sum(f["status"] == key for f in findings) for key in ("pending", "accepted", "rejected", "needs_information")}
        decisions = [event for event in events if event["action"] == "decision.recorded"]
        created = {f["id"]: f["created_at"] for f in findings}
        hours = []
        first_decisions = {}
        for event in decisions:
            first_decisions.setdefault(event["entity_id"], event["created_at"])
        for finding_id, stamp in first_decisions.items():
            if finding_id in created:
                hours.append(max(0, (_utc(stamp) - _utc(created[finding_id])).total_seconds() / 3600))
        return {**counts, "total": len(findings), "decision_count": len(decisions), "median_review_hours": round(median(hours), 3) if hours else None}

    def _latest_report(self, db, tenant_id, basis_hash, run_id=None):
        query = "SELECT * FROM analysis_reports WHERE tenant_id=?"
        values = [tenant_id]
        if run_id is not None:
            query += " AND run_id=?"
            values.append(run_id)
        query += " ORDER BY CASE WHEN basis_hash=? THEN 0 ELSE 1 END,created_at DESC,id DESC LIMIT 1"
        values.append(basis_hash)
        return db.execute(query, values).fetchone()

    def insights(self, tenant_id, run_id=None):
        with self.store.connect() as db:
            run = None
            if run_id is not None:
                row = db.execute("SELECT * FROM runs WHERE tenant_id=? AND id=?", (tenant_id, run_id)).fetchone()
                if row is None:
                    raise HTTPException(404, "Review not found")
                run = item_dict(row)
            snapshot = self._snapshot(db, tenant_id, run["as_of"], run["source_ids"], run) if run else self._snapshot(db, tenant_id)
            current_basis = _basis(snapshot)
            # An older leased job can finish after a newer, current check. Do
            # not hide that current report behind the late historical result.
            row = self._latest_report(db, tenant_id, current_basis, run_id)
            latest = _report(row) if row else None
            return {
                "latest": latest, "stale": latest is not None and latest["basis_hash"] != current_basis,
                "workload": self._workload(db, tenant_id), "capabilities": CAPABILITIES,
                "scope": "review" if run else "workspace", "run_id": run_id,
                "review_title": run["title"] if run else None,
            }

    def status(self, tenant_id):
        with self.store.connect() as db:
            self._tenant(db, tenant_id)
            state = db.execute("SELECT * FROM monitoring_state WHERE tenant_id=?", (tenant_id,)).fetchone()
            return {
                "jobs": [_job(row) for row in db.execute("SELECT * FROM monitoring_jobs WHERE tenant_id=? ORDER BY created_at DESC,id DESC LIMIT 100", (tenant_id,))],
                "last_check": state["last_check"] if state else None,
                "last_successful_check": state["last_successful_check"] if state else None,
                "last_digest": state["last_digest"] if state else None,
                "notices": [_notice(row) for row in db.execute("SELECT * FROM inapp_notices WHERE tenant_id=? ORDER BY created_at DESC,id DESC LIMIT 100", (tenant_id,))],
                "settings": get_settings(db, tenant_id), "capabilities": CAPABILITIES,
            }

    def retry(self, tenant_id, actor, jobid, reset=False, rationale=""):
        with self.store.connect(write=True) as db:
            actor = self._actor(db, tenant_id, actor)
            row = db.execute("SELECT * FROM monitoring_jobs WHERE tenant_id=? AND id=?", (tenant_id, jobid)).fetchone()
            if row is None:
                raise HTTPException(404, "Job not found")
            if row["state"] != "failed":
                raise HTTPException(409, "Only failed jobs can be retried")
            if reset:
                if actor["role"] != "owner":
                    raise HTTPException(403, "A policy owner must explicitly start a new retry cycle")
                if row["attempts"] < MAX_ATTEMPTS:
                    raise HTTPException(409, "Use an ordinary retry before the cycle limit is reached")
                payload = json.loads(row["payload"])
                reason = (rationale or "").strip() or "Policy owner explicitly requested a new retry cycle."
                if len(reason) > 4000:
                    raise HTTPException(422, "Retry rationale must be at most 4000 characters")
                history = payload.setdefault("retry_history", [])
                history.append({
                    "reset_at": now(), "reset_by": {"id": actor["id"], "name": actor["name"]},
                    "rationale": reason, "attempts": row["attempts"], "last_error": row["last_error"],
                    "run_id": row["run_id"],
                })
                payload["attempts_total_offset"] = payload.get("attempts_total_offset", 0) + row["attempts"]
                db.execute("UPDATE monitoring_jobs SET state='queued',attempts=0,payload=?,available_at=?,updated_at=?,lease_expires_at=NULL,lease_token=NULL,last_error=NULL WHERE tenant_id=? AND id=?", (canonical(payload), now(), now(), tenant_id, jobid))
                audit(db, actor, "monitoring.retry_cycle_reset", "monitoring_job", jobid, {
                    "rationale": reason, "prior_attempts": row["attempts"],
                    "attempts_total_before": payload["attempts_total_offset"], "retry_batch": len(history) + 1,
                    "run_id": row["run_id"], "policy_approval": False,
                })
                return _job(db.execute("SELECT * FROM monitoring_jobs WHERE tenant_id=? AND id=?", (tenant_id, jobid)).fetchone())
            if row["attempts"] >= MAX_ATTEMPTS:
                raise HTTPException(409, "Retry limit reached; resolve the problem before creating a new review")
            db.execute("UPDATE monitoring_jobs SET state='queued',available_at=?,updated_at=?,lease_expires_at=NULL,lease_token=NULL WHERE tenant_id=? AND id=?", (now(), now(), tenant_id, jobid))
            audit(db, actor, "monitoring.retried", "monitoring_job", jobid, {"attempts_so_far": row["attempts"]})
            return _job(db.execute("SELECT * FROM monitoring_jobs WHERE tenant_id=? AND id=?", (tenant_id, jobid)).fetchone())

    def get_job(self, tenant_id, job_id):
        with self.store.connect() as db:
            row = db.execute("SELECT * FROM monitoring_jobs WHERE tenant_id=? AND id=?", (tenant_id, job_id)).fetchone()
            if row is None:
                raise HTTPException(404, "Job not found")
            return _job(row)

    def cancel_pending(self, tenant_id, db=None):
        with (nullcontext(db) if db is not None else self.store.connect(write=True)) as db:
            result = db.execute("UPDATE monitoring_jobs SET state='cancelled',updated_at=?,last_error='Settings or context changed; refresh the check.' WHERE tenant_id=? AND (state='queued' OR (state='failed' AND attempts<?))", (now(), tenant_id, MAX_ATTEMPTS))
            return result.rowcount

    def read_notice(self, tenant_id, noticeid):
        with self.store.connect(write=True) as db:
            row = db.execute("SELECT * FROM inapp_notices WHERE tenant_id=? AND id=?", (tenant_id, noticeid)).fetchone()
            if row is None:
                raise HTTPException(404, "Notice not found")
            db.execute("UPDATE inapp_notices SET read_at=COALESCE(read_at,?) WHERE tenant_id=? AND id=?", (now(), tenant_id, noticeid))
            return _notice(db.execute("SELECT * FROM inapp_notices WHERE tenant_id=? AND id=?", (tenant_id, noticeid)).fetchone())

    def tick(self):
        """Schedule due local checks and digests, then process at most one job."""
        instant = datetime.now(timezone.utc)
        with self.store.connect() as db:
            tenants = [row["id"] for row in db.execute("SELECT id FROM tenants ORDER BY id")]
        for tenant_id in tenants:
            with self.store.connect() as db:
                settings = get_settings(db, tenant_id)
                monitoring = settings["monitoring"]
                if not monitoring["enabled"]:
                    continue
                try:
                    actor = self._actor(db, tenant_id)
                except HTTPException:
                    # One unprovisioned workspace must not stop checks for all
                    # other workspaces. Provisioning an owner is a prerequisite.
                    continue
                row = db.execute("SELECT * FROM monitoring_state WHERE tenant_id=?", (tenant_id,)).fetchone()
                state = dict(row) if row else {}
            local_date = instant.astimezone(ZoneInfo(monitoring["timezone"])).date().isoformat()
            scheduled_at = state.get("last_scheduled_at") or state.get("last_check")
            interval_due = not scheduled_at or instant - _utc(scheduled_at) >= timedelta(hours=monitoring["check_interval_hours"])
            date_due = monitoring["effective_dates"] and state.get("last_effective_date") != local_date
            if interval_due or date_due:
                self.enqueue(tenant_id, actor, "effective_date" if date_due else "scheduled", as_of=local_date)
                with self.store.connect(write=True) as db:
                    db.execute("INSERT INTO monitoring_state(tenant_id,last_scheduled_at,last_effective_date) VALUES(?,?,?) ON CONFLICT(tenant_id) DO UPDATE SET last_scheduled_at=excluded.last_scheduled_at,last_effective_date=excluded.last_effective_date", (tenant_id, now(), local_date))
            last_digest = state.get("last_digest")
            if not last_digest:
                with self.store.connect(write=True) as db:
                    db.execute("INSERT INTO monitoring_state(tenant_id,last_digest) VALUES(?,?) ON CONFLICT(tenant_id) DO UPDATE SET last_digest=excluded.last_digest", (tenant_id, now()))
            elif instant - _utc(last_digest) >= timedelta(days=monitoring["digest_interval_days"]):
                with self.store.connect(write=True) as db:
                    workload = self._workload(db, tenant_id)
                    current_basis = _basis(self._snapshot(db, tenant_id))
                    latest = self._latest_report(db, tenant_id, current_basis)
                    stale = latest is None or latest["basis_hash"] != current_basis
                    if latest is None:
                        freshness_note = " No analysis report is available; run a new check."
                    elif stale:
                        freshness_note = " The available analysis uses older inputs; run a new check."
                    else:
                        freshness_note = " Analysis matches the current supplied inputs."
                    self._add_notice(db, tenant_id, f"digest:{local_date}", {
                        "kind": "digest", "title": "Policy review digest", "severity": "info",
                        "message": f"{workload['pending']} pending findings and {workload['needs_information']} requests for information. This is an in-app summary of local records; external coverage remains unverified." + freshness_note,
                        "run_id": latest["run_id"] if latest else None, "analysis_id": latest["id"] if latest else None,
                        "workload": workload, "stale": stale,
                        "analysis_status": "missing" if latest is None else "stale" if stale else "current",
                    })
                    db.execute("UPDATE monitoring_state SET last_digest=? WHERE tenant_id=?", (now(), tenant_id))
                    audit(db, actor, "monitoring.digest_created", "workspace", tenant_id, {"automated": True, "external_delivery": False})
        return self.process()
