"""Dataset scope must influence the existing sensitivity/tiering policy safely."""
from dataclasses import replace
from io import BytesIO
import json
from zipfile import ZipFile

import pytest

from src.upload_assessment import Intake, build_assessment, data_scope, risk_and_applicability
from src.guided_assessment_demo import complete_review, package_bytes, record_action, row_fingerprint


def intake(**values):
    return Intake('scope-test', 'Synthetic Vendor', 'Synthetic Portal', 'Synthetic processing', **values)


@pytest.mark.parametrize('category,points', [
    ('Public data', 5), ('Internal business data', 5), ('Confidential business data', 10),
    ('Personal data (PII)', 15), ('Sensitive personal data', 20),
    ('Health data (PHI)', 25), ('Payment card data (PCI)', 25),
    ('Authentication credentials', 25), ('Financial records', 10),
])
def test_existing_classification_weights_and_declared_floor(category, points):
    context = intake(data='Public', data_types=(category,))
    score, factors, _ = risk_and_applicability(context)
    assert factors[0] == points
    assert score == points + 16 + 15
    higher = replace(context, data='Restricted')
    assert risk_and_applicability(higher)[1][0] == max(points, 20)


def test_highest_category_not_sum_changes_tier_and_existing_applicability():
    baseline = build_assessment(intake(data_types=('Confidential business data',)))
    health = intake(data_types=('Personal data (PII)', 'Health data (PHI)', 'Financial records'))
    model = build_assessment(health)
    assert baseline.inherent_score == 41 and baseline.inherent_tier == 'Tier 3 — Moderate'
    assert model.inherent_score == 56 and model.inherent_tier == 'Tier 2 — High'
    assert 'REG-01' in {r.requirement_id for r in model.worklist.rows}
    assert not any(r.requirement_id == 'REG-01' for r in baseline.worklist.rows)
    assert data_scope(health)['effective_sensitivity_points'] == 25
    assert data_scope(health)['regulated_data_review'] is True
    assert replace(health, data_types=tuple(reversed(health.data_types))) == health


@pytest.mark.parametrize('types', [('Unknown',), ('Other / not yet classified',), ('Public data', 'Unknown'), ('Health data (PHI)', 'Unknown')])
def test_unknown_scope_stays_explicit_without_erasing_known_exposure(types):
    context = intake(data='Public', data_types=types)
    model = build_assessment(context)
    scope = model.customer_context['data_scope']
    assert scope['uncertainties']
    assert scope['effective_sensitivity_points'] == (25 if 'Health data (PHI)' in types else 5)
    assert any('provisional' in d for d in model.risk_drivers)
    assert 'DATA-01' in {r.requirement_id for r in model.worklist.rows}
    applicability = risk_and_applicability(context)[2]
    assert applicability.review_required
    assert any(d.rule_id == 'INTAKE-DATA-UNKNOWN' for d in applicability.decisions)
    if scope['effective_sensitivity_points'] < 10:
        assert not any(d.rule_id == 'AP-001' and d.applies for d in applicability.decisions)
    with ZipFile(BytesIO(package_bytes(model, (), complete_review(model, ())))) as archive:
        report = json.loads(archive.read('report.json'))
        html = archive.read('summary.html').decode()
        assert report['assessment_context']['data_scope'] == scope
        assert 'Data types are not fully classified' in html
        assert report['risk']['residual_score'] is None
        assert report['review_completion']['vendor_approved'] is False


@pytest.mark.parametrize('types', [(), [], ('invented',), ('Unknown', 'Unknown'), (None,), ('<script>',), 'Public data'])
def test_invalid_or_empty_data_scope_rejected(types):
    with pytest.raises(ValueError, match='data types'):
        intake(data_types=types)


def test_changed_scope_stales_review_and_export_retains_exact_selected_types():
    # Equal scoring data types still change the review context fingerprint.
    first = build_assessment(intake(data_types=('Health data (PHI)',)))
    second = build_assessment(intake(data_types=('Payment card data (PCI)',)))
    row = next(r for r in first.worklist.rows if r.requirement_id == 'ENC-01')
    row2 = next(r for r in second.worklist.rows if r.requirement_id == 'ENC-01')
    assert first.inherent_score == second.inherent_score
    assert row_fingerprint(first, row) != row_fingerprint(second, row2)
    history = record_action(first, (), 'ENC-01', 'Create Finding', 'Synthetic evidence gap review.')
    with ZipFile(BytesIO(package_bytes(second, history, complete_review(second, history)))) as archive:
        report = json.loads(archive.read('report.json'))
        assert report['findings'][0]['context_status'].startswith('Stale')
        assert not report['findings'][0]['resolved']
        assert 'Payment card data (PCI)' in archive.read('summary.html').decode()
        assert report['risk']['residual_score'] is None
