"""Real-app pilot organization settings and frozen assessment behavior."""
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
import json
import pytest

from streamlit.testing.v1 import AppTest
from test_guided_assessment_demo_ui import no_live_effects, packages, run, widget
from test_upload_assessment_ui import stage
from src.organization_methodology import default_definition


def start():
    at=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=50).run()
    assert not at.exception
    return at


def fill(at):
    widget(at.text_input,'Synthetic vendor name').set_value('Synthetic Organization Vendor')
    widget(at.text_input,'Service being assessed').set_value('Synthetic Portal')
    widget(at.text_area,'Business use case').set_value('Synthetic organization methodology test')
    widget(at.multiselect,'Data types in scope').set_value(['Confidential business data'])
    widget(at.selectbox,'Does the accessed system host or process critical data?').set_value('Hosts or processes critical data')
    widget(at.selectbox,'Network access').set_value('None')
    widget(at.number_input,'Estimated records in scope').set_value(100001)
    widget(at.number_input,'Active or expected client users').set_value(1000)
    widget(at.number_input,'Defined workforce population').set_value(2000)
    widget(at.selectbox,'Dependency on this service').set_value('No operational dependency')
    widget(at.selectbox,'Is scale already included in the baseline assessment?').set_value('No')
    widget(at.selectbox,'Critical consequence under organization methodology').set_value('Not identified')
    run(at)


def test_default_policy_is_usable_and_changed_settings_do_not_rewrite_current_assessment(no_live_effects,packages):
    at=start();fill(at);widget(at.button,'Create assessment').click();run(at)
    original=at.session_state['customer_assessment:model']
    assert original.inherent_score==41 and original.inherent_tier=='Tier 2 — High'
    stage(at,'Report');widget(at.button,'Finish assessment review').click();run(at)
    before=packages[-1]
    widget(at.text_input,'New methodology version').set_value('2')
    widget(at.selectbox,'Tiering method').set_value('weighted');run(at)
    widget(at.button,'Apply pilot methodology').click();run(at)
    assert at.session_state['customer_assessment:model'] is original
    assert packages[-1]==before
    with ZipFile(BytesIO(before)) as z:
        assert json.loads(z.read('methodology.json'))['version']=='1'
        report=json.loads(z.read('report.json'))
        assert report['risk']['tier_decision']['final_tier']=='T2'
        assert report['risk']['tier_decision']['baseline_tier']=='T3'
        assert report['risk']['residual_score'] is None and not report['review_completion']['vendor_approved']
    widget(at.button,'Start another assessment').click();run(at)
    fill(at);widget(at.button,'Create assessment').click();run(at)
    later=at.session_state['customer_assessment:model']
    assert later.customer_context['methodology_snapshot']['version']=='2'
    assert later.customer_context['tier_decision']['strategy']=='weighted'
    assert later.inherent_score==51


def test_create_second_pilot_organization_and_import_only_its_own_version(no_live_effects):
    at=start();widget(at.selectbox,'Pilot organization').set_value('Create pilot organization');run(at)
    widget(at.text_input,'New pilot organization ID').set_value('org-b');run(at)
    widget(at.button,'Apply pilot methodology').click();run(at)
    assert widget(at.selectbox,'Pilot organization').value=='org-b'
    widget(at.radio,'Configure methodology').set_value('Import full configuration');run(at)
    wrong=default_definition('pilot-default','foreign')
    at.get('file_uploader')[0].upload('wrong.json',json.dumps(wrong).encode());run(at)
    widget(at.button,'Apply imported methodology').click();run(at)
    assert any('different pilot organization' in e.value for e in at.error)
    good=default_definition('org-b','2');good['adoption']['high_count']=500
    good['uplift'].update(critical_condition_required=False,critical_override=False)
    at.get('file_uploader')[0].set_value([('good.json',json.dumps(good).encode(),'application/json')]);run(at)
    widget(at.button,'Apply imported methodology').click();run(at)
    assert widget(at.selectbox,'Pilot organization').value=='org-b'
    assert '2' in next(c.value for c in at.caption if c.value.startswith('Active version:'))
    registry=at.session_state['pilot_methodology:registry']
    assert registry.get('org-b').definition['adoption']['high_count']==500
    assert registry.get('pilot-default').definition['adoption']['high_count']==1000
    assert not any(s.label=='Critical consequence under organization methodology' for s in at.selectbox)
    assert any('permits scale-derived criticality' in c.value for c in at.caption)


def test_invalid_common_configuration_keeps_active_policy(no_live_effects):
    at=start();original=at.session_state['pilot_methodology:registry'].get('pilot-default')
    widget(at.number_input,'High adoption: at least users').set_value(50);run(at)
    widget(at.button,'Apply pilot methodology').click();run(at)
    assert at.error
    assert at.session_state['pilot_methodology:registry'].get('pilot-default').fingerprint==original.fingerprint


def test_invalid_new_organization_id_is_a_validation_error_not_app_crash(no_live_effects):
    at=start();widget(at.selectbox,'Pilot organization').set_value('Create pilot organization');run(at)
    widget(at.text_input,'New pilot organization ID').set_value('invalid organization id');run(at)
    assert not at.exception
    widget(at.button,'Apply pilot methodology').click();run(at)
    assert at.error and at.session_state['pilot_methodology:registry'].organizations==('pilot-default',)


@pytest.mark.parametrize('field', ['rto_minutes','rpo_minutes'])
def test_oversized_recovery_import_does_not_break_settings_or_replace_profile(no_live_effects, field):
    at=start();original=at.session_state['pilot_methodology:registry'].get('pilot-default')
    widget(at.radio,'Configure methodology').set_value('Import full configuration');run(at)
    d=default_definition('pilot-default','2');d['assurance'][field]=2**53
    at.get('file_uploader')[0].upload('oversized.json',json.dumps(d).encode());run(at)
    widget(at.button,'Apply imported methodology').click();run(at)
    assert at.error and not at.exception
    assert at.session_state['pilot_methodology:registry'].get('pilot-default').fingerprint==original.fingerprint
    widget(at.radio,'Configure methodology').set_value('Common settings');run(at)
    assert widget(at.number_input,'Maximum achieved RTO minutes (blank means not applicable)').value==240
    assert widget(at.number_input,'Maximum achieved RPO minutes (blank means not applicable)').value==60


@pytest.mark.parametrize('value', [None,2**53-1])
def test_allowed_nullable_or_maximum_recovery_values_render_after_import(no_live_effects,value):
    at=start();widget(at.radio,'Configure methodology').set_value('Import full configuration');run(at)
    d=default_definition('pilot-default','2');d['assurance'].update(rto_minutes=value,rpo_minutes=value)
    at.get('file_uploader')[0].upload('allowed.json',json.dumps(d).encode());run(at)
    widget(at.button,'Apply imported methodology').click();run(at)
    assert not at.exception and not at.error
    assert widget(at.number_input,'Maximum achieved RTO minutes (blank means not applicable)').value==value
    assert widget(at.number_input,'Maximum achieved RPO minutes (blank means not applicable)').value==value
