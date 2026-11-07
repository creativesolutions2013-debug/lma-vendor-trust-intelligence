"""Replay real stale browser widget snapshots through the actual Streamlit app."""
from copy import deepcopy
from datetime import timedelta
from io import BytesIO
from zipfile import ZipFile
import json

import pytest

from test_guided_assessment_demo_ui import no_live_effects, packages, run, widget
from test_upload_assessment_ui import start, stage
from test_upload_evaluation import source_text
from test_upload_evaluation_ui import suggestions


def trigger_snapshot(snapshot, button_id):
    state = deepcopy(snapshot)
    for value in state.widgets:
        if value.id == button_id:
            value.trigger_value = True
            return state
    raise AssertionError('Expected source action not found in snapshot')


def test_old_second_click_snapshot_preserves_first_source_application(no_live_effects, packages):
    at = start(); intake = at.session_state['customer_assessment:intake']
    observed = intake.as_of-timedelta(days=5)
    tls = source_text(intake,'Listener 443: TLS 1.0 is enabled.',date=observed.isoformat()).encode()
    dr = source_text(intake,'Recovery exercise completed.\nAchieved RTO 300 minutes and RPO 90 minutes.','BCP-01',date=observed.isoformat()).encode()
    at.get('file_uploader')[0].upload('first.txt',tls).upload('second.txt',dr); run(at)
    # Capture exactly what a still-old browser sends on the second button event:
    # both files are assertion/no date. Never seed the application session state.
    stale = deepcopy(at._tree.get_widget_states())
    first_id, second_id = [b.proto.id for b in suggestions(at)]
    at._run(trigger_snapshot(stale,first_id)); assert not at.exception
    at._run(trigger_snapshot(stale,second_id)); assert not at.exception
    kinds = [w.value for w in at.selectbox if w.label=='Document kind (your declaration)']
    assert kinds == ['configuration','test']
    assert [w.value for w in at.date_input] == [observed,observed]
    assert at.session_state['customer_assessment:uploads_dirty']
    stage(at,'Report'); assert at.warning and not at.get('download_button')
    stage(at,'Upload evidence')
    assert [w.value for w in at.date_input] == [observed,observed]
    widget(at.button,'Evaluate attached evidence').click();run(at)
    model = at.session_state['customer_assessment:model']
    assert [(u.evidence.source.evidence_kind,u.evidence.source.observed_on) for u in at.session_state['customer_assessment:uploads']] == [('configuration',observed),('test',observed)]
    assert all(not f['confirmed'] for e in model.customer_context['evaluations'] for f in e['facts'])

    stage(at,'Report');widget(at.button,'Finish assessment review').click();run(at)
    with ZipFile(BytesIO(packages[-1])) as archive:
        report=json.loads(archive.read('report.json'))
        assert report['risk']['residual_score'] is None
        assert report['review_completion']['vendor_approved'] is False
        originals={archive.read(a['archive_path']) for a in json.loads(archive.read('manifest.json'))['artifacts']}
        assert originals=={tls,dr}


