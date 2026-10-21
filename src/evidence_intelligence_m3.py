"""M3A: pure, provisional evaluation of PAM-01.MFA, never a governed decision.

Callers supply structured interpretations, not model outcomes. Exact citation
verification proves provenance, not entailment: analysts must verify each fact's
value, scope, dates and implementation details against the quoted context.
No extraction, I/O, persistence, AI, orchestration or scoring occurs here.
"""
from dataclasses import dataclass, field
from datetime import date
from typing import Iterable, Mapping

EVALUATOR_VERSION = "MFA-1.1"
REQUIREMENT_ID = "PAM-01.MFA"
PARENT_CONTROL_ID = "PAM-01"
BOOLEAN_DIMENSIONS = ("existence", "enforcement", "operating", "fallback_safe",
                      "recovery_safe", "exceptions_absent")
DIMENSIONS = ("existence", "method", "enforcement", "operating", "fallback_safe",
              "recovery_safe", "exceptions_absent")
KNOWN_METHODS = frozenset({"sms", "totp", "push", "fido2", "webauthn"})


@dataclass(frozen=True)
class MfaRequirement:
    customer_policy_id: str
    version: str
    service: str
    environment: str
    account_scope: str
    allowed_methods: tuple[str, ...]
    phishing_resistant: bool
    require_operating: bool
    max_age_days: int
    approved_equivalents: tuple[str, ...] = ()
    requirement_id: str = field(default=REQUIREMENT_ID, init=False)
    parent_control_id: str = field(default=PARENT_CONTROL_ID, init=False)

    def __post_init__(self):
        if any(not isinstance(v, str) or not v.strip() for v in (
            self.customer_policy_id, self.version, self.service,
            self.environment, self.account_scope,
        )):
            raise ValueError("Explicit customer policy, version and scope are required.")
        if type(self.max_age_days) is not int or self.max_age_days < 0:
            raise ValueError("max_age_days must be a nonnegative integer.")
        if type(self.phishing_resistant) is not bool or type(self.require_operating) is not bool:
            raise ValueError("Explicit boolean thresholds are required.")
        for values in (self.allowed_methods, self.approved_equivalents):
            if (not isinstance(values, tuple) or
                    any(not isinstance(v, str) or not v.strip() or v != v.lower() for v in values) or
                    len(set(values)) != len(values)):
                raise ValueError("Methods must be unique lowercase tuples.")
        if not self.allowed_methods or not set(self.allowed_methods) <= KNOWN_METHODS | set(self.approved_equivalents):
            raise ValueError("Allowed methods must be known or explicitly approved equivalents.")
        if set(self.approved_equivalents) & KNOWN_METHODS:
            raise ValueError("Known methods cannot be reclassified as equivalents.")


@dataclass(frozen=True)
class SourceSegment:
    """Map by stable document-version/segment ID; filenames need not be unique."""
    filename: str
    location: str
    text: str


@dataclass(frozen=True)
class Citation:
    source_id: str
    quote: str


@dataclass(frozen=True)
class MfaFact:
    dimension: str
    value: bool | str | None
    citation: Citation
    service: str | None
    environment: str | None
    account_scope: str | None
    observed_on: date | None
    evidence_kind: str  # policy, assertion, configuration, test
    uncertainty: str = ""
    # For a method fact, these describe this cited implementation, not the brand.
    implementation_evidenced: bool | None = None
    origin_bound: bool | None = None
    verifier_bound: bool | None = None
    multifactor: bool | None = None
    # Only configuration/test evidence can establish an active authentication path.
    authentication_path: str | None = None
    active: bool | None = None


@dataclass(frozen=True)
class FactAssessment:
    fact: MfaFact
    status: str  # supports, adverse, reported_exception, unknown, excluded
    reason: str


@dataclass(frozen=True)
class DimensionAssessment:
    dimension: str
    status: str  # supported, adverse, conflict, reported_exception, unknown, not_required


