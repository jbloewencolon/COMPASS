"""Input contracts. Applicability is a reviewed determination, never a score."""

from datetime import date
from typing import Annotated, Literal
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StringConstraints, field_validator, model_validator

from .jurisdictions import is_us_authority


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


Jurisdiction = str
Determination = Literal["unknown", "binding", "conditional", "persuasive", "not_applicable"]
LegalStatus = Literal["in_force", "adopted_not_effective", "draft", "guidance", "research", "repealed", "unknown"]


class VerificationInput(Input):
    status: Literal["unverified", "verified", "disputed"] = "unverified"
    primary_source_location: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def primary_required(self):
        if self.status == "verified" and not self.primary_source_location:
            raise ValueError("A verified source requires the primary source location")
        return self


class PageSpan(Input):
    page: int = Field(ge=1, le=500)
    start: int = Field(ge=0)
    end: int = Field(gt=0)


class FailedPage(Input):
    page: int = Field(ge=1, le=500)
    reason: str = Field(min_length=1, max_length=1000)


class MembershipInput(Input):
    can_determine_applicability: bool


class SourceReviewInput(Input):
    verification: VerificationInput
    legal_status: LegalStatus
    rationale: str = Field(min_length=30, max_length=10_000)


class SourceInput(Input):
    kind: Literal["instrument", "external"]
    title: str = Field(min_length=1, max_length=200)
    jurisdiction_id: Jurisdiction = Field(pattern=r"^[A-Z][A-Z0-9-]{1,31}$")
    version: str = Field(min_length=1, max_length=80)
    text: Annotated[str, StringConstraints(strip_whitespace=False, min_length=1, max_length=200_000)]
    authority_type: Literal[
        "statute", "regulation", "executive_order", "internal_policy", "adopted_standard",
        "voluntary_standard", "guidance", "research", "other",
        "funding_condition", "agreement", "court_or_ag",
    ]
    legal_status: LegalStatus
    source_url: HttpUrl | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    adoption_reference: str | None = Field(default=None, max_length=2000)
    source_key: str | None = Field(default=None, min_length=1, max_length=200)
    replaces_source_id: str | None = Field(default=None, max_length=100)
    reference_keys: list[Annotated[str, StringConstraints(min_length=1, max_length=200)]] = Field(default_factory=list, max_length=100)
    topics: list[Annotated[str, StringConstraints(min_length=1, max_length=100)]] = Field(default_factory=list, max_length=50)
    reference_scope: Literal["private", "public"] = "private"
    verification: VerificationInput = Field(default_factory=VerificationInput)
    text_provenance: Literal["original", "extracted", "transcribed"] = "original"
    original_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    page_spans: list[PageSpan] = Field(default_factory=list, max_length=500)
    page_count: int | None = Field(default=None, ge=1, le=500)
    failed_pages: list[FailedPage] = Field(default_factory=list, max_length=500)

    @model_validator(mode="after")
    def valid_period(self):
        if not self.text.strip():
            raise ValueError("Source text cannot be only whitespace")
        if self.effective_from and self.effective_to and self.effective_to <= self.effective_from:
            raise ValueError("effective_to must follow effective_from (end date is exclusive)")
        if (self.kind == "instrument" or self.jurisdiction_id.startswith("US")) and not is_us_authority(self.jurisdiction_id):
            raise ValueError("Use a recognized US state, DC, or US-FED jurisdiction identifier")
        if self.text_provenance == "extracted" and not self.original_sha256:
            raise ValueError("Extracted text requires the original file SHA-256")
        if self.page_spans and (self.text_provenance != "extracted" or self.page_count is None or not self.original_sha256):
            raise ValueError("Page mappings require extracted text, page count, and the original file hash")
        pages, previous_end, previous_page = set(), 0, 0
        for span in self.page_spans:
            if span.start < previous_end or span.end <= span.start or span.end > len(self.text) or span.page <= previous_page or span.page > self.page_count:
                raise ValueError("Page mappings must be ordered nonoverlapping ranges within the preserved text")
            pages.add(span.page)
            previous_end, previous_page = span.end, span.page
        failures = [item.page for item in self.failed_pages]
        if failures and (self.page_count is None or len(failures) != len(set(failures)) or any(page > self.page_count or page in pages for page in failures)):
            raise ValueError("Failed-page records must identify distinct original pages outside successful mappings")
        if self.page_count and self.text_provenance == "extracted" and pages | set(failures) != set(range(1, self.page_count + 1)):
            raise ValueError("Every original PDF page must be mapped or explicitly reported as failed")
        return self


class RunInput(Input):
    title: str = Field(min_length=3, max_length=200)
    as_of: date
    source_ids: list[str] = Field(min_length=1, max_length=200)
    coverage_note: str = Field(min_length=1, max_length=4000)


class FindingEvidenceInput(Input):
    source_id: str = Field(min_length=1, max_length=100)
    quote: Annotated[str, StringConstraints(strip_whitespace=False, min_length=1, max_length=10_000)]
    location: str = Field(min_length=1, max_length=500)


class FindingInput(Input):
    summary: str = Field(min_length=5, max_length=500)
    category: Literal["missing_obligation", "conflict", "stale_reference", "public_commitment", "opportunity"]
    severity: Literal["low", "medium", "high", "critical"]
    rationale: str = Field(min_length=5, max_length=10_000)
    finding_type: Literal["external_gap", "internal_conflict", "absence"] = "external_gap"
    evidence: list[FindingEvidenceInput] = Field(default_factory=list, max_length=50)
    search_source_ids: list[str] = Field(default_factory=list, max_length=200)
    search_description: str | None = Field(default=None, max_length=4000)
    program_or_contract: str | None = Field(default=None, max_length=2000)
    concentrated_harm: bool | None = None
    irreversible: bool | None = None
    instrument_source_id: str | None = None
    external_source_id: str | None = None
    instrument_quote: Annotated[str | None, StringConstraints(strip_whitespace=False, min_length=1, max_length=10_000)] = None
    instrument_location: str | None = Field(default=None, min_length=1, max_length=500)
    external_quote: Annotated[str | None, StringConstraints(strip_whitespace=False, min_length=1, max_length=10_000)] = None
    external_location: str | None = Field(default=None, min_length=1, max_length=500)

    @model_validator(mode="after")
    def valid_structure(self):
        legacy = (self.instrument_source_id, self.external_source_id, self.instrument_quote, self.instrument_location, self.external_quote, self.external_location)
        if any(value is not None for value in legacy):
            if self.finding_type != "external_gap" or self.evidence or not all(legacy):
                raise ValueError("Use either a complete legacy source pair or the evidence list, not both")
            self.evidence = [FindingEvidenceInput(source_id=self.instrument_source_id, quote=self.instrument_quote, location=self.instrument_location), FindingEvidenceInput(source_id=self.external_source_id, quote=self.external_quote, location=self.external_location)]
        if self.finding_type == "absence":
            if self.evidence or not self.search_source_ids or len(set(self.search_source_ids)) != len(self.search_source_ids) or not self.search_description or len(self.search_description) < 30:
                raise ValueError("An absence needs distinct searched sources, a search description of at least 30 characters, and no invented quotation")
        elif len(self.evidence) < 2 or self.search_source_ids or self.search_description:
            raise ValueError("A gap or internal conflict needs at least two passages; absence-search fields are separate")
        return self


class ApplicabilityInput(Input):
    determination: Determination
    rationale: str = Field(min_length=30, max_length=10_000)
    authority_relied_on: str = Field(min_length=3, max_length=4000)
    scope_complete: bool = False


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
