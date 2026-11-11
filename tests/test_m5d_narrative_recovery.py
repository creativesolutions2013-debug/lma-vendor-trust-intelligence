"""Independent synthetic manual-review cues, never numeric recovery conclusions."""
from dataclasses import replace
from datetime import date
from hashlib import sha256
from io import BytesIO
import json
from zipfile import ZipFile

import pytest

from src.guided_assessment_demo import complete_review, package_bytes
from src.organization_methodology import OrganizationMethodology, default_definition
from src.upload_assessment import build_assessment, read_upload
from src import upload_evaluation
from test_upload_evaluation import intake, upload, evaluation, source_text


POSITIVE = [
    'Service restoration took six hours.',
    'Failover required 150 minutes.',
    'Recovering the service took two hours, with up to twenty minutes of data loss.',
    'Switching service required approximately 2.5 hours.',
    'Recovery took 20 minutes.',  # Benign duration: attention is not a breach claim.
    'Service recovery took forty-five minutes, with half an hour of data loss.',
]


@pytest.mark.parametrize('statement', POSITIVE[:5])
def test_direct_narrative_is_cited_manual_attention_without_metric_or_adverse_result(intake, statement):
    bound = upload(intake, 'Recovery exercise completed.\n' + statement, 'BCP-01')
    model = build_assessment(intake, (bound,))
    result = evaluation(model, 'BCP-01')
    assert len(result['review_alerts']) == 1
    alert = result['review_alerts'][0]
    assert alert['eligible_for_current_review']
    assert alert['quote'] == statement and not alert['confirmed'] and not alert['authoritative']
    assert alert['document_id'] == bound.evidence.source.document_id
    assert alert['source_fingerprint'] == bound.evidence.fingerprint
    segment = bound.evidence.document.segments[int(alert['source_id'].rsplit(':', 1)[1]) - 1]
    assert alert['quote'] in segment.text and alert['location'] == segment.location
    assert 'no exact achieved RTO/RPO or threshold breach' in ' '.join(alert['uncertainties'])
    assert 'compare it with the captured customer threshold' in alert['next_action']
    assert not any(f['dimension'].startswith('achieved_') or f['direction'] == 'adverse' for f in result['facts'])
    assert result['preview']['outcome_if_confirmed'] not in ('Met', 'Risk Identified')
    assert result['status'] == 'Unverified evidence review'
    assert all(r.outcome not in ('Met', 'Risk Identified') for r in model.worklist.rows)
    assert all(not f.confirmed for r in model.worklist.rows for f in r.review.facts)


@pytest.mark.parametrize('statement', [
    'Management reports service restoration took six hours.',
    'According to the supplier, recovery took 180 minutes.',
    'The vendor says: Recovery took 180 minutes.',
    'Management reports; recovery took 180 minutes.',
    'It is false that recovery took 180 minutes.',
    '"Recovery took 180 minutes."',
    'Recovery did not take 180 minutes.',
    'Recovery should take 180 minutes.',
    'Recovery took 180 minutes if the backup is available.',
    'Recovery took 180 minutes?',
    'Planned failover required 180 minutes.',
    'Our policy requires recovery within 180 minutes.',
    'Customer support took six hours.',
    'Recovery took office hours.',
    'Restoring service took six hours but not in production.',
    POSITIVE[5],  # Unsupported compound wording stays manual in the original.
])
def test_attribution_intent_negation_or_unrecognized_qualification_is_not_promoted(intake, statement):
    model = build_assessment(intake, (upload(intake, statement, 'BCP-01'),))
    result = evaluation(model, 'BCP-01')
    assert not result['review_alerts']
    assert result['preview']['outcome_if_confirmed'] not in ('Met', 'Risk Identified')


@pytest.mark.parametrize('heading', ['Management reports:', 'Hypothetical example:', 'According to management', 'Exercise notes:'])
def test_preceding_attribution_or_unknown_heading_limits_narrative_review(intake, heading):
    bound = upload(intake, heading + '\n' + POSITIVE[0], 'BCP-01')
    result = evaluation(build_assessment(intake, (bound,)), 'BCP-01')
    alert = result['review_alerts'][0]
    assert not alert['eligible_for_current_review']
    assert any('Preceding source context' in u for u in alert['uncertainties'])
    context = alert['context_citations'][0]
    assert context['quote'] == heading and context['document_id'] == bound.evidence.source.document_id
    assert context['source_fingerprint'] == bound.evidence.fingerprint
    segment = bound.evidence.document.segments[int(context['source_id'].rsplit(':', 1)[1]) - 1]
    assert context['quote'] in segment.text and context['location'] == segment.location
    assert result['preview']['outcome_if_confirmed'] != 'Risk Identified'