@dataclass(frozen=True)
class MfaEvaluation:
    requirement: MfaRequirement
    as_of: date
    outcome: str
    dimensions: tuple[DimensionAssessment, ...]
    facts: tuple[FactAssessment, ...]
    follow_up: tuple[str, ...]
    sources: tuple[tuple[str, SourceSegment], ...]
    evaluator_version: str = field(default=EVALUATOR_VERSION, init=False)
    provisional: bool = field(default=True, init=False)
    review_required: bool = field(default=True, init=False)


def _assess(fact: MfaFact, policy: MfaRequirement, as_of: date) -> FactAssessment:
    def result(status, reason):
        if (status == "unknown" and fact.evidence_kind == "assertion"
                and fact.dimension in BOOLEAN_DIMENSIONS and fact.value is False):
            return FactAssessment(fact, "reported_exception",
                                  "Unverified reported exception; priority investigation required. " + reason)
        return FactAssessment(fact, status, reason)

    scope = (fact.service, fact.environment, fact.account_scope)
    target = (policy.service, policy.environment, policy.account_scope)
    if any(actual is not None and actual != expected for actual, expected in zip(scope, target)):
        return result("excluded", "Scope mismatch; retained for analyst review.")
    if None in scope:
        return result("unknown", "Service, environment or account scope is unknown.")
    if fact.observed_on is None or not 0 <= (as_of - fact.observed_on).days <= policy.max_age_days:
        return result("unknown", "Observation date is unknown, future or outside customer freshness threshold.")
    if fact.uncertainty or fact.value is None:
        return result("unknown", "Interpretation is uncertain or value is unknown.")
    if fact.evidence_kind in {"policy", "assertion"}:
        return result("unknown", "Policy intent or assertion does not establish implementation/operation.")
    if fact.dimension == "operating" and fact.evidence_kind != "test":
        return result("unknown", "Operating evidence requires actual testing, not configuration alone.")
    if fact.dimension != "method":
        return result("supports" if fact.value else "adverse",
                      "Cited fact supports the threshold." if fact.value else
                      "Cited fact affirmatively contradicts the threshold.")
    if fact.active is False:
        return result("unknown", "Disabled method does not establish an active authentication path.")
    method = fact.value
    if method not in KNOWN_METHODS | set(policy.approved_equivalents):
        return result("unknown", "Authentication method is unknown or unclassified.")
    if fact.implementation_evidenced is not True:
        return result("unknown", "Method name alone is not implementation evidence.")
    if method not in policy.allowed_methods:
        return result("adverse", "Implemented method is outside customer allowed methods.")
    if fact.multifactor is False:
        return result("adverse", "Implemented authentication does not use multiple factors.")
    if fact.multifactor is not True:
        return result("unknown", "Multiple factors require implementation evidence.")
    if policy.phishing_resistant:
        if method in {"sms", "totp", "push"}:
            return result("adverse", "This method does not establish phishing-resistant authentication.")
        properties = (fact.origin_bound, fact.verifier_bound, fact.multifactor)
        if False in properties:
            return result("adverse", "Implementation lacks a required phishing-resistant MFA property.")
        if any(value is not True for value in properties):
            return result("unknown", "Origin binding, verifier binding and multiple factors require implementation evidence.")
    return result("supports", "Implemented method meets the customer method threshold.")


