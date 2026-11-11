"""Native empty-uploader replay must not discard unevaluated evidence."""
from datetime import timedelta
from io import BytesIO
import json
from zipfile import ZipFile

from test_guided_assessment_demo_ui import no_live_effects, packages, run, widget
from test_upload_assessment_ui import start, stage
from test_upload_evaluation import source_text
from test_upload_evaluation_ui import suggestions


def test_empty_remounted_uploader_preserves_pending_originals_and_metadata(no_live_effects, packages):
    at = start()
    intake = at.session_state['customer_assessment:intake']
    observed = intake.as_of - timedelta(days=5)
    tls = source_text(intake, 'Listener 443: TLS 1.0 is enabled.', date=observed.isoformat()).encode()
    dr = source_text(intake, 'Recovery exercise completed.\nAchieved RTO 300 minutes and RPO 90 minutes.', 'BCP-01', date=observed.isoformat()).encode()
    at.get('file_uploader')[0].upload('tls.txt', tls).upload('dr.txt', dr)
    run(at)
    for index in range(2):
        suggestions(at)[index].click(); run(at)
    pending = at.session_state['customer_assessment:pending_files']
    stage(at, 'Report')
    assert at.warning and not at.get('download_button')
    stage(at, 'Upload evidence')
    # Browser remounts an empty native uploader after leaving this stage.
    # Replay its empty value through the real widget callback, not seeded state.
    at.get('file_uploader')[0].set_value([]); run(at)
    assert at.session_state['customer_assessment:pending_files'] == pending
    assert len(at.multiselect) == 2
    assert [f.value for f in at.date_input] == [observed, observed]
    widget(at.button, 'Evaluate attached evidence').click(); run(at)
    stage(at, 'Review gaps')
    widget(at.selectbox, 'Review requirement').set_value('ENC-01'); run(at)
    widget(at.radio, 'Draft action').set_value('Create Finding')
    widget(at.text_area, 'Rationale').set_value('Synthetic finding retained with uploaded evidence.'); run(at)
    widget(at.button, 'Record draft review').click(); run(at)
    stage(at, 'Report'); widget(at.button, 'Finish assessment review').click(); run(at)
    with ZipFile(BytesIO(packages[-1])) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        assert {a['filename']: archive.read(a['archive_path']) for a in manifest['artifacts']} == {'tls.txt': tls, 'dr.txt': dr}
        report = json.loads(archive.read('report.json'))
        assert len(report['findings']) == 1
        assert report['risk']['residual_score'] is None
        assert report['review_completion']['vendor_approved'] is False
        assert all(not fact['confirmed'] for evaluation in report['assessment_context']['evaluations'] for fact in evaluation['facts'])
    widget(at.button, 'Reopen review').click(); run(at)
    stage(at, 'Upload evidence')
    at.get('file_uploader')[0].upload('pending.txt', b'Synthetic context only.'); run(at)
    widget(at.button, 'Discard new file selections').click(); run(at)
    assert not at.session_state.get('customer_assessment:pending_files')
    assert len(at.multiselect) == 2  # Discard affects pending selections, not retained evidence.
