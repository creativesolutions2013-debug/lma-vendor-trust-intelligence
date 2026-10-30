"""Five-stage, memory-only development experience for user-selected synthetic files."""
from dataclasses import replace
from datetime import date
from hashlib import sha256
from uuid import uuid4

import streamlit as st

from src.guided_assessment_demo import (
    ACTIONS, active_actions, complete_review, completion_is_current, package_bytes,
    record_action, report_payload, source_role,
)
from src.upload_assessment import (
    Intake, LIMITATION, MAX_FILES, MAX_TOTAL_BYTES, MAX_UPLOAD_BYTES,
    build_assessment, read_upload, risk_and_applicability, suggested_requirements,
)

PREFIX = 'customer_assessment:'
STAGES = ('About vendor', 'Upload evidence', 'Evaluate', 'Review gaps', 'Report')


def _reset():
    for key in list(st.session_state):
        if key.startswith(PREFIX): del st.session_state[key]


def _go(stage):
    st.session_state[PREFIX + 'stage'] = stage


def _invalidate_uploads():
    st.session_state[PREFIX + 'uploads_dirty'] = True
    st.session_state.pop(PREFIX + 'completion', None)


def _capture_metadata(widget_key):
    # Durable draft state is deliberately separate from Streamlit-owned widget keys,
    # which are removed when Upload evidence is not rendered.
    edits = dict(st.session_state.get(PREFIX + 'metadata_edits', {}))
    edits[widget_key] = st.session_state[widget_key]
    st.session_state[PREFIX + 'metadata_edits'] = edits
    _invalidate_uploads()


def _capture_files(widget_key):
    _invalidate_uploads()
    files = st.session_state.get(widget_key, [])
    if not files:
        st.session_state[PREFIX + 'pending_files'] = ()
        st.session_state.pop(PREFIX + 'file_error', None)
        return
    if len(files) > MAX_FILES or sum(f.size for f in files) > MAX_TOTAL_BYTES or any(f.size > MAX_UPLOAD_BYTES for f in files):
        st.session_state[PREFIX + 'file_error'] = 'Select at most 10 files, 2 MB each and 10 MB total.'
        return
    pending = dict(st.session_state.get(PREFIX + 'pending_files', ()))
    for file in files:
        content = file.getvalue()
        key = sha256(file.name.encode() + b'\0' + content).hexdigest()
        pending[key] = (file.name, content)
    if len(pending) > MAX_FILES or sum(len(item[1]) for item in pending.values()) > MAX_TOTAL_BYTES:
        st.session_state[PREFIX + 'file_error'] = 'Pending selections exceed 10 files / 10 MB; discard them and select fewer files.'
        return
    st.session_state[PREFIX + 'pending_files'] = tuple(pending.items())
    st.session_state.pop(PREFIX + 'file_error', None)


def _discard_pending():
    st.session_state.pop(PREFIX + 'pending_files', None)
    st.session_state.pop(PREFIX + 'file_error', None)
    st.session_state[PREFIX + 'upload_epoch'] = st.session_state.get(PREFIX + 'upload_epoch', 0) + 1
    _invalidate_uploads()


def _about():
    st.subheader('Start a synthetic vendor assessment')
    vendor = st.text_input('Synthetic vendor name', key=PREFIX + 'vendor', max_chars=200)
    service = st.text_input('Service being assessed', key=PREFIX + 'service', max_chars=200)
    purpose = st.text_area('Business use case', key=PREFIX + 'purpose', max_chars=500)
    environment = st.selectbox('Assessed environment', ('production', 'test'), key=PREFIX + 'environment')
    cols = st.columns(3)
    data = cols[0].selectbox('Data sensitivity', ('Public', 'Confidential', 'Restricted'), index=1, key=PREFIX + 'data')
    access = cols[1].selectbox('Service access', ('None', 'Production', 'Privileged'), index=1, key=PREFIX + 'access')
    criticality = cols[2].selectbox('Business criticality', ('Limited', 'Important', 'Critical'), index=1, key=PREFIX + 'criticality')
    st.caption('Inherent risk uses the existing engine. Uncollected volume, regulation, fourth-party, geography and AI inputs contribute zero illustrative points; this is not a complete risk intake.')
    if st.button('Create assessment', type='primary', disabled=not all(s.strip() for s in (vendor, service, purpose))):
        try:
            intake = Intake('local-' + uuid4().hex, vendor.strip(), service.strip(), purpose.strip(), data, access, criticality, environment, as_of=date.today())
            model = build_assessment(intake)
        except ValueError as error: st.error(str(error))
        else:
            # Creating a new case never transfers annotations or source bytes from an older case.
            _reset()
            st.session_state[PREFIX + 'intake'] = intake
            st.session_state[PREFIX + 'model'] = model
            st.session_state[PREFIX + 'actions'] = ()
            st.session_state[PREFIX + 'stage'] = 'Upload evidence'
            st.rerun()


