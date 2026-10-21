"""M4A-1: pure presentation adapter over the existing work plan and M3D review.

No new assessment, technical or approval engine lives here. Legacy sufficiency is
informational. Explicitly scoped customer mappings and source-bound M3D inspection
determine what can be presented; workflow intents and questions are previews only.
"""
from dataclasses import asdict, dataclass, field, replace
from datetime import date, timedelta
from types import SimpleNamespace

from src.applicability import ApplicabilityResult
from src.assessment_orchestrator import AssessmentWorkPlan, build_assessment_work_plan
from src.control_assurance import (
    ControlCase, ControlReview, ControlReviewState, ControlThreshold, RequirementContext,
    inspect_control, requirement_fingerprint,
)
from src.control_assurance_presentation import AssurancePresentation, present_control
from src.evidence_source_validation import _digest, segment_id, source_issues
from src.targeted_gap import analyze_targeted_evidence_gaps


@dataclass(frozen=True)
class AssessmentScope:
    engagement_id: str
    service: str
    environment: str
    as_of: date


@dataclass(frozen=True)
class EvidenceNeed:
    """Explicit artifact request context; dimensions describe analyst work only.

    Presence of an accepted candidate suppresses a duplicate artifact request,
    never establishes any dimension or technical threshold as satisfied.
    """
    need_id: str
    missing_fact: str
    acceptable_evidence: str
    question: str
    accepted_kinds: tuple[str, ...]
    dimensions: tuple[str, ...] = ()
    max_age_days: int | None = None

    def __post_init__(self):
        if (any(not isinstance(x, str) or not x.strip() for x in (
                self.need_id, self.missing_fact, self.acceptable_evidence, self.question))
                or not self.accepted_kinds
                or any(x not in {"policy", "assertion", "configuration", "test"} for x in self.accepted_kinds)
                or (self.max_age_days is not None and (type(self.max_age_days) is not int or self.max_age_days < 1))):
            raise ValueError("Supply a specific missing fact, acceptable evidence and scoped question.")


@dataclass(frozen=True)
class RequirementMapping:
    control_id: str
    requirement: RequirementContext
    threshold: ControlThreshold
    needs: tuple[EvidenceNeed, ...] = ()
    workflow_status: str = "Evidence review"


@dataclass(frozen=True)
class AssuranceLink:
    engagement_id: str
    control_id: str
    case: ControlCase
    state: ControlReviewState = ControlReviewState()


@dataclass(frozen=True)
class ScopedLegacyEvidence:
    engagement_id: str
    service: str
    environment: str
    record: object


@dataclass(frozen=True)
class VendorRequestPreview:
    request_id: str
    requirement_ids: tuple[str, ...]
    missing_fact: str
    acceptable_evidence: str
    question: str
    provisional: bool = field(default=True, init=False)


@dataclass(frozen=True)
class WorklistRow:
    row_id: str
    control_id: str
    requirement_id: str
    title: str
    requirement: RequirementContext | None
    threshold: str
    outcome: str
    legacy_status: str
    legacy_action: str
    specialist_available: bool | None
    priority: int
    intent: str
    next_action: str
    missing_fact: str
    request_ids: tuple[str, ...]
    presentation: AssurancePresentation | None
    review: ControlReview | None
    limitations: tuple[str, ...]
    workflow_status: str
    provisional: bool = field(default=True, init=False)


@dataclass(frozen=True)
class AssessmentWorklist:
    scope: AssessmentScope
    rows: tuple[WorklistRow, ...]
    requests: tuple[VendorRequestPreview, ...]
    diagnostics: tuple[str, ...]
    legacy_plan: AssessmentWorkPlan
    baseline_questions: int
    provisional: bool = field(default=True, init=False)


def _source_map(view):
    return {segment_id(b.source.document_id, n): (b, part)
            for b in view.evidence for n, part in enumerate(b.document.segments, 1)}


def _citation_intact(p, sources):
    found = sources.get(p.source_id)
    return bool(found and p.source_fingerprint == found[0].fingerprint
                and p.location == found[1].location and isinstance(p.quote, str)
                and p.quote.strip() and p.quote in found[1].text)


