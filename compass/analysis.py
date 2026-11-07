"""Evidence-linked, deterministic review aids. None determine legal force.

All inputs must already be tenant-scoped. Text heuristics produce review candidates,
not legal conclusions. This module has no network, model, or persistence access.
"""

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher
import hashlib
import json
import re

from .jurisdictions import US_STATE_IDS, is_us_authority
from .catalogue import catalogue_hash, load_catalogue, vague_terms


ENGINE_VERSION = "rules-v4"
FEATURES = (
    "change_detection", "obligations", "citations", "terminology", "coverage",
    "impact", "language", "deadlines", "peer_research",
)
ADVANCED = {"terminology", "impact", "language", "peer_research"}
MAX_ITEMS = 100
MODAL = re.compile(r"\b(shall|must|should|may|will|is\s+required\s+to|are\s+required\s+to|is\s+prohibited\s+from|are\s+prohibited\s+from|is\s+responsible\s+for|are\s+responsible\s+for|is\s+to|are\s+to)\b", re.I)
EXCEPTION = re.compile(r"\b(except(?:ions?)?|unless|exclud(?:ing|e[ds]?)|exempt(?:ions?|ed)?|does not apply|not applicable|other than)\b", re.I)
CONDITION = re.compile(r"\b(if|when|provided that|subject to|upon|only if|for recipients)\b", re.I)
TIMING = re.compile(r"\b(?:within\s+\d+\s+(?:(?:business|calendar)\s+)?(?:days?|months?|years?)|by\s+\d{4}-\d{2}-\d{2}|annual(?:ly)?|quarterly|monthly|every\s+\d+\s+(?:days?|months?|years?))\b", re.I)
TEXT_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b", re.I)
DEFINITION = re.compile(r'''(?:[“"'](?P<quoted>[^”"'\n]{2,80})[”"']|(?P<plain>[A-Za-z][A-Za-z /-]{1,70}))\s+(?:means|is defined as|refers to)\s+(?P<meaning>[^\n.]+(?:\.(?=\s|$))?)''', re.I)
STOPWORDS = set("a an the and or of to in for by on with from as at this that these those is are be been it its their shall must may should section policy office state system systems applies apply".split())
CHANGE_METADATA = ("legal_status", "effective_from", "effective_to", "authority_type", "adoption_reference")
SENTENCE_ABBREVIATIONS = (
    "U.S.C.", "U.S.", "C.F.R.", "Fed. Reg.", "Fed.Reg.", "Pub. L.", "Pub.L.",
    "O.C.G.A.", "Stat.", "Sec.", "No.", "e.g.", "i.e.", "Inc.", "Co.", "Corp.",
    "Dr.", "Mr.", "Ms.", "vs.", "et al.", "H.R.", "S.", "pt.", "subpt.", "ch.",
)
_CATALOGUE = load_catalogue()
VAGUE_WORDING = vague_terms(_CATALOGUE)
METHOD_CATALOGUE = {"version": _CATALOGUE["catalogue_version"], "hash": catalogue_hash(_CATALOGUE),
                    "policy_review_status": _CATALOGUE["policy_review_status"], "vague_terms": list(VAGUE_WORDING)}
VAGUE_PATTERN = re.compile(r"\b(?:" + "|".join(re.escape(value) for value in sorted(VAGUE_WORDING, key=len, reverse=True)) + r")\b", re.I)
# Federal citation syntax is shared. State code and instrument patterns are
# office-profile configuration, rather than assumptions in this pipeline.
FEDERAL_CITATION_PATTERNS = (
    ("us_code", r"\b\d{1,3}\s+U\.?\s*S\.?\s*C\.?(?:\s*§{1,2}\s*|\s+)\d+[A-Za-z]*(?:[-–.]\d+[A-Za-z]*)*(?:\([A-Za-z0-9]+\))*(?:\s+et\s+seq\.?)?"),
    ("regulation", r"\b\d{1,3}\s+C\.?\s*F\.?\s*R\.?(?:\s*§{1,2}\s*|\s+(?:(?:pt|part)\.?\s+)?)\d+(?:\.\d+)*(?:[-–]\d+(?:\.\d+)*)?(?:\([A-Za-z0-9]+\))*"),
    ("federal_register", r"\b\d{1,3}\s+Fed\.?\s*Reg\.?\s+\d[\d,]*(?:[-–]\d[\d,]*)?"),
    ("public_law", r"\b(?:Pub\.?\s*L\.?|Public\s+Law)\s+(?:No\.?\s+)?\d{1,3}[-–]\d{1,4}\b"),
    ("statutes_at_large", r"\b\d{1,4}\s+Stat\.?\s+\d+(?:[-–]\d+)?\b"),
    ("bill", r"(?<![\w.])(?:H\.?\s*R\.?|S\.|H\.?\s*B\.?|S\.?\s*B\.?|A\.?\s*B\.?|L\.?\s*B\.?|H\.?\s*F\.?|S\.?\s*F\.?)\s*\d{1,6}\b"),
)


