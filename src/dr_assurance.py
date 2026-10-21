"""Typed disaster-recovery rules: actual completed exercises and achieved results."""
from dataclasses import dataclass
import re

from src.control_assurance import Check, TechnicalResult

DR_SIGNALS = re.compile(r"\b(?:except\w*|fail\w*|untested|not\s+tested|excluded|overrun|incomplete)\b", re.I)


@dataclass(frozen=True)
class DrThreshold:
    max_test_age_days: int
    max_rto_minutes: int | None
    max_rpo_minutes: int | None

    def __post_init__(self):
        if type(self.max_test_age_days) is not int or self.max_test_age_days < 1:
            raise ValueError("A positive customer-approved test interval is required.")
        if any(x is not None and (type(x) is not int or x < 0)
               for x in (self.max_rto_minutes, self.max_rpo_minutes)):
            raise ValueError("Recovery objectives must be nonnegative minutes or explicitly not applicable.")

    def describe(self):
        def objective(name, value):
            return f"{name} not applicable by customer policy" if value is None else f"achieved {name} ≤ {value} minutes"
        return (f"Completed full-service test every {self.max_test_age_days} days; "
                f"{objective('RTO', self.max_rto_minutes)}; {objective('RPO', self.max_rpo_minutes)}. "
                "Plan targets alone are insufficient.")


def dr_direction(threshold, fact, source):
    if not isinstance(threshold, DrThreshold):
        raise ValueError("A typed DR threshold is required.")
    if type(fact.active) is not bool or not isinstance(fact.subject, str) or not fact.subject.strip():
        return "unknown"
    if fact.dimension in {"completed", "scope_complete"} and type(fact.value) is bool:
        return "support" if fact.value else "adverse"
    bound = {"achieved_rto_minutes": threshold.max_rto_minutes,
             "achieved_rpo_minutes": threshold.max_rpo_minutes}.get(fact.dimension)
    if fact.dimension in {"achieved_rto_minutes", "achieved_rpo_minutes"} and type(fact.value) is int and fact.value >= 0:
        return "support" if bound is None or fact.value <= bound else "adverse"
    return "unknown"


def evaluate_dr(threshold, observations, as_of):
    if not isinstance(threshold, DrThreshold):
        raise ValueError("A typed DR threshold is required.")
    checks = []
    stale = [(f, s) for f, s in observations if s.evidence_kind == "test"
             and (s.observed_on is None or not 0 <= (as_of - s.observed_on).days <= threshold.max_test_age_days)]
    current = [(f, s) for f, s in observations if f.active is True and (f, s) not in stale]
    if stale:
        checks.append(Check("test_cadence", "uncertain", "The exercise is outside this customer's test interval; obtain current operating evidence.",
                            tuple(f.fact_id for f, _ in stale)))
    groups = {}
    for f, s in current:
        if dr_direction(threshold, f, s) != "unknown":
            groups.setdefault((f.dimension, f.subject), []).append((f, s))
    for (dimension, subject), rows in groups.items():
        if len({f.value for f, _ in rows}) > 1:
            checks.append(Check(dimension, "conflict", f"Conflicting recovery results for {subject}; retain both sources.",
                                tuple(f.fact_id for f, _ in rows)))
    for f, s in current:
        if dr_direction(threshold, f, s) == "adverse":
            verified = s.evidence_kind == "test"
            checks.append(Check(f.dimension, "failed" if verified else "reported",
                                f"{'Completed exercise' if verified else 'Unverified vendor/plan'} exception: "
                                f"{f.subject}: {f.dimension}={f.value}.", (f.fact_id,)))
    required = ["completed", "scope_complete"]
    if threshold.max_rto_minutes is not None:
        required.append("achieved_rto_minutes")
    if threshold.max_rpo_minutes is not None:
        required.append("achieved_rpo_minutes")
    for dimension in required:
        rows = [(f, s) for f, s in current if f.dimension == dimension and f.subject == "complete scope"
                and s.evidence_kind == "test" and s.observed_on is not None
                and 0 <= (as_of - s.observed_on).days <= threshold.max_test_age_days
                and dr_direction(threshold, f, s) == "support"]
        checks.append(Check(dimension, "supported" if rows else "missing",
                            f"{'Confirmed' if rows else 'Need'} completed, dated full-service exercise evidence for {dimension}; "
                            f"customer interval {threshold.max_test_age_days} days.",
                            tuple(f.fact_id for f, _ in rows)))
    # All achieved metrics must be tied to the same completed exercise, not
    # assembled from unrelated good RTO/RPO samples from different reports.
    sources = [{s.document_id for f, s in current if f.fact_id in check.fact_ids}
               for check in checks if check.dimension in required]
    if sources and not set.intersection(*sources):
        checks.append(Check("exercise_binding", "missing", "Completion, coverage and achieved objectives must belong to one exercise."))
    statuses = {c.status for c in checks}
    if "conflict" in statuses:
        outcome, action = "Needs Review", "Reconcile the conflicting exercise records before relying on recovery results."
    elif "failed" in statuses:
        outcome, action = "Risk Identified", "Investigate the failed recovery objective or incomplete exercise; request a corrective retest."
    elif "uncertain" in statuses:
        outcome, action = "Needs Review", "Obtain a completed exercise within the customer's required testing interval."
    elif "reported" in statuses:
        outcome, action = "Needs Review", "Obtain the executed exercise record for the vendor-reported recovery exception."
    elif "missing" in statuses:
        outcome = "Partially Met" if "supported" in statuses else "Evidence Missing"
        action = "Request a completed full-service recovery exercise with date and achieved RTO/RPO against this customer's objectives."
    else:
        outcome, action = "Met", "Submit this provisional interpretation for independent governed review."
    return TechnicalResult(outcome, tuple(checks), action)
