"""Input contracts. Applicability is a reviewed determination, never a score."""

from datetime import date
from typing import Annotated, Literal
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StringConstraints, field_validator, model_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


Jurisdiction = str
Determination = Literal["unknown", "binding", "conditional", "persuasive", "not_applicable"]


class SourceInput(Input):
    kind: Literal["instrument", "external"]
    title: str = Field(min_length=1, max_length=200)
    jurisdiction_id: Jurisdiction = Field(pattern=r"^[A-Z][A-Z0-9-]{1,31}$")
    version: str = Field(min_length=1, max_length=80)
    text: Annotated[str, StringConstraints(strip_whitespace=False, min_length=1, max_length=200_000)]
    authority_type: Literal[
        "statute", "regulation", "executive_order", "internal_policy", "adopted_standard",
        "voluntary_standard", "guidance", "research", "other",
    ]
    legal_status: Literal[
        "in_force", "adopted_not_effective", "draft", "guidance", "research", "repealed", "unknown",
    ]
    source_url: HttpUrl | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    adoption_reference: str | None = Field(default=None, max_length=2000)
    source_key: str | None = Field(default=None, min_length=1, max_length=200)
    replaces_source_id: str | None = Field(default=None, max_length=100)
    reference_keys: list[Annotated[str, StringConstraints(min_length=1, max_length=200)]] = Field(default_factory=list, max_length=100)
    topics: list[Annotated[str, StringConstraints(min_length=1, max_length=100)]] = Field(default_factory=list, max_length=50)
    reference_scope: Literal["private", "public"] = "private"

    @model_validator(mode="after")
    def valid_period(self):
        if not self.text.strip():
            raise ValueError("Source text cannot be only whitespace")
        if self.effective_from and self.effective_to and self.effective_to <= self.effective_from:
            raise ValueError("effective_to must follow effective_from (end date is exclusive)")
        return self


class RunInput(Input):
    title: str = Field(min_length=3, max_length=200)
    as_of: date
    source_ids: list[str] = Field(min_length=2, max_length=200)
    coverage_note: str = Field(min_length=1, max_length=4000)


class FindingInput(Input):
    summary: str = Field(min_length=5, max_length=500)
    category: Literal["missing_obligation", "conflict", "stale_reference", "public_commitment", "opportunity"]
    severity: Literal["low", "medium", "high", "critical"]
    rationale: str = Field(min_length=5, max_length=10_000)
    instrument_source_id: str
    external_source_id: str
    instrument_quote: Annotated[str, StringConstraints(strip_whitespace=False, min_length=1, max_length=10_000)]
    instrument_location: str = Field(min_length=1, max_length=500)
    external_quote: Annotated[str, StringConstraints(strip_whitespace=False, min_length=1, max_length=10_000)]
    external_location: str = Field(min_length=1, max_length=500)


class ApplicabilityInput(Input):
    determination: Determination
    rationale: str = Field(min_length=5, max_length=10_000)


class DecisionInput(Input):
    outcome: Literal["accept", "reject", "needs_information"]
    rationale: str = Field(min_length=5, max_length=10_000)


class DemoSessionInput(Input):
    persona: str = Field(max_length=100)


class PreferencesInput(Input):
    view_mode: Literal["simple", "advanced"] = "simple"


class AnalysisFeatures(Input):
    change_detection: bool = True
    obligations: bool = True
    citations: bool = True
    terminology: bool = True
    coverage: bool = True
    impact: bool = True
    language: bool = True
    deadlines: bool = True
    peer_research: bool = False


class MonitoringSettings(Input):
    enabled: bool = False
    source_changes: bool = True
    context_changes: bool = True
    effective_dates: bool = True
    check_interval_hours: int = Field(default=24, ge=1, le=168)
    digest_interval_days: int = Field(default=7, ge=1, le=30)
    timezone: str = Field(default="America/New_York", max_length=100)

    @field_validator("timezone")
    @classmethod
    def known_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError) as error:
            raise ValueError("Choose a valid IANA timezone") from error
        return value


class AnalysisSettings(Input):
    advanced_analysis: bool = True
    features: AnalysisFeatures = Field(default_factory=AnalysisFeatures)
    horizon_days: int = Field(default=30, ge=1, le=365)
    monitoring: MonitoringSettings = Field(default_factory=MonitoringSettings)


ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class AssetInput(Input):
    id: str = Field(default_factory=lambda: str(uuid4()), min_length=1, max_length=100)
    name: ShortText
    program: str = Field(default="", max_length=200)
    owner: str = Field(default="", max_length=200)
    source_keys: list[ShortText] = Field(default_factory=list, max_length=100)


class ContextInput(Input):
    topics: list[ShortText] = Field(default_factory=lambda: ["Governance", "Inventory", "Privacy", "Accessibility", "Procurement", "Security", "Human oversight"], max_length=50)
    programs: list[ShortText] = Field(default_factory=list, max_length=100)
    funding_conditions: list[Annotated[str, StringConstraints(min_length=1, max_length=1000)]] = Field(default_factory=list, max_length=100)
    assets: list[AssetInput] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def unique_assets(self):
        if len({a.id for a in self.assets}) != len(self.assets):
            raise ValueError("Inventory asset IDs must be unique")
        return self


class AssignmentInput(Input):
    assignee: str = Field(min_length=1, max_length=200)
    due_date: date | None = None


class RetryInput(Input):
    reset: bool = False
    rationale: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def reset_reason(self):
        if self.reset and len(self.rationale.strip()) < 5:
            raise ValueError("Describe the resolved issue before restarting an exhausted check")
        return self
