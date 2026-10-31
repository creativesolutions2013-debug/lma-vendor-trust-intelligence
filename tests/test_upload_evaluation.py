"""Real synthetic uploaded sources, not prefilled/confirmed assurance facts."""
from dataclasses import replace
from datetime import date
from hashlib import sha256
from io import BytesIO
import json
from zipfile import ZipFile

import pytest

from src.upload_assessment import Intake, read_upload, build_assessment
from src.guided_assessment_demo import record_action, complete_review, completion_is_current, package_bytes, report_payload
from src.tls_assurance import TlsThreshold
from src.dr_assurance import DrThreshold
from test_upload_assessment import pdf_bytes, docx_bytes

@pytest.fixture
def intake():
    return Intake('m5b-case', 'Cedarline Synthetic', 'Cedarline Analytics', 'Synthetic reporting', as_of=date(2026,10,30))


def source_text(intake, body, family='ENC-01', **changes):
    context = {'service': intake.service, 'environment': intake.environment, 'date': '2026-10-20',
               'type': 'Configuration export' if family=='ENC-01' else 'DR exercise results'}
    context.update(changes)
    return f"{context['type']}\nService: {context['service']}\nEnvironment: {context['environment']}\nTest date: {context['date']}\n{body}"


def upload(intake, body, family='ENC-01', fmt='txt', **changes):
    text = source_text(intake, body, family, **changes)
    content = text.encode() if fmt=='txt' else docx_bytes(text) if fmt=='docx' else pdf_bytes(text.replace('\n', ') Tj 0 -14 Td ('))
    return read_upload(intake, 'independent.'+fmt, content, (family,),
                       kind='configuration' if family=='ENC-01' else 'test', observed_on=date(2026,10,20))


def evaluation(model, family='ENC-01'):
    return next(x for x in model.customer_context['evaluations'] if x['requirement_id']==family)


@pytest.mark.parametrize('fmt', ['txt','pdf','docx'])
@pytest.mark.parametrize('family,body,expected', [
    ('ENC-01', 'Primary listener 443: TLS 1.2 is enabled.\nAlternate production listener 9443: TLS 1.0 is enabled.', ('enabled_version',10)),
    ('BCP-01', 'Recovery exercise completed.\nAchieved RTO 300 minutes and RPO 90 minutes.\nIdentity provider was excluded from the exercise.', ('achieved_rto_minutes',300)),
])
def test_real_upload_exception_candidates_exact_quotes_and_export(intake, fmt, family, body, expected):
    bound = upload(intake,body,family,fmt)
    model = build_assessment(intake,(bound,))
    result = evaluation(model,family)
    assert result['status']=='Unverified threshold concern'
    assert any((f['dimension'],f['value'])==expected and f['direction']=='adverse' for f in result['facts'])
    assert result['preview']['outcome_if_confirmed']=='Risk Identified'
    if family=='ENC-01': assert any(f['subject']=='listener 9443' and f['value']==10 for f in result['facts'])
    else: assert any(f['dimension']=='scope_complete' and f['value'] is False and 'Identity provider' in f['quote'] for f in result['facts'])
    for fact in result['facts']:
        assert not fact['confirmed']
        segment = bound.evidence.document.segments[int(fact['source_id'].rsplit(':',1)[1])-1]
        assert fact['location']==segment.location and fact['quote'] in segment.text
        assert fact['source_fingerprint']==bound.evidence.fingerprint
    assert all(r.outcome not in ('Met','Partially Met','Risk Identified') for r in model.worklist.rows)
    assert all(not f.confirmed for r in model.worklist.rows for f in r.review.facts)
    history = record_action(model,(),family,'Create Finding','Validate the cited technical exception.')
    completed = complete_review(model,history)
    with ZipFile(BytesIO(package_bytes(model,history,completed))) as archive:
        report = json.loads(archive.read('report.json'))
        item = json.loads(archive.read('manifest.json'))['artifacts'][0]
        assert archive.read(item['archive_path'])==bound.evidence.source.content
        assert sha256(archive.read(item['archive_path'])).hexdigest()==item['sha256']
        assert report['risk']['residual_score'] is None and not report['review_completion']['vendor_approved']
        assert report['assessment_context']['evaluations']==model.customer_context['evaluations']
        assert b'Unconfirmed source-cited threshold comparisons' in archive.read('summary.html')


@pytest.mark.parametrize('body', [
    'Listener 443: TLS 1.0 is disabled; TLS 1.2 is enabled.',
    'Listener 443: TLS 1.0 is rejected; TLS 1.1 is blocked; TLS 1.2 is enabled.',
    'We use TLS 1.2.', 'TLS 1.0 may be enabled.',
])
def test_disabled_or_ambiguous_tls_never_becomes_current_failure_or_pass(intake, body):
    result = evaluation(build_assessment(intake,(upload(intake,body),)))
    assert result['preview']['outcome_if_confirmed'] not in ('Met','Risk Identified')
    if 'disabled' in body or 'rejected' in body:
        assert not any(f['direction']=='adverse' for f in result['facts'])
    else: assert any(f['uncertainties'] for f in result['facts'])