def _uploads(intake):
    st.subheader('Attach your synthetic evidence')
    st.write('No vendor files are preloaded. Upload nonconfidential synthetic PDF, DOCX or UTF-8 TXT files. Files stay in this browser session on the development server; they are not sent to an AI provider or saved to the legacy database.')
    st.caption('Limits: 10 files, 2 MB each, 10 MB total. Scans without readable text need local OCR before upload. This is not secure production document custody or malware scanning.')
    retained = st.session_state.get(PREFIX + 'uploads', ())
    st.caption('Attached files are retained for this assessment. New selections add files; use Clear this assessment to remove all session data.')
    widget_key = PREFIX + 'files:' + str(st.session_state.get(PREFIX + 'upload_epoch', 0))
    st.file_uploader('Choose synthetic evidence', type=['pdf', 'docx', 'txt'], accept_multiple_files=True,
                     key=widget_key, max_upload_size=2, on_change=_capture_files, args=(widget_key,))
    st.button('Discard new file selections', on_click=_discard_pending)
    applicable = risk_and_applicability(intake)[2]
    titles = {c.control_id: c.requirement for c in applicable.controls}
    proposed = []
    errors = []
    combined = {u.evidence.source.document_id: (u.evidence.document.filename, u.evidence.source.content, u) for u in retained}
    if st.session_state.get(PREFIX + 'file_error'):
        st.error(st.session_state[PREFIX + 'file_error']); return
    for _, (filename, content) in st.session_state.get(PREFIX + 'pending_files', ()):
        name = filename.replace('\\', '/').rsplit('/', 1)[-1]
        identity = 'upload-' + sha256(name.encode() + b'\0' + content).hexdigest()
        combined.setdefault(identity, (filename, content, None))
    if len(combined) > MAX_FILES or sum(len(item[1]) for item in combined.values()) > MAX_TOTAL_BYTES:
        _invalidate_uploads()
        st.error('The retained files plus this selection exceed 10 files / 10 MB. Start a new assessment or select fewer new files.'); return
    for filename, content, previous in combined.values():
        try:
            parsed = read_upload(intake, filename, content)
        except ValueError as error:
            st.error('File not attached.'); st.text(f'{filename}: {error}'); errors.append(str(error)); continue
        bound = parsed.evidence
        key = PREFIX + 'file:' + bound.source.document_id
        edits = st.session_state.get(PREFIX + 'metadata_edits', {})
        st.text(bound.document.filename + f' — readable text extracted ({len(bound.document.segments)} sections)')
        with st.expander('File details and routing: ' + bound.document.filename, expanded=False):
            st.text(f'{len(bound.document.segments)} readable sections · SHA-256 {bound.content_sha256}')
            targets = st.multiselect('Related requirements (routing only)', list(titles),
                default=edits.get(key + ':targets', previous.requirements if previous else suggested_requirements(bound.document, titles)),
                format_func=lambda value: value + ' · ' + titles[value], key=key + ':targets', on_change=_capture_metadata, args=(key + ':targets',))
            st.caption('Suggested routing is a text hint, not control proof. Correct the choices before evaluation. No selection keeps the file as context only.')
            kind = st.selectbox('Document kind (your declaration)', ('assertion', 'policy', 'configuration', 'test'), index=('assertion', 'policy', 'configuration', 'test').index(edits.get(key + ':kind', previous.evidence.source.evidence_kind if previous else 'assertion')), key=key + ':kind', on_change=_capture_metadata, args=(key + ':kind',))
            observed = st.date_input('Document observation/test date (if known)', value=edits.get(key + ':date', previous.evidence.source.observed_on if previous else None), max_value=date.today(), key=key + ':date', on_change=_capture_metadata, args=(key + ':date',))
            source_service = st.text_input('Service stated by this document', value=edits.get(key + ':scope', previous.evidence.source.service if previous else intake.service), key=key + ':scope', max_chars=200, on_change=_capture_metadata, args=(key + ':scope',))
            source_environment = st.text_input('Environment stated by this document', value=edits.get(key + ':environment', previous.evidence.source.environment if previous else intake.environment), key=key + ':environment', max_chars=100, on_change=_capture_metadata, args=(key + ':environment',))
            st.text('Role: ' + ('uploaded synthetic vendor evidence' if targets else 'uploaded context only') + ' · Declared scope: ' + source_service + ' / ' + source_environment)
            st.caption('Scope is uploader-declared, not verified from the document. Missing/stale dates and different scope remain explicit evidence limitations.')
            try:
                proposed.append(read_upload(intake, filename, content, tuple(targets), kind=kind, observed_on=observed, service=source_service, environment=source_environment))
            except ValueError as error: errors.append(str(error)); st.error(str(error))
    st.session_state[PREFIX + 'uploads_dirty'] = bool(errors) or tuple(proposed) != tuple(retained)
    if st.session_state[PREFIX + 'uploads_dirty']: st.session_state.pop(PREFIX + 'completion', None)
    if st.button('Evaluate attached evidence', type='primary', disabled=bool(errors)):
        try: model = build_assessment(intake, tuple(proposed))
        except ValueError as error: st.error(str(error))
        else:
            previous = st.session_state[PREFIX + 'model']
            changed = report_payload(previous, st.session_state[PREFIX + 'actions']) != report_payload(model, st.session_state[PREFIX + 'actions'])
            st.session_state[PREFIX + 'model'] = model
            st.session_state[PREFIX + 'uploads'] = tuple(proposed)
            st.session_state.pop(PREFIX + 'pending_files', None)
            if changed: st.session_state.pop(PREFIX + 'completion', None)
            st.session_state[PREFIX + 'uploads_dirty'] = False
            st.session_state[PREFIX + 'pending_stage'] = 'Evaluate'
            st.rerun()
    if not combined: st.info('No files selected. You can evaluate an empty assessment to see the evidence requests; no control will be marked satisfied.')


