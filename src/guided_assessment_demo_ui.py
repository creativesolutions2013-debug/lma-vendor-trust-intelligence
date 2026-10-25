"""One session-only, synthetic assessment journey over the existing worklist.

The UI accepts code-supplied fixtures only. It does not import database, storage,
vendor messaging or governed-decision services.
"""
from dataclasses import replace

import streamlit as st

from src.control_assurance_presentation import render_assurance_summary
from src.guided_assessment_demo import (
    ACTIONS, RISK_PROFILES, SCENARIOS, active_actions, build_demo, record_action,
    report_bytes, report_payload, row_fingerprint, source_role, SourceRole,
    complete_review, completion_is_current,
)


PREFIX = "guided_demo:"
STEPS = ("Start", "Evidence", "Assess", "Questions", "Analyst Review", "Results")
SCENARIO_LABELS = {"gap": "Evidence gap", "exception": "Material TLS exception"}
REVIEW_LIMIT = (
    "Simulated Accept records a draft discussion annotation only; it does not confirm facts, "
    "satisfy an evidence need or approve a control. Factual confirmation and independently "
    "governed approval must happen outside this demo."
)


def _reset():
    for key in list(st.session_state):
        if key.startswith(PREFIX):
            del st.session_state[key]


def _change_scenario():
    scenario = st.session_state[PREFIX + "scenario"]
    risk = st.session_state.get(PREFIX + "risk_profile", RISK_PROFILES[0])
    _reset()
    st.session_state[PREFIX + "scenario"] = scenario
    st.session_state[PREFIX + "risk_profile"] = risk


def _go(step):
    st.session_state[PREFIX + "step"] = step


def _receive():
    st.session_state[PREFIX + "received"] = True


def _clear_review_draft():
    st.session_state.pop(PREFIX + "rationale", None)


def _finish(model, actions):
    if st.session_state.get(PREFIX + "completion") is None:
        st.session_state[PREFIX + "completion"] = complete_review(model, actions)


def _reopen():
    st.session_state.pop(PREFIX + "completion", None)
    st.session_state[PREFIX + "step"] = "Analyst Review"


def _completed_summary(completion):
    snapshot = completion.snapshot
    st.success("Assessment review completed (demo) — vendor decision pending; open actions remain")
    st.caption("Completed at (UTC): " + completion.completed_at)
    st.caption("As-of report fingerprint: " + completion.fingerprint)
    st.write("**Synthetic case:** " + snapshot["scenario_id"])
    scope = snapshot["scope"]
    st.write(f"**Assessed scope:** {scope['service']} · {scope['environment']} · as of {scope['as_of']}")
    st.caption("Synthetic engagement: " + scope["engagement_id"])
    statuses = {}
    for row in snapshot["requirements"]:
        statuses[row["outcome"]] = statuses.get(row["outcome"], 0) + 1
    st.write("**Requirement status summary:** " + "; ".join(f"{status}: {count}" for status, count in statuses.items()))
    actions = snapshot["analyst_actions"]
    st.write(f"**Inherent risk:** {snapshot['risk']['inherent_score']} · {snapshot['risk']['inherent_rating']}")
    st.info(snapshot["risk"]["residual_recommendation"])
    st.write(f"Simulated annotations: {sum(a['active'] for a in actions)} active; "
             f"{sum(a['status'] == 'Superseded' for a in actions)} superseded; "
             f"{sum(a['status'] == 'Stale context' for a in actions)} stale.")
    st.warning(f"Open draft findings: {len(snapshot['findings'])} · "
               f"Targeted follow-ups: {len(snapshot['targeted_requests'])}. "
               "Unconfirmed interpretations, evidence gaps and risk concerns remain open.")
    for request in snapshot["targeted_requests"]:
        st.write("**Remaining question:** " + request["question"])
    st.write("**Next steps:** Obtain missing evidence, validate source meanings and review exceptions; "
             "vendor decisions and risk authorization require independent governance outside this demo.")
    st.button("Reopen demo review", key=PREFIX + "reopen", on_click=_reopen)
    st.button("Start another assessment", key=PREFIX + "another", on_click=_reset)


def _matches(model):
    return tuple(match for row in model.worklist.rows for match in row.need_matches)


