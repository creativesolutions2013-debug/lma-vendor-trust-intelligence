from dataclasses import replace
from datetime import date, timedelta
from hashlib import sha256
from io import BytesIO
import json
from zipfile import ZipFile, ZIP_DEFLATED, ZIP_BZIP2, ZIP_LZMA

import pytest
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

from src.upload_assessment import Intake, build_assessment, read_upload, suggested_requirements, MAX_UPLOAD_BYTES, MAX_TOTAL_BYTES
from src.guided_assessment_demo import (
    active_actions, complete_review, completion_is_current, package_bytes, record_action, report_payload, source_role, SourceRole,
)


@pytest.fixture
def intake():
    return Intake('synthetic-case-1', 'Customer-entered vendor', 'Customer analytics', 'Synthetic reporting', as_of=date(2026,10,28))


def pdf_bytes(text):
    writer = PdfWriter()
    page = writer.add_blank_page(width=400, height=400)
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
    stream = DecodedStreamObject(); stream.set_data(('BT /F1 12 Tf 20 300 Td (' + text + ') Tj ET').encode())
    page[NameObject('/Contents')] = writer._add_object(stream)
    buffer = BytesIO(); writer.write(buffer); return buffer.getvalue()


def docx_bytes(text):
    out = BytesIO()
    with ZipFile(out, 'w', ZIP_DEFLATED) as archive:
        archive.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>' + text + '</w:t></w:r></w:p></w:body></w:document>')
    return out.getvalue()


@pytest.mark.parametrize('filename,content,location', [
    ('own-tls.txt', b'TLS 1.0 is enabled on an alternate production listener.\nTLS 1.2 is enabled on primary listeners.', 'Line 1'),
    ('own-tls.pdf', pdf_bytes('TLS 1.0 is enabled on an alternate listener.'), 'Page 1'),
    ('own-tls.docx', docx_bytes('TLS 1.0 is enabled on an alternate listener.'), 'Paragraph 1'),
])
def test_actual_originals_are_parsed_screened_bound_and_exported(intake, filename, content, location):
    uploaded = read_upload(intake, filename, content, ('ENC-01',), observed_on=intake.as_of)
    dr_content = b'A completed recovery exercise achieved RTO 300 minutes and RPO 90 minutes. Scope excluded identity recovery.'
    recovery = read_upload(intake, 'own-recovery.txt', dr_content, ('BCP-01',), kind='test', observed_on=intake.as_of)
    model = build_assessment(intake, (uploaded, recovery))
    tls = next(r for r in model.worklist.rows if r.requirement_id == 'ENC-01')
    dr = next(r for r in model.worklist.rows if r.requirement_id == 'BCP-01')
    assert model.worklist.rows[0].priority == 1
    assert tls.outcome == dr.outcome == 'Needs Review'
    assert all(not f.confirmed for row in model.worklist.rows for f in row.review.facts)
    assert tls.review.facts and tls.review.facts[0].proposal.location == location
    assert tls.review.facts[0].proposal.quote in uploaded.evidence.document.segments[0].text
    assert dr.review.evidence[0].source.content == dr_content
    assert not dr.review.specialist_available
    assert 'RTO/RPO extraction' in model.customer_context['limitations']
    assert suggested_requirements(uploaded.evidence.document, {'ENC-01','BCP-01'}) == ('ENC-01',)
    history = record_action(model, (), 'ENC-01', 'Create Finding', '<script>Unverified alternate listener</script>')
    completion = complete_review(model, history)
    with ZipFile(BytesIO(package_bytes(model, history, completion))) as package:
        report = json.loads(package.read('report.json'))
        manifest_bytes = package.read('manifest.json')
        assert report['assessment_context']['vendor'] == intake.vendor
        assert report['evidence_received'] is True
        assert all('four selected' not in text for text in report['limitations'])
        assert report['review_completion']['vendor_approved'] is False
        assert report['risk']['residual_score'] is None
        assert report['evidence_manifest']['sha256'] == sha256(manifest_bytes).hexdigest()
        artifacts = json.loads(manifest_bytes)['artifacts']
        assert len(artifacts) == 2
        originals = {uploaded.evidence.source.document_id: content, recovery.evidence.source.document_id: dr_content}
        for artifact in artifacts:
            assert package.read(artifact['archive_path']) == originals[artifact['document_id']]
            assert sha256(package.read(artifact['archive_path'])).hexdigest() == artifact['sha256']
            assert artifact['archive_path'].startswith('vendor-evidence/')
        html = package.read('summary.html').decode()
        assert intake.vendor in html and '&lt;script&gt;' in html and '<script>' not in html
        assert set(a['document_id'] for a in artifacts) == set(originals)
        assert not any('synthetic-soc2' in name or 'customer-access-policy' in name for name in package.namelist())


