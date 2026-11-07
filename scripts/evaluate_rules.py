"""Score real, independently adjudicated labels; never turn pending work into accuracy.

Without complete independent labels, validation/predictions run and metrics stay
null. --require-adjudication refuses pending work. An evaluated --baseline always
requires completed labels and gates severe misses on the identical corpus/labels.
"""

import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from compass.analysis import ENGINE_VERSION, FEATURES, analyze

CORE_BOOLEAN = ("segmentation_approved", "obligation_present", "condition_present", "exception_present", "scope_changing_exception")
ENUMS = {"modality": {"obligation", "prohibition", "permission", "advisory", "none"},
         "temporal_status": {"in_force", "future", "not_applicable", "unknown"},
         "binding_status": {"binding", "nonbinding", "conditional", "unknown"}}
SEVERE_CATEGORIES = ("missed_prohibition", "missed_scope_changing_exception", "future_reported_current", "nonbinding_reported_binding")


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def validate_corpus(corpus, root=None):
    if corpus.get("schema_version") != 1 or not corpus.get("corpus_id") or not corpus.get("cases"):
        raise ValueError("Missing/unsupported corpus or empty case list")
    ids = [case.get("case_id") for case in corpus["cases"]]
    if None in ids or len(ids) != len(set(ids)):
        raise ValueError("Missing or duplicate case IDs")
    if corpus.get("corpus_kind") == "uploaded_pdf":
        if len(ids) != 150 or len(corpus.get("sources", [])) != 7:
            raise ValueError("Version 1 requires 150 excerpts from the seven supplied PDFs")
        sources = {source["source"]: source for source in corpus["sources"]}
        if len(sources) != 7 or {case["source"] for case in corpus["cases"]} != set(sources):
            raise ValueError("Every preserved instrument must appear in the corpus")
        if root:
            for source in sources.values():
                path = (Path(root) / source["source"]).resolve()
                if not path.is_relative_to((Path(root) / "case-studies/georgia/instruments").resolve()):
                    raise ValueError("Evaluation source is outside preserved instruments")
                if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != source["original_sha256"]:
                    raise ValueError("Evaluation source hash changed or source is missing")
        for case in corpus["cases"]:
            source = sources[case["source"]]
            if case["original_sha256"] != source["original_sha256"] or not (1 <= case["page"] <= source["page_count"]):
                raise ValueError("Invalid case source/page provenance")
            if case["page_char_start"] < 0 or case["page_char_end"] - case["page_char_start"] != len(case["text"]):
                raise ValueError("Invalid extracted-page character offsets")
    elif corpus.get("corpus_kind") != "synthetic_test":
        raise ValueError("Declare uploaded_pdf or synthetic_test corpus provenance")
    if any(not case.get("text", "").strip() for case in corpus["cases"]):
        raise ValueError("Empty evaluation passage")


