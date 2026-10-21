"""Session-only synthetic MFA pilot embedded in the existing Evidence Center."""
import streamlit as st

from src.mfa_analyst_review import (
    ReviewState, acknowledge_bundle, challenge_supporting, confirm_exception,
    confirm_supporting, describe_interpretation, inspect_review, triage_signal,
)
from src.mfa_review_pilot import pilot_cases
from src.mfa_assurance_adapter import present_mfa
from src.control_assurance_presentation import render_assurance_summary


def render_mfa_review_pilot(*, actor_label="Pilot analyst"):
    """No upload, database handle, external API or governed write is accepted."""
    cases = pilot_cases()
    with st.container(border=True):
        st.subheader("Privileged MFA — synthetic review pilot")
        st.caption(
            "Synthetic evidence only. Review records last for this session. "
            "Every result is provisional and needs separate governed confirmation."
        )
        case_id = st.selectbox(
            "Synthetic evidence package", [item.case_id for item in cases],
            format_func=lambda key: next(item.title for item in cases if item.case_id == key),
            key="m3c1_case",
        )
        case = next(item for item in cases if item.case_id == case_id)
        initial = inspect_review(case)
        prefix = f"m3c1:{actor_label}:{case_id}:{initial.bundle_fingerprint}"
        state_key = "m3c1_current_review"
        saved = st.session_state.get(state_key)
        if saved and saved[0] != prefix:
            st.session_state.pop(state_key, None)
        state = saved[1] if saved and saved[0] == prefix else ReviewState()
        view = inspect_review(case, state)
        render_assurance_summary(present_mfa(case, view))
        st.caption(f"Synthetic assessment date: {case.as_of.isoformat()} · Demo reviewer: {actor_label}")
        secondary = [issue for issue in view.issues if issue.priority > 2]

        with st.expander("Source context and remaining evidence detail", expanded=False):
            for issue in secondary:
                st.write(f"**{issue.title}:** {issue.detail}")
                for citation in issue.citations:
                    st.caption(f"{citation.filename} · {citation.location}")
                    st.code(citation.quote, language=None)
            for bound in view.validation.evidence:
                source = bound.source
                st.markdown(f"**{bound.document.filename}**")
                st.caption(
                    f"{source.evidence_kind} · {source.service} · {source.environment} · "
                    f"{source.account_scope} · observed {source.observed_on} · captured {source.captured_on} · "
                    f"version {source.version} · {source.origin}"
                )
                st.code("\n".join(f"{part.location} | {part.text}" for part in bound.document.segments), language=None)
                st.caption(f"Original-content SHA-256: {bound.content_sha256}")

        with st.expander("Record a session-only analyst review", expanded=False):
            st.caption(
                "Confirm meaning only after checking the presented interpretations and full source context, "
                "including account and authentication-path coverage. Exception triage is separate. "
                "These are simulated review records, not production authorization or control approval."
            )
            note = st.text_area("Reason for this review", key=prefix + ":note")

            def record(operation):
                try:
                    updated = operation()
                    st.session_state[state_key] = (prefix, updated)
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))

            common = dict(expected_bundle=view.bundle_fingerprint, analyst=actor_label,
                          reviewed_on=case.as_of, rationale=note)
            if case.supporting_fact_ids:
                st.markdown("**Challenge a supporting interpretation**")
                proposals = {item.fact_id: item for item in case.proposals}
                challenge_id = st.selectbox(
                    "Supporting interpretation to challenge", case.supporting_fact_ids,
                    format_func=lambda key: proposals[key].fact.dimension.replace("_", " ").title(),
                    key=prefix + ":challenge",
                )
                challenged = proposals[challenge_id]
                source_name = next((bound.document.filename for bound in view.validation.evidence
                                    if challenged.fact.citation.source_id.startswith(bound.source.document_id + ":")),
                                   "Unmatched source")
                st.write(describe_interpretation(challenged))
                st.caption(f"{source_name} · {challenged.location}")
                st.code(challenged.fact.citation.quote, language=None)
                challenge_disposition = st.radio(
                    "Challenge disposition", ("Unsupported", "Ambiguous"),
                    key=prefix + ":challenge_disposition:" + challenge_id,
                )
                if st.button("Record supporting interpretation challenge", key=prefix + ":challenge_record",
                             disabled=not note.strip()):
                    record(lambda: challenge_supporting(
                        case, state, fact_id=challenge_id, decision=challenge_disposition.lower(), **common,
                    ))
            if view.supporting:
                st.markdown("**Supporting interpretations to confirm together**")
                for item in view.supporting:
                    st.write(f"• {item.statement}")
                    st.caption(f"{item.filename} · {item.location}")
                    st.code(item.quote, language=None)
                agrees = st.checkbox(
                    "I checked every displayed interpretation against its full sources and confirm its meaning, not just its quotation.",
                    value=False, key=prefix + ":semantics:" + ",".join(view.supporting_fingerprints),
                )
                if st.button(
                    "Confirm displayed supporting interpretations", key=prefix + ":confirm_support",
                    disabled=not agrees or not note.strip() or all(item.confirmed for item in view.supporting),
                ):
                    record(lambda: confirm_supporting(
                        case, state, presented_fingerprints=view.supporting_fingerprints,
                        confirms_semantics=agrees, **common,
                    ))

            exception_ids = tuple(dict.fromkeys(
                fact_id for issue in view.issues for fact_id in issue.fact_ids
                if issue.kind in {"verified_failure", "vendor_reported_exception", "potential_exception"}
                if fact_id not in {item.fact_id for item in view.supporting}
                and next((p.fact.value is False or p.fact.dimension == "method"
                          for p in case.proposals if p.fact_id == fact_id), False)
            ))
            if exception_ids:
                st.markdown("**Check the meaning of a reported weakness separately**")
                exception_id = st.selectbox("Exception interpretation", exception_ids, key=prefix + ":exception")
                proposed = next(item for item in case.proposals if item.fact_id == exception_id)
                st.code(proposed.fact.citation.quote, language=None)
                exception_agrees = st.checkbox(
                    "I checked this exception's meaning and affected population in the full source context.",
                    value=False, key=prefix + ":exception_meaning:" + exception_id,
                )
                exception_confirmed = any(
                    row.proposal.fact_id == exception_id and row.status == "validated"
                    for row in view.validation.facts
                )
                if st.button("Confirm this exception's meaning", key=prefix + ":confirm_exception",
                             disabled=exception_confirmed or not exception_agrees or not note.strip()):
                    record(lambda: confirm_exception(case, state, fact_id=exception_id,
                                                      confirms_semantics=exception_agrees, **common))

            if view.validation.signals:
                st.markdown("**Triage each source signal separately**")
                signals = {item.signal_id: item for item in view.validation.signals}
                signal_id = st.selectbox(
                    "Source signal", list(signals),
                    format_func=lambda key: f"{signals[key].filename} · {signals[key].location}",
                    key=prefix + ":signal",
                )
                st.code(signals[signal_id].quote, language=None)
                material_label = st.radio(
                    "After checking the full context", ("Retain as material or potentially material", "Not material to this requirement"),
                    key=prefix + ":material:" + signal_id,
                )
                if st.button("Record this signal triage", key=prefix + ":triage", disabled=not note.strip()):
                    record(lambda: triage_signal(
                        case, state, signal_id=signal_id,
                        material=material_label == "Retain as material or potentially material", **common,
                    ))
            whole_bundle = st.checkbox(
                "I reviewed all supplied documents and their disagreements, scope, dates, account and recovery paths.",
                value=False, key=prefix + ":complete_bundle",
            )
            if st.button("Record complete-bundle review", key=prefix + ":acknowledge",
                         disabled=not whole_bundle or not note.strip()):
                record(lambda: acknowledge_bundle(
                    case, state, confirms_complete_bundle=whole_bundle, **common,
                ))
            st.caption(f"Recorded analyst decisions in this pilot session: {len(state.events)}")
            action_labels = {
                "group_confirmation": "Confirmed supporting interpretations",
                "exception_confirmation": "Confirmed exception meaning",
                "signal_triage": "Recorded source signal triage",
                "bundle_acknowledgment": "Reviewed the complete source bundle",
                "challenge_unsupported": "Challenged an interpretation as unsupported",
                "challenge_ambiguous": "Challenged an interpretation as ambiguous",
            }
            for event in state.events:
                st.caption(f"{event.reviewed_on} · {event.analyst} · {action_labels[event.kind]}")
                st.write(event.rationale)