def test_applied_revision_preserves_manual_fields_and_accepts_later_manual_edits(no_live_effects, packages):
    at=start();intake=at.session_state['customer_assessment:intake'];observed=intake.as_of-timedelta(days=5)
    content=source_text(intake,'Listener 443: TLS 1.0 is enabled.',date=observed.isoformat()).encode()
    at.get('file_uploader')[0].upload('manual.txt',content);run(at)
    widget(at.button,'Evaluate attached evidence').click();run(at)
    stage(at,'Review gaps');widget(at.selectbox,'Review requirement').set_value('ENC-01');run(at)
    widget(at.radio,'Draft action').set_value('Create Finding');widget(at.text_area,'Rationale').set_value('Validate the reported legacy protocol.');run(at)
    widget(at.button,'Record draft review').click();run(at)
    history=at.session_state['customer_assessment:actions']
    stage(at,'Report');widget(at.button,'Finish assessment review').click();run(at)
    stage(at,'Upload evidence')
    at.multiselect[0].set_value(['ENC-01','BCP-01'])
    widget(at.text_input,'Service stated by this document').set_value('Analyst scope challenge')
    widget(at.text_input,'Environment stated by this document').set_value('test');run(at)
    stale=deepcopy(at._tree.get_widget_states())
    suggestions(at)[0].click();run(at)
    at._run(stale);assert not at.exception
    assert widget(at.selectbox,'Document kind (your declaration)').value=='configuration'
    assert at.date_input[0].value==observed
    assert at.multiselect[0].value==['ENC-01','BCP-01']
    assert widget(at.text_input,'Service stated by this document').value=='Analyst scope challenge'
    assert widget(at.text_input,'Environment stated by this document').value=='test'
    assert at.session_state['customer_assessment:actions']==history
    assert 'customer_assessment:completion' not in at.session_state
    stage(at,'Report');assert at.warning and not at.get('download_button')
    stage(at,'Upload evidence')
    widget(at.selectbox,'Document kind (your declaration)').set_value('policy')
    at.date_input[0].set_value(None)
    at.multiselect[0].set_value(['ENC-01'])
    widget(at.text_input,'Service stated by this document').set_value('Newer manual scope');run(at)
    widget(at.button,'Evaluate attached evidence').click();run(at)
    source=at.session_state['customer_assessment:uploads'][0]
    assert source.evidence.source.evidence_kind=='policy' and source.evidence.source.observed_on is None
    assert source.evidence.source.service=='Newer manual scope' and source.evidence.source.environment=='test'
    assert source.requirements==('ENC-01',)
    stage(at,'Report');widget(at.button,'Finish assessment review').click();run(at)
    with ZipFile(BytesIO(packages[-1])) as archive:
        report=json.loads(archive.read('report.json'))
        assert report['findings'][0]['context_status'].startswith('Stale')
        assert report['findings'][0]['resolved'] is False
        assert report['risk']['residual_score'] is None
        artifact=json.loads(archive.read('manifest.json'))['artifacts'][0]
        assert archive.read(artifact['archive_path'])==content


@pytest.mark.parametrize('field,value', [('kind','policy'),('date',None),('targets',[]),('scope',''),('environment','test')])
def test_stale_metadata_callback_cannot_override_new_revision_or_invalidate_its_completion(monkeypatch,field,value):
    import src.upload_assessment_ui as ui
    key=ui.PREFIX+'file:synthetic-source';completion=object()
    edits={key+':'+field:'newer accepted draft'}
    state={ui.PREFIX+'metadata_revisions':{key:1},ui.PREFIX+'metadata_edits':edits,
           ui.PREFIX+'completion':completion,ui.PREFIX+'uploads_dirty':False,
           key+':v0:'+field:'obsolete browser value',key+':v1:'+field:value}
    monkeypatch.setattr(ui.st,'session_state',state)
    ui._capture_metadata(key,field,0)
    assert state[ui.PREFIX+'metadata_edits']==edits
    assert state[ui.PREFIX+'completion'] is completion
    assert state[ui.PREFIX+'uploads_dirty'] is False
    ui._capture_metadata(key,field,1)
    assert state[ui.PREFIX+'metadata_edits'][key+':'+field]==value
    assert ui.PREFIX+'completion' not in state
    assert state[ui.PREFIX+'uploads_dirty'] is True


def test_current_revision_manual_edits_in_same_snapshot_as_source_action_are_preserved(no_live_effects):
    at=start();intake=at.session_state['customer_assessment:intake'];observed=intake.as_of-timedelta(days=5)
    content=source_text(intake,'Listener 443: TLS 1.0 is enabled.',date=observed.isoformat()).encode()
    at.get('file_uploader')[0].upload('inline.txt',content);run(at)
    suggestions(at)[0].click();run(at)
    at.multiselect[0].set_value(['ENC-01','BCP-01'])
    widget(at.text_input,'Service stated by this document').set_value('Pending inline scope')
    widget(at.text_input,'Environment stated by this document').set_value('test')
    suggestions(at)[0].click();run(at)
    assert at.multiselect[0].value==['ENC-01','BCP-01']
    assert widget(at.text_input,'Service stated by this document').value=='Pending inline scope'
    assert widget(at.text_input,'Environment stated by this document').value=='test'
    assert widget(at.selectbox,'Document kind (your declaration)').value=='configuration'
    assert at.date_input[0].value==observed