@pytest.mark.parametrize('changes,statement,needle', [
    ({'date': '2024-02-01'}, POSITIVE[0], 'older than'),
    ({'environment': 'test'}, POSITIVE[0], 'environment'),
    ({'service': 'Sibling Service'}, POSITIVE[0], 'service'),
    ({'type': 'Recovery policy'}, POSITIVE[0], 'type'),
    ({}, 'Recovery took six hours in 2024.', 'year'),
    ({}, 'Recovery took six hours on 2024-02-01.', 'Clause-local date'),
    ({}, 'Recovery took six hours in the test environment.', 'outside'),
])
def test_context_limited_narrative_stays_cited_but_not_current(intake, changes, statement, needle):
    result = evaluation(build_assessment(intake, (upload(intake, statement, 'BCP-01', **changes),)), 'BCP-01')
    alert = result['review_alerts'][0]
    assert alert['quote'] == statement and not alert['eligible_for_current_review']
    assert any(needle in issue for issue in alert['uncertainties'])
    assert 'Resolve the cited source-context limitations' in alert['next_action']
    assert result['preview']['outcome_if_confirmed'] not in ('Met', 'Risk Identified')


def test_captured_organization_kinds_and_freshness_gate_narrative_without_comparing_amount(intake):
    definition = default_definition('narrative-synthetic')
    rule = next(r for r in definition['requirements'] if r['id'] == 'BCP-01')
    rule.update(max_age_days=5, evidence_kinds=['policy'])
    definition['assurance'].update(dr_max_test_age_days=5, rto_minutes=1, rpo_minutes=None)
    scoped = replace(intake, organization_id='narrative-synthetic', methodology=OrganizationMethodology.from_dict(definition))
    result = evaluation(build_assessment(scoped, (upload(scoped, POSITIVE[4], 'BCP-01'),)), 'BCP-01')
    alert = result['review_alerts'][0]
    assert not alert['eligible_for_current_review']
    assert any('older than 5 days' in u for u in alert['uncertainties'])
    assert any('not accepted' in u for u in alert['uncertainties'])
    assert not result['facts'] and result['preview']['outcome_if_confirmed'] != 'Risk Identified'


@pytest.mark.parametrize('budget', ['MAX_FACTS', 'MAX_LINES'])
def test_budget_exhaustion_never_leaves_a_current_narrative_alert(intake, monkeypatch, budget):
    monkeypatch.setattr(upload_evaluation, budget, 1 if budget == 'MAX_FACTS' else 5)
    body = 'Service restoration took six hours.\nFailover required 150 minutes.'
    result = evaluation(build_assessment(intake, (upload(intake, body, 'BCP-01'),)), 'BCP-01')
    assert result['review_alerts']
    assert all(not a['eligible_for_current_review'] for a in result['review_alerts'])
    assert all(any('incomplete' in u for u in a['uncertainties']) for a in result['review_alerts'])


def test_alert_budget_cannot_suppress_an_independent_typed_adverse_metric(intake, monkeypatch):
    monkeypatch.setattr(upload_evaluation, 'MAX_FACTS', 5)
    body = 'Recovery exercise completed.\nAchieved RTO 300 minutes.\n' + '\n'.join([POSITIVE[0]] * 6)
    result = evaluation(build_assessment(intake, (upload(intake, body, 'BCP-01'),)), 'BCP-01')
    assert result['preview']['outcome_if_confirmed'] == 'Risk Identified'
    assert any(f['dimension'] == 'achieved_rto_minutes' and f['eligible_for_preview'] for f in result['facts'])
    assert all(not a['eligible_for_current_review'] for a in result['review_alerts'])


def test_export_preserves_narrative_original_bytes_uncertainty_and_no_governed_decision(intake):
    body = POSITIVE[2]
    content = source_text(intake, body, 'BCP-01').encode()
    bound = read_upload(intake, '<synthetic>.txt', content, ('BCP-01',), kind='test', observed_on=date(2026, 10, 20))
    model = build_assessment(intake, (bound,))
    with ZipFile(BytesIO(package_bytes(model, (), complete_review(model, ())))) as archive:
        report = json.loads(archive.read('report.json'))
        alert = next(e for e in report['assessment_context']['evaluations'] if e['requirement_id'] == 'BCP-01')['review_alerts'][0]
        assert alert['quote'] == body and not alert['confirmed']
        html = archive.read('summary.html').decode()
        assert 'Narrative recovery statement' in html and '&lt;synthetic&gt;.txt' in html
        assert '<synthetic>.txt' not in html and body in html
        assert alert['next_action'] in html
        artifact = report['evidence_manifest']['artifacts'][0]
        assert archive.read(artifact['archive_path']) == content
        assert sha256(content).hexdigest() == artifact['sha256']
        assert report['risk']['residual_score'] is None
        assert not report['review_completion']['vendor_approved']


def test_tls_subject_is_unchanged(intake):
    line = 'Client sessions on legacy gateway port 9555 accept TLS 1.0.'
    result = evaluation(build_assessment(intake, (upload(intake, line),)))
    assert result['facts'][0]['subject'] == 'legacy gateway port 9555'
    assert not result['review_alerts']
