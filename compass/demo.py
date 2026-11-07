"""Synthetic fixtures only. These texts describe no real legal obligation."""

import json

from .store import audit, canonical, digest, new_id, now


PERSONAS = {
    "ga-owner": {"name": "Alex Morgan", "tenant_id": "demo-ga-office", "workspace": "Georgia Policy Office · Demo", "role": "owner", "jurisdiction_id": "US-GA"},
    "ga-reviewer": {"name": "Jordan Lee", "tenant_id": "demo-ga-office", "workspace": "Georgia Policy Office · Demo", "role": "reviewer", "jurisdiction_id": "US-GA"},
    "ga-peer-owner": {"name": "Casey Rivera", "tenant_id": "demo-ga-agency", "workspace": "Georgia Agency Workspace · Demo", "role": "owner", "jurisdiction_id": "US-GA"},
    "ca-owner": {"name": "Taylor Brooks", "tenant_id": "demo-ca-office", "workspace": "California Policy Office · Demo", "role": "owner", "jurisdiction_id": "US-CA"},
}


def seed(store):
    with store.connect(write=True) as db:
        for user_id, persona in PERSONAS.items():
            tenant = persona["tenant_id"]
            profile = {
                "jurisdiction_id": persona["jurisdiction_id"],
                "name": "Georgia" if persona["jurisdiction_id"] == "US-GA" else "California",
                "version": "demo-2", "status": "synthetic",
                "notice": "Synthetic demonstration configuration; not a legally approved jurisdiction profile.",
                "terms": {"covered_entity": "office"},
                "families": [{"local_name": "Demo policy", "canonical_tier": "binding_policy"}],
                "citation_patterns": [
                    r"\b(?:PS|SS|GS|PM)-\d{2}-\d{3}\b",
                    r"\bO\.C\.G\.A\.?\s*(?:§\s*)?\d+-\d+-\d+(?:\([^)]+\))*",
                ] if persona["jurisdiction_id"] == "US-GA" else [],
                "sentence_abbreviations": ["Ga."] if persona["jurisdiction_id"] == "US-GA" else [],
            }
            db.execute("INSERT OR IGNORE INTO tenants VALUES(?,?,?,?,?)", (tenant, persona["workspace"], persona["jurisdiction_id"], canonical(profile), digest(profile)))
            db.execute("INSERT OR IGNORE INTO users VALUES(?,?)", (user_id, persona["name"]))
            db.execute("INSERT OR IGNORE INTO memberships VALUES(?,?,?)", (tenant, user_id, persona["role"]))
            current = db.execute("SELECT profile FROM tenants WHERE id=?", (tenant,)).fetchone()
            previous = json.loads(current["profile"])
            if previous.get("status") == "synthetic" and previous.get("version") == "demo-1" and "citation_patterns" not in previous:
                # Upgrade only the original synthetic fixture. Saved runs/reports
                # contain their own profile copies and retain their old hashes.
                updated = {**previous, "version": "demo-2", "citation_patterns": profile["citation_patterns"], "sentence_abbreviations": previous.get("sentence_abbreviations", profile["sentence_abbreviations"])}
                db.execute("UPDATE tenants SET profile=?,profile_hash=? WHERE id=?", (canonical(updated), digest(updated), tenant))
                audit(db, {"id": user_id, "name": persona["name"], "tenant_id": tenant}, "profile.updated", "workspace", tenant, {"synthetic": True, "previous_hash": digest(previous), "current_hash": digest(updated), "reason": "Add explicit citation and abbreviation configuration; historical snapshots retained"})
            if db.execute("SELECT 1 FROM runs WHERE tenant_id=?", (tenant,)).fetchone():
                continue
            stamp = now()
            actor = {"id": user_id, "name": persona["name"], "tenant_id": tenant}
            internal = {
                "kind": "instrument", "title": "SYNTHETIC · AI governance policy", "jurisdiction_id": persona["jurisdiction_id"],
                "version": "demo-1", "text": "Demonstration text only; not real policy.\n\nSection 1. The office maintains an inventory of AI systems.\nSection 2. A policy lead reviews proposed changes.",
                "authority_type": "internal_policy", "legal_status": "in_force", "source_url": None,
                "effective_from": "2026-01-01", "effective_to": None, "adoption_reference": None,
            }
            external = {
                **internal, "kind": "external", "title": "SYNTHETIC · Annual inventory requirement",
                "text": "Demonstration text only; not a real statute.\n\nSection 4. The office shall review its AI inventory annually.\nSection 5. Research-only pilots are excluded from Section 4.",
                "authority_type": "statute",
            }
            source_ids = []
            for payload in (internal, external):
                source_id = new_id()
                source_ids.append(source_id)
                db.execute("INSERT INTO sources VALUES(?,?,?,?,?)", (source_id, tenant, canonical(payload), digest(payload), stamp))
            run_id = new_id()
            run = {
                "title": "AI inventory review · Synthetic example", "as_of": "2026-11-03", "profile": profile,
                "profile_hash": digest(profile), "source_ids": source_ids, "analysis_method": "manual",
                "coverage_note": "Two synthetic excerpts only. No real legal sources or external database are connected.",
                "coverage_status": "unverified", "code_version": "0.1.0",
            }
            db.execute("INSERT INTO runs VALUES(?,?,?,?)", (run_id, tenant, canonical(run), stamp))
            for source_id in source_ids:
                db.execute("INSERT INTO run_sources VALUES(?,?,?)", (tenant, run_id, source_id))
            finding_id = new_id()
            finding = {
                "run_id": run_id, "summary": "Confirm an annual review schedule for the AI inventory", "category": "missing_obligation", "severity": "medium",
                "rationale": "The selected internal excerpt has no review interval. The synthetic external excerpt specifies annual review and excludes research-only pilots. The policy owner must confirm scope and exceptions before accepting a gap.",
                "status": "pending", "analysis_method": "manual",
                "applicability": {"determination": "unknown", "rationale": "Scope and the research-only exception need owner review.", "reviewed_by": None, "reviewed_at": None},
                "evidence": [
                    {"source_id": source_ids[0], "title": internal["title"], "kind": "instrument", "quote": "The office maintains an inventory of AI systems.", "location": "Section 1"},
                    {"source_id": source_ids[1], "title": external["title"], "kind": "external", "quote": "The office shall review its AI inventory annually.", "location": "Section 4; exception in Section 5"},
                ],
            }
            db.execute("INSERT INTO findings VALUES(?,?,?,?,?,?,?)", (finding_id, tenant, run_id, *source_ids, canonical(finding), stamp))
            audit(db, actor, "demo.seeded", "run", run_id, {"synthetic": True})