def _timestamp(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _date(value):
    try:
        return date.fromisoformat(str(value)) if value else None
    except ValueError:
        return None


def _sentences(source, profile=None):
    """Small abbreviation-aware splitter, preserving original character spans."""
    text = source.get("text", "")
    extras = (profile or {}).get("sentence_abbreviations", [])
    if not isinstance(extras, list):
        extras = []
    abbreviations = [*SENTENCE_ABBREVIATIONS, *(value for value in extras if isinstance(value, str) and value)]
    pattern = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(value) for value in sorted(set(abbreviations), key=len, reverse=True)) + r")", re.I)
    protected = {position for match in pattern.finditer(text) for position in range(match.start(), match.end()) if text[position] == "."}
    result = []
    start = 0
    for boundary in re.finditer(r"[.!?]+(?=\s|$)|\n[ \t]*\n", text):
        if boundary.start() in protected:
            continue
        raw = text[start:boundary.end()]
        left = start + len(raw) - len(raw.lstrip())
        right = start + len(raw.rstrip())
        if left < right:
            result.append((left, right, text[left:right]))
        start = boundary.end()
    raw = text[start:]
    left, right = start + len(raw) - len(raw.lstrip()), len(text.rstrip())
    if left < right:
        result.append((left, right, text[left:right]))
    return result


def _evidence(source, start=0, end=None):
    text = source.get("text", "")
    end = min(len(text), start + 1500) if end is None else min(end, start + 1500)
    if not text or end <= start:
        return None
    pages = [str(span["page"]) for span in source.get("page_spans", [])
             if span["start"] < end and span["end"] > start]
    page_location = "Page " + pages[0] if len(pages) == 1 else "Pages " + ", ".join(pages) if pages else ""
    return {
        "source_id": source["id"], "quote": text[start:end],
        "location": (page_location + "; " if pages else "") + f"Line {text.count(chr(10), 0, start) + 1}; characters {start + 1}–{end}",
    }


def _item(title, detail, source_ids=(), evidence=(), data=None, severity="review"):
    evidence = [piece for piece in evidence if piece]
    content = {"title": title, "detail": detail, "severity": severity,
               "source_ids": list(dict.fromkeys(source_ids)), "evidence": evidence, "data": data or {}}
    content["id"] = hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()[:20]
    return content


def _words(text):
    return {word.casefold() for word in re.findall(r"[A-Za-z][A-Za-z-]{2,}", text) if word.casefold() not in STOPWORDS}


def _phrase_evidence(source, phrase, profile=None):
    match = re.search(re.escape(phrase), source.get("text", ""), re.I)
    if not match:
        return None
    for start, end, _ in _sentences(source, profile):
        if start <= match.start() < end:
            if match.start() - start > 1000:
                start = max(start, match.start() - 300)
            return _evidence(source, start, end)
    return _evidence(source, match.start(), match.end())


def _predecessor(current, candidates):
    """Resolve explicit identity in the same scope, never title similarity."""
    key, replaces = current.get("source_key"), current.get("replaces_source_id")
    cutoff = _timestamp(current.get("created_at"))
    possible = [candidates[replaces]] if replaces in candidates else []
    if not replaces and key:
        possible = [source for source in candidates.values() if source.get("source_key") == key and source["id"] != current["id"]]
    prior = [source for source in possible if source.get("kind") == current.get("kind")
             and source.get("jurisdiction_id") == current.get("jurisdiction_id")
             and cutoff and _timestamp(source.get("created_at")) and _timestamp(source["created_at"]) < cutoff]
    return max(prior, key=lambda source: (_timestamp(source["created_at"]), source["id"])) if prior else None