def test_customer_threshold_rules_and_conflicts_are_reused(intake):
    uploaded = upload(intake,'Listener 8443: TLS 1.2 is enabled.')
    assert not any(f['direction']=='adverse' for f in evaluation(build_assessment(intake,(uploaded,)))['facts'])
    strict = evaluation(build_assessment(intake,(uploaded,),tls_threshold=TlsThreshold(13)))
    assert any(f['direction']=='adverse' for f in strict['facts'])
    contrary = upload(intake,'Listener 8443: TLS 1.0 is enabled.\nListener 8443: TLS 1.0 is disabled.')
    assert evaluation(build_assessment(intake,(contrary,)))['preview']['conflicts']
    both = upload(intake,'Listener 8443: TLS 1.0 and TLS 1.2 are enabled.')
    assert any(f['direction']=='adverse' and f['value']==10 for f in evaluation(build_assessment(intake,(both,)))['facts'])


@pytest.mark.parametrize('change,needle', [
    ({'date':'2024-01-01'}, 'date'), ({'date':'2030-01-01'}, 'date'), ({'date':'unknown'}, 'date'),
    ({'service':'Another service'}, 'service'), ({'environment':'test'}, 'environment'),
    ({'type':'Vendor policy'}, 'type'),
])
@pytest.mark.parametrize('family,body', [('ENC-01','Listener 9443: TLS 1.0 is enabled.'),('BCP-01','Completed recovery exercise. Achieved RTO 300 minutes and RPO 90 minutes.')])
def test_source_metadata_discrepancies_block_current_preview(intake, change, needle, family, body):
    result = evaluation(build_assessment(intake,(upload(intake,body,family,**change),)),family)
    assert any(needle in s.lower() for x in result['sources'] for s in x['uncertainties'])
    assert all(not f['eligible_for_preview'] for f in result['facts'])
    assert result['preview']['outcome_if_confirmed'] not in ('Met','Risk Identified')


@pytest.mark.parametrize('body,kind', [
    ('Plan objectives: RTO 300 minutes and RPO 90 minutes.','Recovery plan'),
    ('Achieved RTO 300 and RPO 90.','DR exercise results'),
    ('Target RTO 300 minutes and target RPO 90 minutes.','DR exercise results'),
    ('RTO was not achieved: 300 minutes.','DR exercise results'),
])
def test_dr_plans_targets_missing_units_and_negation_are_not_achieved_metrics(intake,body,kind):
    result = evaluation(build_assessment(intake,(upload(intake,body,'BCP-01',type=kind),)),'BCP-01')
    assert not any(f['dimension'].startswith('achieved_') for f in result['facts'])
    assert result['preview']['outcome_if_confirmed'] not in ('Met','Risk Identified')


def test_dr_units_thresholds_exclusions_and_no_complete_scope_inference(intake):
    source = upload(intake,'Completed recovery exercise.\nAchieved RTO 1.5 hours and RPO 0.5 hours.\nIdentity service was excluded.','BCP-01')
    model = build_assessment(intake,(source,))
    facts=evaluation(model,'BCP-01')['facts']
    assert {f['value'] for f in facts if f['dimension'].startswith('achieved_')}=={90,30}
    assert any(f['dimension']=='scope_complete' and f['direction']=='adverse' for f in facts)
    strict=build_assessment(intake,(source,),dr_threshold=DrThreshold(90,60,5))
    assert len([f for f in evaluation(strict,'BCP-01')['facts'] if f['dimension'].startswith('achieved_') and f['direction']=='adverse'])==2
    assert all(f['subject']!='complete scope' for f in facts)


def test_unrelated_sources_and_all_other_requirements_remain_visible(intake):
    source=upload(intake,'Synthetic lunch menu.')
    model=build_assessment(intake,(source,))
    assert not evaluation(model)['facts']
    assert len(model.worklist.rows)>2
    assert all(r.outcome!='Met' for r in model.worklist.rows)


def test_reclassification_reupload_threshold_change_and_challenge_preserve_history(intake):
    source=upload(intake,'Listener 9443: TLS 1.0 is enabled.')
    model=build_assessment(intake,(source,))
    history=record_action(model,(),'ENC-01','Create Finding','Validate the noncompliant listener.')
    completion=complete_review(model,history)
    changed=read_upload(intake,source.evidence.source.filename,source.evidence.source.content,('ENC-01',),kind='policy',observed_on=date(2026,10,21))
    for updated in (build_assessment(intake,(changed,)),build_assessment(intake,(source,),tls_threshold=TlsThreshold(13))):
        assert not completion_is_current(updated,history,completion)
        assert report_payload(updated,history)['findings'][0]['context_status'].startswith('Stale')
    challenged=record_action(model,history,'ENC-01','Challenge','The endpoint scope needs validation.')
    assert not completion_is_current(model,challenged,completion)
    assert all(not f['confirmed'] for f in evaluation(model)['facts'])


