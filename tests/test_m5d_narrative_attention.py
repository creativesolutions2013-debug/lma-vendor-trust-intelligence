"""Supplemental review visibility only; frozen M5C labels/scoring stay unchanged."""
from datetime import date
import json
import os
from pathlib import Path

from src.upload_assessment import Intake, read_upload, build_assessment
from src.evidence_source_validation import segment_id
from test_m5c_benchmark import CORPUS_PATH, _case_bytes, benchmark


def test_supplemental_narrative_review_visibility_preserves_source_and_confirmation():
    corpus = json.loads(CORPUS_PATH.read_text())
    config = corpus['assessment']
    intake = Intake('m5d-narrative-attention', config['vendor'], config['service'],
                    'Synthetic manual attention measurement', environment=config['environment'],
                    as_of=date.fromisoformat(config['as_of']))
    cases = []
    for case in corpus['cases']:
        bound = read_upload(intake, case['id'] + '.' + case['format'], _case_bytes(case), (case['family'],),
                            kind=case['kind'], observed_on=date.fromisoformat(case['observed_on']),
                            service=case['service'], environment=case['environment'])
        model = build_assessment(intake, (bound,))
        evaluation = next(e for e in model.customer_context['evaluations'] if e['requirement_id'] == case['family'])
        alerts = evaluation['review_alerts']
        for alert in alerts:
            assert not alert['confirmed'] and not alert['authoritative']
            assert alert['document_id'] == bound.evidence.source.document_id
            assert alert['source_fingerprint'] == bound.evidence.fingerprint
            assert any(alert['source_id'] == segment_id(bound.evidence.source.document_id, n)
                       and alert['quote'] in segment.text and alert['location'] == segment.location
                       for n, segment in enumerate(bound.evidence.document.segments, 1))
        cases.append({'id': case['id'], 'annotation': case['attention'], 'review_alerts': alerts,
                      'current_manual_review': any(a['eligible_for_current_review'] for a in alerts)})
    # Acceptance of the requested manual visibility, not a new gold label or
    # adverse-score target: the typed benchmark must retain its narrative miss.
    target = next(c for c in cases if c['id'] == 'dr-failover-narrative')
    assert target['current_manual_review'] and len(target['review_alerts']) == 1
    frozen = benchmark()
    assert next(c for c in frozen['cases'] if c['id'] == target['id'])['adverse_case_missed']
    report = {
        'basis': 'Supplemental lexical manual-review visibility, not material exception detection, semantic accuracy or field evidence.',
        'frozen_benchmark': frozen['summary'],
        'current_manual_review_case_ids': [c['id'] for c in cases if c['current_manual_review']],
        'non_exception_or_abstain_cases_with_current_review_cues': sum(c['current_manual_review'] and c['annotation'] != 'exception' for c in cases),
        'workload_limit': 'Benign durations also alert in independent tests. Review cues do not infer magnitude, exact recovery metrics or threshold breach.',
        'cases': cases,
    }
    if os.environ.get('M5D_NARRATIVE_REPORT_PATH'):
        Path(os.environ['M5D_NARRATIVE_REPORT_PATH']).write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps(report, indent=2, sort_keys=True))