def _change_types(previous, current, metadata_changes, profile=None):
    """Classify possible changes using surface rules, not legal interpretation."""
    old, new = previous.get("text", ""), current.get("text", "")
    result = ["metadata"] if metadata_changes else []
    if old == new:
        return result
    tokens = lambda text: re.findall(r"\w+", text.casefold())
    if tokens(old) == tokens(new):
        return [*result, "formatting_only"]
    result.append("text")
    modal = lambda text: [(match.group().casefold(), bool(re.match(r"\s+(?:not|never)\b", text[match.end():], re.I))) for match in MODAL.finditer(text)]
    if modal(old) != modal(new):
        result.append("modal")
    for name, pattern in (("timing", TIMING), ("date", TEXT_DATE)):
        if [match.group().casefold() for match in pattern.finditer(old)] != [match.group().casefold() for match in pattern.finditer(new)]:
            result.append(name)
    exceptions = lambda source: [tokens(sentence[match.start():]) for _, _, sentence in _sentences(source, profile) if (match := EXCEPTION.search(sentence))]
    if exceptions(previous) != exceptions(current):
        result.append("exception")
    definitions = lambda text: [(tokens(match.group("quoted") or match.group("plain")), tokens(match.group("meaning"))) for match in DEFINITION.finditer(text)]
    if definitions(old) != definitions(new):
        result.append("definition")
    return result


def _citation_key(value):
    value = str(value).strip()
    # Normalize recognized federal forms only. Punctuation in an arbitrary
    # declared/profile identifier is identity, not optional abbreviation syntax.
    if any(re.fullmatch(pattern, value, re.I) for _, pattern in FEDERAL_CITATION_PATTERNS):
        value = re.sub(r"(?<=[A-Za-z])\.", "", value).replace("–", "-").replace("—", "-")
        value = re.sub(r"(?<=\d),(?=\d)", "", value)
        value = re.sub(r"[\s§]", "", value)
    return value.casefold()


def _citation_patterns(profile, warnings):
    patterns = [(name, re.compile(pattern, re.I)) for name, pattern in FEDERAL_CITATION_PATTERNS]
    additions = (profile or {}).get("citation_patterns", [])
    if not isinstance(additions, list):
        warnings.append("Profile citation_patterns must be a list; federal defaults remain active.")
        return patterns
    for index, expression in enumerate(additions):
        try:
            pattern = re.compile(expression, re.I)
            if pattern.match(""):
                raise ValueError("empty citation matches")
            patterns.append(("profile_pattern", pattern))
        except (re.error, TypeError, ValueError):
            warnings.append(f"Invalid profile citation pattern {index + 1} was skipped; federal defaults remain active.")
    return patterns


def _detected_citations(text, patterns):
    result = []
    for name, pattern in patterns:
        for match in pattern.finditer(text):
            if match.group().strip():
                result.append((match.start(), match.end(), match.group(), name))
    return sorted(result, key=lambda item: (item[0], -(item[1] - item[0]), item[3]))


def _context_scope(source, jurisdiction_id):
    scope = str(source.get("jurisdiction_id") or "unknown")
    if not is_us_authority(scope):
        return "foreign_or_unspecified_context"
    if scope == jurisdiction_id:
        return "active_jurisdiction"
    if scope == "US-FED":
        return "us_federal_context"
    return "other_us_jurisdiction_context"