def _counts(model):
    matches = _matches(model)
    columns = st.columns(3)
    columns[0].metric("Draft vendor requests", len(model.worklist.requests))
    columns[1].metric("Ask-everything baseline", model.worklist.baseline_questions)
    columns[2].metric("Needs awaiting analyst validation", sum(
        match.status == "Analyst validation required" for match in matches))
    st.caption(
        f"Reviewed evidence needs: {sum(m.status == 'Supported by reviewed evidence' for m in matches)} · "
        f"Distinct evidence needs: {len(matches)} · "
        f"Missing or insufficient: {sum(m.status == 'Missing or insufficient' for m in matches)}. "
        "The baseline asks one broad question per applicable requirement. These are synthetic counts; "
        "deferred analyst validation is not resolved evidence or measured real-world time savings."
    )


def _exceptions(model):
    rows = tuple(row for row in model.worklist.rows if row.priority <= 1)
    if rows:
        st.warning("Adverse or conflicting evidence remains open: " + ", ".join(
            row.requirement_id for row in rows))
    return rows


def _action_label(action):
    return "Accept draft for discussion — does not verify or approve control" if action == "Accept" else action


def _table(model, actions=()):
    st.caption(REVIEW_LIMIT)
    current = {action.requirement_id: action for action in active_actions(model, actions)}
    st.dataframe([
        {
            "Requirement": row.requirement_id,
            "Control mapping": row.control_id,
            "Provisional outcome": row.outcome,
            "Attention": row.presentation.attention[0].title if row.presentation and row.presentation.attention else "",
            "Workflow": row.intent,
            "Simulated review": _action_label(current[row.requirement_id].action) if row.requirement_id in current else "Unreviewed",
            "Next action": row.next_action,
        } for row in model.worklist.rows
    ], use_container_width=True, hide_index=True)


def _source(bound):
    source = bound.source
    st.caption("Source role: " + source_role(bound).value)
    if source_role(bound) == SourceRole.CUSTOMER_POLICY:
        st.caption("Customer acceptance criteria only; not vendor implementation or operating proof.")
    st.caption(
        f"{source.evidence_kind} · {source.service} · {source.environment} · {source.account_scope} · "
        f"observed {source.observed_on} · captured {source.captured_on} · version {source.version}"
    )
    st.caption("Origin: " + source.origin)
    for part in bound.document.segments:
        st.caption(bound.document.filename + " · " + part.location)
        st.code(part.text, language=None)
    st.caption("Original-content SHA-256: " + bound.content_sha256)
    st.caption("Source fingerprint: " + bound.fingerprint)


def _detail(row):
    st.caption("Confirmation-oriented next actions describe work outside this demo. " + REVIEW_LIMIT)
    if row.presentation:
        render_assurance_summary(replace(row.presentation, outcome=row.outcome, next_action=row.next_action))
    else:
        st.markdown(f"**{row.requirement_id} · {row.title}**")
        st.info("Provisional outcome: " + row.outcome)
        st.write("Customer threshold: " + row.threshold)
        st.write("Recommended next action: " + row.next_action)
    with st.expander("Sources, specific evidence needs and limits", expanded=False):
        for match in row.need_matches:
            st.write(f"**{match.need_id} · {match.status}**")
            if match.status == "Missing or insufficient":
                st.info("Evidence Missing for this specific need; missing proof does not establish control failure.")
            st.write(match.missing_fact)
            st.caption("Acceptable evidence: " + match.acceptable_evidence)
            st.caption(match.rationale)
        if row.review:
            for bound in row.review.evidence:
                st.markdown("**" + bound.document.filename + "**")
                _source(bound)
        for limitation in row.limitations:
            st.warning(limitation)
        st.caption("Exact quotations and source hashes establish consistency; they do not confirm meaning or control operation.")


def _replay(model):
    st.button("Replay new evidence received", key=PREFIX + "replay", on_click=_receive,
              disabled=model.evidence_received)
    if model.evidence_received:
        st.info("Simulated recovery-exercise evidence received. Its meaning, scope and achieved objectives still need analyst validation.")
    else:
        st.caption("Simulate the vendor supplying the missing completed recovery exercise. No invitation, upload or message is sent.")


