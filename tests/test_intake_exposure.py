"""Relationship tiering uses all requested exposure factors, not data type alone."""
from dataclasses import replace
from io import BytesIO
import json
from zipfile import ZipFile

import pytest
from src.upload_assessment import Intake, build_assessment, risk_and_applicability, exposure_scope
from src.guided_assessment_demo import complete_review, completion_is_current, package_bytes, record_action


def base(**changes):
    context = Intake('exposure-test', 'Synthetic Vendor', 'Synthetic Portal', 'Synthetic processing',
        data_types=('Confidential business data',), access='None', criticality='Limited',
        network_access='None', data_volume_records=0, service_dependency='No operational dependency')
    return replace(context, **changes)


@pytest.mark.parametrize('change,score,tier', [
    ({}, 15, 'Tier 4 — Low'),
    ({'access':'Production'}, 31, 'Tier 3 — Moderate'),
    ({'network_access':'Network connectivity'}, 27, 'Tier 3 — Moderate'),
    ({'data_volume_records':100_001}, 25, 'Tier 3 — Moderate'),
    ({'service_dependency':'Critical dependency / no viable workaround'}, 30, 'Tier 3 — Moderate'),
    ({'criticality':'Critical'}, 30, 'Tier 3 — Moderate'),
])
def test_each_factor_changes_tier_with_identical_data_types(change, score, tier):
    model = build_assessment(base(**change))
    assert model.inherent_score == score and model.inherent_tier == tier
    assert not model.customer_context['exposure_scope']['missing_inputs']
    assert model.customer_context['tier_status'].startswith('Illustrative tier')


@pytest.mark.parametrize('records,points', [(0,0),(1,2),(1_000,2),(1_001,5),(100_000,5),(100_001,10),(10**12,10)])
def test_volume_bands_have_explicit_units_and_boundaries(records, points):
    context = base(data_volume_records=records)
    scope = exposure_scope(context)
    assert scope['data_volume_points'] == points
    assert scope['data_volume_unit'] == 'records in the assessed use case'
    assert risk_and_applicability(context)[1][3] == points


def test_access_and_dependency_use_maximum_not_double_counting_and_drive_requirements():
    context = base(data_types=('Health data (PHI)',), access='Privileged', network_access='Network connectivity',
                   criticality='Critical', service_dependency='Critical dependency / no viable workaround', data_volume_records=100_001)
    score, points, applicability = risk_and_applicability(context)
    assert points[:4] == (25,25,20,10) and score == 80
    assert build_assessment(context).inherent_tier == 'Tier 1 — Critical'
    known = base(network_access='Network connectivity', service_dependency='Critical dependency / no viable workaround')
    applicable = risk_and_applicability(known)[2]
    ids = {c.control_id for c in applicable.controls}
    assert 'IAM-01' in ids and 'BCP-01' in ids
    # Connectivity/system access never asserts public internet exposure.
    assert not any(d.rule_id == 'AP-005' and d.applies and 'internet' in d.reason.lower() for d in applicable.decisions)


@pytest.mark.parametrize('field', ['access','network_access','criticality','service_dependency','data_volume_records'])
def test_unknown_is_recorded_as_missing_not_a_known_zero_or_removed_review(field):
    value = None if field == 'data_volume_records' else 'Unknown'
    context = base(**{field:value})
    model = build_assessment(context)
    scope = model.customer_context['exposure_scope']
    assert scope['missing_inputs'] and scope['uncertainties']
    assert model.customer_context['tier_status'].startswith('Provisional')
    assert any('known-input subtotal' in driver for driver in model.risk_drivers)
    _, _, applicable = risk_and_applicability(context)
    assert applicable.review_required
    expected = 'IAM-01' if field in ('access','network_access') else 'DATA-01' if field == 'data_volume_records' else 'BCP-01'
    assert expected in {r.requirement_id for r in model.worklist.rows}
    if field == 'data_volume_records':
        assert scope['data_volume_points'] is None
        assert any('Data volume: unassessed' in d for d in model.risk_drivers)
    if field == 'network_access': assert scope['network_access_points'] is None


@pytest.mark.parametrize('field,value', [
    ('data_volume_records',-1),('data_volume_records',True),('data_volume_records',1.5),
    ('data_volume_records',10**12+1),('data_volume_records','1000'),
    ('network_access',[]),('access',{}),('criticality','invented'),('service_dependency','invented'),
])
def test_invalid_exposure_inputs_fail_before_assessment(field, value):
    with pytest.raises(ValueError): base(**{field:value})


def test_exposure_changes_invalidate_completion_and_keep_prior_findings():
    first = build_assessment(base())
    history = record_action(first, (), 'GOV-01', 'Create Finding', 'Synthetic follow-up preserved.')
    completion = complete_review(first, history)
    # A record-count change within the same scoring band still changes context.
    second = build_assessment(base(data_volume_records=1))
    third = build_assessment(base(data_volume_records=999))
    assert second.inherent_score == third.inherent_score
    assert not completion_is_current(second, history, completion)
    assert not completion_is_current(third, (), complete_review(second, ()))
    with ZipFile(BytesIO(package_bytes(third, history, complete_review(third, history)))) as z:
        report = json.loads(z.read('report.json'))
        scope = report['assessment_context']['exposure_scope']
        assert scope['data_volume_records'] == 999
        assert scope['network_access'] == 'None'
        assert scope['service_dependency'] == 'No operational dependency'
        assert report['findings'][0]['context_status'].startswith('Stale')
        assert not report['findings'][0]['resolved']
        assert report['risk']['residual_score'] is None and not report['review_completion']['vendor_approved']
        assert '999 records' in z.read('summary.html').decode()
