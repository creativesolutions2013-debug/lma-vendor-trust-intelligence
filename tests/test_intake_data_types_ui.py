"""Exercise dataset scope through the real customer intake and exported report."""
from io import BytesIO
from pathlib import Path
import json
from zipfile import ZipFile

from streamlit.testing.v1 import AppTest
from test_guided_assessment_demo_ui import no_live_effects, packages, run, shown, widget
from test_upload_assessment_ui import stage


def test_customer_selects_data_scope_and_it_survives_navigation_completion_and_reset(no_live_effects, packages):
    at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'), default_timeout=40).run()
    widget(at.text_input, 'Synthetic vendor name').set_value('Synthetic Health Vendor')
    widget(at.text_input, 'Service being assessed').set_value('Synthetic Records')
    widget(at.text_area, 'Business use case').set_value('Synthetic health processing')
    assert widget(at.multiselect, 'Data types in scope').value == ['Unknown']
    widget(at.multiselect, 'Data types in scope').set_value([]); run(at)
    assert widget(at.button, 'Create assessment').disabled
    widget(at.selectbox, 'Data sensitivity').set_value('Public')
    widget(at.multiselect, 'Data types in scope').set_value(['Health data (PHI)', 'Personal data (PII)']); run(at)
    widget(at.button, 'Create assessment').click(); run(at)
    model = at.session_state['customer_assessment:model']
    assert model.inherent_score == 56
    assert model.inherent_tier == 'Tier 2 — High'
    types = ['Personal data (PII)', 'Health data (PHI)']
    assert model.customer_context['data_scope']['data_types'] == types
    assert 'REG-01' in {r.requirement_id for r in model.worklist.rows}
    for target in ('About vendor', 'Upload evidence', 'Evaluate', 'Review gaps', 'Report'):
        stage(at, target)
        assert 'Health data (PHI)' in shown(at)
        assert at.session_state['customer_assessment:model'].customer_context['data_scope']['data_types'] == types
    widget(at.button, 'Finish assessment review').click(); run(at)
    with ZipFile(BytesIO(packages[-1])) as archive:
        report = json.loads(archive.read('report.json'))
        assert report['assessment_context']['data_scope']['data_types'] == types
        html = archive.read('summary.html').decode()
        assert all(t in html for t in types)
        assert report['risk']['residual_score'] is None
        assert report['review_completion']['vendor_approved'] is False
    widget(at.button, 'Start another assessment').click(); run(at)
    assert widget(at.multiselect, 'Data types in scope').value == ['Unknown']
    assert 'customer_assessment:intake' not in at.session_state


def test_unknown_data_scope_warning_survives_creation_and_report(no_live_effects, packages):
    from test_upload_assessment_ui import start
    at = start()
    assert at.session_state['customer_assessment:intake'].data_types == ('Unknown',)
    stage(at, 'Report')
    assert any('score and tier are provisional' in w.value for w in at.warning)
    widget(at.button, 'Finish assessment review').click(); run(at)
    with ZipFile(BytesIO(packages[-1])) as archive:
        assert 'Data types are not fully classified' in archive.read('summary.html').decode()