def test_empty_unrelated_unsupported_and_declared_scope_dates_never_approve(intake):
    empty = build_assessment(intake)
    assert empty.worklist.requests and all(r.outcome == 'Evidence Missing' for r in empty.worklist.rows)
    assert not empty.documents and not empty.context_documents
    unrelated = read_upload(intake, 'unrelated.txt', b'Synthetic cafeteria lunch menu.')
    assert source_role(unrelated.evidence) == SourceRole.VENDOR_CONTEXT
    model = build_assessment(intake, (unrelated,))
    assert all(r.outcome == 'Evidence Missing' for r in model.worklist.rows)
    assert not any(s['citations'] for s in model.customer_context['screening'])
    with ZipFile(BytesIO(package_bytes(model, ()))) as package:
        artifact = json.loads(package.read('manifest.json'))['artifacts'][0]
        assert artifact['archive_path'].startswith('vendor-context/')
    for observed, service, environment in ((None, intake.service, 'production'), (intake.as_of-timedelta(days=500), intake.service, 'production'), (intake.as_of, 'Different service', 'production'), (intake.as_of, intake.service, 'test')):
        source = read_upload(intake, 'tls.txt', b'TLS 1.2 is supported.', ('ENC-01',), observed_on=observed, service=service, environment=environment)
        result = next(r for r in build_assessment(intake, (source,)).worklist.rows if r.requirement_id == 'ENC-01')
        assert result.outcome == 'Evidence Missing'
        assert any('date' in s or 'scope' in s for s in result.limitations)
    # Even wrongly routed unrelated prose remains manual, never technical support.
    routed = read_upload(intake, 'menu.txt', b'Lunch menu only.', ('ENC-01','BCP-01'), observed_on=intake.as_of)
    assert all(r.outcome != 'Met' for r in build_assessment(intake, (routed,)).worklist.rows)


def test_added_evidence_preserves_history_and_invalidates_affected_review_and_completion(intake):
    first = read_upload(intake, 'tls.txt', b'TLS 1.0 is enabled.', ('ENC-01',), observed_on=intake.as_of)
    model = build_assessment(intake, (first,))
    history = record_action(model, (), 'ENC-01', 'Create Finding', 'Investigate reported legacy TLS.')
    completion = complete_review(model, history)
    second = read_upload(intake, 'scan.txt', b'TLS 1.0 is disabled on primary listeners. TLS 1.2 is used.', ('ENC-01',), kind='test', observed_on=intake.as_of)
    revised = build_assessment(intake, (first,second))
    assert not active_actions(revised, history)
    assert not completion_is_current(revised, history, completion)
    report = report_payload(revised, history)
    assert report['findings'][0]['context_status'].startswith('Stale')
    assert report['findings'][0]['resolved'] is False
    assert history[0].citations[0].quote == first.evidence.document.segments[0].text
    with pytest.raises(ValueError, match='context changed'): package_bytes(revised, history, completion)
    changed_vendor = build_assessment(replace(intake, vendor='Another vendor'), (first,))
    assert not active_actions(changed_vendor, history)
    assert completion.snapshot['assessment_context']['vendor'] == intake.vendor
    with pytest.raises(ValueError, match='identical'): record_action(model, history, 'ENC-01','Create Finding', history[0].rationale)


@pytest.mark.parametrize('filename,content', [('empty.txt',b''), ('bad.pdf',b'not pdf'), ('bad.docx',b'not zip'), ('binary.txt',b'\xff'), ('code.html',b'<script>'), ('huge.txt',b'x'*(MAX_UPLOAD_BYTES+1))])
def test_invalid_uploads_are_actionable_and_not_attached(intake, filename, content):
    with pytest.raises(ValueError): read_upload(intake, filename, content)