def evaluate_privileged_mfa(
    requirement: MfaRequirement,
    facts: Iterable[MfaFact],
    sources: Mapping[str, SourceSegment],
    *,
    as_of: date,
) -> MfaEvaluation:
    """Evaluate exact-scope facts with mandatory enforcement and safe alternate paths.

    Boolean facts refer to the entire stated population/path inventory: e.g.
    enforcement=True means all accounts in account_scope, fallback_safe=True means
    all fallback paths meet this same policy (including explicitly no such paths).
    Method facts with distinct authentication_path IDs and active=True describe
    simultaneously enabled paths; opposed claims for one path remain conflicts.
    Separate populations must be evaluated separately. Machine accounts must not
    silently inherit interactive-human MFA requirements.

    Invalid citations/input raise ValueError; no partial conclusion is returned.
    All valid facts, including stale/adverse/out-of-scope ones, remain in results.
    """
    if type(as_of) is not date:
        raise ValueError("An explicit evaluation date is required.")
    facts = tuple(facts)
    for fact in facts:
        if fact.dimension not in DIMENSIONS:
            raise ValueError("Unsupported MFA dimension.")
        if fact.evidence_kind not in {"policy", "assertion", "configuration", "test"}:
            raise ValueError("Unsupported evidence kind.")
        if fact.observed_on is not None and type(fact.observed_on) is not date:
            raise ValueError("Observation date must be a date or None.")
        if fact.dimension in BOOLEAN_DIMENSIONS:
            if fact.value is not None and type(fact.value) is not bool:
                raise ValueError("Boolean dimension requires bool or None.")
        elif fact.value is not None and (not isinstance(fact.value, str) or not fact.value.strip()):
            raise ValueError("Method requires a nonempty string or None.")
        if fact.authentication_path is not None and (
            fact.dimension != "method" or not isinstance(fact.authentication_path, str)
            or not fact.authentication_path.strip()
        ):
            raise ValueError("Authentication path requires a nonempty method path identifier.")
        if fact.active is not None and (fact.dimension != "method" or not fact.authentication_path):
            raise ValueError("Active method facts require an authentication path identifier.")
        for value in (fact.implementation_evidenced, fact.origin_bound, fact.verifier_bound, fact.multifactor, fact.active):
            if value is not None and type(value) is not bool:
                raise ValueError("Implementation properties require bool or None.")
        source = sources.get(fact.citation.source_id)
        quote = fact.citation.quote
        if (source is None or not source.filename or not source.location or
                not isinstance(quote, str) or not quote.strip() or quote not in source.text):
            raise ValueError("Citation must match the original source segment exactly.")

    assessed = tuple(_assess(fact, requirement, as_of) for fact in facts)
    dimensions = []
    for dimension in DIMENSIONS:
        states = {item.status for item in assessed if item.fact.dimension == dimension}
        if "supports" in states and "adverse" in states:
            status = "conflict"
        elif "adverse" in states:
            status = "adverse"
        elif "reported_exception" in states:
            status = "reported_exception"
        elif "unknown" in states:
            status = "unknown"  # A strong source cannot erase unresolved evidence.
        elif "supports" in states:
            status = "supported"
        else:
            status = "unknown"
        if dimension == "operating" and not requirement.require_operating and not states:
            status = "not_required"
        dimensions.append(DimensionAssessment(dimension, status))
    states = {item.status for item in dimensions}
    # Distinct tested/configured active paths may coexist: a strong method does
    # not negate a weaker enabled path. Opposed claims about the same path remain
    # a conflict. Unidentified paths do not establish simultaneous enablement.
    active_weak_path = any(
        item.status == "adverse" and item.fact.dimension == "method"
        and item.fact.active is True
        and not any(
            other.status == "supports" and other.fact.dimension == "method"
            and other.fact.authentication_path == item.fact.authentication_path
            for other in assessed
        )
        for item in assessed
    )
    if "adverse" in states or active_weak_path:
        outcome = "Risk Identified"
    elif "conflict" in states or "reported_exception" in states:
        outcome = "Needs Review"
    elif not facts or all(item.status == "excluded" for item in assessed):
        outcome = "Evidence Missing"
    elif states <= {"supported", "not_required"}:
        outcome = "Met"
    elif "supported" in states:
        outcome = "Partially Met"
    else:
        outcome = "Needs Review"
    reported_follow_up = tuple(
        f"Priority: investigate reported {item.fact.dimension} exception from "
        f"{item.fact.citation.source_id}; verify affected accounts, scope, currency "
        "and bypass/remediation status with configuration and operating tests."
        for item in assessed if item.status == "reported_exception"
    )
    follow_up = reported_follow_up + tuple(
        f"Verify {item.dimension} against customer policy: {item.status}."
        for item in dimensions if item.status not in {"supported", "not_required"}
    ) + ("Analyst must confirm interpretations, source context and the provisional result.",)
    return MfaEvaluation(requirement, as_of, outcome, tuple(dimensions), assessed, follow_up,
                         tuple(sorted((key, sources[key]) for key in
                                      {fact.citation.source_id for fact in facts})))
