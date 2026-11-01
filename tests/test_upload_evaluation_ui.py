"""Actual customer entry, own synthetic documents, no fixture-based assessments."""
from datetime import timedelta
from io import BytesIO
import json
from zipfile import ZipFile

from test_guided_assessment_demo_ui import no_live_effects, packages, run, shown, widget
from test_upload_assessment_ui import start, stage
from test_upload_evaluation import source_text


def test_customer_sees_cited_tls_and_dr_exceptions_then_exports_and_reevaluates(no_live_effects,packages):
    at=start()
    intake=at.session_state['customer_assessment:intake']
    observed=intake.as_of-timedelta(days=5)
    tls=source_text(intake,'Primary listener 443: TLS 1.2 is enabled.\nAlternate production listener 9443: TLS 1.0 is enabled.',date=observed.isoformat()).encode()
    dr=source_text(intake,'Recovery exercise completed.\nAchieved RTO 300 minutes and RPO 90 minutes.\nIdentity provider was excluded.', 'BCP-01',date=observed.isoformat()).encode()
    at.get('file_uploader')[0].upload('customer-config.txt',tls).upload('customer-exercise.txt',dr); run(at)
    for field in at.date_input: field.set_value(observed)
    kinds=[w for w in at.selectbox if w.label=='Document kind (your declaration)']
    kinds[0].set_value('configuration'); kinds[1].set_value('test'); run(at)
    widget(at.button,'Evaluate attached evidence').click();run(at)
    tables='\n'.join(str(t.value) for t in at.dataframe)
    assert 'observed enabled TLS 1.0' in tables and 'RTO 300 minutes' in tables and 'RPO 90 minutes' in tables
    assert 'Unverified threshold concern' in shown(at)
    assert any('9443' in q.value for q in at.code) and any('Identity provider' in q.value for q in at.code)
    model=at.session_state['customer_assessment:model']
    assert all(not f.confirmed for r in model.worklist.rows for f in r.review.facts)
    stage(at,'Review gaps');widget(at.selectbox,'Review requirement').set_value('BCP-01');run(at)
    widget(at.radio,'Draft action').set_value('Create Finding');widget(at.text_area,'Rationale').set_value('Validate achieved recovery times and excluded identity dependency.');run(at)
    widget(at.button,'Record draft review').click();run(at)
    stage(at,'Report');widget(at.button,'Finish assessment review').click();run(at)
    with ZipFile(BytesIO(packages[-1])) as archive:
        report=json.loads(archive.read('report.json')); manifest=json.loads(archive.read('manifest.json'))
        assert report['risk']['residual_score'] is None
        assert all(not f['confirmed'] for e in report['assessment_context']['evaluations'] for f in e['facts'])
        assert {archive.read(a['archive_path']) for a in manifest['artifacts']}=={tls,dr}
    stage(at,'Upload evidence')
    dates=at.date_input;dates[1].set_value(observed-timedelta(days=10));run(at)
    assert 'customer_assessment:completion' not in at.session_state
    stage(at,'Report');assert not at.get('download_button')
    stage(at,'Upload evidence');widget(at.button,'Evaluate attached evidence').click();run(at)
    revised=at.session_state['customer_assessment:model']
    recovery=next(e for e in revised.customer_context['evaluations'] if e['requirement_id']=='BCP-01')
    assert any('differs from uploader' in u for s in recovery['sources'] for u in s['uncertainties'])
    assert not any(f['eligible_for_preview'] for f in recovery['facts'])
    stage(at,'Review gaps')
    assert any('Context' in t.value.columns and 'Stale context' in set(t.value['Context']) for t in at.dataframe)


def suggestions(at):
    return [b for b in at.button if b.label == 'Use source-stated metadata for this file']


