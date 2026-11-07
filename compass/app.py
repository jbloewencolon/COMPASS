"""Local runnable review milestone; production identity integration is not shipped."""

import hashlib
import json
import secrets
import asyncio
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import ValidationError

from . import __version__
from .demo import PERSONAS, seed
from .models import AnalysisSettings, AssignmentInput, ContextInput, PreferencesInput, RetryInput, ApplicabilityInput, DecisionInput, DemoSessionInput, FindingInput, RunInput, SourceInput, MembershipInput, SourceReviewInput
from .configuration import get_context, get_settings
from .monitoring import MonitoringService
from .analysis import ENGINE_VERSION
from .jurisdictions import is_us_authority
from .pdf_import import MAX_PDF_BYTES, PDFImportError, extract_pdf
from .method_import import validate_import_bundle
from .store import Store, audit, audit_dict, canonical, digest, item_dict, new_id, now, source_dict


COOKIE = "compass_session"
COVERAGE = {
    "status": "unverified",
    "message": "Only supplied source snapshots are analyzed. The external database is not connected; absence of findings does not establish coverage or legal compliance.",
}
STATIC = Path(__file__).parent / "static"


def require_row(db, table, tenant, entity_id):
    # Table names are fixed internal constants, never user input.
    if table not in {"sources", "runs", "findings"}:
        raise ValueError("Unsupported entity table")
    row = db.execute(f"SELECT * FROM {table} WHERE tenant_id=? AND id=?", (tenant, entity_id)).fetchone()
    if row is None:
        raise HTTPException(404, "Not found")
    return row


def workspace(actor):
    return {"id": actor["tenant_id"], "name": actor["workspace_name"], "jurisdiction_id": actor["jurisdiction_id"], "role": actor["role"], "can_determine_applicability": bool(actor.get("can_determine_applicability"))}


def require_owner(actor):
    if actor["role"] != "owner":
        raise HTTPException(403, "A policy owner must perform this action")


def require_applicability_reviewer(actor):
    if not actor.get("can_determine_applicability"):
        raise HTTPException(403, "Your agency must explicitly grant applicability-review permission for this action")


def stamp_verification(data, actor):
    verification = dict(data.get("verification") or {"status": "unverified", "primary_source_location": None})
    if verification["status"] == "verified":
        require_applicability_reviewer(actor)
        verification.update(verified_by=actor["name"], verified_by_id=actor["id"], verified_at=now())
    else:
        verification.update(verified_by=None, verified_by_id=None, verified_at=None)
    data["verification"] = verification
    return data


def source_identity(data):
    """Repeated import is not a new verification action; explicit review is."""
    value = {**data, "verification": dict(data.get("verification") or {})}
    value["verification"].pop("verified_at", None)
    return value


def finding_authorities(db, tenant, finding):
    sources = [source_dict(require_row(db, "sources", tenant, piece["source_id"])) for piece in finding.get("evidence", [])]
    return [source for source in sources if source["kind"] == "external"] if finding.get("finding_type", "external_gap") == "external_gap" else sources


def validate_binding(source, as_of, program_or_contract=None):
    """Conservative data guards, not an automated determination of law."""
    if not is_us_authority(source.get("jurisdiction_id")):
        raise HTTPException(422, "This source is retained as non-US context, not US binding authority")
    if source.get("verification", {}).get("status") != "verified":
        raise HTTPException(422, "Binding determination requires a verified source revision pinned in this review")
    if source["authority_type"] == "court_or_ag":
        raise HTTPException(422, "Court and Attorney General material is flagged for agency review, not automatically binding")
    if source["authority_type"] in {"funding_condition", "agreement"} and not program_or_contract:
        raise HTTPException(422, "Funding conditions and agreements require the attached program or contract")
    if source["authority_type"] not in {"statute", "regulation", "executive_order", "internal_policy", "adopted_standard", "funding_condition", "agreement"}:
        raise HTTPException(422, "Research, guidance and voluntary standards cannot establish binding authority")
    if source["authority_type"] == "adopted_standard" and not source.get("adoption_reference"):
        raise HTTPException(422, "An adopted standard needs an adoption reference and scope")
    if source["legal_status"] != "in_force":
        raise HTTPException(422, "Binding determination needs an in-force source")
    start = source.get("effective_from")
    if not start:
        raise HTTPException(422, "Confirm the effective date before a binding determination")
    if as_of < start or (source.get("effective_to") and as_of >= source["effective_to"]):
        raise HTTPException(422, "The source is not effective on the review's as-of date")