def test_parser_limits_scan_handling_names_and_routing(intake):
    writer = PdfWriter();writer.add_blank_page(width=100,height=100);out=BytesIO();writer.write(out)
    with pytest.raises(ValueError, match='OCR'): read_upload(intake,'scan.pdf',out.getvalue())
    with pytest.raises(ValueError, match='parser limit'): read_upload(intake,'bomb.docx',docx_bytes('x'*(MAX_UPLOAD_BYTES+1)))
    with pytest.raises(ValueError, match='entity'): read_upload(intake,'entity.docx',docx_bytes('<!DOCTYPE evil>'))
    entity = BytesIO()
    with ZipFile(entity, 'w', ZIP_DEFLATED) as archive:
        archive.writestr('word/document.xml', '<!DOCTYPE evil><document/>'.encode('utf-16'))
    with pytest.raises(ValueError, match='entity'): read_upload(intake, 'utf16.docx', entity.getvalue())
    with pytest.raises(ValueError, match='250,000'): read_upload(intake,'long.txt',b'x'*250001)
    with pytest.raises(ValueError, match='applicable'): read_upload(intake,'a.txt',b'Text',('NOT-APPLICABLE',))
    safe = read_upload(intake,'../../own.txt',b'User text')
    assert safe.evidence.source.filename == 'own.txt'
    assert not suggested_requirements(safe.evidence.document, {'ENC-01','BCP-01'})
    with pytest.raises(ValueError, match='Duplicate'): build_assessment(intake,(safe,safe))
    other = read_upload(intake,'own.txt',b'Different text')
    with pytest.raises(ValueError, match='distinct filenames'): build_assessment(intake,(safe,other))
    too_many = tuple(read_upload(intake,str(i)+'.txt',b'Text') for i in range(11))
    with pytest.raises(ValueError, match='at most'): build_assessment(intake,too_many)


def test_applicability_risk_and_export_do_not_depend_on_fixture_builders(intake, monkeypatch):
    import src.guided_assessment_demo as demo
    from src.upload_assessment import risk_and_applicability
    from src.scoring import InherentRiskInput, calculate_inherent_risk
    def forbidden(*args, **kwargs): raise AssertionError('Fixture builder called from customer path')
    monkeypatch.setattr(demo, 'build_demo', forbidden)
    monkeypatch.setattr(demo, 'worklist_scenarios', forbidden)
    monkeypatch.setattr(demo, 'pilot_cases', forbidden)
    for context in (intake, replace(intake, data='Restricted', access='Privileged', criticality='Critical')):
        score, points, applicability = risk_and_applicability(context)
        model = build_assessment(context)
        assert model.inherent_score == score == calculate_inherent_risk(InherentRiskInput(*points))
        assert {r.control_id for r in model.worklist.rows} == {c.control_id for c in applicability.controls}
        assert all(not row.specialist_available for row in model.worklist.rows)
        assert report_payload(model, ())['evidence_manifest']['artifacts'] == []
    hostile = replace(intake, vendor='<script>vendor</script>', use_case='<img src=x onerror=alert(1)>')
    model = build_assessment(hostile)
    with ZipFile(BytesIO(package_bytes(model, (), complete_review(model, ())))) as archive:
        summary = archive.read('summary.html').decode()
        assert '<script>' not in summary and '<img' not in summary
        assert '&lt;script&gt;vendor' in summary


def malformed_docx(mode):
    """Real ZIP headers exercising stdlib extraction errors, not mocked exceptions."""
    import struct
    if mode in ('bzip2', 'lzma'):
        out = BytesIO()
        with ZipFile(out, 'w', ZIP_BZIP2 if mode == 'bzip2' else ZIP_LZMA) as archive:
            archive.writestr('word/document.xml', b'<document>Synthetic text</document>')
        raw = bytearray(out.getvalue())
        # Destroy compressed payload while keeping valid ZIP headers/directory.
        start = 30 + struct.unpack_from('<H', raw, 26)[0] + struct.unpack_from('<H', raw, 28)[0]
        length = struct.unpack_from('<I', raw, 18)[0]
        raw[start:start+length] = b'\xff' * length
        return bytes(raw)
    raw = bytearray(docx_bytes('Synthetic text'))
    local = raw.index(b'PK\x03\x04')
    central = raw.index(b'PK\x01\x02')
    if mode == 'encrypted':
        for offset in (local + 6, central + 8):
            struct.pack_into('<H', raw, offset, struct.unpack_from('<H', raw, offset)[0] | 1)
    elif mode == 'compression':
        for offset in (local + 8, central + 10): struct.pack_into('<H', raw, offset, 99)
    elif mode == 'corrupt':
        struct.pack_into('<I', raw, central + 16, 0)  # Wrong CRC.
    return bytes(raw)


@pytest.mark.parametrize('mode', ['encrypted', 'compression', 'corrupt', 'bzip2', 'lzma'])
def test_docx_extraction_failures_are_actionable(intake, mode):
    with pytest.raises(ValueError, match='readable, unencrypted DOCX'):
        read_upload(intake, 'bad.docx', malformed_docx(mode))


