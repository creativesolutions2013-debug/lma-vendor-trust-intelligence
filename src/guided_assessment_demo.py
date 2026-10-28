"""Pure composition for the synthetic guided assessment, never a decision engine.

The existing worklist composes applicability, the assessment work plan and M3D
inspection. Demo actions are annotations only: they cannot confirm a fact, close
an evidence need, approve a control or change governed risk. No database, network,
authentication, storage or vendor-delivery API is imported here.
"""
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
import json

from src.assessment_worklist import AssessmentWorklist, WorklistRow, build_assessment_worklist
from src.assessment_worklist_pilot import WorklistScenario, worklist_scenarios
from src.control_assurance_presentation import CitedInterpretation
from src.evidence_source_validation import BoundEvidence, EvidenceInput, _digest, bind_evidence
from src.mfa_review_pilot import pilot_cases
from src.scoring import InherentRiskInput, calculate_inherent_risk, rating_from_score, tier_from_score
from src.guided_assessment_package import artifact_manifest, assessment_package, json_bytes


SCENARIOS = ("gap", "exception")
RISK_PROFILES = ("Confidential production", "Limited test data")
ACTIONS = ("Accept", "Challenge", "Request Evidence", "Create Finding")


class SourceRole(str, Enum):
    CUSTOMER_POLICY = "Customer requirement / policy context"
    VENDOR_EVIDENCE = "Simulated vendor evidence"
    VENDOR_CONTEXT = "Simulated vendor context only"


@dataclass(frozen=True)
class RoleEvidenceInput(EvidenceInput):
    """Explicit provenance for session uploads; existing fixture hashes stay unchanged."""
    role: SourceRole


# Explicit provenance for this closed fixture package, independent of filenames
# and evidence kind (a vendor policy is not a customer acceptance threshold).
SOURCE_ROLES = {
    "tls-customer-policy": SourceRole.CUSTOMER_POLICY,
    "customer-access-policy": SourceRole.CUSTOMER_POLICY,
    "synthetic-soc2-overview": SourceRole.VENDOR_CONTEXT,
    **{key: SourceRole.VENDOR_EVIDENCE for key in (
        "approved-security-policy", "dr-plan", "dr-exercise", "tls-config",
        "tls-scan", "tls-exception", "vm-exception-response", "vm-remediation-tickets",
    )},
}


def source_role(bound):
    if isinstance(bound.source, RoleEvidenceInput):
        if not isinstance(bound.source.role, SourceRole):
            raise ValueError("Supply an explicit source role.")
        return bound.source.role
    return SOURCE_ROLES[bound.source.document_id]


@dataclass(frozen=True)
class DemoCitation(CitedInterpretation):
    source_role: str = ""
    provenance: str = ""
    document_id: str = ""


@dataclass(frozen=True)
class DemoAssessment:
    scenario_id: str
    evidence_received: bool
    risk_profile: str
    scenario: WorklistScenario
    worklist: AssessmentWorklist
    inherent_score: int
    inherent_rating: str
    inherent_tier: str
    risk_drivers: tuple[str, ...]
    documents: tuple[BoundEvidence, ...]
    context_documents: tuple[BoundEvidence, ...]

    @property
    def residual_recommendation(self):
        return (
            f"Illustrative, non-authoritative recommendation: retain {self.inherent_rating} "
            "pending independent governance. Unconfirmed interpretations, evidence gaps and "
            "retained exceptions do not establish a defensible risk reduction. "
            "Verified control effectiveness and authorized external-risk inputs are unavailable. "
            "This provisional hold is not an RR-2.0 numeric calculation or vendor approval. "
            "No residual score or approved control-effectiveness value is calculated."
        )

    @property
    def residual_drivers(self):
        """Describe the actual review backlog; do not calculate effectiveness."""
        matches = [match for row in self.worklist.rows for match in row.need_matches]
        concerns = [row.requirement_id for row in self.worklist.rows
                    if row.priority <= 1 and row.intent == "Review exception"]
        unavailable = [row.requirement_id for row in self.worklist.rows
                       if row.specialist_available is False]
        unconfirmed = sum(not fact.confirmed for row in self.worklist.rows if row.review
                          for fact in row.review.facts)
        drivers = [
            f"Missing or insufficient specific evidence needs: {sum(match.status == 'Missing or insufficient' for match in matches)}.",
            f"Specific evidence needs awaiting analyst validation: {sum(match.status == 'Analyst validation required' for match in matches)}.",
            f"Unconfirmed interpretations: {unconfirmed}; matching quotations do not establish their meaning.",
        ]
        if concerns:
            drivers.insert(0, "Retained adverse or conflicting evidence needs review: " + ", ".join(concerns) + ".")
        if unavailable:
            drivers.append("Specialist evaluation unavailable for: " + ", ".join(unavailable) + ".")
        return tuple(drivers)


