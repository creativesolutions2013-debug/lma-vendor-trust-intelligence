"""Synthetic integration of M5D candidates with captured organization policy."""
from dataclasses import replace
from datetime import timedelta
from hashlib import sha256
from io import BytesIO
import json
from zipfile import ZipFile

import pytest

from src.guided_assessment_demo import complete_review, completion_is_current, package_bytes, record_action
from src.organization_methodology import OrganizationMethodology, default_definition
from src.upload_assessment import build_assessment, read_upload
from test_organization_methodology import intake


CASES = [
    ('ENC-01', 'Traffic on production gateway port 8444 accepts TLS 1.2 connections.',
     'enabled_version', 12),
    ('BCP-01', 'Recovery exercise completed.\nMeasured RTO 3 hours 25 minutes.',
     'achieved_rto_minutes', 205),
    ('BCP-01', 'Recovery exercise completed.\nObserved RPO 1 hour and 15 minutes.',
     'achieved_rpo_minutes', 75),
    ('BCP-01', 'Recovery exercise completed.\nIdentity federation was not tested in this exercise.',
     'scope_complete', False),
]


def source(i, family, body):
    kind = 'configuration' if family == 'ENC-01' else 'test'
    genre = 'Configuration export' if family == 'ENC-01' else 'DR exercise results'
    observed = i.as_of - timedelta(days=10)
    content = (f'{genre}\nService: {i.service}\nEnvironment: production\n'
               f'Observation date: {observed.isoformat()}\n{body}\n').encode()
    return read_upload(i, 'synthetic-m5d.txt', content, (family,),
                       kind=kind, observed_on=observed)


def result(model, family):
    return next(e for e in model.customer_context['evaluations'] if e['requirement_id'] == family)


@pytest.mark.parametrize('family,body,dimension,value', CASES[:3])
@pytest.mark.parametrize('strict', [False, True])
def test_m5d_candidates_compare_against_organization_thresholds(family, body, dimension, value, strict):
    definition = default_definition('m5d-synthetic', 'strict' if strict else 'lenient')
    definition['assurance'].update(tls_minimum_version=13 if strict else 12,
                                   rto_minutes=200 if strict else 210,
                                   rpo_minutes=60 if strict else 80)
    i = intake(OrganizationMethodology.from_dict(definition))
    bound = source(i, family, body)
    model = build_assessment(i, (bound,))
    evaluation = result(model, family)
    fact = next(f for f in evaluation['facts'] if f['dimension'] == dimension)
    assert fact['value'] == value and fact['eligible_for_preview']
    assert (fact['direction'] == 'adverse') is strict
    assert (evaluation['preview']['outcome_if_confirmed'] == 'Risk Identified') is strict
    assert not fact['confirmed'] and not evaluation['authoritative']
    assert all(r.outcome not in ('Met', 'Risk Identified') for r in model.worklist.rows)
    assert fact['source_fingerprint'] == bound.evidence.fingerprint
    segment = bound.evidence.document.segments[int(fact['source_id'].rsplit(':', 1)[1]) - 1]
    assert fact['quote'] in segment.text and fact['location'] == segment.location


@pytest.mark.parametrize('family,body,dimension,value', CASES)
@pytest.mark.parametrize('gate', ['freshness', 'kind'])
def test_organization_evidence_rules_block_m5d_current_previews(family, body, dimension, value, gate):
    definition = default_definition('m5d-synthetic')
    definition['assurance'].update(tls_minimum_version=13, rto_minutes=200, rpo_minutes=60)
    rule = next(r for r in definition['requirements'] if r['id'] == family)
    if gate == 'freshness':
        rule['max_age_days'] = 5
        if family == 'BCP-01':
            definition['assurance']['dr_max_test_age_days'] = 5
    else:
        rule['evidence_kinds'] = ['policy']
    i = intake(OrganizationMethodology.from_dict(definition))
    evaluation = result(build_assessment(i, (source(i, family, body),)), family)
    fact = next(f for f in evaluation['facts'] if f['dimension'] == dimension)
    assert fact['value'] == value and fact['direction'] == 'adverse'
    assert not fact['eligible_for_preview'] and not fact['confirmed']
    assert evaluation['preview']['outcome_if_confirmed'] not in ('Met', 'Risk Identified')
    assert any(('older than 5 days' if gate == 'freshness' else 'not accepted') in issue
               for issue in evaluation['sources'][0]['uncertainties'])


def test_m5d_export_keeps_captured_policy_findings_and_original_evidence():
    definition = default_definition('m5d-synthetic', '1')
    i = intake(OrganizationMethodology.from_dict(definition))
    family, body, _, _ = CASES[1]
    bound = source(i, family, body)
    original = build_assessment(i, (bound,))
    history = record_action(original, (), family, 'Create Finding', 'Synthetic analyst follow-up remains open.')
    done = complete_review(original, history)
    package = package_bytes(original, history, done)
    definition['version'] = '2'
    definition['assurance']['rto_minutes'] = 200
    later = build_assessment(replace(i, methodology=OrganizationMethodology.from_dict(definition)), (bound,))
    assert result(original, family)['preview']['outcome_if_confirmed'] != 'Risk Identified'
    assert result(later, family)['preview']['outcome_if_confirmed'] == 'Risk Identified'
    assert completion_is_current(original, history, done)
    assert not completion_is_current(later, history, done)
    assert package_bytes(original, history, done) == package
    with ZipFile(BytesIO(package)) as archive:
        policy = archive.read('methodology.json')
        report = json.loads(archive.read('report.json'))
        artifact = json.loads(archive.read('manifest.json'))['artifacts'][0]
        assert json.loads(policy)['version'] == '1'
        assert sha256(policy).hexdigest() == i.methodology.fingerprint
        assert report['assessment_context']['methodology_sha256'] == i.methodology.fingerprint
        assert archive.read(artifact['archive_path']) == bound.evidence.source.content
        assert sha256(bound.evidence.source.content).hexdigest() == artifact['sha256']
        assert report['risk']['residual_score'] is None
        assert not report['review_completion']['vendor_approved']
        assert not report['findings'][0]['resolved']
        assert all(not f['confirmed'] for e in report['assessment_context']['evaluations'] for f in e['facts'])