def _start(model):
    st.subheader("Start with the relationship and customer requirements")
    st.write("**Synthetic vendor:** Acme Analytics Cloud · **Service:** " + model.scenario.scope.service)
    st.write("**Purpose:** Production analytics supporting customer operations and reporting.")
    st.write("**Data and access context:** " + model.risk_profile)
    st.metric("Inherent risk", f"{model.inherent_score} · {model.inherent_rating}")
    st.caption(model.inherent_tier)
    for driver in model.risk_drivers:
        st.write("• " + driver)
    st.markdown("**Customer-defined requirements for this walkthrough**")
    st.dataframe([
        {
            "Requirement": mapping.requirement.requirement_id,
            "Customer policy": f"{mapping.requirement.customer_policy_id} v{mapping.requirement.policy_version}",
            "Threshold": mapping.threshold.describe(),
            "Service": mapping.requirement.service,
            "Environment": mapping.requirement.environment,
        } for mapping in model.scenario.requirements
    ], use_container_width=True, hide_index=True)
    st.caption("This bounded walkthrough covers every listed requirement. Requirements without specialist rules remain in the same review queue.")


def _evidence(model):
    st.subheader("Simulated vendor submission")
    st.write("The vendor has shared an existing evidence package before receiving a questionnaire. "
             "Customer policy sources are shown separately by role: they define the assessment "
             "criteria and are not vendor-supplied proof of implementation or operation.")
    links = {}
    for row in model.worklist.rows:
        if row.review:
            for bound in row.review.evidence:
                links.setdefault(bound.fingerprint, []).append(row.requirement_id)
    all_sources = model.documents + model.context_documents
    vendor_sources = tuple(b for b in all_sources if source_role(b) != SourceRole.CUSTOMER_POLICY)
    customer_sources = tuple(b for b in all_sources if source_role(b) == SourceRole.CUSTOMER_POLICY)
    st.caption(f"Simulated vendor artifacts: {len(vendor_sources)} · Customer policy sources: {len(customer_sources)}. "
               "Vendor context-only artifacts do not satisfy the selected requirements.")
    for label, sources in (("Simulated vendor package", vendor_sources),
                           ("Customer acceptance criteria — separate from vendor submission", customer_sources)):
        st.markdown("**" + label + "**")
        st.dataframe([
        {
            "Document": bound.document.filename,
            "Source role": source_role(bound).value,
            "Kind": bound.source.evidence_kind,
            "Observed": str(bound.source.observed_on),
            "Service scope": f"{bound.source.service} · {bound.source.environment}",
            "Assessment use": ", ".join(links.get(bound.fingerprint, ())) or "Reference context only",
        } for bound in sources
        ], use_container_width=True, hide_index=True)
    for bound in model.documents:
        with st.expander(bound.document.filename, expanded=False):
            _source(bound)
    with st.expander("SOC 2 and IAM/MFA reference context", expanded=False):
        st.info("These excerpts provide background. Privileged MFA is outside this four-requirement walkthrough; no MFA or SOC 2 technical conclusion is generated.")
        for bound in model.context_documents:
            st.markdown("**" + bound.document.filename + "**")
            _source(bound)
    _replay(model)


def _assess(model, actions):
    st.subheader("Review exceptions before supporting claims")
    st.caption("All outcomes below come from the existing worklist and source-bound assurance evaluators.")
    _exceptions(model)
    _table(model, actions)
    for diagnostic in model.worklist.diagnostics:
        st.warning(diagnostic)
    requirement_id = st.selectbox("Requirement detail", [row.requirement_id for row in model.worklist.rows],
                                  key=PREFIX + "assessment_requirement")
    _detail(next(row for row in model.worklist.rows if row.requirement_id == requirement_id))


def _questions(model):
    st.subheader("Ask only for the remaining missing facts")
    _counts(model)
    if model.worklist.requests:
        st.info("Evidence Missing: the specific facts below need additional evidence. This does not establish a control failure.")
        for request in model.worklist.requests:
            with st.container(border=True):
                st.write(request.question)
                st.caption("Requirement(s): " + ", ".join(request.requirement_ids))
                st.write("**Missing fact:** " + request.missing_fact)
                st.write("**Acceptable evidence:** " + request.acceptable_evidence)
    else:
        st.info("No distinct vendor request is proposed now. Candidate evidence still requires analyst validation; no control is approved.")
    st.caption("Policy documents may support documented governance. They do not establish technical operating effectiveness.")
    _replay(model)
    _exceptions(model)


