"""Synthetic source-bound insufficiency review, follow-up and export regressions."""
from dataclasses import replace
from datetime import date, timedelta
from hashlib import sha256
from html import escape
from io import BytesIO
import json
from zipfile import ZipFile

import pytest

from src.guided_assessment_demo import (
    active_actions, complete_review, completion_is_current, package_bytes,
    record_action, report_payload,
)
from src.organization_methodology import OrganizationMethodology, default_definition
from src.upload_assessment import (
    Intake, build_assessment, read_upload, record_upload_review,
)


@pytest.fixture
def intake():
    methodology = OrganizationMethodology.from_dict(default_definition())
    return Intake(
        'synthetic-followup', 'Synthetic vendor', 'Synthetic analytics',
        'Synthetic reporting', as_of=date(2026, 11, 20),
        organization_id=methodology.definition['organization_id'],
        methodology=methodology,
    )


def policy(intake, filename='dr-policy.txt', **changes):
    observed = changes.pop('observed_on', intake.as_of - timedelta(days=5))
    content = changes.pop('content', (
        'Recovery plan\n'
        f'Service: {intake.service}\nEnvironment: {intake.environment}\n'
        f'Observation date: {observed.isoformat() if observed else "unknown"}\n'
        'Target RTO 120 minutes and target RPO 30 minutes.\n'
        'No completed recovery exercise record is supplied.'
    ).encode())
    return read_upload(
        intake, filename, content, changes.pop('requirements', ('BCP-01',)),
        kind=changes.pop('kind', 'policy'), observed_on=observed, **changes,
    )


def row(model, requirement='BCP-01'):
    return next(r for r in model.worklist.rows if r.requirement_id == requirement)


def requests(model, requirement='BCP-01'):
    return tuple(r for r in model.worklist.requests if requirement in r.requirement_ids)


def reviews(model):
    return tuple(review for link in model.scenario.assurance_links
                 for review in link.need_reviews)


def request_review(model, actions=(), rationale='Existing policy lacks completed exercise results.'):
    return record_upload_review(
        model, actions, 'BCP-01', 'Request Evidence', rationale,
        confirms_insufficiency=True,
    )


def assert_no_assurance_or_risk_approval(model, actions):
    assert all(r.outcome not in ('Met', 'Partially Met', 'Risk Identified')
               for r in model.worklist.rows)
    assert all(not fact.confirmed for r in model.worklist.rows for fact in r.review.facts)
    report = report_payload(model, actions)
    assert report['risk']['residual_score'] is None
    assert report['risk']['approved_risk'] is False
    assert report['review_completion']['vendor_approved'] is False
    assert report['review_completion']['technical_facts_confirmed_by_completion'] is False


def test_policy_review_creates_real_source_bound_followup_and_traceable_package(intake):
    upload = policy(intake)
    original = build_assessment(intake, (upload,))
    assert row(original).outcome == 'Needs Review'
    assert row(original).need_matches[0].status == 'Analyst validation required'
    assert not requests(original)
    rationale = '<script>Request completed recovery results</script> & dependency coverage.'

    updated, actions = request_review(original, rationale=rationale)

    assert row(updated).outcome == row(original).outcome
    assert row(updated).need_matches[0].status == 'Missing or insufficient'
    assert len(requests(updated)) == 1
    mapping = next(mapping for mapping in original.scenario.requirements
                   if mapping.control_id == 'BCP-01')
    assert requests(updated)[0].question == rationale
    assert requests(updated)[0].acceptable_evidence == mapping.needs[0].acceptable_evidence
    assert requests(updated)[0].missing_fact == mapping.needs[0].missing_fact
    assert updated.scenario.requirements == original.scenario.requirements
    assert row(updated).next_action == rationale
    review, = reviews(updated)
    assert review.decision == 'insufficient' and review.confirms is True
    assert review.rationale == rationale
    assert review.source_fingerprints == (upload.evidence.fingerprint,)
    assert review.fact_fingerprints == ()
    assert not reviews(original) and not requests(original)
    assert actions[0].action == 'Request Evidence'
    assert actions[0] in active_actions(updated, actions)
    assert actions[0].citations[0].quote in upload.evidence.document.segments[0].text
    assert_no_assurance_or_risk_approval(updated, actions)

    completion = complete_review(updated, actions)
    with ZipFile(BytesIO(package_bytes(updated, actions, completion))) as archive:
        report = json.loads(archive.read('report.json'))
        gap_review, = report['evidence_gap_reviews']
        assert gap_review['requirement_id'] == 'BCP-01'
        assert gap_review['status'] == 'Current'
        assert gap_review['rationale'] == rationale
        assert gap_review['source_fingerprints'] == [upload.evidence.fingerprint]
        assert gap_review['semantic_confirmation'] is False
        assert gap_review['governed_decision'] is False
        assert any('BCP-01' in request['requirement_ids'] for request in report['targeted_requests'])
        manifest_bytes = archive.read('manifest.json')
        assert sha256(manifest_bytes).hexdigest() == report['evidence_manifest']['sha256']
        artifact, = json.loads(manifest_bytes)['artifacts']
        assert archive.read(artifact['archive_path']) == upload.evidence.source.content
        assert artifact['sha256'] == sha256(upload.evidence.source.content).hexdigest()
        html = archive.read('summary.html').decode()
        assert escape(rationale, quote=True) in html and '<script>' not in html