def validate_labels(document, corpus, expected_role):
    if document.get("schema_version") != 1 or document.get("corpus_id") != corpus["corpus_id"] or document.get("corpus_sha256") != fingerprint(corpus) or document.get("role") != expected_role:
        raise ValueError(f"{expected_role}: role/corpus identity mismatch")
    labels = document.get("labels", [])
    by_id = {label.get("case_id"): label for label in labels}
    if len(by_id) != len(labels) or set(by_id) != {case["case_id"] for case in corpus["cases"]}:
        raise ValueError(f"{expected_role}: duplicate, missing or unknown label IDs")
    for label in labels:
        if set(label) != {"case_id", *CORE_BOOLEAN, "actor", *ENUMS, "notes"}:
            raise ValueError("Unexpected or missing label fields")
        for field in CORE_BOOLEAN:
            if label[field] is not None and type(label[field]) is not bool:
                raise ValueError(f"{field} must be boolean or null")
        for field, allowed in ENUMS.items():
            if label[field] is not None and (not isinstance(label[field], str) or label[field] not in allowed):
                raise ValueError(f"Invalid {field}")
        if label["actor"] is not None and not isinstance(label["actor"], str):
            raise ValueError("Actor must be exact text, empty string, or pending null")
        if not isinstance(label["notes"], str):
            raise ValueError("Label notes must be text")
        if label["scope_changing_exception"] and not label["exception_present"]:
            raise ValueError("A scope-changing exception must also be labeled an exception")
    if document.get("person_id") is not None and (not isinstance(document["person_id"], str) or not document["person_id"].strip()):
        raise ValueError("person_id must be a nonempty attributed reviewer ID or null")
    if document.get("completed_at"):
        try:
            stamp = datetime.fromisoformat(document["completed_at"].replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                raise ValueError("Timezone required")
        except (AttributeError, TypeError, ValueError):
            raise ValueError("completed_at needs an actual ISO timestamp with timezone") from None
    return by_id


def complete(label):
    return all(type(label[field]) is bool for field in CORE_BOOLEAN) and label["segmentation_approved"] and isinstance(label["actor"], str) and all(label[field] in allowed for field, allowed in ENUMS.items())


def predict(corpus):
    predictions = {}
    modalities = {"prohibition_wording": "prohibition", "permission": "permission", "advisory_wording": "advisory"}
    sources, reports = {}, {}
    for case in corpus["cases"]:
        key = case["source"] if corpus["corpus_kind"] == "uploaded_pdf" else case["case_id"]
        if key not in sources:
            if corpus["corpus_kind"] == "uploaded_pdf":
                from compass.pdf_import import extract_pdf
                extracted = extract_pdf((ROOT / key).read_bytes())
                text, page_spans = extracted["text"], extracted["page_spans"]
            else:
                text, page_spans = case["text"], []
            source = {"id": key, "title": "Evaluation source", "kind": "instrument", "text": text, "page_spans": page_spans, "jurisdiction_id": "US-GA", "legal_status": case.get("legal_status", "unknown"), "authority_type": "internal_policy", "created_at": "2026-07-27T00:00:00+00:00"}
            sources[key] = source
            # Analyze full original text, so neighboring exceptions and headings
            # receive the same treatment as application runs. Labelers still see
            # only the original PDF/context and their own blind template.
            reports[key] = analyze([source], [], {"features": {feature: feature == "obligations" for feature in FEATURES}}, {}, "2026-07-27", [], [], "US-GA")["features"]["obligations"]["items"]
        start, end = (case["source_char_start"], case["source_char_end"]) if corpus["corpus_kind"] == "uploaded_pdf" else (0, len(case["text"]))
        items = []
        for item in reports[key]:
            for evidence in item["evidence"]:
                span = re.search(r"characters (\d+)–(\d+)$", evidence["location"])
                if span and start < int(span[2]) and end > int(span[1]) - 1:
                    items.append(item)
                    break
        # Keep any detected prohibition visible in a multi-clause passage.
        preferred = next((item for item in items if item["data"]["candidate_type"] == "prohibition_wording"), items[0] if items else None)
        data = preferred["data"] if preferred else {}
        modality = modalities.get(data.get("candidate_type"), "obligation" if preferred else "none")
        predictions[case["case_id"]] = {"obligation_present": modality in {"obligation", "prohibition"}, "actor": data.get("actor") or "", "modality": modality,
                                          "condition_present": any(item["data"].get("conditions") for item in items), "exception_present": any(item["data"].get("exceptions") for item in items),
                                          "current_rule_claim": any(item["data"].get("applicability") == "binding" and item["data"].get("source_status") == "in_force" for item in items),
                                          "binding_claim": any(item["data"].get("applicability") == "binding" for item in items)}
    return predictions


def binary_metrics(expected, actual):
    tp = sum(gold and prediction for gold, prediction in zip(expected, actual))
    fp = sum(not gold and prediction for gold, prediction in zip(expected, actual))
    fn = sum(gold and not prediction for gold, prediction in zip(expected, actual))
    return {"true_positive": tp, "false_positive": fp, "false_negative": fn, "precision": tp / (tp + fp) if tp + fp else None, "recall": tp / (tp + fn) if tp + fn else None, "support": sum(expected)}


def tokens(value):
    return Counter(re.findall(r"[\w'-]+", value.casefold()))


def actor_metrics(expected, actual):
    tp = fp = fn = exact = 0
    for gold, prediction in zip(expected, actual):
        g, p = tokens(gold), tokens(prediction)
        overlap = sum((g & p).values())
        tp += overlap
        fp += sum(p.values()) - overlap
        fn += sum(g.values()) - overlap
        exact += re.findall(r"[\w'-]+", gold.casefold()) == re.findall(r"[\w'-]+", prediction.casefold())
    precision, recall = (tp / (tp + fp) if tp + fp else None), (tp / (tp + fn) if tp + fn else None)
    return {"precision": precision, "recall": recall, "token_f1": 2 * precision * recall / (precision + recall) if precision is not None and recall is not None and precision + recall else None, "exact_token_match_rate": exact / len(expected) if expected else None, "token_true_positive": tp, "token_false_positive": fp, "token_false_negative": fn}


def agreement(first, second):
    result = {}
    for field in ("obligation_present", "modality", "condition_present", "exception_present", "scope_changing_exception", "temporal_status", "binding_status"):
        a, b = [label[field] for label in first], [label[field] for label in second]
        observed = sum(x == y for x, y in zip(a, b)) / len(a)
        ac, bc = Counter(a), Counter(b)
        chance = sum(ac[value] * bc[value] for value in set(ac) | set(bc)) / len(a) ** 2
        result[field] = {"agreement": observed, "cohen_kappa": (observed - chance) / (1 - chance) if chance < 1 else None, "count": len(a)}
    result["actor"] = actor_metrics([label["actor"] for label in first], [label["actor"] for label in second])
    return result


def score(gold, predictions):
    ordered = sorted(gold)
    metrics = {field: binary_metrics([gold[key][field] for key in ordered], [predictions[key][field] for key in ordered]) for field in ("obligation_present", "condition_present", "exception_present")}
    for modality in ("prohibition", "permission", "obligation", "advisory"):
        metrics[modality] = binary_metrics([gold[key]["modality"] == modality for key in ordered], [predictions[key]["modality"] == modality for key in ordered])
    metrics["actor"] = actor_metrics([gold[key]["actor"] for key in ordered], [predictions[key]["actor"] for key in ordered])
    severe = {category: [] for category in SEVERE_CATEGORIES}
    for key in ordered:
        label, prediction = gold[key], predictions[key]
        if label["modality"] == "prohibition" and prediction["modality"] != "prohibition":
            severe["missed_prohibition"].append(key)
        if label["scope_changing_exception"] and not prediction["exception_present"]:
            severe["missed_scope_changing_exception"].append(key)
        if label["temporal_status"] == "future" and prediction["current_rule_claim"]:
            severe["future_reported_current"].append(key)
        if label["binding_status"] == "nonbinding" and prediction["binding_claim"]:
            severe["nonbinding_reported_binding"].append(key)
    return metrics, {"by_category": {category: len(cases) for category, cases in severe.items()}, "case_ids": severe, "distinct_cases": len(set().union(*map(set, severe.values()))), "occurrences": sum(map(len, severe.values())), "temporal_unknown_cases": sum(label["temporal_status"] == "unknown" for label in gold.values()), "binding_unknown_cases": sum(label["binding_status"] == "unknown" for label in gold.values())}


def evaluate(corpus, documents, predictions=None, require_adjudication=False):
    validate_corpus(corpus)
    roles = ("labeler_a", "labeler_b", "adjudicator")
    if len(documents) != 3:
        raise ValueError("Two label files and third-person adjudication are required")
    labeled = [validate_labels(document, corpus, role) for document, role in zip(documents, roles)]
    counts = {role: sum(complete(label) for label in labels.values()) for role, labels in zip(roles, labeled)}
    ready = all(count == len(corpus["cases"]) for count in counts.values()) and all(document.get("person_id") and document.get("completed_at") for document in documents) and all(document.get("independently_completed") is True for document in documents[:2])
    people = [document.get("person_id") for document in documents]
    if any(people) and len({person for person in people if person}) != len([person for person in people if person]):
        raise ValueError("Labelers and adjudicator must be three distinct people")
    predictions = predict(corpus) if predictions is None else predictions
    if set(predictions) != set(labeled[2]):
        raise ValueError("Predictions must cover exactly the declared corpus")
    result = {"schema_version": 1, "corpus_id": corpus["corpus_id"], "corpus_sha256": fingerprint(corpus), "engine_version": ENGINE_VERSION, "status": "evaluated" if ready else "awaiting_independent_labels", "case_count": len(corpus["cases"]), "prediction_count": len(predictions), "completed_labels": counts, "metrics": None, "interrater_agreement": None, "severe_misses": None, "label_set_sha256": fingerprint(documents) if ready else None, "limits": "Stratified sample metrics do not estimate prevalence. Unknown temporal/binding cases cannot establish legal-status accuracy. Candidate wording is not a legal determination."}
    if ready:
        result["metrics"], result["severe_misses"] = score(labeled[2], predictions)
        ordered = sorted(labeled[0])
        result["interrater_agreement"] = agreement([labeled[0][key] for key in ordered], [labeled[1][key] for key in ordered])
    elif require_adjudication:
        raise ValueError("Evaluation pending: obtain two independent labels and third-person adjudication; do not fabricate metrics")
    return result


def check_baseline(result, baseline):
    if baseline.get("corpus_sha256") != result["corpus_sha256"]:
        raise ValueError("Baseline corpus differs; reviewed versioned rebaselining is required")
    if baseline.get("status") == "awaiting_independent_labels":
        return "pending_adjudicated_baseline"
    if baseline.get("status") != "evaluated":
        raise ValueError("Unknown baseline status; cannot disable the severe-miss gate")
    if result["status"] != "evaluated" or baseline.get("label_set_sha256") != result.get("label_set_sha256"):
        raise ValueError("Evaluated baseline requires the same completed independent label set")
    if result["severe_misses"]["distinct_cases"] > baseline["severe_misses"]["distinct_cases"] or any(result["severe_misses"]["by_category"][key] > baseline["severe_misses"]["by_category"][key] for key in SEVERE_CATEGORIES):
        raise ValueError("Severe misses increased against adjudicated baseline")
    return "no_severe_increase"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=ROOT / "tests/evaluation")
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--require-adjudication", action="store_true")
    args = parser.parse_args()
    try:
        corpus = json.loads((args.directory / "corpus.json").read_text())
        validate_corpus(corpus, ROOT)
        documents = [json.loads((args.directory / name).read_text()) for name in ("labeler-a.json", "labeler-b.json", "adjudication.json")]
        report = evaluate(corpus, documents, require_adjudication=args.require_adjudication)
        if args.baseline:
            report["baseline_gate"] = check_baseline(report, json.loads(args.baseline.read_text()))
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        print(json.dumps(report, indent=2, ensure_ascii=False))
    except (ValueError, KeyError, OSError) as error:
        print(f"Evaluation refused: {error}", file=sys.stderr)
        raise SystemExit(1)