def analyze(sources, history, settings, context, as_of, findings, audit_events, jurisdiction_id, profile=None, method_catalogue=None):
    """Return bounded, reproducible review aids from explicitly supplied inputs.

    `as_of` is legal calendar time. Snapshot history is separately bounded by each
    selected source's creation time, so retrospective runs cannot see later text.
    """
    day = date.fromisoformat(as_of)
    settings, context, profile = settings or {}, context or {}, profile or {}
    sources, history = sources or [], history or []
    findings, audit_events = findings or [], audit_events or []
    flags = settings.get("features", {})
    catalogue = json.loads(json.dumps(method_catalogue or METHOD_CATALOGUE))
    vague_pattern = VAGUE_PATTERN if catalogue == METHOD_CATALOGUE else re.compile(r"\b(?:" + "|".join(re.escape(term) for term in sorted(catalogue["vague_terms"], key=len, reverse=True)) + r")\b", re.I)
    report = {"method": ENGINE_VERSION, "engine_version": ENGINE_VERSION, "method_catalogue": catalogue, "as_of": as_of,
              "features": {}, "summary": {}, "warnings": [], "coverage_status": "unverified"}
    counts = {}
    for feature in FEATURES:
        enabled = bool(flags.get(feature, True)) and (feature not in ADVANCED or bool(settings.get("advanced_analysis", False)))
        report["features"][feature] = {"enabled": enabled, "status": "completed" if enabled else "disabled",
                                       "summary": "No candidates identified in the selected inputs." if enabled else "Disabled in workspace settings.", "items": []}
        counts[feature] = 0
    attention = 0

    def active(feature):
        return report["features"][feature]["enabled"]

    def add(feature, item):
        nonlocal attention
        counts[feature] += 1
        if item["severity"] in {"review", "urgent"}:
            attention += 1
        if len(report["features"][feature]["items"]) < MAX_ITEMS:
            report["features"][feature]["items"].append(item)

    def needs(feature, message):
        report["features"][feature]["status"] = "needs_input"
        report["features"][feature]["summary"] = message

    selected = {source["id"]: source for source in sources}
    spans = {source["id"]: _sentences(source, profile) for source in sources}
    changed_ids = set()
    unresolved = 0
    dates_count = 0

    # Impact needs the same underlying change facts even when the optional diff
    # display is off. Avoid all history comparison when neither aid is enabled.
    comparisons = []
    if active("change_detection") or active("impact"):
        candidates = {source["id"]: source for source in [*history, *sources]}
        for current in sources:
            key, replaces = current.get("source_key"), current.get("replaces_source_id")
            if not key and not replaces:
                continue
            previous = _predecessor(current, candidates)
            if previous is None:
                if active("change_detection"):
                    report["warnings"].append(f"No verified earlier snapshot available for {current['id']}; no version difference was inferred.")
                continue
            metadata_changes = {field: {"before": previous.get(field), "after": current.get(field)}
                                for field in CHANGE_METADATA if previous.get(field) != current.get(field)}
            comparisons.append((previous, current, metadata_changes))
            if previous.get("text", "") != current.get("text", "") or metadata_changes:
                changed_ids.add(current["id"])

    if active("change_detection"):
        for previous, current, metadata_changes in comparisons:
            old, new = previous.get("text", ""), current.get("text", "")
            if old == new and not metadata_changes:
                continue
            changes = []
            old_lines, new_lines = old.splitlines(keepends=True), new.splitlines(keepends=True)
            for tag, a1, a2, b1, b2 in SequenceMatcher(None, old_lines, new_lines, autojunk=True).get_opcodes():
                if tag != "equal":
                    changes.append({"kind": tag, "old_lines": [a1 + 1, a2], "new_lines": [b1 + 1, b2],
                                    "removed": "".join(old_lines[a1:a2])[:4000], "added": "".join(new_lines[b1:b2])[:4000]})
            evidence = []
            if changes:
                first = changes[0]
                old_start = sum(map(len, old_lines[:max(0, first["old_lines"][0] - 1)]))
                new_start = sum(map(len, new_lines[:max(0, first["new_lines"][0] - 1)]))
                evidence = [_evidence(previous, old_start), _evidence(current, new_start)]
            label = "Changed text" if old != new else "Changed source metadata"
            add("change_detection", _item(f"{label}: {current.get('title', current.get('source_key'))}",
                "Exact snapshot differences and rule-based change categories are review candidates. Even formatting-only candidates need owner confirmation of substantive effect; no legal force is inferred.",
                [previous["id"], current["id"]], evidence,
                {"previous_source_id": previous["id"], "current_source_id": current["id"], "changes": changes[:25], "change_count": len(changes),
                 "metadata_changes": metadata_changes, "text_changed": old != new, "change_types": _change_types(previous, current, metadata_changes, profile), "substantive_status": "unreviewed"}))
            if changes and (len(changes) > 25 or any(len("".join(part)) > 4000 for part in (old_lines, new_lines))):
                report["warnings"].append(f"Version difference for {current['id']} is excerpted; consult both preserved full snapshots.")
        if not comparisons:
            needs("change_detection", "Add source keys or explicit predecessor links and earlier timestamped snapshots to compare versions.")

    if active("obligations"):
        for source in sources:
            sentences = spans[source["id"]]
            for index, (start, end, sentence) in enumerate(sentences):
                modals = list(MODAL.finditer(sentence))
                if not modals:
                    continue
                # Mixed permission/prohibition sentences occur in actual policy
                # text. Keep the prohibition visible rather than downgrading the
                # whole sentence to the first permissive modal.
                modal = next((match for match in modals if "prohibited" in match.group().casefold()
                              or re.match(r"\s+(?:not|never|no longer)\b", sentence[match.end():], re.I)), modals[0])
                actor = re.sub(r"^(?:Section|§)\s*[\w().-]+\s*[:.]?\s*", "", sentence[:modal.start()].strip(), flags=re.I)
                exceptions = [sentence[match.start():] for match in [EXCEPTION.search(sentence)] if match]
                evidence = [_evidence(source, start, end)]
                # A numbered heading may split into its own sentence. Look only
                # across nearby headings, never infer a whole document's scope.
                for following in sentences[index + 1:index + 4]:
                    if EXCEPTION.search(following[2]):
                        exceptions.append(following[2])
                        evidence.append(_evidence(source, following[0], following[1]))
                        break
                    if not re.fullmatch(r"(?:Section|§)\s*[\w().-]+[.:]?", following[2], re.I):
                        break
                conditions = [sentence[match.start():] for match in [CONDITION.search(sentence)] if match]
                wording = " ".join(modal.group().casefold().split())
                negated = bool(re.match(r"\s+(?:not|never|no longer)\b", sentence[modal.end():], re.I)) or "prohibited" in wording
                basis = "commitment" if wording == "will" else "responsibility" if "responsible for" in wording else "drafting" if wording in {"is to", "are to"} else "explicit_modal"
                candidate_type = "prohibition_wording" if negated and wording != "should" else (
                    "permission" if wording == "may" else "advisory_wording" if wording == "should" else
                    "commitment_wording" if basis == "commitment" else "responsibility_wording" if basis == "responsibility" else
                    "drafting_wording" if basis == "drafting" else "mandatory_wording")
                context_scope = _context_scope(source, jurisdiction_id)
                scope_note = " Foreign or unspecified source context is retained; applicability to U.S. offices is unassessed." if context_scope == "foreign_or_unspecified_context" else ""
                add("obligations", _item(f"Candidate action: {source.get('title', 'source')}",
                    "Wording extracted for review; actor, scope, conditions, exceptions and actual applicability remain unconfirmed." + scope_note, [source["id"]], evidence,
                    {"actor": actor or None, "modal": modal.group(), "action": sentence[modal.end():].strip(), "candidate_type": candidate_type,
                     "wording_basis": basis, "wording_evidence": "weaker_candidate" if basis != "explicit_modal" else "explicit_modal_candidate",
                     "timing": [match.group() for match in TIMING.finditer(sentence)], "conditions": conditions, "exceptions": exceptions,
                     "negated_or_prohibited": negated, "applicability": "unknown", "source_status": source.get("legal_status", "unknown"),
                     "jurisdiction_id": source.get("jurisdiction_id"), "context_scope": context_scope},
                    severity="info" if candidate_type == "permission" else "review"))

    if active("citations"):
        patterns = _citation_patterns(profile, report["warnings"])
        registry = defaultdict(list)
        for source in sources:
            aliases = [source.get("source_key"), *(item[2] for item in _detected_citations(source.get("title", ""), patterns))]
            for alias in dict.fromkeys(_citation_key(alias) for alias in aliases if alias):
                registry[alias].append(source)
        for source in sources:
            own = {_citation_key(source.get("source_key") or ""), *(_citation_key(item[2]) for item in _detected_citations(source.get("title", ""), patterns))}
            detected = _detected_citations(source.get("text", ""), patterns)
            references = {_citation_key(value): (value, "declared_reference", True) for value in source.get("reference_keys", [])}
            for _, _, value, citation_type in detected:
                references.setdefault(_citation_key(value), (value, citation_type, False))
            for normalized, (key, citation_type, declared) in references.items():
                if normalized in own:
                    continue
                matches = registry.get(normalized, [])
                status = "unresolved_in_selected_corpus" if not matches else "candidate_match" if len(matches) == 1 else "multiple_selected_versions_or_matches"
                if not matches:
                    unresolved += 1
                actual = next((item[2] for item in detected if _citation_key(item[2]) == normalized), key)
                context_scope = _context_scope(source, jurisdiction_id)
                detail = "No matching selected source was found; this does not establish that the referenced authority is invalid." if not matches else "A selected record matches this citation candidate; its legal accuracy, scope and current status remain unverified."
                if citation_type == "bill":
                    detail += " A bill reference does not establish enactment or binding authority."
                if context_scope == "foreign_or_unspecified_context":
                    detail += " Foreign or unspecified source context is retained; applicability to U.S. offices is unassessed."
                add("citations", _item(f"Reference {key}",
                    detail, [source["id"], *(match["id"] for match in matches)], [_phrase_evidence(source, actual, profile)],
                    {"reference": key, "resolution": status, "matched_source_ids": [match["id"] for match in matches],
                     "origin": "declared_metadata" if declared else "profile_pattern" if citation_type == "profile_pattern" else "federal_or_bill_pattern",
                     "citation_type": citation_type, "jurisdiction_id": source.get("jurisdiction_id"), "context_scope": context_scope, "verification": "unverified"},
                    severity="info" if len(matches) == 1 else "review"))

    if active("terminology"):
        definitions = defaultdict(list)
        scoped = [source for source in sources if source.get("kind") == "instrument" and source.get("jurisdiction_id") == jurisdiction_id]
        for source in scoped:
            for match in DEFINITION.finditer(source.get("text", "")):
                term = re.sub(r"^(?:the term|the|a|an)\s+", "", match.group("quoted") or match.group("plain"), flags=re.I).strip()
                definitions[term.casefold()].append((source, term, match.group("meaning").strip(), match.start(), match.end()))
        for key, entries in definitions.items():
            distinct = {re.sub(r"\W+", " ", entry[2]).strip().casefold() for entry in entries}
            if len(distinct) > 1 and len({entry[0]["id"] for entry in entries}) > 1:
                add("terminology", _item(f"Definition variation: {entries[0][1]}", "Selected same-jurisdiction instruments define this term differently. Context may justify the difference; review before harmonizing.",
                    [entry[0]["id"] for entry in entries], [_evidence(entry[0], entry[3], entry[4]) for entry in entries[:8]],
                    {"term": key, "scope": "selected internal instruments in the active jurisdiction", "alternatives": [{"source_id": entry[0]["id"], "definition": entry[2]} for entry in entries[:20]]}))
        if not scoped:
            needs("terminology", "Add internal instruments in the active jurisdiction to compare definitions.")

    if active("coverage"):
        topics = list(dict.fromkeys(str(topic).strip() for topic in context.get("topics", []) if str(topic).strip()))
        if not topics:
            needs("coverage", "Choose the topics in scope to build an evidence-presence matrix; source completeness remains unverified.")
        for topic in topics:
            matches = []
            for source in sources:
                tagged = topic.casefold() in {str(value).casefold() for value in source.get("topics", [])}
                quoted = _phrase_evidence(source, topic, profile)
                if tagged or quoted:
                    matches.append((source, quoted, "explicit_topic_tag" if tagged else "text_mention"))
            internal = [source["id"] for source, _, _ in matches if source.get("kind") == "instrument"]
            external = [source["id"] for source, _, _ in matches if source.get("kind") == "external"]
            matched_ids = set(internal + external)
            related = [finding for finding in findings if matched_ids.intersection(piece.get("source_id") for piece in finding.get("evidence", []))]
            reviewed = any(finding.get("status") in {"accepted", "rejected"} for finding in related)
            state = "paired_evidence" if internal and external else "missing_internal_evidence" if external else "missing_external_evidence" if internal else "no_selected_evidence"
            add("coverage", _item(f"Topic: {topic}", "This records selected evidence presence and review activity, not legal coverage or compliance. Missing evidence may reflect an incomplete corpus.",
                sorted(matched_ids), [quote for _, quote, _ in matches[:8]],
                {"topic": topic, "evidence_state": state, "review_state": "reviewed_findings_present" if reviewed else "unreviewed", "internal_source_ids": internal, "external_source_ids": external,
                 "match_methods": [{"source_id": source["id"], "method": method} for source, _, method in matches]},
                severity="info" if internal and external else "review"))

    if active("impact"):
        assets = context.get("assets", [])
        if not assets:
            needs("impact", "Map programs, systems, vendors or processes to explicit source keys before assessing possible impact.")
        source_keys = defaultdict(list)
        for source in sources:
            if source.get("source_key"):
                source_keys[source["source_key"].casefold()].append(source)
        for asset in assets:
            linked = {source["id"]: source for key in asset.get("source_keys", []) for source in source_keys.get(str(key).casefold(), [])}
            if not linked:
                continue
            changed = sorted(set(linked).intersection(changed_ids))
            add("impact", _item(f"Mapped review impact: {asset.get('name', asset.get('id', 'asset'))}",
                "An explicit owner-supplied source mapping connects this asset to the selected review. Confirm actual operational effect; no cost or legal severity is inferred.",
                sorted(linked), [], {"asset_id": asset.get("id"), "name": asset.get("name"), "program": asset.get("program"), "owner": asset.get("owner"), "mapped_source_keys": asset.get("source_keys", []), "changed_source_ids": changed},
                severity="review" if changed else "info"))

    if active("language"):
        for source in sources:
            text = source.get("text", "")
            defined = {match.group(1) for match in re.finditer(r"\b[A-Za-z]+(?:\s+[A-Za-z]+){1,8}\s*\(([A-Z]{2,8})\)", text)}
            defined.update(match.group(1) for match in re.finditer(r"\b([A-Z]{2,8})\s+(?:means|is defined as)\b", text))
            defined.update(match.group(1) for match in re.finditer(r"\b([A-Z]{2,8})\s*\([A-Za-z][^)]{4,100}\)", text))
            seen_acronyms = set()
            for start, end, sentence in spans[source["id"]]:
                reasons = []
                word_count = len(re.findall(r"\b[\w'-]+\b", sentence))
                if word_count > 40:
                    reasons.append(f"Long sentence ({word_count} words)")
                vague = vague_pattern.findall(sentence)
                if vague:
                    reasons.append("Potentially vague wording: " + ", ".join(dict.fromkeys(vague)))
                if re.search(r"^(?:shall|must|should)\b|\bit is (?:required|expected)|\b(?:shall|must|should) be\b", sentence, re.I):
                    reasons.append("Confirm that the responsible actor is explicit")
                if len({match.group().casefold() for match in MODAL.finditer(sentence)}) > 1:
                    reasons.append("Mixed modal wording; check each clause's intent")
                undefined = []
                for acronym in re.findall(r"\b[A-Z]{2,8}\b", sentence):
                    if acronym not in defined | seen_acronyms | {"US", "USA", "PDF", "DOCX", "HTTP", "HTTPS", "ISO", "UTC", "AM", "PM"} and acronym not in jurisdiction_id.split("-"):
                        undefined.append(acronym)
                        seen_acronyms.add(acronym)
                if undefined:
                    reasons.append("No recognized expansion in this source: " + ", ".join(undefined))
                if reasons:
                    add("language", _item(f"Language review: {source.get('title', 'source')}", "Advisory language flag. Legal precision, intended audience and preserved definitions take precedence over a readability heuristic.", [source["id"]], [_evidence(source, start, end)], {"flags": reasons, "word_count": word_count, "unexpanded_acronyms": undefined}))

    if active("deadlines"):
        horizon = max(1, min(365, int(settings.get("horizon_days", 30))))
        for source in sources:
            for field, label in (("effective_from", "Effective date"), ("effective_to", "End of effective period")):
                due = _date(source.get(field))
                if source.get(field) and due is None:
                    report["warnings"].append(f"Invalid {field} on source {source['id']}; no date was inferred.")
                if due and day <= due <= day + timedelta(days=horizon):
                    dates_count += 1
                    add("deadlines", _item(f"{label}: {source.get('title', 'source')}", "Source metadata supplies this calendar date. Confirm scope and resulting work; this is not an inferred compliance deadline.", [source["id"]], [],
                        {"kind": "source_date", "field": field, "date": due.isoformat(), "days_until": (due - day).days, "end_is_exclusive": field == "effective_to"}, severity="urgent" if (due - day).days <= 7 else "review"))
                elif due and due < day and ((field == "effective_to" and source.get("legal_status") == "in_force") or (field == "effective_from" and source.get("legal_status") == "adopted_not_effective")):
                    add("deadlines", _item(f"Check date/status consistency: {source.get('title', 'source')}", "The recorded date and status may need reconciliation. A past source date does not establish that an owner task is overdue.", [source["id"]], [], {"kind": "status_date_check", "field": field, "date": due.isoformat(), "legal_status": source.get("legal_status")}, severity="review"))
        pending = [finding for finding in findings if finding.get("status") in {"pending", "needs_information"}]
        overdue_tasks = 0
        for finding in pending:
            assignment = finding.get("assignment") or {}
            due = _date(assignment.get("due_date"))
            if assignment.get("due_date") and due is None:
                report["warnings"].append(f"Invalid owner due date on finding {finding.get('id', 'unknown')}; no date was inferred.")
            if not due or due > day + timedelta(days=horizon):
                continue
            overdue = due < day
            overdue_tasks += int(overdue)
            dates_count += int(not overdue)
            linked = [piece["source_id"] for piece in finding.get("evidence", []) if piece.get("source_id") in selected]
            add("deadlines", _item(f"{'Overdue owner review' if overdue else 'Owner review due'}: {finding.get('summary', finding.get('id', 'finding'))}",
                "This is an explicit owner-assigned task date, separate from source effective dates or a legal compliance deadline.", linked, [],
                {"kind": "owner_task_due", "finding_id": finding.get("id"), "date": due.isoformat(), "days_until": (due - day).days,
                 "overdue": overdue, "owner": assignment.get("owner") or assignment.get("assignee"), "status": finding.get("status")},
                severity="urgent" if (due - day).days <= 7 else "review"))
        blocked = [finding for finding in pending if finding.get("status") == "needs_information" or finding.get("applicability", {}).get("determination", "unknown") == "unknown"]
        reopened = [event for event in audit_events if event.get("action") == "applicability.reviewed" and event.get("details", {}).get("invalidated_status") in {"accepted", "rejected"}]
        add("deadlines", _item("Review workload", "Counts describe supplied review records. No due date or lateness is inferred when an owner deadline is unavailable.",
            [piece["source_id"] for finding in pending for piece in finding.get("evidence", []) if piece.get("source_id") in selected], [],
            {"kind": "review_workload", "pending": len(pending), "blocked": len(blocked), "reopened_events": len(reopened), "overdue_owner_tasks": overdue_tasks,
             "accepted": sum(finding.get("status") == "accepted" for finding in findings), "rejected": sum(finding.get("status") == "rejected" for finding in findings)}, severity="review" if pending else "info"))

    if active("peer_research"):
        local = [source for source in sources if source.get("kind") == "instrument" and source.get("jurisdiction_id") == jurisdiction_id]
        public = [source for source in sources if source.get("kind") == "external" and source.get("reference_scope") == "public" and source.get("jurisdiction_id") in US_STATE_IDS and source.get("jurisdiction_id") != jurisdiction_id]
        if not local or not public:
            needs("peer_research", "Select local instruments and explicitly approved public external material from another US state or DC for optional comparison. Foreign and federal context remains in the source library.")
        local_tokens = [(source, _words(source.get("text", ""))) for source in local]
        for peer in public:
            best = None
            for start, end, sentence in spans[peer["id"]]:
                tokens = _words(sentence)
                for internal, terms in local_tokens:
                    shared = tokens & terms
                    if len(shared) >= 2 and (best is None or len(shared) > len(best[0])):
                        best = (shared, internal, start, end)
            if best:
                shared, internal, start, end = best
                local_quote = next((_evidence(internal, a, b) for a, b, sentence in spans[internal["id"]] if len(_words(sentence) & shared) >= 2), None)
                add("peer_research", _item(f"Optional public comparison: {peer.get('title', 'reference')}", "Shared vocabulary suggests a passage worth reading. This public peer/research reference is nonbinding for this comparison and does not establish applicability or equivalence.", [internal["id"], peer["id"]], [local_quote, _evidence(peer, start, end)], {"shared_terms": sorted(shared)[:12], "reference_scope": "public", "comparison_type": "lexical_related_passage", "applicability": "unconfirmed"}, severity="info"))

    all_sources = {source["id"]: source for source in [*history, *sources]}
    for feature, result in report["features"].items():
        for item in result["items"]:
            context_ids = sorted(key for key in item["source_ids"]
                                 if key in all_sources and not is_us_authority(all_sources[key].get("jurisdiction_id")))
            if context_ids:
                jurisdictions = {key: all_sources[key].get("jurisdiction_id", "unknown") for key in context_ids}
                item["data"]["context_only_source_ids"] = context_ids
                item["data"]["source_jurisdictions"] = jurisdictions
                item["detail"] += " Non-US or unrecognized jurisdiction context (" + ", ".join(sorted(set(jurisdictions.values()))) + "); this record does not establish US authority."
                item["id"] = _item(item["title"], item["detail"], item["source_ids"], item["evidence"], item["data"], item["severity"])["id"]
        if result["enabled"] and result["status"] == "completed":
            result["summary"] = f"{counts[feature]} review aid{'s' if counts[feature] != 1 else ''} identified in the selected inputs."
        if counts[feature] > MAX_ITEMS:
            report["warnings"].append(f"{feature}: {counts[feature] - MAX_ITEMS} additional items omitted from this report (limit {MAX_ITEMS}); narrow the review scope.")
    report["summary"] = {"attention_count": attention, "obligations": counts["obligations"], "language_flags": counts["language"], "upcoming_dates": dates_count, "unresolved_references": unresolved}
    report["warnings"] = list(dict.fromkeys(report["warnings"]))
    if not sources:
        report["warnings"].append("No source snapshots were supplied; no source completeness or legal coverage can be established.")
    return report
