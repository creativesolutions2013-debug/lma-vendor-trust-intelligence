"""Real file-uploader AppTests with all live effects denied."""
from io import BytesIO
from zipfile import ZipFile
import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

# Reuse existing application/governance tripwires and capture real download bytes.
from test_guided_assessment_demo_ui import no_live_effects, packages, run, shown, widget
from test_upload_assessment import pdf_bytes, docx_bytes


def start():
    at=AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'),default_timeout=40).run()
    assert not at.exception
    assert widget(at.sidebar.radio,'Navigation').value == 'New Assessment'
    assert widget(at.sidebar.radio,'Navigation').options == ['New Assessment']
    assert not any(x.label == 'Demo scenario' for x in at.selectbox)
    widget(at.text_input,'Synthetic vendor name').set_value('My Synthetic Vendor')
    widget(at.text_input,'Service being assessed').set_value('User Analytics')
    widget(at.text_area,'Business use case').set_value('Synthetic reporting service')
    run(at);widget(at.button,'Create assessment').click();run(at)
    return at


def stage(at, value):
    widget(at.radio,'Assessment stage').set_value(value);return run(at)


@pytest.mark.parametrize('kind', ['txt','pdf','docx'])
def test_real_uploaded_files_to_completion_package_and_reassessment(no_live_effects,packages,kind):
    at=start()
    assert not at.session_state['customer_assessment:model'].documents
    text='TLS 1.0 is enabled on an alternate listener.'
    content=text.encode() if kind=='txt' else pdf_bytes(text) if kind=='pdf' else docx_bytes(text)
    at.get('file_uploader')[0].upload('my-tls.'+kind,content).upload('my-recovery.txt',b'Recovery exercise failed. Achieved RTO 300 minutes and RPO 90 minutes; identity excluded.')
    run(at)
    assert len(at.multiselect)==2
    assert at.multiselect[0].value == ['ENC-01']
    assert at.multiselect[1].value == ['BCP-01']
    # Supply declared dates; neither date nor scope is inferred from upload time.
    for field in at.date_input: field.set_value('2026-10-28')
    run(at)
    widget(at.button,'Evaluate attached evidence').click();run(at)
    assert widget(at.radio,'Assessment stage').value == 'Evaluate'
    assert any(text in block.value for block in at.code)
    model=at.session_state['customer_assessment:model']
    assert {b.source.filename for b in model.documents} == {'my-tls.'+kind,'my-recovery.txt'}
    assert model.worklist.rows[0].priority == 1
    stage(at,'Review gaps')
    widget(at.selectbox,'Review requirement').set_value('ENC-01');run(at)
    widget(at.radio,'Draft action').set_value('Create Finding')
    widget(at.text_area,'Rationale').set_value('Review my uploaded alternate listener evidence.');run(at)
    widget(at.button,'Record draft review').click();run(at)
    assert any('ENC-01' in s.value for s in at.success)
    widget(at.button,'Record draft review').click();run(at)
    assert at.error and len(at.session_state['customer_assessment:actions'])==1
    stage(at,'Report');widget(at.button,'Finish assessment review').click();run(at)
    assert any('review completed' in x.value for x in at.success)
    completed=at.session_state['customer_assessment:completion']
    with ZipFile(BytesIO(packages[-1])) as archive:
        report=json.loads(archive.read('report.json'));manifest=json.loads(archive.read('manifest.json'))
        assert report['assessment_context']['vendor']=='My Synthetic Vendor'
        assert report['review_completion']['completed_at']==completed.completed_at
        assert report['risk']['residual_score'] is None
        assert report['findings'][0]['requirement_id']=='ENC-01'
        assert len(manifest['artifacts'])==2
        for artifact in manifest['artifacts']:
            if artifact['filename']=='my-tls.'+kind: assert archive.read(artifact['archive_path'])==content
        assert 'My Synthetic Vendor' in archive.read('summary.html').decode()
    original=packages[-1];run(at);assert packages[-1]==original
    stage(at,'Upload evidence')
    assert len(at.multiselect)==2  # Files/metadata survive navigation; no manual reupload.
    at.get('file_uploader')[0].upload('new-scan.txt',b'TLS 1.0 is disabled on the primary listener. TLS 1.2 is used.')
    run(at)
    assert 'customer_assessment:completion' not in at.session_state
    stage(at,'Report')
    assert any('current upload selections' in x.value for x in at.warning)
    assert not at.get('download_button')
    stage(at,'Upload evidence')
    # Pending bytes also survive navigation; no manual reupload is needed.
    assert len(at.multiselect)==3
    widget(at.button,'Evaluate attached evidence').click();run(at)
    assert len(at.session_state['customer_assessment:model'].documents)==3
    stage(at,'Review gaps')
    assert any('Context' in t.value.columns and 'Stale context' in set(t.value['Context']) for t in at.dataframe)
    stage(at,'Report');widget(at.button,'Finish assessment review').click();run(at)
    with ZipFile(BytesIO(packages[-1])) as archive:
        report=json.loads(archive.read('report.json'))
        assert len(report['evidence_manifest']['artifacts'])==3
        assert report['findings'][0]['resolved'] is False
    widget(at.button,'Reopen review').click();run(at)
    assert widget(at.radio,'Assessment stage').value=='Review gaps'
    assert 'customer_assessment:completion' not in at.session_state
    other=start(); assert not other.session_state['customer_assessment:actions']
    widget(at.sidebar.button,'Clear this assessment').click();run(at)
    assert 'customer_assessment:intake' not in at.session_state


def test_empty_bad_scans_and_unrelated_files_remain_honest(no_live_effects,packages):
    at=start();widget(at.button,'Evaluate attached evidence').click();run(at)
    assert all(r.outcome=='Evidence Missing' for r in at.session_state['customer_assessment:model'].worklist.rows)
    stage(at,'Upload evidence')
    at.get('file_uploader')[0].upload('bad.pdf',b'not a pdf');run(at)
    assert at.error and widget(at.button,'Evaluate attached evidence').disabled
    stage(at,'Report');assert at.warning and not at.get('download_button')
    stage(at,'Upload evidence');widget(at.button,'Discard new file selections').click();run(at);at.get('file_uploader')[0].set_value([('menu.txt',b'Synthetic lunch menu.','text/plain')]);run(at)
    assert not at.multiselect[0].value
    widget(at.button,'Evaluate attached evidence').click();run(at)
    assert all(r.outcome=='Evidence Missing' for r in at.session_state['customer_assessment:model'].worklist.rows)


def test_pending_bytes_remain_in_memory_across_navigation_and_clear(no_live_effects):
    at=start()
    at.get('file_uploader')[0].upload('pending.txt',b'Synthetic recovery test evidence.')
    run(at)
    assert len(at.multiselect)==1
    stage(at,'Report')
    assert at.warning and not at.get('download_button')
    stage(at,'Upload evidence')
    assert len(at.multiselect)==1
    assert 'pending.txt' in shown(at)
    widget(at.button,'Discard new file selections').click();run(at)
    assert not at.multiselect
    assert not at.session_state.get('customer_assessment:pending_files')