@dataclass(frozen=True)
class DemoAction:
    requirement_id: str
    fingerprint: str
    action: str
    rationale: str
    recorded_at: str
    citations: tuple[CitedInterpretation, ...] = ()
    customer_context: str = ""
    threshold: str = ""


def _risk_context(profile):
    # Same bounded point inputs used by Intake; these are declared scenario
    # assumptions, not observed vendor facts or new weighting/rating rules.
    values = ((10, 16, 15, 8, 5, 3, 1, 0) if profile == RISK_PROFILES[0]
              else (5, 16, 10, 2, 0, 2, 1, 0))
    labels = (
        "Data sensitivity", "Production system access", "Business criticality",
        "Data volume", "Regulatory exposure", "Fourth-party dependency",
        "Geographic risk", "AI autonomy",
    )
    risk = InherentRiskInput(*values)
    return calculate_inherent_risk(risk), tuple(
        f"{label}: {points} declared demo points" for label, points in zip(labels, values)
    )


def _context_documents(scenario):
    # The MFA module retains its own M3B/M3C contract. Its policy is shown only as
    # source context, without translating meanings or inventing a new evaluator.
    mfa_policy = next(case for case in pilot_cases() if case.case_id == "strong").documents[0]
    scope = scenario.scope
    overview = EvidenceInput(
        "synthetic-soc2-overview", "synthetic-soc2-overview.txt",
        (
            "SYNTHETIC SOC 2 overview fixture: review period 2025-10-01 through 2026-09-30.\n"
            "Service context is Acme Analytics production, processing customer analytics data.\n"
            "This demonstration excerpt supplies no authenticated auditor opinion or trust-center access. "
            "It does not establish the implementation or operating effectiveness of the selected controls."
        ).encode("utf-8"),
        "synthetic-demo-v1", "Hand-authored synthetic context; no authenticated vendor artifact",
        scope.as_of, scope.service, scope.environment, "Service overview; context only",
        scope.as_of, "assertion",
    )
    return bind_evidence(overview), bind_evidence(mfa_policy)


def build_demo(scenario_id="gap", evidence_received=False, risk_profile=RISK_PROFILES[0]):
    """Rebuild actual worklist results from fresh, unreviewed synthetic packages."""
    if (type(scenario_id) is not str or scenario_id not in SCENARIOS
            or type(evidence_received) is not bool
            or type(risk_profile) is not str or risk_profile not in RISK_PROFILES):
        raise ValueError("Choose a registered synthetic scenario, risk profile and evidence replay state.")
    packages = {item.scenario_id: item for item in worklist_scenarios()}
    scenario = packages["initial" if scenario_id == "gap" else "adverse"]
    if evidence_received:
        completed = next(link for link in packages["gap-closed"].assurance_links
                         if link.control_id == "BCP-01")
        scenario = replace(scenario, assurance_links=tuple(
            completed if link.control_id == "BCP-01" else link for link in scenario.assurance_links
        ), title=("Completed recovery exercise received — source meanings still require analyst review"
                  if scenario_id == "gap" else
                  "Active alternate TLS exception remains; completed recovery exercise received, meanings unconfirmed"))
    worklist = build_assessment_worklist(
        scenario.scope, scenario.applicability, scenario.requirements, scenario.assurance_links,
        legacy_evidence=scenario.legacy_evidence, control_claims=scenario.control_claims,
    )
    by_fingerprint = {bound.fingerprint: bound for row in worklist.rows if row.review
                      for bound in row.review.evidence}
    documents = tuple(sorted(by_fingerprint.values(), key=lambda bound: (bound.document.filename, bound.fingerprint)))
    score, drivers = _risk_context(risk_profile)
    return DemoAssessment(
        scenario_id, evidence_received, risk_profile, scenario, worklist, score,
        rating_from_score(score), tier_from_score(score), drivers, documents,
        _context_documents(scenario),
    )