def test_txt_and_docx_limits_stop_before_binding_fingerprint(intake, monkeypatch):
    import src.evidence_source_validation as bindings
    import src.evidence_intelligence_mvp as parser
    def forbidden(*args, **kwargs): raise AssertionError('Oversized parse reached fingerprinting')
    monkeypatch.setattr(bindings, '_digest', forbidden)
    original = parser.EvidenceSegment
    calls = []
    def counted(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)
    monkeypatch.setattr(parser, 'EvidenceSegment', counted)
    for name, content in [('lines.txt', b'x\n' * 200000),
                          ('chars.txt', b'x' * 250001),
                          ('paragraphs.docx', docx_bytes('</w:t></w:r></w:p><w:p><w:r><w:t>'.join(['x']*10000)))]:
        calls.clear()
        with pytest.raises(ValueError, match='2,000-section'):
            read_upload(intake, name, content)
        assert len(calls) <= 2000


def test_pdf_expansion_is_contained_before_parent_binding(intake, monkeypatch):
    import src.evidence_source_validation as bindings
    def forbidden(*args, **kwargs): raise AssertionError('Oversized PDF reached fingerprinting')
    monkeypatch.setattr(bindings, '_digest', forbidden)
    writer = PdfWriter(clone_from=BytesIO(pdf_bytes('Synthetic text')))
    page = writer.pages[0]
    stream = DecodedStreamObject()
    stream.set_data(b'BT /F1 12 Tf 20 300 Td (' + b'x'* (12*1024*1024) + b') Tj ET')
    page[NameObject('/Contents')] = writer._add_object(stream.flate_encode())
    out = BytesIO(); writer.write(out)
    assert len(out.getvalue()) < MAX_UPLOAD_BYTES
    with pytest.raises(ValueError, match='limit'):
        read_upload(intake, 'compressed.pdf', out.getvalue())


def test_pdf_timeout_is_actionable_and_original_source_binding_is_unchanged(intake, monkeypatch):
    import subprocess
    import src.bounded_document_parser as parser
    from src.evidence_source_validation import bind_evidence
    upload = read_upload(intake, 'original.txt', 'First\r\n\r\nThird\u2028Fourth'.encode())
    assert upload.evidence == bind_evidence(upload.evidence.source)
    def timeout(*args, **kwargs):
        assert kwargs['timeout'] == parser.WALL_SECONDS
        raise subprocess.TimeoutExpired(args[0], kwargs['timeout'])
    monkeypatch.setattr(parser.subprocess, 'run', timeout)
    with pytest.raises(ValueError, match='resource limits'):
        read_upload(intake, 'timeout.pdf', pdf_bytes('Synthetic text'))


def test_assessment_reuses_bounded_bindings_in_all_downstream_services(intake, monkeypatch):
    from src.evidence_source_validation import bind_evidence
    import src.evidence_source_validation as bindings
    import src.bounded_document_parser as parser
    uploaded = read_upload(intake, 'shared.pdf', pdf_bytes('TLS 1.0 exception; recovery test failed.'),
                           ('ENC-01', 'BCP-01'), observed_on=intake.as_of)
    def forbidden(*args, **kwargs):
        raise AssertionError('Accepted evidence was reparsed during assessment/review/export')
    monkeypatch.setattr(bindings, 'read_evidence_document', forbidden)
    monkeypatch.setattr(parser, 'read_bounded_document', forbidden)
    model = build_assessment(intake, (uploaded,))
    for row in model.worklist.rows:
        if row.requirement_id in uploaded.requirements:
            assert row.review.evidence[0] is uploaded.evidence
    history = record_action(model, (), 'ENC-01', 'Create Finding', 'Investigate source concern.')
    package_bytes(model, history, complete_review(model, history))
    # The cache is scoped to construction; it neither leaks into another session
    # nor turns source ID equality into stale-metadata reuse.
    with pytest.raises(AssertionError): bind_evidence(uploaded.evidence.source)
    changed = replace(uploaded.evidence.source, service='Changed scope')
    from src.evidence_source_validation import reuse_evidence_bindings
    with reuse_evidence_bindings((uploaded.evidence,)):
        with pytest.raises(AssertionError): bind_evidence(changed)


def test_docx_rejection_does_not_hide_unrelated_server_io_faults(intake, monkeypatch):
    content = docx_bytes('Synthetic document')
    def unexpected_fault(*args, **kwargs):
        raise OSError('Synthetic server fault, not a corrupt decompressor stream')
    monkeypatch.setattr(ZipFile, 'open', unexpected_fault)
    with pytest.raises(OSError, match='Synthetic server fault'):
        read_upload(intake, 'server-fault.docx', content)