def _ledger(model, actions):
    if not actions:
        st.caption("No simulated reviews have been recorded in this session.")
        return
    st.markdown("**Session-only review history**")
    current = active_actions(model, actions)
    contexts = {row.requirement_id: row_fingerprint(model, row) for row in model.worklist.rows}
    st.dataframe([
        {
            "Requirement": action.requirement_id,
            "Simulated action": _action_label(action.action),
            "Review context": ("Current" if action in current else "Superseded"
                               if contexts.get(action.requirement_id) == action.fingerprint
                               else "Stale — source or context changed"),
            "Rationale": action.rationale,
            "Recorded at": action.recorded_at,
        } for action in actions
    ], use_container_width=True, hide_index=True)
    with st.expander("Review context fingerprints"):
        for action in actions:
            st.caption(action.requirement_id + " · " + action.fingerprint)


def _review(model, actions):
    st.subheader("Simulate the analyst's judgment")
    st.caption(REVIEW_LIMIT)
    requirement_id = st.selectbox("Review requirement", [row.requirement_id for row in model.worklist.rows],
                                  key=PREFIX + "review_requirement", on_change=_clear_review_draft)
    row = next(row for row in model.worklist.rows if row.requirement_id == requirement_id)
    _detail(row)
    action = st.radio("Simulated analyst action", ACTIONS, format_func=_action_label, key=PREFIX + "action", horizontal=True)
    rationale = st.text_area("Review rationale", key=PREFIX + "rationale", max_chars=1200,
                             placeholder="Explain your judgment using the source, requirement and unresolved uncertainty.")
    if st.button("Record simulated review", key=PREFIX + "record", disabled=not rationale.strip()):
        try:
            actions = record_action(model, actions, requirement_id, action, rationale)
        except ValueError as error:
            st.error(str(error))
        else:
            st.session_state[PREFIX + "actions"] = actions
            if st.session_state.pop(PREFIX + "completion", None) is not None:
                st.rerun()
            st.success("Simulated review recorded for this source and requirement context.")
            if action == "Accept":
                st.info(REVIEW_LIMIT)
    st.caption("Challenge, Request Evidence and Create Finding record draft reviewer intentions. They do not change evaluator outcomes or send vendor messages.")
    _ledger(model, actions)