@pytest.mark.parametrize('confirmation', ['omitted', False, 'true'])
def test_request_requires_explicit_confirmation_without_partial_mutation(intake, confirmation):
    model = build_assessment(intake, (policy(intake),))
    actions = ()
    completion = complete_review(model, actions)
    before = report_payload(model, actions)
    kwargs = {} if confirmation == 'omitted' else {'confirms_insufficiency': confirmation}

    with pytest.raises(ValueError):
        record_upload_review(model, actions, 'BCP-01', 'Request Evidence',
                             'Review the existing plan before requesting operating proof.', **kwargs)

    assert report_payload(model, actions) == before
    assert reviews(model) == () and actions == ()
    assert completion_is_current(model, actions, completion)


@pytest.mark.parametrize('rationale', ['', 'Invalid\x00rationale'])
def test_invalid_rationale_cannot_create_review_or_annotation(intake, rationale):
    model = build_assessment(intake, (policy(intake),))
    before = report_payload(model, ())
    with pytest.raises(ValueError):
        request_review(model, rationale=rationale)
    assert report_payload(model, ()) == before
    assert reviews(model) == ()


def test_insufficiency_review_binds_every_current_candidate_before_requesting(intake):
    first = policy(intake, 'plan-one.txt')
    second = policy(intake, 'plan-two.txt', content=(
        'Recovery policy\nService: Synthetic analytics\nEnvironment: production\n'
        'Observation date: 2026-11-15\nAlternate recovery target RTO 180 minutes.'
    ).encode())
    stale = policy(intake, 'old-plan.txt', observed_on=date(2024, 1, 1))
    model = build_assessment(intake, (first, second, stale))

    updated, actions = request_review(model)

    review, = reviews(updated)
    assert set(review.source_fingerprints) == {first.evidence.fingerprint, second.evidence.fingerprint}
    assert stale.evidence.fingerprint not in review.source_fingerprints
    assert len(requests(updated)) == 1
    assert {citation.document_id for citation in actions[0].citations} == {
        first.evidence.source.document_id, second.evidence.source.document_id, stale.evidence.source.document_id,
    }
    assert_no_assurance_or_risk_approval(updated, actions)


def test_other_review_actions_remain_annotations_and_do_not_close_needs(intake):
    original = build_assessment(intake, (policy(intake),))
    for action in ('Accept', 'Challenge', 'Create Finding'):
        updated, actions = record_upload_review(original, (), 'BCP-01', action,
                                               'Synthetic draft annotation only.')
        assert reviews(updated) == ()
        assert row(updated).need_matches == row(original).need_matches
        assert requests(updated) == ()
        assert actions[0].action == action
        assert_no_assurance_or_risk_approval(updated, actions)


