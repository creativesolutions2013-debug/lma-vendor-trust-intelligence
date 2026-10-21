"""One bounded Control Assurance Review in the existing Evidence Center."""
import streamlit as st

from src.control_assurance import ControlReviewState, inspect_control, record_control_review
from src.control_assurance_pilot import control_pilot_cases, fallback_pilot_cases, suitability_pilot_cases
from src.control_assurance_presentation import present_control, render_assurance_summary
from src.control_assurance_registry import registered_review_families
from src.mfa_assurance_adapter import mfa_review_family


def render_control_assurance_pilot(*, actor_label="Pilot analyst"):
    st.subheader("Evidence-Based Control Assurance")
    st.caption("Control Assurance Review · applicable customer requirements, with specialist coverage disclosed. "
               "Synthetic evidence only. "
               "Session-only, provisional results; separate governed confirmation is required. "
               "This pilot does not provide production authorization.")
    registrations = registered_review_families(
        control_pilot_cases() + fallback_pilot_cases() + suitability_pilot_cases(), adapters=(mfa_review_family(),),
    )
    if not registrations:
        st.info("No applicable customer requirements are registered for review.")
        return
    family = st.selectbox("Control family", tuple(registrations), key="m3d_family")
    prior = st.session_state.get("m3d_last_family")
    if prior != family:
        for registration in registrations.values():
            for key in registration.state_keys:
                st.session_state.pop(key, None)
    st.session_state["m3d_last_family"] = family
    registration = registrations[family]
    if registration.renderer:
        registration.renderer(actor_label=actor_label)
        return
    cases = registration.cases
    case_id = st.selectbox("Synthetic control package", [c.case_id for c in cases],
                           format_func=lambda key: next(c.title for c in cases if c.case_id == key), key="m3d_case:" + family)
    case = next(c for c in cases if c.case_id == case_id)
    initial = inspect_control(case)
    prefix = f"m3d:{actor_label}:{case_id}:{initial.bundle_fingerprint}"
    saved = st.session_state.get("m3d_current_review")
    if saved and saved[0] != prefix:
        st.session_state.pop("m3d_current_review", None)
    state = saved[1] if saved and saved[0] == prefix else ControlReviewState()
    view = inspect_control(case, state)
    with st.container(border=True):
        render_assurance_summary(present_control(case, view))
        st.caption(f"Synthetic assessment date: {case.as_of} · Demo reviewer: {actor_label}")
        with st.expander("Source context and remaining evidence detail"):
            for check in view.checks:
                st.write(f"{check.dimension} · {check.status}: {check.rationale}")
            for b in view.evidence:
                s = b.source
                st.markdown(f"**{b.document.filename}**")
                st.caption(f"{s.evidence_kind} · {s.service} · {s.environment} · {s.account_scope} · "
                           f"observed {s.observed_on} · captured {s.captured_on} · version {s.version} · {s.origin}")
                st.code("\n".join(f"{p.location} | {p.text}" for p in b.document.segments), language=None)
                if not view.specialist_available:
                    st.caption("Review eligibility: " + ("matches supplied expectations and relevance binding; sufficiency not evaluated"
                               if b.fingerprint in view.eligible_source_fingerprints else "not established; source retained for context"))
                    for binding in case.relevance:
                        if binding.source_fingerprint == b.fingerprint:
                            st.caption(f"Supplied relevance rationale: {binding.rationale or 'not supplied'}")
                st.caption("Original-content SHA-256: " + b.content_sha256)
            for f in view.facts:
                st.write(f"{f.proposal.fact_id}: " + ("; ".join(f.reasons) if f.reasons else "Source binding consistent; meaning requires analyst review."))
                st.caption("Individual interpretation fingerprint: " + f.fingerprint)
        with st.expander("Record a session-only analyst review"):
            note = st.text_area("Reason for this review", key=prefix + ":note")
            common = dict(expected_bundle=view.bundle_fingerprint, analyst=actor_label,
                          reviewed_on=case.as_of, rationale=note)

            def record(**kwargs):
                try:
                    updated = record_control_review(case, state, **common, **kwargs)
                    st.session_state["m3d_current_review"] = (prefix, updated)
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))

            # All individual interpretations + exact quotes are presented before
            # the one explicit group action. No adverse interpretation is grouped.
            support = [f for f in view.facts if f.direction == "support" and not f.reasons]
            if support:
                st.markdown("**Supporting interpretations to confirm together**")
                for f in support:
                    p = f.proposal
                    st.write(f"{p.dimension} = {p.value}; subject: {p.subject}; active: {p.active}")
                    st.caption(f"{f.filename} · {p.location}")
                    st.code(p.quote, language=None)
                fps = tuple(f.fingerprint for f in support)
                agrees = st.checkbox("I checked every displayed interpretation against its full sources and confirm its meaning, not just its quotation.",
                                     value=False, key=prefix + ":semantics:" + ",".join(fps))
                if st.button("Confirm displayed supporting interpretations", key=prefix + ":support",
                             disabled=not agrees or not note.strip() or all(f.confirmed for f in support)):
                    record(action="support", fact_ids=tuple(f.proposal.fact_id for f in support),
                           presented_fingerprints=fps, confirms=agrees)
            meanings = [f for f in view.facts if f.direction == "review"]
            if meanings:
                st.markdown("**Review an interpretation's meaning — sufficiency not evaluated**")
                meaning_id = st.selectbox("Interpretation to review", [f.proposal.fact_id for f in meanings], key=prefix + ":meaning")
                f = next(f for f in meanings if f.proposal.fact_id == meaning_id)
                st.write(f"{f.proposal.dimension} = {f.proposal.value}; subject: {f.proposal.subject}")
                st.caption(f"{f.filename} · {f.proposal.location}")
                st.code(f.proposal.quote, language=None)
                agrees = st.checkbox(
                    "I checked this interpretation against its full source and confirm its meaning, without judging whether the requirement is met.",
                    key=prefix + ":meaning-confirmation:" + f.fingerprint,
                )
                if st.button("Confirm this interpretation's meaning", key=prefix + ":meaning-record",
                             disabled=not agrees or not note.strip() or bool(f.reasons) or f.confirmed):
                    record(action="meaning", fact_ids=(meaning_id,), presented_fingerprints=(f.fingerprint,), confirms=agrees)
            adverse = [f for f in view.facts if f.direction == "adverse" and not f.reasons]
            if adverse:
                st.markdown("**Review exception meaning separately**")
                exception_id = st.selectbox("Exception interpretation", [f.proposal.fact_id for f in adverse], key=prefix + ":exception")
                f = next(f for f in adverse if f.proposal.fact_id == exception_id)
                st.write(f"{f.proposal.dimension} = {f.proposal.value}; subject: {f.proposal.subject}; active: {f.proposal.active}")
                st.caption(f"{f.filename} · {f.proposal.location}")
                st.code(f.proposal.quote, language=None)
                agree = st.checkbox("I checked this exception's meaning and affected scope in the full source context.",
                                    key=prefix + ":exception-meaning:" + exception_id)
                if st.button("Confirm this exception's meaning", key=prefix + ":exception-record",
                             disabled=not agree or not note.strip() or f.confirmed):
                    record(action="exception", fact_ids=(exception_id,), presented_fingerprints=(f.fingerprint,), confirms=agree)
            if view.facts:
                challenge_id = st.selectbox("Interpretation to challenge", [f.proposal.fact_id for f in view.facts], key=prefix + ":challenge")
                f = next(f for f in view.facts if f.proposal.fact_id == challenge_id)
                st.write(f"{f.proposal.dimension} = {f.proposal.value}; subject: {f.proposal.subject}; active: {f.proposal.active}")
                st.caption(f"{f.filename} · {f.proposal.location}")
                st.code(f.proposal.quote, language=None)
                decision = st.radio("Challenge disposition", ("Unsupported", "Ambiguous"), key=prefix + ":challenge-decision:" + challenge_id)
                if st.button("Record interpretation challenge", key=prefix + ":challenge-record", disabled=not note.strip()):
                    record(action="challenge", fact_ids=(challenge_id,), presented_fingerprints=(f.fingerprint,), decision=decision.lower())
            if view.signals:
                signal_id = st.selectbox("Source signal", [s.signal_id for s in view.signals],
                                         format_func=lambda key: next(f"{s.filename} · {s.location}" for s in view.signals if s.signal_id == key), key=prefix + ":signal")
                s = next(s for s in view.signals if s.signal_id == signal_id)
                st.code(s.quote, language=None)
                material = st.radio("After checking the full context", ("Retain as material or potentially material", "Not material to this requirement"),
                                    key=prefix + ":material:" + signal_id)
                if st.button("Record this signal triage", key=prefix + ":triage", disabled=not note.strip()):
                    record(action="signal", signal_id=signal_id, material=material == "Retain as material or potentially material")
            complete = st.checkbox("I reviewed all supplied documents and their disagreements, scope, dates and technical coverage.", key=prefix + ":bundle")
            if st.button("Record complete-bundle review", key=prefix + ":bundle-record", disabled=not complete or not note.strip()):
                record(action="bundle", confirms=complete)
            st.caption(f"Recorded analyst decisions in this pilot session: {len(state.events)}")
            for event in state.events:
                st.caption(f"{event.reviewed_on} · {event.analyst} · {event.kind.replace('_', ' ')} · {', '.join(event.target_ids)}")
                st.write(event.rationale)