def row_fingerprint(model: DemoAssessment, row: WorklistRow):
    """Bind annotations to this row's policy, sources, needs and business context.

    Receiving DR evidence changes only that row. A global replay flag is not an
    authority token and must not invalidate unrelated source-bound annotations.
    """
    if row not in model.worklist.rows:
        raise ValueError("Select a requirement from the current assessment.")
    mapping = next((mapping for mapping in model.scenario.requirements
                    if mapping.control_id == row.control_id
                    and mapping.requirement.requirement_id == row.requirement_id), None)
    return _digest({
        "scope": asdict(model.worklist.scope), "risk_profile": model.risk_profile,
        "inherent_score": model.inherent_score, "risk_drivers": model.risk_drivers,
        "row_id": row.row_id, "requirement": asdict(row.requirement) if row.requirement else None,
        "threshold": row.threshold,
        "bundle": row.review.bundle_fingerprint if row.review else None,
        "needs": [asdict(need) for need in mapping.needs] if mapping else [],
        "need_matches": [asdict(match) for match in row.need_matches],
        "customer_context": getattr(model, "customer_context", None),
    })


def _actions(actions):
    if not isinstance(actions, (tuple, list)) or any(type(action) is not DemoAction for action in actions):
        raise ValueError("Use only recorded synthetic demo actions.")
    return tuple(actions)


def record_action(model, actions, requirement_id, action, rationale):
    """Append an explicit session annotation; evaluator/review state is untouched."""
    history = _actions(actions)
    rows = [row for row in model.worklist.rows if row.requirement_id == requirement_id]
    if (type(requirement_id) is not str or len(rows) != 1
            or type(action) is not str or action not in ACTIONS
            or type(rationale) is not str or not 1 <= len(rationale) <= 1200 or not rationale.strip()
            or any(ord(char) < 32 and char not in "\n\t" or ord(char) == 127 for char in rationale)):
        raise ValueError("Choose a current requirement and action, with a 1–1200 character review rationale.")
    row = rows[0]
    fingerprint = row_fingerprint(model, row)
    if action == "Create Finding" and any(
        previous.action == "Create Finding" and previous.requirement_id == requirement_id
        and previous.fingerprint == fingerprint and previous.rationale.strip() == rationale.strip()
        for previous in history
    ):
        raise ValueError(f"An identical draft finding already exists for {requirement_id} in this source and requirement context. "
                         "Use a distinct rationale for a separate finding.")
    citations = tuple(DemoCitation(
        f"Supplied {bound.source.evidence_kind}; {bound.source.service} · {bound.source.environment} · "
        f"{bound.source.account_scope}; observed {bound.source.observed_on}; captured {bound.source.captured_on}; "
        "source consistency only, not confirmed meaning",
        bound.document.filename, segment.location, segment.text, bound.fingerprint, False,
        source_role(bound).value, bound.source.origin, bound.source.document_id,
    ) for bound in row.review.evidence for segment in bound.document.segments) if row.review else ()
    return history + (DemoAction(
        requirement_id, fingerprint, action, rationale.strip(),
        datetime.now(timezone.utc).isoformat(),
        citations, row.presentation.customer_requirement if row.presentation else "Customer context unavailable",
        row.review.threshold_summary if row.review else row.threshold,
    ),)


def active_actions(model, actions):
    """Return only each requirement's latest annotation when its context matches."""
    latest = {action.requirement_id: action for action in _actions(actions)}
    return tuple(latest[row.requirement_id] for row in model.worklist.rows
                 if row.requirement_id in latest
                 and latest[row.requirement_id].fingerprint == row_fingerprint(model, row))


def _date(value):
    return value.isoformat() if value is not None else None


def _citations(row):
    # These are actual parser segments, including policy/adverse context. Their
    # presence is neither a semantic confirmation nor evidence of authenticity.
    return [dict(
        document_id=bound.source.document_id, filename=bound.document.filename,
        location=segment.location, quote=segment.text,
        source_fingerprint=bound.fingerprint, evidence_kind=bound.source.evidence_kind,
        source_role=source_role(bound).value,
        service=bound.source.service, environment=bound.source.environment,
        scope=bound.source.account_scope, observed_on=_date(bound.source.observed_on),
        captured_on=_date(bound.source.captured_on), provenance=bound.source.origin,
    ) for bound in row.review.evidence for segment in bound.document.segments] if row.review else []


