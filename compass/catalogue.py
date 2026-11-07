"""Load one versioned method catalogue without a YAML runtime dependency.

The .yaml file deliberately uses the JSON subset of YAML. Structural validation
does not establish policy approval or legal correctness. Semantic coverage stays
a manual method until its separate agency-review and implementation gates pass.
"""

from datetime import date
import hashlib
import json
from pathlib import Path, PurePosixPath
import re


DEFAULT_CATALOGUE = Path(__file__).resolve().parents[1] / "method" / "catalogue.yaml"
CATALOGUE_FIELDS = {
    "schema_version", "catalogue_version", "policy_review_status", "agency_reviews",
    "scope", "provenance", "defect_classes", "coherence_checks", "coverage_domains",
    "recurring_patterns", "vague_terms", "coverage_review", "illustrative_federal_examples",
    "priority_rubric", "audience_review", "prompts", "language_rules",
}
VERSION = re.compile(r"\d+\.\d+\.\d+(?:-[a-z0-9.-]+)?")


def _require(condition, message):
    if not condition:
        raise ValueError("Invalid method catalogue: " + message)


def _object(value, fields, name):
    _require(isinstance(value, dict), f"{name} must be an object")
    _require(set(value) == set(fields), f"{name} has missing or unknown fields")
    return value


def _text(value, name, maximum=4000):
    _require(isinstance(value, str) and bool(value.strip()) and len(value) <= maximum,
             f"{name} must be nonempty text of at most {maximum} characters")
    return value


def _texts(value, name, maximum=100):
    _require(isinstance(value, list) and 0 < len(value) <= maximum, f"{name} must be a nonempty bounded list")
    for item in value:
        _text(item, name)
    _require(len({item.casefold() for item in value}) == len(value), f"{name} must not contain duplicates")
    return value


def _rows(value, name, maximum=100):
    _require(isinstance(value, list) and 0 < len(value) <= maximum, f"{name} must be a nonempty bounded list")
    _require(all(isinstance(item, dict) for item in value), f"{name} entries must be objects")
    return value


def _path(value, name):
    _text(value, name, 500)
    path = PurePosixPath(value)
    _require(not path.is_absolute() and ".." not in path.parts and "\\" not in value,
             f"{name} must be a relative path without parent traversal")


def _version(value, name):
    _text(value, name, 100)
    _require(VERSION.fullmatch(value) is not None, f"{name} must be a version such as 0.1.0-draft")


def _diagnostics(value, name, expected_ids, extra_fields=()):
    fields = {"id", "label", "diagnostic", "source_locator", "evidence_required", *extra_fields}
    rows = _rows(value, name)
    ids = []
    for row in rows:
        _object(row, fields, name)
        for field in ("id", "label", "diagnostic", "source_locator"):
            _text(row[field], f"{name}.{field}")
        _texts(row["evidence_required"], f"{name}.evidence_required", 20)
        ids.append(row["id"])
    _require(len(set(ids)) == len(ids) and set(ids) == expected_ids, f"{name} has missing, duplicate or unknown IDs")


