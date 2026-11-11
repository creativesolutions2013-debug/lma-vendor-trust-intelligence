"""Streamlit AppTest simulation; real Chromium observations are recorded separately."""
from datetime import timedelta
from io import BytesIO
import json
from zipfile import ZipFile

import pytest

from test_guided_assessment_demo_ui import no_live_effects, packages, run, shown, widget
from test_upload_assessment_ui import start, stage
from test_upload_evaluation import source_text


@pytest.mark.parametrize('context', ['current', 'attributed', 'stale', 'test-only'])
def test_narrative_review_remains_visible_through_analyst_workflow_and_export(no_live_effects, packages, context):
    at = start()
    intake = at.session_state['customer_assessment:intake']
    statement = 'Service restoration took seven hours, with up to twenty-five minutes of data loss.'
    if context == 'attributed':
        statement = 'The supplier reports ' + statement[0].lower() + statement[1:]
    observed = intake.as_of - timedelta(days=800 if context == 'stale' else 5)
    content = source_text(intake, 'Recovery exercise completed.\n' + statement, 'BCP-01',
                          date=observed.isoformat(), environment='test' if context == 'test-only' else 'production').encode()
    at.get('file_uploader')[0].upload('independent-recovery.txt', content)
    run(at)
    at.multiselect[0].set_value(['BCP-01'])
    widget(at.selectbox, 'Document kind (your declaration)').set_value('test')
    at.date_input[0].set_value(observed)
    run(at)
    widget(at.button, 'Evaluate attached evidence').click()
    run(at)
    model = at.session_state['customer_assessment:model']
    result = next(e for e in model.customer_context['evaluations'] if e['requirement_id'] == 'BCP-01')
    assert result['threshold'] in shown(at)
    if context == 'attributed':
        assert not result['review_alerts']
        assert 'Narrative recovery statement' not in shown(at)
    else:
        alert = result['review_alerts'][0]
        assert alert['eligible_for_current_review'] is (context == 'current')
        assert alert['filename'] + ' · ' + alert['location'] in shown(at)
        assert any(block.value == statement for block in at.code)
        assert alert['next_action'] in shown(at)
        assert 'no exact achieved RTO/RPO or threshold breach' in shown(at)
        assert ('Context-limited statement' in shown(at)) is (context != 'current')
    stage(at, 'Review gaps')
    widget(at.selectbox, 'Review requirement').set_value('BCP-01')
    run(at)
    assert 'Finding/review for BCP-01' in shown(at) and result['threshold'] in shown(at)
    assert any(statement in block.value for block in at.code)  # Rejected attribution stays inspectable in original sources.
    if context != 'attributed':
        assert alert['next_action'] in shown(at) and 'Narrative recovery statement' in shown(at)
    assert not at.session_state['customer_assessment:actions']
    stage(at, 'Report')
    widget(at.button, 'Finish assessment review').click()
    run(at)
    with ZipFile(BytesIO(packages[-1])) as archive:
        report = json.loads(archive.read('report.json'))
        assert report['risk']['residual_score'] is None
        assert not report['review_completion']['vendor_approved']
        assert not report['findings']
        assert report['assessment_context']['evaluations'] == model.customer_context['evaluations']
        if context != 'attributed':
            assert statement in archive.read('summary.html').decode()