def _assessment_payload(model, actions):
    """Export the same current rows, source segments and explicit session ledger."""
    history = _actions(actions)
    active = active_actions(model, history)
    by_requirement = {row.requirement_id: row for row in model.worklist.rows}
    matches = [match for row in model.worklist.rows for match in row.need_matches]
    payload = {
        "title": "SYNTHETIC DEMO — Provisional vendor assessment report",
        "synthetic": True, "provisional": True, "authoritative": False,
        "session_only": True, "scenario_id": model.scenario_id,
        "evidence_received": model.evidence_received,
        "scope": {**asdict(model.worklist.scope), "as_of": model.worklist.scope.as_of.isoformat()},
        "assessment_context": getattr(model, "customer_context", None),
        "risk": {
            "profile": model.risk_profile, "inherent_score": model.inherent_score,
            "inherent_rating": model.inherent_rating, "inherent_tier": model.inherent_tier,
            "drivers": list(model.risk_drivers),
            "residual_recommendation": model.residual_recommendation,
            "residual_drivers": list(model.residual_drivers),
            "residual_score": None, "approved_risk": False,
            "residual_status": "Pending verified inputs / risk-owner decision",
            "residual_rating": None, "residual_hold_rating": model.inherent_rating,
        },
        "requirements": [{
            "control_id": row.control_id, "requirement_id": row.requirement_id,
            "title": row.title, "threshold": row.threshold, "outcome": row.outcome,
            "customer_policy_id": row.requirement.customer_policy_id if row.requirement else None,
            "policy_version": row.requirement.policy_version if row.requirement else None,
            "max_age_days": row.requirement.max_age_days if row.requirement else None,
            "scope": row.requirement.scope if row.requirement else None,
            "threshold_summary": row.review.threshold_summary if row.review else row.threshold,
            "presentation": asdict(row.presentation) if row.presentation else None,
            "specialist_available": row.specialist_available, "provisional": True,
            "next_action": row.next_action,
            "citations": [c for c in _citations(row) if c["source_role"] != SourceRole.CUSTOMER_POLICY],
            "customer_policy_citations": [c for c in _citations(row) if c["source_role"] == SourceRole.CUSTOMER_POLICY],
            "needs": [asdict(match) for match in row.need_matches],
            "limitations": list(row.limitations),
        } for row in model.worklist.rows],
        "targeted_requests": [asdict(request) for request in model.worklist.requests],
        "question_metrics": {
            "ask_everything_baseline": model.worklist.baseline_questions,
            "baseline_unit": "One broad question per applicable customer requirement",
            "distinct_targeted_requests": len(model.worklist.requests),
            "reviewed_supporting_needs": sum(match.status == "Supported by reviewed evidence" for match in matches),
            "awaiting_analyst_validation_needs": sum(match.status == "Analyst validation required" for match in matches),
            "missing_or_insufficient_needs": sum(match.status == "Missing or insufficient" for match in matches),
            "limitation": "Deferred questions are not resolved needs; these counts do not measure real-world time savings or technical compliance.",
        },
        "analyst_actions": [{
            **asdict(action), "active": action in active,
            "status": ("Current" if action in active else "Stale context"
                       if action.requirement_id not in by_requirement
                       or action.fingerprint != row_fingerprint(model, by_requirement[action.requirement_id])
                       else "Superseded"),
            "semantic_confirmation": False, "governed_decision": False,
        } for action in history],
        "findings": [{
            "requirement_id": action.requirement_id, "rationale": action.rationale,
            "recorded_at": action.recorded_at, "fingerprint": action.fingerprint,
            "draft": True, "synthetic": True, "resolved": False,
            "context_status": ("Current" if action.requirement_id in by_requirement
                               and action.fingerprint == row_fingerprint(model, by_requirement[action.requirement_id])
                               else "Stale context — re-review required"),
            "customer_context": action.customer_context, "threshold": action.threshold,
            "citations": [asdict(citation) for citation in action.citations],
        } for action in history if action.action == "Create Finding"],
        "context_only_sources": [{
            "document_id": bound.source.document_id, "filename": bound.document.filename,
            "source_role": source_role(bound).value, "provenance": bound.source.origin,
            "source_fingerprint": bound.fingerprint,
            "use": "Context only; not used to satisfy the selected customer requirements",
            "segments": [{"location": segment.location, "quote": segment.text}
                         for segment in bound.document.segments],
        } for bound in model.context_documents if source_role(bound) != SourceRole.CUSTOMER_POLICY],
        "customer_policy_sources": [{
            "document_id": bound.source.document_id, "filename": bound.document.filename,
            "source_role": source_role(bound).value, "provenance": bound.source.origin,
            "source_fingerprint": bound.fingerprint,
            "use": "Customer acceptance criteria only; not vendor implementation or operating proof",
            "segments": [{"location": segment.location, "quote": segment.text}
                         for segment in bound.document.segments],
        } for bound in model.documents + model.context_documents
           if source_role(bound) == SourceRole.CUSTOMER_POLICY],
        "limitations": [
            "Synthetic hand-authored evidence and supplied interpretations are not real vendor assurance.",
            "A source hash or quotation match proves consistency, not authenticity or semantic truth.",
            "Demo Accept/Challenge/Request Evidence/Create Finding annotations do not change M3D fact reviews or governed decisions.",
            "Simulated Accept is a draft discussion annotation; it does not confirm facts, satisfy evidence needs or approve a control.",
            ("The selected requirements are synthetic examples; workflow coverage is not automated technical coverage or a complete production assessment."
             if getattr(model, "customer_context", None) else
             "The four selected requirements are a bounded demonstration, not a complete production assessment or standards certification."),
            "No vendor messages, confidential evidence, real authentication or authoritative risk updates are enabled.",
        ],
    }
    links = {}
    for row in model.worklist.rows:
        if row.review:
            for bound in row.review.evidence:
                links.setdefault(bound.source.document_id, []).append({
                    "requirement_id": row.requirement_id,
                    "citations": [{"location": s.location, "quote": s.text} for s in bound.document.segments],
                })
    manifest = artifact_manifest(_package_sources(model), links)
    payload["evidence_manifest"] = {
        "path": "manifest.json", "sha256": sha256(json_bytes(manifest)).hexdigest(),
        "artifacts": manifest["artifacts"],
    }
    artifacts = {a["document_id"]: a for a in manifest["artifacts"]}
    cited_sources = payload["context_only_sources"] + payload["customer_policy_sources"]
    for row in payload["requirements"]:
        cited_sources += row["citations"] + row["customer_policy_citations"]
    for entry in payload["analyst_actions"] + payload["findings"]:
        cited_sources += entry["citations"]
    for citation in cited_sources:
        artifact = artifacts.get(citation["document_id"])
        fingerprint = citation.get("source_fingerprint", citation.get("fingerprint"))
        if artifact is not None and fingerprint == artifact["source_fingerprint"]:
            citation.update(artifact_id=artifact["document_id"], archive_path=artifact["archive_path"],
                            content_sha256=artifact["sha256"])
        else:
            citation.update(artifact_id=None, archive_path=None, content_sha256=None,
                            attachment_status="Historical source not attached to current evidence set")
    # Ensure this public payload has only JSON-native values (including lists
    # rather than dataclass tuples), matching the downloaded report exactly.
    return json.loads(json.dumps(payload, ensure_ascii=False))


