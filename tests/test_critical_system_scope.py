"""Only critical-data-system access may contribute to the access risk score."""
from dataclasses import replace
from io import BytesIO
import json
from zipfile import ZipFile
import pytest

from src.upload_assessment import build_assessment, exposure_scope, risk_and_applicability
from src.guided_assessment_demo import complete_review, completion_is_current, package_bytes, record_action
from test_intake_exposure import base

CRITICAL = 'Hosts or processes critical data'
NONCRITICAL = 'Does not host or process critical data'


@pytest.mark.parametrize('access,points', [('Production',16),('Privileged',25)])
def test_noncritical_access_does_not_count_but_access_review_is_preserved(access, points):
    noncritical = base(access=access, system_data_criticality=NONCRITICAL)
    critical = replace(noncritical, system_data_criticality=CRITICAL)
    assert risk_and_applicability(noncritical)[1][1] == 0
    assert risk_and_applicability(critical)[1][1] == points
    assert exposure_scope(noncritical)['system_access_points'] == 0
    assert exposure_scope(noncritical)['system_access_unqualified_points'] == points
    assert build_assessment(noncritical).inherent_score == 15
    assert 'IAM-01' in {r.requirement_id for r in build_assessment(noncritical).worklist.rows}


@pytest.mark.parametrize('criticality', [CRITICAL, NONCRITICAL, 'Unknown'])
def test_no_system_access_requires_no_data_criticality_qualification(criticality):
    scope = exposure_scope(base(access='None', system_data_criticality=criticality))
    assert scope['system_access_points'] == 0
    assert not scope['missing_inputs']


def test_network_access_still_counts_independently_and_unknown_is_not_known_zero():
    noncritical = base(access='Privileged', system_data_criticality=NONCRITICAL, network_access='Network connectivity')
    assert risk_and_applicability(noncritical)[1][1] == 12
    unknown = replace(noncritical, system_data_criticality='Unknown')
    scope = exposure_scope(unknown)
    assert scope['system_access_points'] is None
    assert scope['network_access_points'] == 12
    assert 'critical-system scope' in scope['missing_inputs']
    assert build_assessment(unknown).customer_context['tier_status'].startswith('Provisional')
    assert risk_and_applicability(unknown)[2].review_required
    # Even a noncritical system doesn't turn an unknown access level into a known fact.
    assert 'system access' in exposure_scope(replace(noncritical, access='Unknown'))['missing_inputs']


@pytest.mark.parametrize('value', ['', None, [], True, 'invented'])
def test_invalid_qualification_rejected(value):
    with pytest.raises(ValueError): base(system_data_criticality=value)


def test_qualification_change_stales_history_even_when_network_masks_score_difference():
    first = build_assessment(base(access='Production', network_access='Network connectivity', system_data_criticality=NONCRITICAL))
    # Changing only the qualification from noncritical to unknown leaves network at 12.
    second = build_assessment(base(access='Production', network_access='Network connectivity', system_data_criticality='Unknown'))
    assert first.inherent_score == second.inherent_score
    history = record_action(first, (), 'GOV-01', 'Create Finding', 'Preserve synthetic review history.')
    completion = complete_review(first, history)
    assert not completion_is_current(second, history, completion)
    with ZipFile(BytesIO(package_bytes(second, history, complete_review(second, history)))) as z:
        report = json.loads(z.read('report.json'))
        scope = report['assessment_context']['exposure_scope']
        assert scope['system_data_criticality'] == 'Unknown'
        assert scope['system_access_points'] is None and scope['network_access_points'] == 12
        assert scope['policy'] == 'INTAKE-EXPOSURE-PILOT-2'
        assert report['findings'][0]['context_status'].startswith('Stale')
        assert not report['findings'][0]['resolved']
        assert 'critical-data scope: Unknown' in z.read('summary.html').decode()
        assert report['risk']['residual_score'] is None and not report['review_completion']['vendor_approved']
