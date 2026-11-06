"""Workspace analysis choices are independent of each person's display mode."""

import json

from .models import AnalysisSettings, ContextInput


def get_settings(db, tenant_id):
    row = db.execute("SELECT payload FROM workspace_settings WHERE tenant_id=?", (tenant_id,)).fetchone()
    return AnalysisSettings.model_validate(json.loads(row["payload"]) if row else {}).model_dump(mode="json")


def get_context(db, tenant_id):
    row = db.execute("SELECT payload FROM workspace_context WHERE tenant_id=?", (tenant_id,)).fetchone()
    return ContextInput.model_validate(json.loads(row["payload"]) if row else {}).model_dump(mode="json")