def _details(row):
    st.write('Customer example threshold: ' + row.threshold)
    st.text(f'{row.requirement.customer_policy_id} v{row.requirement.policy_version} · {row.requirement.service} · {row.requirement.environment}')
    st.info(row.outcome)
    st.text('Next action: ' + row.next_action)
    if row.review:
        for fact in row.review.facts:
            if fact.direction == 'adverse':
                st.warning('Unverified text concern'); st.code(fact.proposal.quote, language=None)
        for signal in row.review.signals:
            st.warning('Unverified exception text'); st.code(signal.quote, language=None)
    with st.expander('Sources and limitations'):
        if row.review:
            for bound in row.review.evidence:
                st.text(bound.document.filename + ' · ' + source_role(bound).value)
                for segment in bound.document.segments:
                    st.caption(segment.location); st.code(segment.text, language=None)
        for limitation in row.limitations: st.caption(limitation)
        st.caption('No specialist technical interpretation is supplied for arbitrary uploaded documents. Quotation matches and uploader routing do not establish meaning, operating effectiveness or compliance.')


def _evaluate(model):
    st.subheader('What LMA evaluated')
    st.write('The existing applicability engine selected the requirements below. Your source text is parsed and routed to source-bound manual reviews. No uploaded control is automatically satisfied. Example criteria are supplied for synthetic testing, not your organization’s approved policies.')
    st.dataframe([{'Requirement': r.requirement_id, 'Title': r.title, 'Status': r.outcome,
                   'Next action': r.next_action} for r in model.worklist.rows], hide_index=True)
    st.markdown('**Limited deterministic text screening**')
    for result in model.customer_context['screening']:
        if result['citations']:
            st.write(result['requirement_id'] + ' · Unverified text screening: ' + result['draft_text_signal'])
            st.write(result['reason'])
            for citation in result['citations']:
                st.caption(citation['filename'] + ' · ' + citation['location'])
                st.code(citation['excerpt'], language=None)
    st.caption('TLS screening compares statements to TLS 1.2; it does not verify enabled configuration or reject historical/out-of-scope text automatically. Recovery RTO/RPO and other technical/control thresholds require human interpretation. AI is off; no external calls are enabled.')
    selected = st.selectbox('Requirement details', [r.requirement_id for r in model.worklist.rows], key=PREFIX + 'detail')
    _details(next(r for r in model.worklist.rows if r.requirement_id == selected))


