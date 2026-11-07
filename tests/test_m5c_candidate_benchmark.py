"""Opt-in candidate rubric; frozen v1.1 remains the default historical baseline.

No extractor changes. Qualified source meaning and exact-metric eligibility are
separate from targeted manual-review attention, which is not yet instrumented.
"""
from copy import deepcopy
from datetime import date
from hashlib import sha256
import json
import os
from pathlib import Path

import pytest

from src.upload_assessment import Intake
from test_m5c_benchmark import CORPUS_PATH, _score, _rate

ROOT = Path(__file__).resolve().parents[1]
PROPOSAL = ROOT / 'benchmarks/proposals/m5c_gold_1_2_proposal.json'
VERSION = 'M5C-candidate-rubric-1.2'
NARRATIVE = 'dr-failover-narrative'


def candidate_corpus(raw, proposal):
    """Apply the accepted qualifications to an in-memory copy, never the file."""
    if sha256(raw).hexdigest() != proposal['parent']['sha256']:
        raise ValueError('Candidate parent hash differs from frozen v1.1.')
    corpus = json.loads(raw)
    if (corpus['version'] != 'M5C-holdout-1.1'
            or proposal['version'] != 'M5C-gold-correction-1.2-proposal'
            or proposal['status'] != 'proposed_not_active'):
        raise ValueError('Expected frozen v1.1 and an inactive correction proposal.')
    cases = deepcopy(corpus['cases'])
    case = next(c for c in cases if c['id'] == proposal['case_id'])
    if sha256(case['source'].encode()).hexdigest() != proposal['source_text_sha256']:
        raise ValueError('Qualified source hash mismatch.')
    if case['id'] != NARRATIVE:
        raise ValueError('This candidate rubric covers only the accepted narrative correction.')
    replacement = proposal['annotation_replacement_if_adopted']
    case['gold'] = deepcopy(replacement['gold'])
    # Explicit candidate-only rubric: source attention is not a demand for an
    # exact numerical adverse comparison. Never feed legacy exception scoring
    # a manual-review case as though its metric semantics were established.
    case['attention'] = 'manual_interpretation'
    case['reason'] = replacement['attention_basis']
    case['qualified_source_assertions'] = deepcopy(replacement['qualified_source_assertions'])
    return corpus['assessment'], cases


def qualified_metric_review(evaluation):
    """Exact achieved metrics in this source need the accepted unresolved mapping.

    Record all point-metric proposals, including ineligible ones. Eligible adverse
    point comparisons are a separate overclaim; neither is hidden as a true match.
    This score does not claim that a generic Needs Review is a targeted signal.
    """
    exact = [f for f in evaluation['facts'] if f['dimension'] in
             ('achieved_rto_minutes', 'achieved_rpo_minutes')]
    return {
        'unsupported_exact_metric_proposals': [
            {k: f[k] for k in ('dimension', 'value', 'subject', 'quote')}
            for f in exact
        ],
        'eligible_exact_metric_comparisons': sum(bool(f['eligible_for_preview']) for f in exact),
        'eligible_adverse_overclaim': any(f['eligible_for_preview'] and f['direction'] == 'adverse' for f in exact),
        'targeted_manual_signal_measured': False,
        'targeted_manual_signal_surfaced': None,
        'note': 'A source-visible manual worklist or generic request is not proof of a targeted source-cited signal. No separate signal contract is instrumented yet.',
    }


