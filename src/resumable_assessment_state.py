"""Bounded data contract for the unwired synthetic analyst resume service.

This module authenticates nobody. Only the server revision service may persist
native review history, and every original must first be retrieved under current
custody authorization. JSON carries declarations and historical annotations;
analysis, currentness and reports are rebuilt from the verified original bytes.
"""
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, timezone
from hashlib import sha256
import json
import re

from src.assessment_worklist import NeedReview
from src.guided_assessment_demo import (
    ACTIONS, DemoAction, DemoCitation, DemoCompletion, SourceRole,
    complete_review, completion_is_current,
)
from src.organization_methodology import OrganizationMethodology
from src.synthetic_evidence_custody import SyntheticEvidenceReceipt, SyntheticEvidenceResult
from src.upload_assessment import Intake, Upload, UploadAssessment, build_assessment, read_upload


MAX_STATE_BYTES = 65536
MAX_SOURCES = 4
MAX_ACTIONS = 16
MAX_NEED_REVIEWS = 32
ENGINE_VERSION = "upload-assessment-v1"
_INTAKE_FIELDS = (
    "assessment_id", "vendor", "service", "use_case", "data", "access", "criticality",
    "environment", "as_of", "data_types", "network_access", "data_volume_records",
    "service_dependency", "system_data_criticality", "organization_id", "active_client_users",
    "workforce_size", "user_count_basis", "scale_already_counted", "scale_overlap_reason",
    "critical_consequence", "critical_consequence_reason",
)
_IDS = ("organization_id", "vendor_id", "engagement_id", "assessment_id", "evidence_id")
_SOURCE_FIELDS = (*_IDS, "generation", "sha256", "byte_length", "filename", "requirements", "kind",
                  "observed_on", "captured_on", "service", "environment", "source_fingerprint")
_FIELDS = ("schema_version", "engine_version", "intake", "methodology", "methodology_sha256",
           "sources", "actions", "need_reviews", "completion")
_ACTION_FIELDS = tuple(DemoAction.__dataclass_fields__)
_CITATION_FIELDS = tuple(DemoCitation.__dataclass_fields__)
_REVIEW_FIELDS = tuple(NeedReview.__dataclass_fields__)


def _keys(value, fields):
    if type(value) is not dict or set(value) != set(fields):
        raise ValueError("Unsupported assessment-state fields.")


def _text(value, maximum, *, empty=False, multiline=False):
    if (type(value) is not str or len(value) > maximum
            or not empty and not value.strip()
            or any((ord(c) < 32 and not (multiline and c in "\n\t")) or ord(c) == 127 for c in value)):
        raise ValueError("Invalid bounded state text.")


def _hex(value, length=64):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{" + str(length) + "}", value) is None:
        raise ValueError("Invalid state fingerprint.")


def _id(value):
    if type(value) is not int or not 0 < value <= 2**63 - 1:
        raise ValueError("Invalid custody reference.")


def _date(value):
    if type(value) is not str or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
        raise ValueError("Invalid state date.")
    return date.fromisoformat(value)


def _timestamp(value):
    _text(value, 64)
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("State timestamps require a timezone.")


def _list(value, maximum):
    if type(value) is not list or len(value) > maximum:
        raise ValueError("Invalid bounded state collection.")


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate state field.")
        result[key] = value
    return result


def _intake(packet):
    _keys(packet["intake"], _INTAKE_FIELDS)
    values = dict(packet["intake"])
    values["as_of"] = _date(values["as_of"])
    _list(values["data_types"], 64)
    values["data_types"] = tuple(values["data_types"])
    if type(packet["methodology"]) is not str:
        raise ValueError("Use the exact bounded methodology JSON snapshot.")
    policy = OrganizationMethodology(packet["methodology"])
    _hex(packet["methodology_sha256"])
    if policy.fingerprint != packet["methodology_sha256"]:
        raise ValueError("Methodology fingerprint differs.")
    return Intake(**values, methodology=policy)