def test_no_parser_calls_during_candidate_extraction_worklist_review_or_export(intake,monkeypatch):
    import src.evidence_source_validation as bindings
    import src.bounded_document_parser as parser
    source=upload(intake,'Listener 9443: TLS 1.0 is enabled.',fmt='pdf')
    def forbidden(*args,**kwargs): raise AssertionError('Unexpected parsing')
    monkeypatch.setattr(bindings,'read_evidence_document',forbidden)
    monkeypatch.setattr(parser,'read_bounded_document',forbidden)
    model=build_assessment(intake,(source,)); package_bytes(model,(),complete_review(model,()))


@pytest.mark.parametrize('phrase', ['TLS 1.0 is not allowed.', 'TLS 1.0 is not accepted.', 'TLS 1.0 is not enabled.', 'TLS 1.0 is not disabled.'])
def test_negated_tls_states_are_not_inverted(intake,phrase):
    result=evaluation(build_assessment(intake,(upload(intake,'Listener 9443: '+phrase),)))
    assert result['preview']['outcome_if_confirmed']!='Risk Identified'
    assert not any(f['dimension']=='enabled_version' for f in result['facts'])


def test_candidate_budget_exhaustion_is_explicit_and_never_a_complete_preview(intake):
    source=upload(intake,'\n'.join('Listener '+str(i)+': TLS 1.2 is enabled.' for i in range(150)))
    result=evaluation(build_assessment(intake,(source,)))
    assert len(result['facts'])==128
    assert any('incomplete:' in u for s in result['sources'] for u in s['uncertainties'])
    assert not any(f['eligible_for_preview'] for f in result['facts'])
    assert result['preview']['outcome_if_confirmed']!='Met'


def test_supported_versions_do_not_become_enabled_config_or_complete_scope(intake):
    result=evaluation(build_assessment(intake,(upload(intake,'Listener 443 supports TLS 1.0 and TLS 1.2.'),)))
    assert all(f['dimension']=='reported_versions' for f in result['facts'])
    assert result['preview']['outcome_if_confirmed']=='Evidence Missing'


def test_tls_supported_clause_is_not_promoted_by_neighbor_enabled_clause(intake):
    result=evaluation(build_assessment(intake,(upload(intake,'Listener 443 supports TLS 1.0; TLS 1.2 is enabled.'),)))
    assert not any(f['dimension']=='enabled_version' and f['value']==10 for f in result['facts'])
    assert result['preview']['outcome_if_confirmed']!='Risk Identified'


def test_dr_metric_scope_conflict_remains_unconfirmed_and_ineligible(intake):
    result=evaluation(build_assessment(intake,(upload(intake,'Achieved RTO 300 minutes and RPO 90 minutes for the test environment.','BCP-01'),)),'BCP-01')
    assert result['facts'] and all(not f['eligible_for_preview'] for f in result['facts'])
    assert result['preview']['outcome_if_confirmed']!='Risk Identified'


@pytest.mark.parametrize('body', [
    'Achieved RTO 4 hours 30 minutes and RPO 1 hour 30 minutes.',
    'Achieved RTO 4 hours and 30 minutes; achieved RPO 1 hour and 30 minutes.',
    'Achieved RTO 4 hours, 30 minutes; actual RPO 1 hour, 30 minutes.',
    'Achieved RTO 4 hours plus 30 minutes; actual RPO 1 hour plus 30 minutes.',
    'Achieved RTO 4 hours (30 minutes extra); actual RPO 1 hour (30 minutes extra).',
    'Achieved RTO 4 hours and a half; actual RPO 1 hour and a half.',
])
def test_compound_dr_durations_never_compare_only_the_first_component(intake,body):
    result=evaluation(build_assessment(intake,(upload(intake,body,'BCP-01'),)),'BCP-01')
    assert result['facts'] and all(f['dimension']=='unresolved_metric' for f in result['facts'])
    assert not any(f['eligible_for_preview'] for f in result['facts'])


@pytest.mark.parametrize('body', [
    'Listener 443: TLS 1.0 is supported; logging is enabled.',
    'Listener 443: TLS 1.0 is supported. Logging is enabled.',
    'Listener 443: TLS 1.0 is supported and logging is enabled.',
    'Listener 443: TLS 1.0 is never enabled.',
    "Listener 443: TLS 1.0 isn't enabled.",
    'Listener 443: TLS 1.0 is no longer enabled.',
])
def test_tls_unrelated_states_and_unhandled_negations_stay_unresolved(intake,body):
    result=evaluation(build_assessment(intake,(upload(intake,body),)))
    assert not any(f['dimension']=='enabled_version' for f in result['facts'])
    assert result['preview']['outcome_if_confirmed']!='Risk Identified'