def candidate_benchmark():
    raw = CORPUS_PATH.read_bytes()
    proposal_bytes = PROPOSAL.read_bytes()
    proposal = json.loads(proposal_bytes)
    config, cases = candidate_corpus(raw, proposal)
    intake = Intake('m5c-candidate-1-2', config['vendor'], config['service'],
                    'Synthetic candidate rubric only', environment=config['environment'],
                    as_of=date.fromisoformat(config['as_of']))
    details = []
    for case in cases:
        row = _score(case, intake, include_evaluation=True)
        evaluation = row.pop('evaluation')
        if case['attention'] == 'manual_interpretation':
            row['needs_human_interpretation'] = True
            row['qualified_metric_review'] = qualified_metric_review(evaluation)
            row['qualified_source_assertions'] = case['qualified_source_assertions']
        details.append(row)
    technical = [r for r in details if r['expected_attention'] == 'exception']
    manual = [r for r in details if r['expected_attention'] == 'manual_interpretation']
    benign = [r for r in details if r['expected_attention'] == 'no_exception']
    abstain = [r for r in details if r['expected_attention'] == 'abstain']
    matched = sum(r['fact_matches'] for r in details)
    gold = sum(r['gold_facts'] for r in details)
    predicted = sum(r['typed_predicted'] for r in details)
    return {'summary': {
        'version': VERSION, 'status': 'candidate_not_active',
        'frozen_parent_version': proposal['parent']['version'],
        'frozen_parent_sha256': sha256(raw).hexdigest(),
        'proposal_sha256': sha256(proposal_bytes).hexdigest(),
        'as_of': config['as_of'], 'case_count': len(details),
        'human_tprm_validation_complete': False,
        'interpretation_limit': 'Owner accepted two narrative qualifications only. This is an exposed synthetic rubric candidate, not an external blind study or an adopted baseline.',
        'comparison_warning': 'Changed annotations/denominators, unchanged extraction. Differences from v1.1 are not model improvement or vendor-evidence accuracy.',
        'typed_facts': {'matched_count': matched, 'gold_count': gold,
                        'predicted_count': predicted, 'missed_count': gold-matched,
                        'extra_count': predicted-matched,
                        'recall_against_candidate_annotations': _rate(matched, gold),
                        'precision_against_candidate_annotations': _rate(matched, predicted)},
        'technical_exception_triage': {
            'cases': len(technical), 'surfaced': sum(r['eligible_adverse'] for r in technical),
            'missed_ids': [r['id'] for r in technical if not r['eligible_adverse']],
            'case_recall_against_candidate_labels': _rate(sum(r['eligible_adverse'] for r in technical), len(technical)),
        },
        'manual_interpretation': {
            'cases': len(manual), 'ids': [r['id'] for r in manual],
            'eligible_metric_overclaim_cases': sum(r['qualified_metric_review']['eligible_adverse_overclaim'] for r in manual),
            'unsupported_point_proposals': sum(len(r['qualified_metric_review']['unsupported_exact_metric_proposals']) for r in manual),
            'targeted_signal_surfaced_count': None,
            'targeted_signal_measurement': 'Not instrumented; do not credit generic Needs Review as material signal recall.',
        },
        'no_exception': {'cases': len(benign), 'eligible_adverse_overclaims': sum(r['eligible_adverse'] for r in benign)},
        'abstain': {'cases': len(abstain), 'eligible_adverse_overclaims': sum(r['eligible_adverse'] for r in abstain)},
        'human_effort_metrics': None,
    }, 'cases': details}


def test_candidate_runs_separately_without_mutating_frozen_source():
    before = CORPUS_PATH.read_bytes()
    report = candidate_benchmark()
    assert CORPUS_PATH.read_bytes() == before
    assert report['summary']['status'] == 'candidate_not_active'
    assert report['summary']['case_count'] == 16
    assert report['summary']['manual_interpretation']['cases'] == 1
    assert report['summary']['manual_interpretation']['targeted_signal_surfaced_count'] is None
    # The correction changes what is exact, not whether the extractor improved.
    assert report['summary']['typed_facts']['gold_count'] == 27
    narrative = next(r for r in report['cases'] if r['id'] == NARRATIVE)
    assert narrative['needs_human_interpretation'] is True
    assert narrative['adverse_case_missed'] is False
    output = json.dumps(report, indent=2, sort_keys=True)
    if os.environ.get('M5C_CANDIDATE_REPORT_PATH'):
        Path(os.environ['M5C_CANDIDATE_REPORT_PATH']).write_text(output+'\n')
    print(output)


def test_candidate_preserves_every_other_case_and_only_qualifies_accepted_case():
    raw = CORPUS_PATH.read_bytes(); original = json.loads(raw)
    proposal = json.loads(PROPOSAL.read_text())
    _, cases = candidate_corpus(raw, proposal)
    for old, new in zip(original['cases'], cases, strict=True):
        if old['id'] != NARRATIVE:
            assert new == old
        else:
            assert new['source'] == old['source']
            assert new['gold'] == [g for g in old['gold'] if g['dimension']=='completed']
            assert new['attention'] == 'manual_interpretation'
            assert new['qualified_source_assertions'][1]['operator'] == '<='
    assert proposal == json.loads(PROPOSAL.read_text())


@pytest.mark.parametrize('target', ['parent', 'source'])
def test_candidate_rejects_stale_hashes(target):
    raw = CORPUS_PATH.read_bytes(); proposal = json.loads(PROPOSAL.read_text())
    if target == 'parent': raw += b' '
    else: proposal['source_text_sha256'] = '0'*64
    with pytest.raises(ValueError, match='hash'):
        candidate_corpus(raw, proposal)


@pytest.mark.parametrize('dimension,value', [('achieved_rto_minutes',300), ('achieved_rpo_minutes',90)])
@pytest.mark.parametrize('eligible', [True,False])
def test_qualified_number_is_not_a_correct_exact_metric(dimension,value,eligible):
    result = qualified_metric_review({'facts':[{
        'dimension':dimension,'value':value,'subject':'exercise for orion ledger gateway',
        'quote':'Switching the service took five hours, with up to ninety minutes of data loss.',
        'eligible_for_preview':eligible,'direction':'adverse',
    }]})
    assert len(result['unsupported_exact_metric_proposals']) == 1
    assert result['eligible_adverse_overclaim'] is eligible
    assert result['eligible_exact_metric_comparisons'] == int(eligible)
    assert result['targeted_manual_signal_surfaced'] is None