def _review(model):
    st.subheader('Review gaps and record draft findings')
    st.caption('Exceptions are ordered first. Review actions are annotations, never factual confirmations or control/vendor approvals.')
    actions = st.session_state[PREFIX + 'actions']
    selected = st.selectbox('Review requirement', [r.requirement_id for r in model.worklist.rows], key=PREFIX + 'review',
                            on_change=lambda: st.session_state.pop(PREFIX + 'reason', None))
    row = next(r for r in model.worklist.rows if r.requirement_id == selected)
    st.write(f'Finding/review for {row.requirement_id} · {row.title}')
    _details(row)
    action = st.radio('Draft action', ACTIONS, format_func=lambda a: f'Create finding for {selected}' if a == 'Create Finding' else 'Accept draft for discussion only' if a == 'Accept' else a, key=PREFIX + 'action')
    rationale = st.text_area('Rationale', max_chars=1200, key=PREFIX + 'reason')
    if st.button('Record draft review', disabled=not rationale.strip()):
        try: actions = record_action(model, actions, selected, action, rationale)
        except ValueError as error: st.error(str(error))
        else:
            st.session_state[PREFIX + 'actions'] = actions
            st.session_state.pop(PREFIX + 'completion', None)
            st.success('Recorded ' + action + ' for ' + selected + '. No approval or risk acceptance was created.')
    st.markdown('**Remaining requests**')
    for request in model.worklist.requests: st.text(request.question)
    if actions:
        payload = report_payload(model, actions)
        st.dataframe([{'Requirement': a['requirement_id'], 'Action': a['action'], 'Context': a['status'],
                       'Rationale': a['rationale']} for a in payload['analyst_actions']], hide_index=True)


def _report(model):
    actions = st.session_state[PREFIX + 'actions']
    completion = st.session_state.get(PREFIX + 'completion')
    if completion is not None and not completion_is_current(model, actions, completion):
        st.session_state.pop(PREFIX + 'completion', None); completion = None
    st.subheader('Assessment report')
    if st.session_state.get(PREFIX + 'uploads_dirty'):
        st.warning('Upload selections may have changed. Return to Upload evidence and evaluate the current files before finishing or exporting.')
        return
    if completion:
        st.success('Assessment review completed (synthetic) — vendor decision pending; open conditions remain')
        st.caption('Completed at: ' + completion.completed_at)
    else:
        if st.button('Finish assessment review', type='primary'):
            st.session_state[PREFIX + 'completion'] = complete_review(model, actions); st.rerun()
    report = report_payload(model, actions, completion)
    from src.guided_assessment_demo_ui import _risk_positions
    _risk_positions(report['risk'])
    st.write('Open draft findings: ' + str(len(report['findings'])))
    for finding in report['findings']: st.text(finding['requirement_id'] + ': ' + finding['rationale'])
    for request in report['targeted_requests']: st.text(request['question'])
    st.download_button('Download assessment package (.zip)', package_bytes(model, actions, completion),
                       'lma_synthetic_uploaded_assessment.zip', mime='application/zip', type='primary', disabled=completion is None)
    if completion:
        if st.button('Reopen review'):
            st.session_state.pop(PREFIX + 'completion', None); st.session_state[PREFIX + 'pending_stage'] = 'Review gaps'; st.rerun()
        st.button('Start another assessment', on_click=_reset)


def render_upload_assessment():
    st.title('New Assessment')
    st.info('Development-only · synthetic/nonconfidential documents only · session memory, no production custody or vendor approval')
    st.caption(LIMITATION)
    st.sidebar.button('Clear this assessment', on_click=_reset)
    intake = st.session_state.get(PREFIX + 'intake')
    if intake is None:
        _about(); return
    st.text(intake.vendor + ' · ' + intake.service + ' · ' + intake.environment + ' · ' + intake.use_case)
    pending = st.session_state.pop(PREFIX + 'pending_stage', None)
    if pending: st.session_state[PREFIX + 'stage'] = pending
    stage = st.radio('Assessment stage', STAGES, horizontal=True, key=PREFIX + 'stage')
    if st.session_state.get(PREFIX + 'uploads_dirty') and stage in ('Evaluate', 'Review gaps', 'Report'):
        st.warning('Evaluate the current upload selections on Upload evidence before continuing. Earlier results are not current.')
        return
    if stage == 'About vendor':
        st.write('To change vendor or risk context, start a new assessment. This prevents reviews transferring to a different relationship.')
        st.button('Start a new assessment', on_click=_reset)
    elif stage == 'Upload evidence': _uploads(intake)
    elif stage == 'Evaluate': _evaluate(st.session_state[PREFIX + 'model'])
    elif stage == 'Review gaps': _review(st.session_state[PREFIX + 'model'])
    else: _report(st.session_state[PREFIX + 'model'])
    position = STAGES.index(stage)
    a, b = st.columns(2)
    a.button('Back', disabled=position == 0, on_click=_go, args=(STAGES[max(0, position-1)],))
    b.button('Continue', disabled=position == 4 or (stage == 'Upload evidence' and st.session_state.get(PREFIX + 'uploads_dirty', False)), on_click=_go, args=(STAGES[min(4, position+1)],))