def test_source_metadata_clicks_enable_unconfirmed_preview_and_preserve_history(no_live_effects, packages):
    from datetime import date
    at = start()
    widget(at.sidebar.button, 'Clear this assessment').click(); run(at)
    widget(at.text_input, 'Synthetic vendor name').set_value('Cedarline Analytics')
    widget(at.text_input, 'Service being assessed').set_value('Cedarline Data Platform')
    widget(at.text_area, 'Business use case').set_value('Synthetic reporting')
    run(at); widget(at.button, 'Create assessment').click(); run(at)
    tls = (b'Configuration export\nService: Cedarline Data Platform\nEnvironment: production\n'
           b'Observation date: 2026-10-26\nPrimary listener 443: TLS 1.2 is enabled.\n'
           b'Alternate production listener 9443: TLS 1.0 is enabled.')
    dr = (b'DR exercise results\nService: Cedarline Data Platform\nEnvironment: production\n'
          b'Test date: 2026-09-20\nRecovery exercise completed.\n'
          b'Achieved RTO 300 minutes and RPO 90 minutes.\nIdentity provider was excluded from the exercise.')
    at.get('file_uploader')[0].upload('Cedarline_TLS.txt', tls).upload('Cedarline_DR.txt', dr); run(at)
    kinds = lambda: [w for w in at.selectbox if w.label == 'Document kind (your declaration)']
    for w in kinds(): w.set_value('policy')
    for w in at.date_input: w.set_value(date(2026,11,1))
    run(at)
    assert 'Source says: configuration / 2026-10-26' in shown(at)
    assert 'Source says: test / 2026-09-20' in shown(at)
    assert 'Your current declaration: policy / 2026-11-01' in shown(at)
    assert any(q.value == 'Observation date: 2026-10-26' for q in at.code)
    widget(at.button, 'Evaluate attached evidence').click(); run(at)
    assert not any(f['eligible_for_preview'] for e in at.session_state['customer_assessment:model'].customer_context['evaluations'] for f in e['facts'])
    stage(at, 'Review gaps'); widget(at.selectbox, 'Review requirement').set_value('BCP-01'); run(at)
    widget(at.radio, 'Draft action').set_value('Create Finding')
    widget(at.text_area, 'Rationale').set_value('Investigate source-cited recovery exception.'); run(at)
    widget(at.button, 'Record draft review').click(); run(at)
    history = at.session_state['customer_assessment:actions']
    stage(at, 'Report'); widget(at.button, 'Finish assessment review').click(); run(at)
    stage(at, 'Upload evidence')
    assert [w.value for w in kinds()] == ['policy', 'policy']  # No silent corrections.
    suggestions(at)[0].click(); run(at)
    assert 'customer_assessment:completion' not in at.session_state
    assert at.session_state['customer_assessment:actions'] == history
    stage(at, 'Report'); assert at.warning and not at.get('download_button')
    stage(at, 'Upload evidence')
    assert [w.value for w in kinds()] == ['configuration', 'policy']
    assert at.date_input[0].value == date(2026,10,26)
    suggestions(at)[1].click(); run(at)
    stage(at, 'Review gaps'); assert at.warning
    stage(at, 'Upload evidence')
    assert [w.value for w in kinds()] == ['configuration', 'test']
    assert [w.value for w in at.date_input] == [date(2026,10,26), date(2026,9,20)]
    widget(at.button, 'Evaluate attached evidence').click(); run(at)
    model = at.session_state['customer_assessment:model']
    for e in model.customer_context['evaluations']:
        assert e['preview']['outcome_if_confirmed'] == 'Risk Identified'
        assert any(f['eligible_for_preview'] for f in e['facts'])
        assert all(not f['confirmed'] for f in e['facts'])
    assert all(not f.confirmed for r in model.worklist.rows for f in r.review.facts)
    stage(at, 'Review gaps')
    assert any('Context' in t.value.columns and 'Stale context' in set(t.value['Context']) for t in at.dataframe)
    stage(at, 'Report'); widget(at.button, 'Finish assessment review').click(); run(at)
    with ZipFile(BytesIO(packages[-1])) as archive:
        report = json.loads(archive.read('report.json'))
        assert report['risk']['residual_score'] is None
        assert report['review_completion']['vendor_approved'] is False
        manifest = json.loads(archive.read('manifest.json'))
        assert {archive.read(a['archive_path']) for a in manifest['artifacts']} == {tls, dr}
        for e in report['assessment_context']['evaluations']:
            for f in e['facts']:
                original = tls if f['filename'] == 'Cedarline_TLS.txt' else dr
                assert f['quote'] == original.decode().splitlines()[int(f['location'].split()[-1])-1]
    stage(at, 'Upload evidence'); at.date_input[1].set_value(date(2026,11,1)); run(at)
    stage(at, 'Report'); assert not at.get('download_button')
    stage(at, 'Upload evidence'); widget(at.button, 'Evaluate attached evidence').click(); run(at)
    dr_result = next(e for e in at.session_state['customer_assessment:model'].customer_context['evaluations'] if e['requirement_id'] == 'BCP-01')
    assert not any(f['eligible_for_preview'] for f in dr_result['facts'])


def test_suggestions_preserve_other_pending_edits_and_partial_ambiguity(no_live_effects):
    at = start(); intake = at.session_state['customer_assessment:intake']
    text = source_text(intake, 'Listener 9443: TLS 1.0 is enabled.') + '\nTest date: 2026-10-21'
    at.get('file_uploader')[0].upload('ambiguous-date.txt', text.encode()); run(at)
    assert not suggestions(at)[0].disabled  # Only the unambiguous kind is offered.
    at.multiselect[0].set_value([])
    widget(at.text_input, 'Service stated by this document').set_value('Analyst scope challenge')
    at.date_input[0].set_value(intake.as_of); run(at)
    suggestions(at)[0].click(); run(at)
    stage(at, 'Report'); assert not at.get('download_button')
    stage(at, 'Upload evidence')
    assert not at.multiselect[0].value
    assert widget(at.text_input, 'Service stated by this document').value == 'Analyst scope challenge'
    assert at.date_input[0].value == intake.as_of
    assert widget(at.selectbox, 'Document kind (your declaration)').value == 'configuration'
    assert 'date missing/ambiguous' in shown(at)


def test_out_of_scope_suggestions_are_visible_but_unavailable(no_live_effects):
    at = start(); intake = at.session_state['customer_assessment:intake']
    text = source_text(intake, 'Listener 9443: TLS 1.0 is enabled.', service='Different service')
    at.get('file_uploader')[0].upload('out-of-scope.txt', text.encode()); run(at)
    assert 'Source says: configuration / 2026-10-20' in shown(at)
    assert suggestions(at)[0].disabled
    assert at.date_input[0].value is None


def test_confirming_already_matching_metadata_still_requires_explicit_evaluation(no_live_effects):
    at = start(); intake = at.session_state['customer_assessment:intake']
    at.get('file_uploader')[0].upload('matching.txt', source_text(intake, 'Listener 9443: TLS 1.0 is enabled.').encode()); run(at)
    suggestions(at)[0].click(); run(at)
    widget(at.button, 'Evaluate attached evidence').click(); run(at)
    stage(at, 'Report'); widget(at.button, 'Finish assessment review').click(); run(at)
    stage(at, 'Upload evidence'); suggestions(at)[0].click(); run(at)
    assert at.session_state['customer_assessment:uploads_dirty']
    assert 'customer_assessment:completion' not in at.session_state
    stage(at, 'Report'); assert at.warning and not at.get('download_button')
    stage(at, 'Upload evidence'); widget(at.button, 'Evaluate attached evidence').click(); run(at)
    assert not at.session_state['customer_assessment:uploads_dirty']