def validate_catalogue(data):
    """Return the input after checking the small supported schema; otherwise refuse.

    This deliberately does not infer that approved wording, a duty or a compliance
    result follows from schema validity. Review is agency-specific and attributable.
    """
    _object(data, CATALOGUE_FIELDS, "catalogue")
    _require(type(data["schema_version"]) is int and data["schema_version"] == 1, "unsupported schema_version")
    _version(data["catalogue_version"], "catalogue_version")
    _require(isinstance(data["policy_review_status"], str) and data["policy_review_status"] in {"draft", "agency_reviewed"}, "unknown policy_review_status")
    _require(isinstance(data["agency_reviews"], list), "agency_reviews must be a list")
    agency_ids = []
    for review in data["agency_reviews"]:
        _object(review, {"agency_id", "reviewer", "reviewed_on", "rationale"}, "agency review")
        for key, value in review.items():
            _text(value, "agency review." + key)
        try:
            date.fromisoformat(review["reviewed_on"])
        except ValueError as error:
            raise ValueError("Invalid method catalogue: agency review date must be ISO 8601") from error
        agency_ids.append(review["agency_id"])
    _require(len(set(agency_ids)) == len(agency_ids), "duplicate agency review")
    if data["policy_review_status"] == "agency_reviewed":
        _require(bool(agency_ids), "agency_reviewed requires attributed agency reviews")

    scope = _object(data["scope"], {"primary", "foreign_context"}, "scope")
    _texts(scope["primary"], "scope.primary")
    _require(set(scope["primary"]) == {"US-FED", "US-STATES", "US-DC"}, "primary scope must preserve US federal, state and DC authority")
    _require(scope["foreign_context"] == "retained_labelled_not_presumed_binding", "foreign context must remain labelled, not presumed binding")
    for source in _rows(data["provenance"], "provenance", 20):
        _object(source, {"path", "sha256", "sections", "derivation"}, "provenance")
        _path(source["path"], "provenance.path")
        _require(isinstance(source["sha256"], str) and re.fullmatch(r"[a-f0-9]{64}", source["sha256"]) is not None, "provenance needs a SHA-256")
        _texts(source["sections"], "provenance.sections", 30)
        _text(source["derivation"], "provenance.derivation")

    defect_ids = {f"D{number}" for number in range(1, 10)}
    _diagnostics(data["defect_classes"], "defect_classes", defect_ids)
    _diagnostics(data["coherence_checks"], "coherence_checks", {f"C{number}" for number in range(1, 8)})
    _diagnostics(data["recurring_patterns"], "recurring_patterns", {f"RP{number:02}" for number in range(1, 23)}, ("defect_class_ids",))
    for pattern in data["recurring_patterns"]:
        _texts(pattern["defect_class_ids"], "recurring pattern classes", 9)
        _require(set(pattern["defect_class_ids"]) <= defect_ids, "recurring pattern refers to an unknown defect class")

    domain_ids, element_ids = [], []
    for domain in _rows(data["coverage_domains"], "coverage_domains", 20):
        _object(domain, {"id", "label", "elements"}, "coverage domain")
        _text(domain["id"], "coverage domain.id")
        _text(domain["label"], "coverage domain.label")
        domain_ids.append(domain["id"])
        for element in _rows(domain["elements"], "coverage elements"):
            _object(element, {"id", "topic", "description", "indicative_phrasings", "source_locator", "evidence_required"}, "coverage element")
            for key in ("id", "topic", "description", "source_locator"):
                _text(element[key], "coverage element." + key)
            phrases = _texts(element["indicative_phrasings"], "coverage element.indicative_phrasings", 3)
            _require(2 <= len(phrases) <= 3, "coverage elements need two or three indicative phrasings")
            _require(all(len(phrase) <= 200 and "\n" not in phrase for phrase in phrases), "indicative phrasings must be short one-line hints")
            _texts(element["evidence_required"], "coverage element.evidence_required", 20)
            element_ids.append(element["id"])
    _require(len(domain_ids) == len(set(domain_ids)), "duplicate coverage domain")
    _require(len(element_ids) == len(set(element_ids)), "duplicate coverage element")
    expected = {*"abcdefghijklmnopqrstuvwxyz", *(letter * 2 for letter in "abcdefghijklmnopqrstuvw"), "k2"}
    _require(set(element_ids) == expected, "coverage elements must preserve original a-ww plus k2")
    terms = _texts(data["vague_terms"], "vague_terms", 100)
    _require(all(term == term.strip() and len(term) <= 100 and not any(character in term for character in "\n\r\t") for term in terms), "vague_terms must be short literal phrases")

    coverage = _object(data["coverage_review"], {"execution", "statuses", "absence_scope", "require_evidence", "automatic_semantic_classification"}, "coverage_review")
    _require(coverage["execution"] == "manual_only_pending_agency_review", "semantic coverage is not enabled by this schema")
    _texts(coverage["statuses"], "coverage_review.statuses")
    _require(set(coverage["statuses"]) == {"covered", "partial", "absent", "not_applicable", "unknown"}, "coverage statuses must preserve unknown")
    _require(coverage["absence_scope"] == "declared_corpus_only" and coverage["require_evidence"] is True and coverage["automatic_semantic_classification"] is False, "coverage must stay scoped, evidenced and manual")
    for example in _rows(data["illustrative_federal_examples"], "illustrative_federal_examples", 20):
        _object(example, {"citation", "purpose", "verification_status"}, "federal example")
        _text(example["citation"], "federal example.citation")
        _text(example["purpose"], "federal example.purpose")
        _require(example["verification_status"] == "unverified", "illustrative leads must not pretend verification")

    language_rules = _rows(data["language_rules"], "language_rules", 2)
    _require({rule.get("id") for rule in language_rules if isinstance(rule.get("id"), str)} == {"LR1", "LR2"}, "language_rules must preserve LR1 and LR2")
    for rule in language_rules:
        common = {"id", "version", "label", "instruction"}
        extra = {"required_basis", "valid_local_instruments_may_bind"} if rule["id"] == "LR1" else {"bill_creates_duty"}
        _object(rule, common | extra, "language rule")
        _version(rule["version"], "language rule.version")
        _text(rule["label"], "language rule.label")
        _text(rule["instruction"], "language rule.instruction")
        if rule["id"] == "LR1":
            _texts(rule["required_basis"], "language rule.required_basis", 4)
            _require(set(rule["required_basis"]) == {"binding_authority", "in_force", "verified", "applicable_scope"}, "mandatory wording requires binding, in-force, verified, applicable authority")
            _require(rule["valid_local_instruments_may_bind"] is True, "valid local binding instruments must retain their actual scope")
        else:
            _require(rule["bill_creates_duty"] is False, "a bill never establishes a current duty by itself")

    rubric = _object(data["priority_rubric"], {"path", "version", "numeric_product"}, "priority_rubric")
    _path(rubric["path"], "priority_rubric.path")
    _version(rubric["version"], "priority_rubric.version")
    _require(rubric["numeric_product"] is False, "priority does not multiply severity and likelihood")
    audience = _object(data["audience_review"], {"resident_target_grade", "estimate_is_advisory", "adversarial_reader_required"}, "audience_review")
    _require(type(audience["resident_target_grade"]) is int and 1 <= audience["resident_target_grade"] <= 12, "invalid resident target grade")
    _require(audience["estimate_is_advisory"] is True and audience["adversarial_reader_required"] is True, "audience review must preserve advisory estimates and adversarial review")
    prompt_ids = []
    for prompt in _rows(data["prompts"], "prompts", 6):
        _object(prompt, {"id", "path", "version"}, "prompt")
        _text(prompt["id"], "prompt.id")
        _path(prompt["path"], "prompt.path")
        _version(prompt["version"], "prompt.version")
        prompt_ids.append(prompt["id"])
    _require(len(set(prompt_ids)) == len(prompt_ids) and set(prompt_ids) == {f"{number:02}" for number in range(1, 7)}, "prompt IDs must be unique 01-06")
    return data


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "duplicate JSON key: " + key)
        result[key] = value
    return result


def load_catalogue(path=None):
    """Load from this checkout, or an explicit path; fail rather than silently default.

    The local app runs from its checkout. This file is not duplicated into a Python
    package or fetched remotely; wheel/distribution data packaging is future work.
    """
    with Path(path if path is not None else DEFAULT_CATALOGUE).open(encoding="utf-8") as file:
        data = json.load(file, object_pairs_hook=_unique_keys)
    return validate_catalogue(data)


def catalogue_hash(data):
    """Identity of the validated content, independent of JSON indentation/key order."""
    validate_catalogue(data)
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def vague_terms(catalogue=None):
    """Validated literal advisory terms; no implied approval or semantic coverage."""
    data = load_catalogue() if catalogue is None else validate_catalogue(catalogue)
    return tuple(data["vague_terms"])
