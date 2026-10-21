"""Control-neutral presentation contract shared by MFA, TLS and recovery reviews."""
from dataclasses import dataclass


@dataclass(frozen=True)
class CitedInterpretation:
    statement: str
    filename: str
    location: str
    quote: str
    fingerprint: str
    confirmed: bool


@dataclass(frozen=True)
class Attention:
    title: str
    detail: str
    citations: tuple[CitedInterpretation, ...] = ()


@dataclass(frozen=True)
class AssurancePresentation:
    requirement_id: str
    title: str
    customer_requirement: str
    threshold: str
    outcome: str
    attention: tuple[Attention, ...]
    supporting: tuple[CitedInterpretation, ...]
    uncertainty: str
    next_action: str
    specialist_available: bool = True
    evidence_for_review: tuple[CitedInterpretation, ...] = ()


def present_control(case, view):
    def cited(f):
        p = f.proposal
        return CitedInterpretation(
            f"{p.dimension} = {p.value}; subject: {p.subject}; active: {p.active}",
            f.filename, p.location, p.quote, f.fingerprint, f.confirmed,
        )
    r = view.requirement
    attention = []
    source_kinds = {b.source.document_id: b.source.evidence_kind for b in view.evidence}
    for f in view.facts:
        if f.direction == "adverse":
            kind = source_kinds.get(f.proposal.source_id.split(":")[0])
            failed = any(c.status == "failed" and f.proposal.fact_id in c.fact_ids for c in view.checks)
            reported = any(c.status == "reported" and f.proposal.fact_id in c.fact_ids for c in view.checks)
            title = ("Reported conflicting interpretation — specialist review required" if f.proposal.concern == "conflict"
                     else "Vendor-reported or policy exception — unverified" if kind in {"assertion", "policy"}
                     else "Evidence-backed threshold failure" if failed
                     else "Untested exception — unverified" if reported
                     else "Confirmed adverse interpretation" if f.confirmed else "Unconfirmed exception interpretation")
            attention.append(Attention(title,
                                       cited(f).statement, (cited(f),)))
    for c in view.checks:
        if c.status not in {"supported", "missing"}:
            attention.append(Attention(c.status.replace("_", " ").title(), c.rationale,
                                       tuple(cited(f) for f in view.facts if f.proposal.fact_id in c.fact_ids)))
    for signal in view.signals:
        if signal.status != "dismissed_by_analyst":
            attention.append(Attention("Source exception needs separate triage", signal.rationale,
                (CitedInterpretation("Potential exception marker, not a verified failure", signal.filename,
                                     signal.location, signal.quote, signal.signal_id, False),)))
    missing = [c for c in view.checks if c.status == "missing"]
    if missing:
        attention.append(Attention("Incomplete operating or implementation evidence",
                                   f"{len(missing)} required check(s) lack confirmed support. " + missing[0].rationale))
    attention.extend(Attention("Evidence limitation", x) for x in view.limitations)
    mapping = (r.standard_reference or "not supplied")
    if r.standard_edition:
        mapping += " · edition " + r.standard_edition
    if r.standard_source:
        mapping += " · source " + r.standard_source
    context = (f" Use case: {r.business_use_case}." if r.business_use_case else "")
    if r.assurance_type:
        context += f" Required assurance: {r.assurance_type}."
    if r.required_evidence:
        context += " Required evidence: " + "; ".join(r.required_evidence) + "."
    review_evidence = tuple(
        CitedInterpretation(
            f"Supplied {b.source.evidence_kind} evidence; {b.source.service} · {b.source.environment} · "
            f"{b.source.account_scope}; observed {b.source.observed_on}; sufficiency not evaluated",
            b.document.filename, segment.location, segment.text, b.fingerprint, False,
        ) for b in view.evidence for segment in b.document.segments
    ) if not view.specialist_available else ()
    return AssurancePresentation(
        r.requirement_id, case.family, f"{r.customer_policy_id} v{r.policy_version}. "
        f"{r.service} · {r.environment} · {r.scope}. "
        f"Approved by {r.approved_by} on {r.approved_on}.{context} "
        f"Customer-supplied standard reference: {mapping} (not independently verified).",
        case.threshold_summary, view.outcome, tuple(attention),
        tuple(cited(f) for f in view.facts if f.direction == "support" and not f.reasons),
        f"{sum(not f.confirmed for f in view.facts)} interpretation(s) unconfirmed or unsupported; "
        f"{sum(s.status == 'needs_review' for s in view.signals)} unresolved source signal(s). "
        "Matching quotations alone do not establish correct meaning or control operation. "
        "Source hashes establish consistency, not authenticity.", view.next_action,
        view.specialist_available, review_evidence,
    )


def render_assurance_summary(presentation):
    """One concise exception-first read-only pattern; no review writes here."""
    import streamlit as st

    p = presentation
    st.markdown(f"**{p.requirement_id} · {p.title}**")
    st.write("Customer requirement: " + p.customer_requirement)
    st.write("Threshold: " + p.threshold)
    st.info("Provisional outcome: " + p.outcome)
    if not p.specialist_available:
        st.caption("Specialist evaluation unavailable; analyst review required.")
    if p.attention:
        st.markdown("**Evidence needing attention first**")
        for issue in p.attention:
            st.warning(f"{issue.title}: {issue.detail}")
            for citation in issue.citations:
                st.caption(f"{citation.filename} · {citation.location}")
                st.code(citation.quote, language=None)
    st.write("**Recommended next action:** " + p.next_action)
    st.caption("Uncertainty: " + p.uncertainty)
    if p.supporting:
        st.markdown("**Strongest supporting evidence**")
        seen = set()
        for item in p.supporting:
            identity = (item.filename, item.location, item.quote)
            if identity in seen:
                continue
            st.caption(f"{item.filename} · {item.location} · "
                       f"{'meaning confirmed' if item.confirmed else 'draft interpretation'}")
            st.code(item.quote, language=None)
            seen.add(identity)
            if len(seen) == 2:
                break
    elif p.specialist_available:
        st.write("No complete supporting interpretation is available for grouped confirmation.")
    if p.evidence_for_review:
        st.markdown("**Cited evidence for specialist review — sufficiency not evaluated**")
        for item in p.evidence_for_review[:2]:
            st.caption(f"{item.filename} · {item.location} · {item.statement}")
            st.code(item.quote, language=None)
