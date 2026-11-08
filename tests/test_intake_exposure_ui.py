"""Exercise the multi-factor customer intake and its exported context."""
from io import BytesIO
import json
from zipfile import ZipFile

from test_guided_assessment_demo_ui import no_live_effects, packages, run, shown, widget
from pathlib import Path
from streamlit.testing.v1 import AppTest
from test_upload_assessment_ui import stage


def test_customer_exposure_fields_persist_export_and_reset(no_live_effects, packages):
    at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'), default_timeout=40).run()
    widget(at.text_input, 'Synthetic vendor name').set_value('Synthetic Dependent Vendor')
    widget(at.text_input, 'Service being assessed').set_value('Synthetic Essential Portal')
    widget(at.text_area, 'Business use case').set_value('Synthetic dependency and volume test')
    widget(at.multiselect, 'Data types in scope').set_value(['Health data (PHI)'])
    widget(at.selectbox, 'System access').set_value('Privileged')
    widget(at.selectbox, 'Network access').set_value('Network connectivity')
    widget(at.selectbox, 'Business criticality').set_value('Important')
    widget(at.number_input, 'Estimated records in scope').set_value(100_001)
    widget(at.selectbox, 'Dependency on this service').set_value('Critical dependency / no viable workaround')
    run(at);widget(at.button, 'Create assessment').click();run(at)
    model = at.session_state['customer_assessment:model']
    assert model.inherent_score == 80 and model.inherent_tier == 'Tier 1 — Critical'
    assert not model.customer_context['exposure_scope']['missing_inputs']
    for target in ('About vendor','Upload evidence','Evaluate','Review gaps','Report'):
        stage(at,target)
        assert at.session_state['customer_assessment:model'].customer_context['exposure_scope']['data_volume_records'] == 100_001
    widget(at.button,'Finish assessment review').click();run(at)
    with ZipFile(BytesIO(packages[-1])) as z:
        report = json.loads(z.read('report.json'))
        scope = report['assessment_context']['exposure_scope']
        assert scope['system_access']=='Privileged' and scope['network_access']=='Network connectivity'
        assert scope['effective_access_points']==25 and scope['effective_business_points']==20
        assert scope['data_volume_points']==10
        assert '100001 records' in z.read('summary.html').decode()
        assert 'Critical dependency / no viable workaround' in z.read('summary.html').decode()
        assert report['risk']['residual_score'] is None and not report['review_completion']['vendor_approved']
    widget(at.button,'Start another assessment').click();run(at)
    assert widget(at.selectbox,'Network access').value=='Unknown'
    assert widget(at.number_input,'Estimated records in scope').value is None
    assert widget(at.selectbox,'Dependency on this service').value=='Unknown'


def test_unknown_volume_is_not_explicit_zero(no_live_effects):
    from test_upload_assessment_ui import start
    at = start()
    scope = at.session_state['customer_assessment:model'].customer_context['exposure_scope']
    assert scope['data_volume_records'] is None and scope['data_volume_points'] is None
    stage(at,'Report')
    assert any('known-input subtotal' in w.value for w in at.warning)
    assert 'Provisional' in shown(at)
