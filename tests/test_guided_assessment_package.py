"""Exact synthetic originals and conservative risk in the downloadable package."""
from dataclasses import replace
from hashlib import sha256
from html.parser import HTMLParser
from io import BytesIO
import json
from pathlib import PurePosixPath
from zipfile import ZipFile

import pytest

from src.guided_assessment_demo import (
    RISK_PROFILES, build_demo, complete_review, package_bytes, record_action, report_payload,
    source_role,
)
from src.guided_assessment_package import artifact_manifest, assessment_package, original_sources, json_bytes
from src.evidence_source_validation import bind_evidence


@pytest.mark.parametrize('scenario', ['gap', 'exception'])
@pytest.mark.parametrize('received', [False, True])
@pytest.mark.parametrize('profile,score,rating', [(RISK_PROFILES[0], 58, 'High'), (RISK_PROFILES[1], 36, 'Moderate')])
def test_package_exact_originals_manifest_citations_and_pending_risk(scenario, received, profile, score, rating):
    model = build_demo(scenario, received, profile)
    target = next(row for row in model.worklist.rows if row.control_id == 'ENC-01')
    actions = record_action(model, (), target.requirement_id, 'Create Finding', '<script>alert("x")</script> & unresolved')
    actions = record_action(model, actions, target.requirement_id, 'Accept', 'Draft discussion; keep concerns open.')
    completion = complete_review(model, actions)
    data = package_bytes(model, actions, completion)
    assert data == package_bytes(model, actions, completion)
    with ZipFile(BytesIO(data)) as archive:
        names = archive.namelist()
        assert len(names) == len(set(names))
        assert all(not PurePosixPath(p).is_absolute() and '..' not in PurePosixPath(p).parts and '\\' not in p for p in names)
        report = json.loads(archive.read('report.json'))
        assert report == report_payload(model, actions, completion)
        manifest_bytes = archive.read('manifest.json')
        manifest = json.loads(manifest_bytes)
        assert sha256(manifest_bytes).hexdigest() == report['evidence_manifest']['sha256']
        assert manifest['artifacts'] == completion.snapshot['evidence_manifest']['artifacts']
        originals = {b.source.document_id: b for b in model.documents + model.context_documents}
        attachments = {a['document_id']: a for a in manifest['artifacts']}
        assert len(manifest['artifacts']) == len(originals) == len(attachments)
        assert set(attachments) == set(originals)
        assert ('dr-exercise' in attachments) is received
        assert attachments['tls-customer-policy']['archive_path'].startswith('customer-policy/')
        assert attachments['customer-access-policy']['archive_path'].startswith('customer-policy/')
        assert attachments['synthetic-soc2-overview']['archive_path'].startswith('vendor-context/')
        assert attachments['dr-plan']['archive_path'].startswith('vendor-evidence/')
        for document_id, artifact in attachments.items():
            bound = originals[document_id]
            content = archive.read(artifact['archive_path'])
            assert content == bound.source.content
            assert sha256(content).hexdigest() == artifact['sha256'] == bound.content_sha256
            assert artifact['source_fingerprint'] == bound.fingerprint
            assert artifact['provenance'] == bound.source.origin
            for link in artifact['requirement_links']:
                assert link['requirement_id'] in {r.requirement_id for r in model.worklist.rows}
                assert link['citations'] == [{'location': s.location, 'quote': s.text} for s in bound.document.segments]
        for row in report['requirements']:
            for citation in row['citations'] + row['customer_policy_citations']:
                artifact = attachments[citation['artifact_id']]
                assert citation['source_role'] == artifact['source_role']
                assert citation['archive_path'] == artifact['archive_path']
                assert citation['content_sha256'] == artifact['sha256']
        risk = report['risk']
        assert (risk['inherent_score'], risk['inherent_rating']) == (score, rating)
        assert risk['residual_status'] == 'Pending verified inputs / risk-owner decision'
        assert risk['residual_score'] is risk['residual_rating'] is None
        assert risk['residual_hold_rating'] == rating
        assert risk['approved_risk'] is False
        assert report['findings'][0]['resolved'] is False
        assert report['review_completion']['vendor_approved'] is False
        assert len(report['targeted_requests']) == (0 if received else 1)
        html = archive.read('summary.html').decode()
        assert '<script>' not in html and '&lt;script&gt;' in html
        assert risk['residual_status'] in html and f'Provisional {rating} hold' in html
        assert completion.completed_at in html and completion.fingerprint in html
        for row in report['requirements']:
            assert row['requirement_id'] in html and row['policy_version'] in html
        class Links(HTMLParser):
            def __init__(self): super().__init__(); self.links = []
            def handle_starttag(self, tag, attrs):
                if tag == 'a': self.links.append(dict(attrs)['href'])
        links = Links(); links.feed(html)
        assert set(links.links) <= set(names)
        assert {a['archive_path'] for a in attachments.values()} <= set(links.links)


def test_safe_unique_paths_deduplication_and_integrity_failures():
    model = build_demo()
    bound = model.documents[0]
    renamed = bind_evidence(replace(bound.source, filename='../../bad\\name".txt'))
    sources = [(renamed, 'Simulated vendor evidence')] * 2
    artifacts = artifact_manifest(sources, {})['artifacts']
    assert len(artifacts) == 1
    path = PurePosixPath(artifacts[0]['archive_path'])
    assert len(path.parts) == 3 and '..' not in path.parts and '"' not in str(path)
    same_name = bind_evidence(replace(renamed.source, document_id='second-source'))
    two = artifact_manifest([(renamed, 'Simulated vendor evidence'), (same_name, 'Simulated vendor evidence')], {})
    assert len({a['archive_path'] for a in two['artifacts']}) == 2
    with pytest.raises(ValueError, match='digest'):
        original_sources([(replace(bound, source=replace(bound.source, content=b'changed')), 'Simulated vendor evidence')])
    with pytest.raises(ValueError, match='Conflicting'):
        original_sources([(bound, 'Simulated vendor evidence'), (renamed, 'Simulated vendor evidence')])
    with pytest.raises(ValueError, match='role'):
        original_sources([(bound, 'unclassified')])
    with pytest.raises(ValueError, match='document ID'):
        original_sources([(replace(bound, source=replace(bound.source, document_id='../escape')), 'Simulated vendor evidence')])
    report = report_payload(model, ())
    report['evidence_manifest']['sha256'] = '0' * 64
    with pytest.raises(ValueError, match='Manifest digest'):
        assessment_package(report, [(b, 'Simulated vendor evidence') for b in model.documents])
    report = report_payload(model, ())
    report['evidence_manifest']['artifacts'][0]['archive_path'] = '../outside.txt'
    manifest = {'synthetic': True, 'artifacts': report['evidence_manifest']['artifacts']}
    report['evidence_manifest']['sha256'] = sha256(json_bytes(manifest)).hexdigest()
    sources = [(b, source_role(b).value) for b in model.documents + model.context_documents]
    with pytest.raises(ValueError, match='does not match'):
        assessment_package(report, sources)