def _results(model, actions, completion=None):
    if completion is not None:
        _completed_summary(completion)
    else:
        st.info("Finish documents this synthetic review only. It does not approve the vendor, "
                "confirm technical facts or accept risk. Open actions remain.")
        st.button("Finish assessment review (demo)", key=PREFIX + "finish",
                  type="primary", on_click=_finish, args=(model, actions))
    st.subheader("Draft assessment results")
    _exceptions(model)
    _table(model, actions)
    st.write(f"**Inherent risk:** {model.inherent_score} · {model.inherent_rating}")
    st.info(model.residual_recommendation)
    for driver in model.residual_drivers:
        st.caption(driver)
    current = active_actions(model, actions)
    findings = report_payload(model, actions)["findings"]
    st.markdown("**Simulated findings**")
    if findings:
        for finding in findings:
            st.text(finding["requirement_id"] + ": " + finding["rationale"])
            st.caption("Finding context: " + finding["context_status"])
            if finding["context_status"] != "Current":
                st.warning("Stale finding context — re-review required. Original rationale and citations are retained.")
            st.caption("Open draft finding for feedback. Later review annotations do not resolve it; no governed finding has been created.")
            with st.expander("Original finding source context · " + finding["requirement_id"] + " · " + finding["recorded_at"]):
                st.write("Customer requirement: " + finding["customer_context"])
                st.write("Threshold: " + finding["threshold"])
                for citation in finding["citations"]:
                    st.caption(citation["source_role"] + " · " + citation["filename"] + " · " + citation["location"])
                    st.code(citation["quote"], language=None)
                st.caption("Recorded source context: " + finding["fingerprint"])
    else:
        st.write("No simulated finding recorded. Open exceptions remain visible regardless of reviewer actions.")
    _ledger(model, actions)
    st.download_button("Download synthetic assessment report", data=report_bytes(model, actions, completion),
                       file_name="lma_synthetic_assessment_report.json", mime="application/json",
                       key=PREFIX + "report")
    st.caption("The download contains synthetic sources, exact citations, provisional results and the simulated review ledger. It grants no approval.")
    st.markdown("**Reviewer insights**")
    _counts(model)
    st.write(f"Analyst queue: {len(model.worklist.rows)} applicable requirements; {len(current)} current simulated reviews.")
    deferred = model.worklist.baseline_questions - len(model.worklist.requests)
    st.write(f"Broad questions deferred: {deferred} of {model.worklist.baseline_questions}. Candidate evidence requiring review remains unresolved.")
    concerns = tuple(row for row in model.worklist.rows if row.priority <= 1)
    if concerns:
        st.write("Top concern: " + concerns[0].requirement_id + " · " + concerns[0].next_action)
    if model.worklist.rows:
        st.write("**Next action:** " + model.worklist.rows[0].next_action)
    with st.expander("Industry feedback discussion guide", expanded=True):
        for question in (
            "Where would this evidence-first journey save unnecessary vendor questions?",
            "Are the requirement thresholds, citations and uncertainties clear enough to review?",
            "Which material risks or required evidence would you expect to see next?",
            "Does the simulated vendor contribution reduce friction without hiding review work?",
            "What would need to change before you would consider a synthetic or scoped pilot?",
        ):
            st.write("• " + question)


def render_guided_assessment_demo():
    """Render a repeatable six-step walkthrough entirely in this browser session."""
    st.title("Guided Assessment Demo")
    st.caption("Assess the evidence before you ask the questions.")
    st.info("Synthetic industry-feedback prototype · All results are provisional · Reviews stay in this session. No real vendor access, messages or approvals.")
    header = st.columns((2, 2, 1))
    scenario_id = header[0].selectbox("Demo scenario", SCENARIOS, format_func=SCENARIO_LABELS.get,
                                      key=PREFIX + "scenario", on_change=_change_scenario)
    risk_profile = header[1].selectbox("Risk context", RISK_PROFILES, key=PREFIX + "risk_profile")
    header[2].button("Reset demo", key=PREFIX + "reset", on_click=_reset)
    st.session_state.setdefault(PREFIX + "received", False)
    st.session_state.setdefault(PREFIX + "actions", ())
    model = build_demo(scenario_id, st.session_state[PREFIX + "received"], risk_profile)
    actions = st.session_state[PREFIX + "actions"]
    completion = st.session_state.get(PREFIX + "completion")
    if completion is not None and not completion_is_current(model, actions, completion):
        st.session_state.pop(PREFIX + "completion", None)
        completion = None
        st.warning("Demo review reopened: evidence, context or annotations changed. Finish again to capture a current summary.")
    st.caption("Review walkthrough: " + ("Completed (demo only); vendor decision pending" if completion else "In progress"))
    st.caption(f"Service: {model.scenario.scope.service} · {model.scenario.scope.environment} · Synthetic assessment date: {model.scenario.scope.as_of}")
    step = st.radio("Demo step", STEPS, horizontal=True, key=PREFIX + "step")
    if step == "Start":
        _start(model)
    elif step == "Evidence":
        _evidence(model)
    elif step == "Assess":
        _assess(model, actions)
    elif step == "Questions":
        _questions(model)
    elif step == "Analyst Review":
        _review(model, actions)
    else:
        _results(model, actions, completion)
    navigation = st.columns(2)
    position = STEPS.index(step)
    navigation[0].button("Back", key=PREFIX + "back", disabled=position == 0,
                         on_click=_go, args=(STEPS[max(0, position - 1)],))
    navigation[1].button("Continue", key=PREFIX + "continue", disabled=position == len(STEPS) - 1,
                         on_click=_go, args=(STEPS[min(len(STEPS) - 1, position + 1)],))
