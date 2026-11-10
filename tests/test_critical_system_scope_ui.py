"""Exercise critical-data qualification through actual intake and export."""
from pathlib import Path
from io import BytesIO
from zipfile import ZipFile
import json
import pytest
from streamlit.testing.v1 import AppTest
from test_guided_assessment_demo_ui import no_live_effects, packages, run, widget, shown
from test_upload_assessment_ui import stage


@pytest.mark.parametrize('qualification,points,provisional', [
    ('Hosts or processes critical data',16,False),
    ('Does not host or process critical data',0,False), ('Unknown',None,True),
])
def test_requester_qualifies_access_and_report_retains_scope(no_live_effects, packages, qualification, points, provisional):
    at=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=40).run()
    widget(at.text_input,'Synthetic vendor name').set_value('Synthetic Qualified Vendor')
    widget(at.text_input,'Service being assessed').set_value('Synthetic Portal')
    widget(at.text_area,'Business use case').set_value('Synthetic system qualification')
    widget(at.multiselect,'Data types in scope').set_value(['Confidential business data'])
    widget(at.selectbox,'Business criticality').set_value('Limited')
    widget(at.selectbox,'Does the accessed system host or process critical data?').set_value(qualification)
    widget(at.selectbox,'Network access').set_value('None')
    widget(at.number_input,'Estimated records in scope').set_value(0)
    widget(at.number_input,'Active or expected client users').set_value(0)
    widget(at.selectbox,'Critical consequence under organization methodology').set_value('Not identified')
    widget(at.selectbox,'Dependency on this service').set_value('No operational dependency')
    run(at); widget(at.button,'Create assessment').click();run(at)
    model=at.session_state['customer_assessment:model']
    assert model.customer_context['exposure_scope']['system_access_points'] == points
    assert model.inherent_score == 15 + (points or 0)
    assert model.customer_context['tier_status'].startswith('Provisional') == provisional
    stage(at,'Report');widget(at.button,'Finish assessment review').click();run(at)
    with ZipFile(BytesIO(packages[-1])) as z:
        report=json.loads(z.read('report.json'))
        scope=report['assessment_context']['exposure_scope']
        assert scope['system_data_criticality']==qualification
        assert scope['system_access_points']==points
        assert qualification in z.read('summary.html').decode()
        assert report['risk']['residual_score'] is None and not report['review_completion']['vendor_approved']
    widget(at.button,'Start another assessment').click();run(at)
    assert widget(at.selectbox,'Does the accessed system host or process critical data?').value == 'Unknown'


def test_no_system_access_hides_unnecessary_qualification(no_live_effects):
    at=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=40).run()
    widget(at.selectbox,'System access').set_value('None');run(at)
    assert not any(s.label=='Does the accessed system host or process critical data?' for s in at.selectbox)