@pytest.mark.parametrize('body', [
    'Achieved RTO 120 minutes; RPO 90 minutes was not measured.',
    'Achieved RTO 120 minutes and RPO 90 minutes was not measured.',
    'Achieved RTO 120 minutes. RPO 90 minutes was not measured.',
    'Achieved RTO 120 minutes; RPO 90 minutes.',
])
def test_dr_achievement_cannot_cross_into_unmeasured_or_separate_metric(intake,body):
    result=evaluation(build_assessment(intake,(upload(intake,body,'BCP-01'),)),'BCP-01')
    assert not any(f['dimension']=='achieved_rpo_minutes' for f in result['facts'])
    assert result['preview']['outcome_if_confirmed']!='Risk Identified'


def test_protocol_conflicts_normalize_label_but_not_case_sensitive_identity(intake):
    result=evaluation(build_assessment(intake,(upload(intake,'Listener 443: TLS 1.0 is enabled.\nlistener 443: TLS 1.0 is disabled.'),)))
    assert result['preview']['conflicts'] and result['preview']['outcome_if_confirmed']=='Needs Review'
    other=evaluation(build_assessment(intake,(upload(intake,'Endpoint HostA: TLS 1.0 is enabled.\nendpoint hosta: TLS 1.0 is disabled.'),)))
    assert {f['subject'] for f in other['facts']}=={'endpoint HostA','endpoint hosta'}


@pytest.mark.parametrize('modifier', ['or more', 'or less', 'minimum', '(rounded)'])
def test_modified_dr_duration_is_not_assumed_to_be_an_exact_scalar(intake,modifier):
    result=evaluation(build_assessment(intake,(upload(intake,'Achieved RTO 4 hours '+modifier+'.','BCP-01'),)),'BCP-01')
    assert result['facts'] and all(f['dimension']=='unresolved_metric' for f in result['facts'])
    assert not any(f['eligible_for_preview'] for f in result['facts'])


@pytest.mark.parametrize('qualifier', ['in the test environment', 'in the staging environment', 'in the development environment', 'in the sandbox environment', 'on the test endpoint'])
def test_tls_clause_local_nonproduction_qualifiers_block_production_preview(intake,qualifier):
    result=evaluation(build_assessment(intake,(upload(intake,'Listener 443: TLS 1.0 is enabled '+qualifier+'.'),)))
    assert result['facts'] and all(not f['eligible_for_preview'] for f in result['facts'])
    assert any('outside the assessed environment' in u for f in result['facts'] for u in f['uncertainties'])
    assert result['preview']['outcome_if_confirmed']!='Risk Identified'


@pytest.mark.parametrize('state', ['disabled','rejected','not enabled'])
def test_bare_tls_disabled_lists_preserve_each_protocol_and_conflict(intake,state):
    body='Listener 443: TLS 1.0 and TLS 1.1 are '+state+'.\nListener 443: TLS 1.0 is enabled.'
    result=evaluation(build_assessment(intake,(upload(intake,body),)))
    assert {f['value'] for f in result['facts'] if f['dimension']=='disabled_version'}=={10,11}
    assert result['preview']['conflicts'] and result['preview']['outcome_if_confirmed']=='Needs Review'


@pytest.mark.parametrize('body', [
    'Identity provider was excluded from the exercise in the test environment.',
    'Identity provider was excluded from the exercise in the staging environment.',
    'Recovery exercise completed in the test environment.',
    'Previously completed recovery exercise.',
    'Historical identity provider was excluded from the exercise.',
])
def test_all_dr_fact_types_inherit_scope_and_temporal_qualification(intake,body):
    result=evaluation(build_assessment(intake,(upload(intake,body,'BCP-01'),)),'BCP-01')
    assert result['facts'] and all(not f['eligible_for_preview'] for f in result['facts'])
    assert all(f['uncertainties'] for f in result['facts'])
    assert result['preview']['outcome_if_confirmed']!='Risk Identified'


@pytest.mark.parametrize('qualification', ['Historical','Previously','Formerly'])
def test_current_document_date_cannot_redate_historical_achieved_metrics(intake,qualification):
    result=evaluation(build_assessment(intake,(upload(intake,qualification+' achieved RTO 300 minutes.','BCP-01'),)),'BCP-01')
    assert result['facts'] and all(f['dimension']=='unresolved_metric' for f in result['facts'])
    assert all(not f['eligible_for_preview'] for f in result['facts'])
    assert result['preview']['outcome_if_confirmed']!='Risk Identified'