def _presentation(case, view):
    """Only actual source matches get citation presentation, not invented quotes."""
    p = present_control(case, view)
    sources = _source_map(view)
    verified = {(f.filename, f.proposal.location, f.proposal.quote, f.fingerprint)
                for f in view.facts if _citation_intact(f.proposal, sources)}
    verified.update((b.document.filename, s.location, s.text, b.fingerprint)
                    for b in view.evidence for s in b.document.segments)
    def valid(c):
        return (c.filename, c.location, c.quote, c.fingerprint) in verified
    # Source signals have their own fingerprint; their quotes still originate
    # from an actual parser segment, never a proposed interpretation.
    verified.update((s.filename, s.location, s.quote, s.signal_id) for s in view.signals)
    return replace(p, supporting=tuple(c for c in p.supporting if valid(c)),
                   evidence_for_review=tuple(c for c in p.evidence_for_review if valid(c)),
                   attention=tuple(replace(i, citations=tuple(c for c in i.citations if valid(c))) for i in p.attention))


def _candidate_gap(scope, mapping, case, view, need):
    """Use existing targeted-gap logic only on explicitly linked source inventory.

    Present but unreviewed/unextracted evidence calls for analyst validation. An
    absent artifact kind/period can justify the supplied precise question; neither
    legacy UNSUPPORTED nor an M3D missing check alone triggers vendor follow-up.
    """
    r = mapping.requirement
    sources = _source_map(view)
    target = requirement_fingerprint(r, mapping.threshold)
    age = min(r.max_age_days, need.max_age_days or r.max_age_days)
    available, opaque = [], False
    for b in view.evidence:
        s = b.source
        if s.evidence_kind not in need.accepted_kinds:
            continue
        if source_issues(s, service=r.service, environment=r.environment, scope=r.scope,
                         max_age_days=age, as_of=scope.as_of):
            continue
        cited = any(_citation_intact(f.proposal, sources) and sources[f.proposal.source_id][0] == b
                    for f in view.facts)
        bindings = [x for x in case.relevance if x.source_fingerprint == b.fingerprint]
        relevant = (len(bindings) == 1 and bindings[0].requirement_fingerprint == target
                    and isinstance(bindings[0].rationale, str) and bindings[0].rationale.strip())
        permitted = relevant or (view.specialist_available and cited)
        if not permitted:
            opaque = True
            continue
        available.append(SimpleNamespace(
            id=len(available) + 1, document_type=need.acceptable_evidence,
            document_name=b.document.filename, status="Current",
            expiration_date=(s.observed_on + timedelta(days=age)).isoformat(),
            exceptions_count=0, detected_exceptions="", extraction_confidence=1.0,
        ))
    gaps = analyze_targeted_evidence_gaps((need.acceptable_evidence,), available, today=scope.as_of)
    return not opaque and gaps.items[0].workflow_action == "Request Vendor"