@dataclass(frozen=True)
class DemoCompletion:
    completed_at: str
    fingerprint: str
    snapshot_json: str

    @property
    def snapshot(self):
        # Return a new value: callers cannot mutate the captured as-of report.
        return json.loads(self.snapshot_json)


def complete_review(model, actions):
    """Capture documentation of a synthetic review; never a vendor decision."""
    payload = _assessment_payload(model, actions)
    return DemoCompletion(
        datetime.now(timezone.utc).isoformat(), _digest(payload),
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
    )


def completion_is_current(model, actions, completion):
    return (type(completion) is DemoCompletion
            and completion.fingerprint == _digest(completion.snapshot)
            and completion.fingerprint == _digest(_assessment_payload(model, actions)))


def report_payload(model, actions, completion=None):
    if completion is not None and not completion_is_current(model, actions, completion):
        raise ValueError("Completion context changed; reopen the demo review and finish again.")
    payload = completion.snapshot if completion is not None else _assessment_payload(model, actions)
    payload["review_completion"] = {
        "status": "Completed (demo review only)" if completion is not None else "In progress",
        "completed_at": completion.completed_at if completion is not None else None,
        "snapshot_fingerprint": completion.fingerprint if completion is not None else None,
        "vendor_decision": "Pending", "vendor_approved": False,
        "technical_facts_confirmed_by_completion": False, "risk_accepted": False,
        "limitation": "Completes the synthetic review walkthrough only; open evidence, findings and risk concerns remain unresolved.",
    }
    return payload


def report_bytes(model, actions, completion=None):
    return (json.dumps(report_payload(model, actions, completion), ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _package_sources(model):
    return [(bound, source_role(bound).value) for bound in model.documents + model.context_documents]


def package_bytes(model, actions, completion=None):
    return assessment_package(report_payload(model, actions, completion), _package_sources(model))