def create_app(db_path=".compass/development.sqlite3", demo=False, run_worker=False):
    store = Store(db_path)
    if demo:
        seed(store)
    monitoring = MonitoringService(store)

    @asynccontextmanager
    async def lifespan(app):
        async def work():
            while True:
                try:
                    await asyncio.to_thread(monitoring.tick)
                except Exception:
                    # Jobs retain their own error/retry state. A scheduler error
                    # must not disable the request server or silently stop polling.
                    import logging
                    logging.getLogger("compass.worker").exception("Local monitoring tick failed")
                await asyncio.sleep(5)

        task = asyncio.create_task(work()) if run_worker and demo else None
        yield
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    app = FastAPI(title="COMPASS policy review", version=__version__, docs_url="/api/docs", redoc_url=None, lifespan=lifespan)
    app.state.store = store
    app.state.demo = demo
    app.state.monitoring = monitoring
    # This milestone is intentionally local. Public deployment needs real identity,
    # deployment host policy, TLS, and the documented production readiness work.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"])

    @app.middleware("http")
    async def browser_guards(request, call_next):
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            if origin:
                parsed = urlsplit(origin)
                if parsed.scheme not in {"http", "https"} or parsed.netloc != request.url.netloc:
                    return JSONResponse({"detail": "Cross-origin mutations are not permitted"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        if request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store"
        return response

    def current_actor(request: Request):
        if not demo:
            # A database restored from a demo must not carry its synthetic
            # sessions into an instance without configured production identity.
            raise HTTPException(401, "Production identity is not configured")
        token = request.cookies.get(COOKIE)
        if not token:
            raise HTTPException(401, "Sign in to a workspace")
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        with store.connect() as db:
            row = db.execute(
                """SELECT u.id,u.name,s.tenant_id,m.role,m.can_determine_applicability,t.name AS workspace_name,t.jurisdiction_id
                FROM sessions s JOIN users u ON u.id=s.user_id
                JOIN memberships m ON m.tenant_id=s.tenant_id AND m.user_id=s.user_id
                JOIN tenants t ON t.id=s.tenant_id
                WHERE s.token_hash=? AND s.expires_at>?""", (token_hash, now()),
            ).fetchone()
        if row is None:
            raise HTTPException(401, "Session expired; sign in again")
        if not is_us_authority(row["jurisdiction_id"]):
            raise HTTPException(422, "Workspace jurisdiction must be a US state, DC, or US-FED identifier")
        return dict(row)

    @app.get("/api/health")
    def health():
        with store.connect() as db:
            db.execute("SELECT 1").fetchone()
        return {"status": "ok", "version": __version__, "mode": "synthetic_demo" if demo else "unconfigured", "production_ready": False, "external_database_connected": False, "automated_analysis": True, "analysis_method": ENGINE_VERSION, "language_model_connected": False, "background_worker": run_worker and demo}

    @app.get("/api/demo/personas")
    def personas():
        if not demo:
            raise HTTPException(404, "Not found")
        return {"personas": [{"id": key, **{k: value[k] for k in ("name", "workspace", "role")}} for key, value in PERSONAS.items()]}

    @app.post("/api/demo/session")
    def demo_session(payload: DemoSessionInput, request: Request, response: Response):
        if not demo:
            raise HTTPException(404, "Not found")
        person = PERSONAS.get(payload.persona)
        if person is None:
            raise HTTPException(404, "Unknown demonstration persona")
        token = secrets.token_urlsafe(32)
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=8)).isoformat()
        with store.connect(write=True) as db:
            # Rotate rather than accumulate a browser's prior session.
            old = request.cookies.get(COOKIE)
            if old:
                db.execute("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256(old.encode()).hexdigest(),))
            db.execute("DELETE FROM sessions WHERE expires_at<=?", (now(),))
            db.execute("INSERT INTO sessions VALUES(?,?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), payload.persona, person["tenant_id"], expires_at))
            actor = {"id": payload.persona, "name": person["name"], "tenant_id": person["tenant_id"]}
            audit(db, actor, "session.started", "workspace", person["tenant_id"], {"demo": True})
        response.set_cookie(COOKIE, token, httponly=True, samesite="strict", secure=False, max_age=8 * 60 * 60)
        return {"user": {"id": payload.persona, "name": person["name"]}, "workspace": {"id": person["tenant_id"], "name": person["workspace"], "jurisdiction_id": person["jurisdiction_id"], "role": person["role"]}, "demo": True}

    @app.post("/api/logout")
    def logout(request: Request, response: Response, actor=Depends(current_actor)):
        token_hash = hashlib.sha256(request.cookies[COOKIE].encode()).hexdigest()
        with store.connect(write=True) as db:
            db.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash,))
            audit(db, actor, "session.ended", "workspace", actor["tenant_id"], {})
        response.delete_cookie(COOKIE)
        return {"ok": True}

    @app.get("/api/session")
    def session(actor=Depends(current_actor)):
        return {"user": {"id": actor["id"], "name": actor["name"]}, "workspace": workspace(actor), "demo": demo}

    @app.get("/api/memberships")
    def memberships(actor=Depends(current_actor)):
        with store.connect() as db:
            rows = db.execute("SELECT m.user_id,u.name,m.role,m.can_determine_applicability FROM memberships m JOIN users u ON u.id=m.user_id WHERE m.tenant_id=? ORDER BY u.name", (actor["tenant_id"],)).fetchall()
        return {"memberships": [{**dict(row), "can_determine_applicability": bool(row["can_determine_applicability"])} for row in rows]}

    @app.patch("/api/memberships/{user_id}")
    def change_membership(user_id: str, payload: MembershipInput, actor=Depends(current_actor)):
        with store.connect(write=True) as db:
            row = db.execute("SELECT * FROM memberships WHERE tenant_id=? AND user_id=?", (actor["tenant_id"], user_id)).fetchone()
            if row is None:
                raise HTTPException(404, "Not found")
            require_owner(actor)
            previous = bool(row["can_determine_applicability"])
            if previous != payload.can_determine_applicability:
                db.execute("UPDATE memberships SET can_determine_applicability=? WHERE tenant_id=? AND user_id=?", (int(payload.can_determine_applicability), actor["tenant_id"], user_id))
                audit(db, actor, "membership.applicability_permission_changed", "membership", user_id, {"previous": previous, "current": payload.can_determine_applicability})
        return {"user_id": user_id, "can_determine_applicability": payload.can_determine_applicability}

    @app.get("/api/preferences")
    def preferences(actor=Depends(current_actor)):
        with store.connect() as db:
            row = db.execute("SELECT view_mode FROM preferences WHERE tenant_id=? AND user_id=?", (actor["tenant_id"], actor["id"])).fetchone()
        return {"view_mode": row["view_mode"] if row else "simple"}

    @app.put("/api/preferences")
    def save_preferences(payload: PreferencesInput, actor=Depends(current_actor)):
        with store.connect(write=True) as db:
            db.execute("INSERT INTO preferences VALUES(?,?,?) ON CONFLICT(tenant_id,user_id) DO UPDATE SET view_mode=excluded.view_mode", (actor["tenant_id"], actor["id"], payload.view_mode))
        return payload.model_dump()

    @app.get("/api/settings")
    def settings(actor=Depends(current_actor)):
        with store.connect() as db:
            return get_settings(db, actor["tenant_id"])

    @app.put("/api/settings")
    def save_settings(payload: AnalysisSettings, actor=Depends(current_actor)):
        require_owner(actor)
        tenant = actor["tenant_id"]
        data = payload.model_dump(mode="json")
        with store.connect(write=True) as db:
            previous = get_settings(db, tenant)
            db.execute("INSERT INTO workspace_settings VALUES(?,?,?) ON CONFLICT(tenant_id) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at", (tenant, canonical(data), now()))
            if previous != data:
                audit(db, actor, "settings.updated", "workspace", tenant, {"previous": previous, "current": data})
            if previous != data:
                monitoring.cancel_pending(tenant, db=db)
                if data["monitoring"]["context_changes"]:
                    monitoring.enqueue(tenant, actor, "context_changed", db=db)
        return data

    @app.get("/api/context")
    def context(actor=Depends(current_actor)):
        with store.connect() as db:
            return get_context(db, actor["tenant_id"])

    @app.put("/api/context")
    def save_context(payload: ContextInput, actor=Depends(current_actor)):
        require_owner(actor)
        tenant = actor["tenant_id"]
        data = payload.model_dump(mode="json")
        with store.connect(write=True) as db:
            previous = get_context(db, tenant)
            db.execute("INSERT INTO workspace_context VALUES(?,?,?) ON CONFLICT(tenant_id) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at", (tenant, canonical(data), now()))
            controls = get_settings(db, tenant)
            if previous != data:
                audit(db, actor, "context.updated", "workspace", tenant, {"previous": previous, "current": data})
            if previous != data:
                monitoring.cancel_pending(tenant, db=db)
                if controls["monitoring"]["context_changes"]:
                    monitoring.enqueue(tenant, actor, "context_changed", db=db)
        return data

    @app.get("/api/insights")
    def insights(run_id: str | None = None, actor=Depends(current_actor)):
        return monitoring.insights(actor["tenant_id"], run_id=run_id)

    @app.get("/api/monitoring")
    def monitoring_status(actor=Depends(current_actor)):
        return monitoring.status(actor["tenant_id"])

    @app.post("/api/monitoring/check")
    def check_now(actor=Depends(current_actor)):
        return monitoring.check(actor["tenant_id"], actor)

    @app.post("/api/jobs/{job_id}/retry")
    def retry_job(job_id: str, payload: RetryInput | None = None, actor=Depends(current_actor)):
        # The scoped lookup occurs before the role check, so another office's
        # object is always hidden, including from reviewers.
        monitoring.get_job(actor["tenant_id"], job_id)
        require_owner(actor)
        choice = payload or RetryInput()
        return monitoring.retry(actor["tenant_id"], actor, job_id, reset=choice.reset, rationale=choice.rationale)

    @app.post("/api/notices/{notice_id}/read")
    def read_notice(notice_id: str, actor=Depends(current_actor)):
        return monitoring.read_notice(actor["tenant_id"], notice_id)

    @app.get("/api/dashboard")
    def dashboard(actor=Depends(current_actor)):
        tenant = actor["tenant_id"]
        with store.connect() as db:
            profile_row = db.execute("SELECT profile,profile_hash FROM tenants WHERE id=?", (tenant,)).fetchone()
            sources = [source_dict(r) for r in db.execute("SELECT * FROM sources WHERE tenant_id=? ORDER BY created_at DESC,id", (tenant,))]
            runs = [item_dict(r) for r in db.execute("SELECT * FROM runs WHERE tenant_id=? ORDER BY created_at DESC,id", (tenant,))]
            findings = [item_dict(r) for r in db.execute("SELECT * FROM findings WHERE tenant_id=? ORDER BY created_at DESC,id", (tenant,))]
            events = [audit_dict(r) for r in db.execute("SELECT * FROM audit WHERE tenant_id=? ORDER BY id DESC LIMIT 20", (tenant,))]
        return {
            "workspace": workspace(actor), "profile": {**json.loads(profile_row["profile"]), "hash": profile_row["profile_hash"]},
            "counts": {"sources": len(sources), "runs": len(runs), "findings": len(findings), "pending": sum(f["status"] in {"pending", "needs_information"} for f in findings), "accepted": sum(f["status"] == "accepted" for f in findings)},
            "sources": sources, "runs": runs, "findings": findings, "audit": events, "coverage": COVERAGE,
        }

    @app.get("/api/sources")
    def sources(actor=Depends(current_actor)):
        with store.connect() as db:
            return {"sources": [source_dict(r) for r in db.execute("SELECT * FROM sources WHERE tenant_id=? ORDER BY created_at DESC,id", (actor["tenant_id"],))]}

    @app.get("/api/sources/{source_id}")
    def source(source_id: str, actor=Depends(current_actor)):
        with store.connect() as db:
            return source_dict(require_row(db, "sources", actor["tenant_id"], source_id))

    @app.post("/api/sources", status_code=201)
    def add_source(payload: SourceInput, response: Response, actor=Depends(current_actor)):
        if payload.kind == "instrument" and payload.jurisdiction_id != actor["jurisdiction_id"]:
            raise HTTPException(422, "Internal instruments must belong to the workspace's jurisdiction")
        if payload.legal_status == "in_force":
            require_applicability_reviewer(actor)
        data = stamp_verification(payload.model_dump(mode="json"), actor)
        content_hash = digest(data)
        tenant = actor["tenant_id"]
        with store.connect(write=True) as db:
            if payload.replaces_source_id:
                prior = source_dict(require_row(db, "sources", tenant, payload.replaces_source_id))
                if prior["kind"] != payload.kind or prior["jurisdiction_id"] != payload.jurisdiction_id:
                    raise HTTPException(422, "A replacement must retain the source role and jurisdiction")
                if payload.source_key and prior.get("source_key") and prior["source_key"] != payload.source_key:
                    raise HTTPException(422, "A replacement must retain the stable source identifier")
                if not payload.source_key and prior.get("source_key"):
                    data["source_key"] = prior["source_key"]
                    content_hash = digest(data)
                if prior["legal_status"] != payload.legal_status:
                    require_applicability_reviewer(actor)
            existing = db.execute("SELECT * FROM sources WHERE tenant_id=? AND content_hash=?", (tenant, content_hash)).fetchone()
            if not existing and data["verification"]["status"] == "verified":
                existing = next((row for row in db.execute("SELECT * FROM sources WHERE tenant_id=?", (tenant,)) if source_identity(json.loads(row["payload"])) == source_identity(data)), None)
            if existing:
                response.status_code = 200
                return source_dict(existing)
            source_id = new_id()
            db.execute("INSERT INTO sources VALUES(?,?,?,?,?)", (source_id, tenant, canonical(data), content_hash, now()))
            audit(db, actor, "source.created", "source", source_id, {"hash": content_hash, "kind": data["kind"]})
            result = source_dict(require_row(db, "sources", tenant, source_id))
            controls = get_settings(db, tenant)
            if controls["monitoring"]["source_changes"]:
                monitoring.enqueue(tenant, actor, "source_changed", db=db)
        return result

    @app.patch("/api/sources/{source_id}/review", status_code=201)
    def review_source(source_id: str, payload: SourceReviewInput, response: Response, actor=Depends(current_actor)):
        with store.connect(write=True) as db:
            prior = source_dict(require_row(db, "sources", actor["tenant_id"], source_id))
            require_applicability_reviewer(actor)
            data = {key: value for key, value in prior.items() if key not in {"id", "hash", "created_at"}}
            data.update(verification=payload.verification.model_dump(mode="json"), legal_status=payload.legal_status, replaces_source_id=source_id)
            try:
                data = SourceInput.model_validate(data).model_dump(mode="json")
            except ValidationError as error:
                raise HTTPException(422, "Historical source metadata does not meet current validation. Preserve this snapshot and import a corrected source revision with an eligible identifier and provenance.") from error
            data = stamp_verification(data, actor)
            existing = db.execute("SELECT * FROM sources WHERE tenant_id=? AND content_hash=?", (actor["tenant_id"], digest(data))).fetchone()
            if existing:
                response.status_code = 200
                return source_dict(existing)
            revised_id = new_id()
            db.execute("INSERT INTO sources VALUES(?,?,?,?,?)", (revised_id, actor["tenant_id"], canonical(data), digest(data), now()))
            audit(db, actor, "source.reviewed", "source", source_id, {"revised_source_id": revised_id, "previous_legal_status": prior["legal_status"], "current_legal_status": data["legal_status"], "previous_verification": prior.get("verification", {"status": "unverified"}), "current_verification": data["verification"], "rationale": payload.rationale})
            monitoring.enqueue(actor["tenant_id"], actor, "source_changed", db=db)
            return source_dict(require_row(db, "sources", actor["tenant_id"], revised_id))

    @app.get("/api/runs")
    def runs(actor=Depends(current_actor)):
        with store.connect() as db:
            return {"runs": [item_dict(r) for r in db.execute("SELECT * FROM runs WHERE tenant_id=? ORDER BY created_at DESC,id", (actor["tenant_id"],))]}

    @app.post("/api/runs", status_code=201)
    def add_run(payload: RunInput, actor=Depends(current_actor)):
        if len(set(payload.source_ids)) != len(payload.source_ids):
            raise HTTPException(422, "Select each source only once")
        tenant = actor["tenant_id"]
        with store.connect(write=True) as db:
            selected = [source_dict(require_row(db, "sources", tenant, key)) for key in payload.source_ids]
            if not any(source["kind"] == "instrument" for source in selected):
                raise HTTPException(422, "A review needs at least one internal instrument")
            profile_row = db.execute("SELECT profile,profile_hash FROM tenants WHERE id=?", (tenant,)).fetchone()
            run_id = new_id()
            data = {**payload.model_dump(mode="json"), "profile": json.loads(profile_row["profile"]), "profile_hash": profile_row["profile_hash"], "analysis_method": "manual", "coverage_status": "unverified", "code_version": __version__}
            db.execute("INSERT INTO runs VALUES(?,?,?,?)", (run_id, tenant, canonical(data), now()))
            for source_id in payload.source_ids:
                db.execute("INSERT INTO run_sources VALUES(?,?,?)", (tenant, run_id, source_id))
            audit(db, actor, "run.created", "run", run_id, {"profile_hash": data["profile_hash"], "source_ids": payload.source_ids, "analysis_method": "manual"})
            return item_dict(require_row(db, "runs", tenant, run_id))

    def run_detail(db, tenant, run_id):
        result = item_dict(require_row(db, "runs", tenant, run_id))
        result["sources"] = [source_dict(require_row(db, "sources", tenant, key)) for key in result["source_ids"]]
        result["findings"] = [item_dict(row) for row in db.execute("SELECT * FROM findings WHERE tenant_id=? AND run_id=? ORDER BY created_at,id", (tenant, run_id))]
        return result

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str, actor=Depends(current_actor)):
        with store.connect() as db:
            return run_detail(db, actor["tenant_id"], run_id)

    @app.post("/api/runs/{run_id}/analyze")
    def analyze_run(run_id: str, actor=Depends(current_actor)):
        with store.connect() as db:
            require_row(db, "runs", actor["tenant_id"], run_id)
        return monitoring.analyze_run(actor["tenant_id"], actor, run_id)

    @app.get("/api/runs/{run_id}/brief")
    def review_brief(run_id: str, actor=Depends(current_actor)):
        with store.connect() as db:
            run = run_detail(db, actor["tenant_id"], run_id)
            analyses = monitoring.analyses_for_run(actor["tenant_id"], run_id, db=db)
        lines = ["COMPASS — Policy review brief", run["title"], f"As of {run['as_of']}", "", "Scope and limitations", run["coverage_note"], COVERAGE["message"], "", "Findings"]
        for finding in run["findings"]:
            lines.extend([f"- {finding['summary']} [{finding['status']}]", finding["rationale"], f"Applicability: {finding['applicability']['determination']}"])
            for evidence in finding["evidence"]:
                lines.append(f"  {evidence['title']} — {evidence['location']}: {evidence['quote']}")
            if finding.get("assignment"):
                lines.append(f"  Follow-up: {finding['assignment']['assignee']}; due {finding['assignment'].get('due_date') or 'not set'}")
            if finding.get("decision"):
                lines.append(f"  Decision by {finding['decision']['decided_by']}: {finding['decision']['rationale']}")
        if not run["findings"]:
            lines.append("No owner findings recorded. This does not establish that there are no gaps.")
        if analyses:
            latest = analyses[-1]
            lines.extend(["", "Rule-based analysis suggestions — owner review needed"])
            for feature, section in latest["features"].items():
                lines.append(f"{feature.replace('_', ' ').title()}: {section['summary']}")
                for item in section["items"]:
                    lines.append(f"- {item['title']}: {item['detail']}")
                    sources_by_id = {source["id"]: source for source in latest.get("evidence_sources", [])}
                    for piece in item.get("evidence", []):
                        cited = sources_by_id.get(piece["source_id"], {})
                        lines.append(f"  {cited.get('title', piece['source_id'])} — {piece['location']}: {piece['quote']}")
            lines.extend(latest.get("warnings", []))
        lines.extend(["", "Sources"])
        lines.extend(f"- {s['title']} (version {s['version']}) {s.get('source_url') or 'Locally supplied text'}" for s in run["sources"])
        return Response("\n".join(lines), media_type="text/plain", headers={"Content-Disposition": f'attachment; filename="compass-brief-{run["id"]}.txt"'})

    @app.get("/api/runs/{run_id}/export")
    def export_run(run_id: str, actor=Depends(current_actor)):
        tenant = actor["tenant_id"]
        with store.connect() as db:
            run = run_detail(db, tenant, run_id)
            related = {run_id, *run["source_ids"], *(f["id"] for f in run["findings"])}
            events = [audit_dict(row) for row in db.execute("SELECT * FROM audit WHERE tenant_id=? ORDER BY id", (tenant,)) if row["entity_id"] in related]
            analyses = monitoring.analyses_for_run(tenant, run_id, db=db)
        run_sources = run.pop("sources")
        findings = run.pop("findings")
        profile = {**run["profile"], "hash": run["profile_hash"]}
        bundle = {"schema_version": 2, "run": run, "profile": profile, "sources": run_sources, "findings": findings, "audit": events, "analysis_method": run.get("analysis_method", "manual"), "analyses": analyses, "coverage": COVERAGE}
        # Always derive the filename from the verified entity, not request text.
        return Response(canonical(bundle), media_type="application/json", headers={"Content-Disposition": f'attachment; filename="compass-review-{run["id"]}.json"'})

    @app.get("/api/findings/{finding_id}")
    def get_finding(finding_id: str, actor=Depends(current_actor)):
        with store.connect() as db:
            return item_dict(require_row(db, "findings", actor["tenant_id"], finding_id))

    @app.post("/api/runs/{run_id}/findings", status_code=201)
    def add_finding(run_id: str, payload: FindingInput, actor=Depends(current_actor)):
        tenant = actor["tenant_id"]
        with store.connect(write=True) as db:
            run = item_dict(require_row(db, "runs", tenant, run_id))
            evidence = []
            for piece in payload.evidence:
                source = source_dict(require_row(db, "sources", tenant, piece.source_id))
                if (payload.instrument_source_id == piece.source_id and source["kind"] != "instrument") or (payload.external_source_id == piece.source_id and source["kind"] != "external"):
                    raise HTTPException(422, "Evidence source kind does not match its legacy role")
                if piece.source_id not in run["source_ids"]:
                    raise HTTPException(422, "Evidence must belong to this run's pinned inputs")
                if piece.quote not in source["text"]:
                    raise HTTPException(422, "The quote must be an exact excerpt from its source")
                evidence.append({**piece.model_dump(), "title": source["title"], "kind": source["kind"]})
            if payload.finding_type == "external_gap" and {piece["kind"] for piece in evidence} != {"instrument", "external"}:
                raise HTTPException(422, "An external gap needs instrument and external-source passages")
            if payload.finding_type == "internal_conflict" and any(piece["kind"] != "instrument" for piece in evidence):
                raise HTTPException(422, "An internal conflict needs at least two instrument passages")
            if len({(piece["source_id"], piece["quote"]) for piece in evidence}) != len(evidence):
                raise HTTPException(422, "Do not duplicate the same evidence passage")
            for source_id in payload.search_source_ids:
                require_row(db, "sources", tenant, source_id)
                if source_id not in run["source_ids"]:
                    raise HTTPException(422, "Searched sources must belong to this run's pinned inputs")
            finding_id = new_id()
            data = {"run_id": run_id, "summary": payload.summary, "category": payload.category, "severity": payload.severity, "rationale": payload.rationale, "finding_type": payload.finding_type, "status": "pending", "analysis_method": "manual", "applicability": {"determination": "unknown", "rationale": "Needs agency applicability review.", "authority_relied_on": None, "scope_complete": False, "reviewed_by": None, "reviewed_at": None}, "evidence": evidence, "search_source_ids": payload.search_source_ids, "search_description": payload.search_description, "program_or_contract": payload.program_or_contract, "concentrated_harm": payload.concentrated_harm, "irreversible": payload.irreversible}
            internal_id = next((piece["source_id"] for piece in evidence if piece["kind"] == "instrument"), None)
            external_id = next((piece["source_id"] for piece in evidence if piece["kind"] == "external"), None)
            db.execute("INSERT INTO findings VALUES(?,?,?,?,?,?,?)", (finding_id, tenant, run_id, internal_id, external_id, canonical(data), now()))
            audit(db, actor, "finding.created", "finding", finding_id, {"run_id": run_id, "summary": data["summary"], "finding_type": payload.finding_type})
            monitoring.enqueue(tenant, actor, "workflow_changed", db=db)
            return item_dict(require_row(db, "findings", tenant, finding_id))

    @app.post("/api/findings/{finding_id}/applicability")
    def set_applicability(finding_id: str, payload: ApplicabilityInput, actor=Depends(current_actor)):
        tenant = actor["tenant_id"]
        with store.connect(write=True) as db:
            row = require_row(db, "findings", tenant, finding_id)
            finding = item_dict(row)
            if payload.determination in {"binding", "conditional"} or payload.scope_complete:
                require_applicability_reviewer(actor)
            elif actor["role"] != "owner" and not actor.get("can_determine_applicability"):
                raise HTTPException(403, "An owner or appointed applicability reviewer must record applicability")
            if payload.scope_complete and finding.get("finding_type", "external_gap") != "absence":
                raise HTTPException(422, "Completeness confirmation belongs to an absence finding")
            if payload.scope_complete:
                run = item_dict(require_row(db, "runs", tenant, finding["run_id"]))
                if set(finding.get("search_source_ids", [])) != set(run["source_ids"]):
                    raise HTTPException(422, "Completeness confirmation requires searching every source in the declared pinned review corpus")
            if payload.determination in {"binding", "conditional"}:
                if finding.get("evidence_gaps"):
                    raise HTTPException(422, "Resolve imported evidence gaps in a supported new finding before determining a duty")
                run = item_dict(require_row(db, "runs", tenant, row["run_id"]))
                references = finding_authorities(db, tenant, finding)
                if not references:
                    raise HTTPException(422, "A duty determination needs exact supporting passages; an absence search alone is not a legal duty")
                for reference in references:
                    if not is_us_authority(reference.get("jurisdiction_id")):
                        raise HTTPException(422, "Non-US context cannot establish a binding or conditional US duty; cite the applicable US authority or agreement")
                    if reference["authority_type"] == "court_or_ag":
                        raise HTTPException(422, "Court and Attorney General material is flagged for agency review, not automatically binding or conditional")
                    if payload.determination == "binding":
                        validate_binding(reference, run["as_of"], finding.get("program_or_contract"))
            previous = finding["applicability"]
            finding["applicability"] = {**payload.model_dump(), "reviewed_by": actor["name"], "reviewed_by_id": actor["id"], "reviewed_at": now(), "reviewer_had_applicability_permission": bool(actor.get("can_determine_applicability")), "completeness_confirmed_by": actor["id"] if payload.scope_complete else None}
            previous_status = finding["status"]
            finding["status"] = "pending"
            previous_decision = finding.pop("decision", None)
            data = {key: value for key, value in finding.items() if key not in {"id", "created_at"}}
            db.execute("UPDATE findings SET payload=? WHERE tenant_id=? AND id=?", (canonical(data), tenant, finding_id))
            audit(db, actor, "applicability.reviewed", "finding", finding_id, {"run_id": finding["run_id"], "previous": previous, "current": finding["applicability"], "invalidated_status": previous_status, "invalidated_decision": previous_decision})
            monitoring.enqueue(tenant, actor, "workflow_changed", db=db)
            return item_dict(require_row(db, "findings", tenant, finding_id))

    @app.post("/api/findings/{finding_id}/decisions")
    def decide(finding_id: str, payload: DecisionInput, actor=Depends(current_actor)):
        tenant = actor["tenant_id"]
        with store.connect(write=True) as db:
            finding = item_dict(require_row(db, "findings", tenant, finding_id))
            require_owner(actor)
            if payload.outcome == "accept" and finding.get("evidence_gaps"):
                raise HTTPException(409, "Resolve imported evidence gaps in a supported new finding before acceptance")
            premise = finding["applicability"]
            if payload.outcome == "accept":
                if not premise.get("reviewed_by_id") or len(premise.get("authority_relied_on") or "") < 3 or len(premise.get("rationale") or "") < 30:
                    raise HTTPException(409, "Record a fresh applicability review under the current verification controls before acceptance")
                if premise["determination"] in {"binding", "conditional"}:
                    if not premise.get("reviewer_had_applicability_permission"):
                        raise HTTPException(409, "An appointed applicability reviewer must record the duty determination before acceptance")
                    run = item_dict(require_row(db, "runs", tenant, finding["run_id"]))
                    references = finding_authorities(db, tenant, finding)
                    if not references:
                        raise HTTPException(409, "A duty determination needs exact supporting authority passages before acceptance")
                    for reference in references:
                        if not is_us_authority(reference.get("jurisdiction_id")) or reference["authority_type"] == "court_or_ag":
                            raise HTTPException(409, "The pinned source does not establish an eligible US duty")
                        if premise["determination"] == "binding":
                            validate_binding(reference, run["as_of"], finding.get("program_or_contract"))
            if payload.outcome == "accept" and finding.get("finding_type") == "absence" and not (finding["applicability"].get("scope_complete") and finding["applicability"].get("completeness_confirmed_by")):
                raise HTTPException(409, "An appointed applicability reviewer must confirm the complete in-scope search set before accepting an absence")
            if payload.outcome == "accept" and finding["applicability"]["determination"] in {"unknown", "not_applicable"}:
                raise HTTPException(409, "Resolve applicability before accepting this finding")
            finding["status"] = {"accept": "accepted", "reject": "rejected", "needs_information": "needs_information"}[payload.outcome]
            finding["decision"] = {**payload.model_dump(), "decided_by": actor["name"], "decided_at": now()}
            data = {k: v for k, v in finding.items() if k not in {"id", "created_at"}}
            db.execute("UPDATE findings SET payload=? WHERE tenant_id=? AND id=?", (canonical(data), tenant, finding_id))
            audit(db, actor, "decision.recorded", "finding", finding_id, {"run_id": finding["run_id"], **finding["decision"]})
            monitoring.enqueue(tenant, actor, "workflow_changed", db=db)
            return item_dict(require_row(db, "findings", tenant, finding_id))

    @app.put("/api/findings/{finding_id}/assignment")
    def assign_finding(finding_id: str, payload: AssignmentInput, actor=Depends(current_actor)):
        tenant = actor["tenant_id"]
        with store.connect(write=True) as db:
            finding = item_dict(require_row(db, "findings", tenant, finding_id))
            require_owner(actor)
            finding["assignment"] = {**payload.model_dump(mode="json"), "assigned_by": actor["name"], "assigned_at": now()}
            data = {k: v for k, v in finding.items() if k not in {"id", "created_at"}}
            db.execute("UPDATE findings SET payload=? WHERE tenant_id=? AND id=?", (canonical(data), tenant, finding_id))
            audit(db, actor, "finding.assigned", "finding", finding_id, finding["assignment"])
            monitoring.enqueue(tenant, actor, "workflow_changed", db=db)
            return item_dict(require_row(db, "findings", tenant, finding_id))

    @app.post("/api/import/pdf-text")
    async def preview_pdf(request: Request, actor=Depends(current_actor)):
        if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/pdf":
            raise HTTPException(415, "Send PDF bytes with Content-Type application/pdf")
        chunks, size = [], 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > MAX_PDF_BYTES:
                raise HTTPException(413, "Choose a PDF no larger than 15 MiB")
            chunks.append(chunk)
        try:
            # Preview is bounded and does not create a source or imply review.
            return await asyncio.to_thread(extract_pdf, b"".join(chunks))
        except PDFImportError as error:
            return JSONResponse({"detail": str(error), "failed_pages": error.failed_pages,
                                 "page_count": error.page_count}, status_code=422)

    @app.post("/api/runs/{run_id}/method-findings", status_code=201)
    def import_method_findings(run_id: str, payload: dict, actor=Depends(current_actor)):
        tenant = actor["tenant_id"]
        with store.connect(write=True) as db:
            run = item_dict(require_row(db, "runs", tenant, run_id))
            if actor["jurisdiction_id"] != "US-GA":
                raise HTTPException(422, "This producer contains Georgia case-study findings; use a Georgia workspace")
            try:
                bundle = validate_import_bundle(payload)
            except ValueError as error:
                raise HTTPException(422, str(error)) from error
            prior = [item_dict(row) for row in db.execute("SELECT * FROM findings WHERE tenant_id=? AND run_id=?", (tenant, run_id))]
            known = {item.get("original_finding_id") for item in prior
                     if item.get("origin") == "method_run" and item.get("method_run_id") == bundle["run_id"]
                     and item.get("provenance") == bundle["provenance"]}
            imported, skipped = [], []
            for item in bundle["findings"]:
                if item["original_finding_id"] in known:
                    skipped.append(item["original_finding_id"])
                    continue
                finding_id = new_id()
                data = {**item, "run_id": run_id, "origin": "method_run", "method_run_id": bundle["run_id"],
                        "provenance": bundle["provenance"], "analysis_method": "method_import",
                        "applicability": {"determination": "unknown", "rationale": "Historical suggestion; current applicability and evidence remain unreviewed.",
                                          "authority_relied_on": None, "reviewed_by": None, "reviewed_at": None},
                        "scope_complete": False}
                db.execute("INSERT INTO findings VALUES(?,?,?,?,?,?,?)", (finding_id, tenant, run_id, None, None, canonical(data), now()))
                audit(db, actor, "finding.imported", "finding", finding_id,
                      {"run_id": run["id"], "method_run_id": bundle["run_id"], "original_finding_id": item["original_finding_id"],
                       "origin": "method_run", "provenance": bundle["provenance"], "status": "pending"})
                imported.append(item_dict(require_row(db, "findings", tenant, finding_id)))
            if imported:
                monitoring.enqueue(tenant, actor, "workflow_changed", db=db)
        return {"imported": imported, "skipped": skipped, "imported_count": len(imported),
                "skipped_count": len(skipped), "import_report": bundle["import_report"]}

    @app.get("/api/audit")
    def get_audit(actor=Depends(current_actor)):
        with store.connect() as db:
            return {"events": [audit_dict(row) for row in db.execute("SELECT * FROM audit WHERE tenant_id=? ORDER BY id DESC LIMIT 500", (actor["tenant_id"],))]}

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC / "index.html")

    # Unknown API paths cannot silently become HTML successes.
    app.mount("/static", StaticFiles(directory=STATIC, check_dir=False), name="static")
    return app