def _citation(value):
    _keys(value, _CITATION_FIELDS)
    for name, maximum in (("statement", 2048), ("filename", 120), ("location", 512),
                          ("quote", 16384), ("provenance", 1024), ("document_id", 80)):
        _text(value[name], maximum, empty=name in ("provenance",), multiline=name == "quote")
    _hex(value["fingerprint"])
    if value["confirmed"] is not False or value["source_role"] not in tuple(item.value for item in SourceRole):
        raise ValueError("Stored citations cannot confirm technical meaning.")


def _validate(packet):
    _keys(packet, _FIELDS)
    if (type(packet["schema_version"]) is not int or packet["schema_version"] != 1
            or packet["engine_version"] != ENGINE_VERSION):
        raise ValueError("Unsupported assessment-state version.")
    intake = _intake(packet)
    _list(packet["sources"], MAX_SOURCES)
    if not packet["sources"]:
        raise ValueError("At least one custodial original is required.")
    identifiers, names, relationships = set(), set(), set()
    for source in packet["sources"]:
        _keys(source, _SOURCE_FIELDS)
        for name in _IDS:
            _id(source[name])
        relationships.add(tuple(source[name] for name in _IDS[:-1]))
        _hex(source["generation"], 32)
        _hex(source["sha256"])
        _hex(source["source_fingerprint"])
        if type(source["byte_length"]) is not int or not 1 <= source["byte_length"] <= 65536:
            raise ValueError("Synthetic original exceeds the custody limit.")
        if (type(source["filename"]) is not str or len(source["filename"]) > 120
                or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_. -]{0,119}", source["filename"]) is None
                or source["filename"] != source["filename"].strip()
                or not source["filename"].lower().endswith((".txt", ".pdf", ".docx"))):
            raise ValueError("Use a supported plain original filename.")
        _list(source["requirements"], 64)
        if (len(set(source["requirements"])) != len(source["requirements"])
                or any(type(item) is not str or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", item) is None
                       for item in source["requirements"])):
            raise ValueError("Invalid source routing.")
        if source["kind"] not in ("assertion", "policy", "configuration", "test"):
            raise ValueError("Invalid source declaration.")
        captured = _date(source["captured_on"])
        if captured > intake.as_of:
            raise ValueError("Original capture cannot follow saved assessment date.")
        if source["observed_on"] is not None:
            _date(source["observed_on"])
        _text(source["service"], 500, empty=True)
        _text(source["environment"], 500, empty=True)
        identifier = source["evidence_id"], source["generation"]
        if identifier in identifiers or source["filename"] in names:
            raise ValueError("Attach each distinct original once.")
        identifiers.add(identifier)
        names.add(source["filename"])
    if len(relationships) != 1 or intake.assessment_id != str(packet["sources"][0]["assessment_id"]):
        raise ValueError("State must reference one exact assessment relationship.")
    _list(packet["actions"], MAX_ACTIONS)
    for action in packet["actions"]:
        _keys(action, _ACTION_FIELDS)
        _text(action["requirement_id"], 80)
        _hex(action["fingerprint"])
        if action["action"] not in ACTIONS:
            raise ValueError("Invalid analyst annotation.")
        _text(action["rationale"], 1200, multiline=True)
        _timestamp(action["recorded_at"])
        _text(action["customer_context"], 4096, empty=True)
        _text(action["threshold"], 4096, empty=True)
        _list(action["citations"], 32)
        for citation in action["citations"]:
            _citation(citation)
    _list(packet["need_reviews"], MAX_NEED_REVIEWS)
    need_ids = set()
    for review in packet["need_reviews"]:
        _keys(review, _REVIEW_FIELDS)
        _text(review["need_id"], 100)
        if review["need_id"] in need_ids:
            raise ValueError("Duplicate need review.")
        need_ids.add(review["need_id"])
        _hex(review["context_fingerprint"])
        _list(review["source_fingerprints"], MAX_SOURCES)
        if not review["source_fingerprints"] or len(set(review["source_fingerprints"])) != len(review["source_fingerprints"]):
            raise ValueError("Need review requires distinct source bindings.")
        for fingerprint in review["source_fingerprints"]:
            _hex(fingerprint)
        if review["decision"] != "insufficient" or review["fact_fingerprints"] != [] or review["confirms"] is not True:
            raise ValueError("Only explicit insufficiency history is supported.")
        _text(review["analyst"], 500)
        _date(review["reviewed_on"])
        _text(review["rationale"], 1200, multiline=True)
    if packet["completion"] is not None:
        _keys(packet["completion"], ("completed_at", "fingerprint"))
        _timestamp(packet["completion"]["completed_at"])
        _hex(packet["completion"]["fingerprint"])
    return intake