@pytest.mark.parametrize('unusable', ['absent', 'stale', 'wrong-scope', 'unaccepted-kind'])
def test_unusable_or_absent_evidence_retains_gap_without_inventing_review_or_failure(intake, unusable):
    if unusable == 'unaccepted-kind':
        definition = intake.methodology.definition
        next(rule for rule in definition['requirements'] if rule['id'] == 'BCP-01')['evidence_kinds'] = ['test']
        intake = replace(intake, methodology=OrganizationMethodology.from_dict(definition))
    uploads = () if unusable == 'absent' else (policy(
        intake,
        **({'observed_on': date(2024, 1, 1)} if unusable == 'stale' else
           {'service': 'Different synthetic service'} if unusable == 'wrong-scope' else {}),
    ),)
    original = build_assessment(intake, uploads)
    assert requests(original)

    updated, actions = request_review(original)

    assert reviews(updated) == ()
    assert requests(updated) == requests(original)
    assert row(updated).outcome == 'Evidence Missing'
    assert actions[0].action == 'Request Evidence'
    assert_no_assurance_or_risk_approval(updated, actions)


@pytest.mark.parametrize('change', ['bytes', 'date', 'kind', 'routing', 'policy', 'threshold', 'intake', 'vendor', 'exposure'])
def test_changed_evidence_or_requirement_invalidates_old_gap_review_and_completion(intake, change):
    upload = policy(intake)
    original = build_assessment(intake, (upload,))
    reviewed, actions = request_review(original)
    completion = complete_review(reviewed, actions)
    revised_intake, revised_upload = intake, upload
    if change == 'bytes':
        revised_upload = policy(intake, content=upload.evidence.source.content + b'\nAdditional synthetic recovery context.')
    elif change == 'date':
        revised_upload = policy(intake, observed_on=intake.as_of - timedelta(days=4))
    elif change == 'kind':
        revised_upload = policy(intake, kind='test')
    elif change == 'routing':
        revised_upload = policy(intake, requirements=())
    elif change in ('policy', 'threshold'):
        definition = intake.methodology.definition
        if change == 'policy':
            definition['version'] = '2'
        else:
            definition['assurance']['rto_minutes'] = 60
        revised_intake = replace(intake, methodology=OrganizationMethodology.from_dict(definition))
    elif change == 'intake':
        revised_intake = replace(intake, use_case='Different synthetic business purpose')
    elif change == 'vendor':
        revised_intake = replace(intake, vendor='Another synthetic vendor')
    else:
        revised_intake = replace(intake, data_volume_records=1234)

    revised = build_assessment(revised_intake, (revised_upload,), need_reviews=reviews(reviewed))

    assert not active_actions(revised, actions)
    assert not completion_is_current(revised, actions, completion)
    assert report_payload(revised, actions)['analyst_actions'][0]['status'] == 'Stale context'
    assert report_payload(revised, actions)['evidence_gap_reviews'][0]['status'] == 'Stale context'
    assert row(revised).need_matches[0].status != 'Supported by reviewed evidence'
    if change != 'routing':
        assert row(revised).need_matches[0].status == 'Analyst validation required'
        assert not requests(revised)
    with pytest.raises(ValueError, match='context changed'):
        package_bytes(revised, actions, completion)
    assert actions[0].citations[0].quote in upload.evidence.document.segments[0].text


def test_review_rebuild_reuses_bounded_sources_and_preserves_unrelated_tls_annotation(intake, monkeypatch):
    import src.evidence_source_validation as source_validation

    dr = policy(intake)
    tls = read_upload(intake, 'tls.txt', (
        'Configuration export\nService: Synthetic analytics\nEnvironment: production\n'
        'Observation date: 2026-11-15\nListener 443: TLS 1.0 is enabled.'
    ).encode(), ('ENC-01',), kind='configuration', observed_on=date(2026, 11, 15))
    original = build_assessment(intake, (dr, tls))
    prior_actions = record_action(original, (), 'ENC-01', 'Create Finding',
                                 'Validate the cited production listener.')
    original_fact = row(original, 'ENC-01').review.facts[0]

    def forbidden(*args, **kwargs):
        raise AssertionError('Review/rebuild reparsed retained untrusted original bytes.')

    monkeypatch.setattr(source_validation, 'read_evidence_document', forbidden)
    updated, actions = request_review(original, prior_actions)
    completed = complete_review(updated, actions)
    package_bytes(updated, actions, completed)

    assert prior_actions[0] in active_actions(updated, actions)
    assert row(updated, 'ENC-01').review.facts[0] == original_fact
    assert len(reviews(updated)) == 1 and requests(updated)
    assert_no_assurance_or_risk_approval(updated, actions)
