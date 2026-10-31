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
