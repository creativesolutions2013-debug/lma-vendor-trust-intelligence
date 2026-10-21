"""Read-only synthetic worklist inside the existing Assessment Workspace."""
from dataclasses import replace

import streamlit as st

from src.assessment_worklist import build_assessment_worklist
from src.assessment_worklist_pilot import worklist_scenarios
from src.control_assurance_presentation import render_assurance_summary


def render_assessment_worklist_preview():
    """Inspect code-supplied packages; no DB, upload, review or send API accepted."""
    with st.container(border=True):
        st.subheader("Evidence-first assessment worklist — synthetic preview")
        st.caption(
            "Assess the evidence before you ask the questions. Synthetic evidence only. "
            "All assurance, workflow intents and next actions are provisional. Inspection records no analyst "
            "confirmation or governed decision; no vendor message is sent."
        )
        scenarios = worklist_scenarios()
        if not scenarios:
            st.info("No synthetic assessment packages are registered for this preview.")
            return
        scenario_id = st.selectbox(
            "Synthetic assessment package", [s.scenario_id for s in scenarios],
            format_func=lambda key: next(s.title for s in scenarios if s.scenario_id == key),
            key="m4a1_scenario",
        )
        scenario = next(s for s in scenarios if s.scenario_id == scenario_id)
        try:
            worklist = build_assessment_worklist(
                scenario.scope, scenario.applicability, scenario.requirements, scenario.assurance_links,
                legacy_evidence=scenario.legacy_evidence, control_claims=scenario.control_claims,
            )
        except ValueError as error:
            st.warning("Needs Review — assessment package rejected: " + str(error))
            return
        scope = worklist.scope
        st.write(
            f"Engagement: {scope.engagement_id} · {scope.service} · {scope.environment} · "
            f"assessment date {scope.as_of}"
        )
        st.metric("Draft vendor requests", len(worklist.requests))
        st.metric("Ask-everything baseline", worklist.baseline_questions)
        st.caption(
            "Counts describe these synthetic requirement sets, not analyst time or vendor accuracy. "
            "Legacy evidence support means document sufficiency under its own policy; it is not "
            "technical compliance, control approval or approved risk."
        )
        for diagnostic in worklist.diagnostics:
            st.warning(diagnostic)
        st.caption("Priority order: exceptions and conflicts, missing evidence, analyst validation, supported evidence awaiting governance.")
        st.dataframe([
            {
                "Requirement": row.requirement_id,
                "Control mapping": row.control_id,
                "Provisional assurance": row.outcome,
                "Evaluator coverage": ("Specialist rules available" if row.specialist_available
                                       else "Specialist review required" if row.specialist_available is False
                                       else "Linkage needs review"),
                "Evidence work plan": row.legacy_status,
                "Workflow": row.workflow_status,
                "Next action": row.next_action,
            } for row in worklist.rows
        ], use_container_width=True, hide_index=True)

        if worklist.rows:
            row_id = st.selectbox(
                "Requirement detail", [row.row_id for row in worklist.rows],
                format_func=lambda key: next(f"{r.requirement_id} · {r.title}" for r in worklist.rows if r.row_id == key),
                key="m4a1_requirement:" + scenario_id,
            )
            row = next(row for row in worklist.rows if row.row_id == row_id)
            st.caption(f"Exact mapping: {row.control_id} → {row.requirement_id} · Workflow: {row.workflow_status}")
            st.caption(f"Legacy evidence status: {row.legacy_status} · Legacy action: {row.legacy_action}")
            if row.presentation:
                # Reuse the common source/threshold presentation while keeping a
                # single worklist-prioritized next action for this selected row.
                render_assurance_summary(replace(row.presentation, outcome=row.outcome, next_action=row.next_action))
            else:
                st.markdown(f"**{row.requirement_id} · {row.title}**")
                st.info("Provisional outcome: " + row.outcome)
                if row.requirement:
                    r = row.requirement
                    st.write(f"Customer requirement: {r.customer_policy_id} v{r.policy_version}. {r.service} · {r.environment} · {r.scope}.")
                st.write("Threshold: " + row.threshold)
                st.write("**Recommended next action:** " + row.next_action)
            if row.missing_fact:
                st.write("**Specific fact or evidence needed:** " + row.missing_fact)
            for limitation in row.limitations:
                st.warning(limitation)
            with st.expander("Source context and assessment limits", expanded=False):
                if row.requirement and row.requirement.business_use_case:
                    st.write("Business use case: " + row.requirement.business_use_case)
                if not row.review or not row.review.evidence:
                    st.write("No permitted source is linked to this requirement in this package.")
                if row.review:
                    for bound in row.review.evidence:
                        source = bound.source
                        st.markdown(f"**{bound.document.filename}**")
                        st.caption(
                            f"{source.evidence_kind} · {source.service} · {source.environment} · "
                            f"{source.account_scope} · observed {source.observed_on} · captured {source.captured_on} · "
                            f"version {source.version} · {source.origin}"
                        )
                        st.code("\n".join(f"{s.location} | {s.text}" for s in bound.document.segments), language=None)
                        st.caption("Original-content SHA-256: " + bound.content_sha256)
                    st.caption("Source hashes and exact quotes establish consistency, not authenticity or semantic truth.")

        st.markdown("**Targeted vendor follow-up preview — not sent**")
        if worklist.requests:
            for request in worklist.requests:
                st.write(request.question)
                st.caption("Requirement(s): " + ", ".join(request.requirement_ids))
                st.write("Missing fact: " + request.missing_fact)
                st.write("Acceptable evidence: " + request.acceptable_evidence)
        else:
            st.write("No distinct vendor request is proposed for this package. Analyst review and governance may still be required.")