def encode_state(packet):
    """Validate plain bounded data; this is never permission to persist history."""
    try:
        _validate(packet)
        encoded = _canonical(packet)
        if len(encoded) > MAX_STATE_BYTES:
            raise ValueError("Assessment state exceeds 64 KiB.")
        return encoded
    except (TypeError, KeyError, OverflowError, RecursionError, UnicodeError) as exc:
        raise ValueError("Invalid assessment state.") from exc


def parse_state(payload):
    """Strict JSON only, returning detached data with no object deserialization."""
    if type(payload) is not bytes or not 1 <= len(payload) <= MAX_STATE_BYTES:
        raise ValueError("Use bounded assessment-state bytes.")
    try:
        packet = json.loads(payload.decode("utf-8"), object_pairs_hook=_unique,
                            parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Nonfinite state number.")))
        encode_state(packet)
        return packet
    except (TypeError, KeyError, RecursionError, UnicodeError) as exc:
        raise ValueError("Invalid assessment-state JSON.") from exc


def _native_json(value):
    return json.loads(json.dumps(value, default=lambda item: item.isoformat() if type(item) is date
                                else (_ for _ in ()).throw(ValueError("Unsupported native state value."))))


def _receipt_matches(source, result):
    if type(result) is not SyntheticEvidenceResult or type(result.receipt) is not SyntheticEvidenceReceipt:
        raise ValueError("Verified custodial originals are required.")
    receipt = result.receipt
    if (any(getattr(receipt, name) != source[name] or type(getattr(receipt, name)) is not int for name in _IDS)
            or receipt.generation != source["generation"] or receipt.sha256 != source["sha256"]
            or receipt.byte_length != source["byte_length"] or receipt.document_name != source["filename"]
            or type(receipt.created_at) is not datetime or receipt.created_at.tzinfo is None
            or receipt.created_at.astimezone(timezone.utc).date() != _date(source["captured_on"])
            or type(result.content) is not bytes or len(result.content) != source["byte_length"]
            or sha256(result.content).hexdigest() != source["sha256"]):
        raise ValueError("Custody reference, metadata or original bytes differ.")


def encode_draft(intake, uploads, receipts):
    """Capture evaluated declarations/original references, never review claims."""
    if (type(intake) is not Intake or type(intake.methodology) is not OrganizationMethodology
            or type(uploads) is not tuple or type(receipts) is not tuple
            or not 1 <= len(uploads) <= MAX_SOURCES or len(uploads) != len(receipts)):
        raise ValueError("Use a bounded intake and exact custodial source inventory.")
    sources = []
    for upload, receipt in zip(uploads, receipts):
        if type(upload) is not Upload or type(receipt) is not SyntheticEvidenceReceipt:
            raise ValueError("Use native uploads and custodial receipts.")
        source = upload.evidence.source
        item = {name: getattr(receipt, name) for name in _IDS}
        item.update(generation=receipt.generation, sha256=receipt.sha256, byte_length=receipt.byte_length,
                    filename=source.filename, requirements=list(upload.requirements), kind=source.evidence_kind,
                    observed_on=source.observed_on.isoformat() if source.observed_on else None,
                    captured_on=source.captured_on.isoformat() if type(source.captured_on) is date else None,
                    service=source.service, environment=source.environment,
                    source_fingerprint=upload.evidence.fingerprint)
        _receipt_matches(item, SyntheticEvidenceResult(receipt, source.content))
        sources.append(item)
    values = {name: getattr(intake, name) for name in _INTAKE_FIELDS}
    packet = dict(schema_version=1, engine_version=ENGINE_VERSION,
                  intake=_native_json(values), methodology=intake.methodology.json_text,
                  methodology_sha256=intake.methodology.fingerprint, sources=sources,
                  actions=[], need_reviews=[], completion=None)
    return encode_state(packet)


@dataclass(frozen=True)
class RestoredAssessmentState:
    intake: Intake
    uploads: tuple[Upload, ...]
    model: UploadAssessment
    actions: tuple[DemoAction, ...]
    completion: DemoCompletion | None
    completion_stale: bool


def restore_state(packet, custody_results, *, as_of):
    """Rebuild source bindings, provisional analysis and historical currentness."""
    packet = parse_state(encode_state(packet))
    saved_intake = _intake(packet)
    if (type(as_of) is not date or as_of < saved_intake.as_of or type(custody_results) is not tuple
            or len(custody_results) != len(packet["sources"])):
        raise ValueError("Use current server date and the exact verified source inventory.")
    uploads = []
    for source, result in zip(packet["sources"], custody_results):
        _receipt_matches(source, result)
        upload = read_upload(replace(saved_intake, as_of=_date(source["captured_on"])), source["filename"],
                             result.content, tuple(source["requirements"]), kind=source["kind"],
                             observed_on=_date(source["observed_on"]) if source["observed_on"] else None,
                             service=source["service"], environment=source["environment"])
        if upload.evidence.fingerprint != source["source_fingerprint"]:
            raise ValueError("Source binding or parser meaning changed; re-review is required.")
        uploads.append(upload)
    reviews = tuple(NeedReview(**{**review, "source_fingerprints": tuple(review["source_fingerprints"]),
        "fact_fingerprints": (), "reviewed_on": _date(review["reviewed_on"])}) for review in packet["need_reviews"])
    actions = tuple(DemoAction(**{**action, "citations": tuple(DemoCitation(**citation)
        for citation in action["citations"])}) for action in packet["actions"])
    intake = replace(saved_intake, as_of=as_of)
    model = build_assessment(intake, tuple(uploads), need_reviews=reviews)
    completion, stale = None, False
    if packet["completion"] is not None:
        rebuilt = complete_review(model, actions)
        if rebuilt.fingerprint == packet["completion"]["fingerprint"]:
            completion = replace(rebuilt, completed_at=packet["completion"]["completed_at"])
        else:
            stale = True
    return RestoredAssessmentState(intake, tuple(uploads), model, actions, completion, stale)


def with_review_state(packet, model, actions, completion):
    """Capture only server-generated native review history for a new revision."""
    packet = parse_state(encode_state(packet))
    if (type(model) is not UploadAssessment or type(actions) not in (tuple, list)
            or any(type(action) is not DemoAction for action in actions)
            or model.worklist.scope.engagement_id != packet["intake"]["assessment_id"]):
        raise ValueError("Use the current native uploaded assessment and annotations.")
    if completion is not None and not completion_is_current(model, actions, completion):
        raise ValueError("Completion no longer matches this assessment.")
    packet["intake"]["as_of"] = model.worklist.scope.as_of.isoformat()
    packet["actions"] = _native_json([asdict(action) for action in actions])
    # Removed/inapplicable needs do not appear in the rebuilt worklist. Retain
    # their inert historical judgments instead of silently dropping them when
    # recording an unrelated review or completion. Current linked judgments
    # replace the same need ID; older revisions preserve earlier versions.
    reviews = {review["need_id"]: review for review in packet["need_reviews"]}
    for link in model.scenario.assurance_links:
        for review in link.need_reviews:
            reviews[review.need_id] = _native_json(asdict(review))
    packet["need_reviews"] = list(reviews.values())
    packet["completion"] = ({"completed_at": completion.completed_at, "fingerprint": completion.fingerprint}
                            if completion is not None else None)
    return parse_state(encode_state(packet))