def build_assessment_worklist(scope: AssessmentScope, applicability: ApplicabilityResult,
                              requirements, assurance_links, *, legacy_evidence=(), control_claims=()):
    if (type(scope.as_of) is not date or any(not isinstance(x, str) or not x.strip()
                                           for x in (scope.engagement_id, scope.service, scope.environment))):
        raise ValueError("An explicit engagement, service, environment and assessment date are required.")
    controls = {c.control_id: c for c in applicability.controls}
    if len(controls) != len(applicability.controls):
        raise ValueError("Duplicate applicable control IDs are ambiguous.")
    mappings, links, diagnostics = tuple(requirements), tuple(assurance_links), []
    keys = [(m.control_id, m.requirement.requirement_id) for m in mappings]
    if len(set(keys)) != len(keys):
        raise ValueError("Duplicate applicable requirement mappings are ambiguous.")
    link_keys = [(link.control_id, link.case.requirement.requirement_id) for link in links]
    if len(set(link_keys)) != len(link_keys):
        # One case is the complete source bundle, not a competing result. Reject
        # duplicates before presenting anything; choosing one can hide a failure.
        raise ValueError("Duplicate assurance linkages require analyst reconciliation; no results were reused.")
    records = []
    for item in legacy_evidence:
        if not isinstance(item, ScopedLegacyEvidence):
            raise ValueError("Legacy evidence requires explicit relationship context.")
        if (item.engagement_id, item.service, item.environment) == (scope.engagement_id, scope.service, scope.environment):
            records.append(item.record)
        else:
            diagnostics.append("Legacy evidence from a different relationship was excluded.")
    ids = [getattr(x, "id", None) for x in records]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate legacy evidence identities are ambiguous.")
    claims = tuple(c for c in control_claims if c.evidence_id in ids and c.control_id in controls)
    plan = build_assessment_work_plan(applicability, records, claims)
    legacy = {i.control_id: i for i in plan.items}
    for m in mappings:
        if m.control_id not in controls:
            diagnostics.append(f"Requirement mapping for non-applicable control {m.control_id} was excluded.")
    rows, requests, consumed = [], {}, set()
    for control_id, control in controls.items():
        defined = [m for m in mappings if m.control_id == control_id]
        for mapping in defined or (None,):
            old = legacy[control_id]
            r = mapping.requirement if mapping else None
            rid = r.requirement_id if r else control_id
            row_id = control_id + ":" + rid
            limits, view, presentation = [], None, None
            row_requests, missing = [], []
            outcome, priority, intent = "Needs Review", 1, "Analyst validate"
            action = "Supply the exact customer requirement, threshold and assurance linkage before evaluation."
            matched = [] if r is None else [(n, link) for n, link in enumerate(links)
                        if link.control_id == control_id and link.case.requirement.requirement_id == rid]
            for n, _ in matched:
                consumed.add(n)
            if mapping is None:
                limits.append("Customer requirement definition and explicit mapping are unavailable; legacy evidence is not technical assurance.")
            elif len(matched) != 1:
                limits.append("A unique explicit assurance linkage is missing or ambiguous.")
            else:
                link = matched[0][1]
                if (link.engagement_id != scope.engagement_id
                        or (r.service, r.environment) != (scope.service, scope.environment)
                        or link.case.requirement != r or link.case.as_of != scope.as_of
                        or requirement_fingerprint(r, mapping.threshold) != requirement_fingerprint(link.case.requirement, link.case.threshold)):
                    limits.append("Assurance linkage differs in engagement, service, environment, customer policy/version, exact requirement, threshold, scope or assessment date.")
                else:
                    view = inspect_control(link.case, link.state)
                    presentation = _presentation(link.case, view)
                    limits.extend(view.limitations)
                    outcome = view.outcome
                    failed_ids = {fid for c in view.checks if c.status == "failed" for fid in c.fact_ids}
                    verified_failure = any(f.confirmed and f.proposal.fact_id in failed_ids
                                           and f.proposal.active is True for f in view.facts)
                    conflict = any(c.status == "conflict" for c in view.checks)
                    potential = any(f.direction == "adverse" for f in view.facts) or any(s.status != "dismissed_by_analyst" for s in view.signals)
                    if outcome == "Risk Identified" and verified_failure:
                        priority, intent, action = 0, "Review exception", view.next_action
                    elif conflict or potential or outcome == "Risk Identified":
                        if outcome == "Risk Identified" and not verified_failure:
                            outcome = "Needs Review"
                        priority, intent, action = 1, "Review exception", "Resolve the cited adverse or conflicting evidence before relying on supporting statements."
                    else:
                        pending = [need for need in mapping.needs if _candidate_gap(scope, mapping, link.case, view, need)]
                        if pending:
                            priority, intent = 2, "Request one missing item"
                            action = pending[0].question
                            for need in pending:
                                key = _digest({"scope": asdict(scope), "control_id": control_id,
                                               "requirement": requirement_fingerprint(r, mapping.threshold),
                                               "need": {k: v for k, v in asdict(need).items() if k != "need_id"}})
                                requests[key] = VendorRequestPreview(key, (rid,), need.missing_fact, need.acceptable_evidence, need.question)
                                row_requests.append(key)
                                missing.append(need.missing_fact)
                        elif outcome == "Met" and view.facts and all(f.confirmed for f in view.facts) and view.bundle_review_valid:
                            priority, intent = 4, "Reuse evidence — governance review required"
                            action = "Reuse the cited provisional assurance and submit it for independent authorized governance."
                        else:
                            if outcome == "Met":
                                outcome = "Needs Review"
                            priority, intent, action = 3, "Analyst validate", view.next_action
            if presentation:
                presentation = replace(presentation, outcome=outcome, next_action=action)
            rows.append(WorklistRow(
                row_id, control_id, rid, control.requirement, r,
                mapping.threshold.describe() if mapping else "Customer threshold not supplied",
                outcome, old.sufficiency_status or old.disposition, old.workflow_action,
                view.specialist_available if view else None, priority, intent, action,
                "; ".join(dict.fromkeys(missing)),
                tuple(dict.fromkeys(row_requests)), presentation, view, tuple(dict.fromkeys(limits)),
                mapping.workflow_status if mapping else "Mapping review required",
            ))
    for n, link in enumerate(links):
        if n not in consumed:
            diagnostics.append(f"Unlinked assurance input for exact requirement {link.case.requirement.requirement_id}; no source content was reused.")
    return AssessmentWorklist(scope, tuple(sorted(rows, key=lambda r: (r.priority, r.row_id))),
                              tuple(requests.values()), tuple(diagnostics), plan, len(rows))
