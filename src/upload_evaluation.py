"""Bounded deterministic candidates, not document understanding or factual approval.

Read already-bound text only. Typed TLS/DR services own threshold interpretation;
this adapter supplies hypothetical unconfirmed observations, never FactReviews.
"""
from dataclasses import asdict, replace
from datetime import date
from decimal import Decimal
from itertools import islice
import re

from src.control_assurance import DomainEvaluator, Observation
from src.evidence_source_validation import segment_id
from src.tls_assurance import TlsThreshold, evaluate_tls, tls_direction, TLS_SIGNALS
from src.dr_assurance import DrThreshold, evaluate_dr, dr_direction, DR_SIGNALS

VERSION = 'M5B-candidates-2'
MAX_LINES = 2000
MAX_LINE_CHARS = 2000
MAX_FACTS = 128
LIMITATION = ('Conservative English/ISO-date candidate extraction for TLS listener configuration/scan statements '
    'and achieved DR exercise metrics only. Every fact and comparison is unconfirmed. '
    'Other controls and unsupported wording need manual review. No vendor approval, authoritative control outcome, '
    'verified scope, complete standards assurance, external AI or risk reduction.')
TLS = DomainEvaluator(VERSION, evaluate_tls, tls_direction, TLS_SIGNALS)
DR = DomainEvaluator(VERSION, evaluate_dr, dr_direction, DR_SIGNALS)


def _lines(bound):
    for ordinal, segment in enumerate(bound.document.segments, 1):
        for line in segment.text.splitlines():
            if line.strip():
                yield ordinal, segment.location, line.strip()


def _citation(bound, ordinal, location, quote):
    return dict(document_id=bound.source.document_id, source_id=segment_id(bound.source.document_id, ordinal),
                source_fingerprint=bound.fingerprint, filename=bound.document.filename, location=location, quote=quote)


def _context(bound, intake, family, age):
    scanned = list(islice(_lines(bound), MAX_LINES + 1))
    truncated = len(scanned) > MAX_LINES or any(len(r[2]) > MAX_LINE_CHARS for r in scanned)
    rows = [r for r in scanned[:MAX_LINES] if len(r[2]) <= MAX_LINE_CHARS]
    fields = {'service': [], 'environment': [], 'date': []}
    traces = []
    kinds = set()
    for ordinal, location, line in rows:
        for field, pattern in (
            ('service', r'^Service\s*:\s*(.+?)\s*[.;]?$'),
            ('environment', r'^Environment\s*:\s*(production|test)\s*[.;]?$'),
            ('date', r'^(?:Observation|Observed|Test|Exercise|Scan|Configuration)(?: date)?\s*:\s*(\d{4}-\d{2}-\d{2})\s*[.;]?$'),
        ):
            match = re.search(pattern, line, re.I)
            if match:
                value = match.group(1).strip()
                if field == 'date':
                    try: value = date.fromisoformat(value).isoformat()
                    except ValueError: value = 'invalid date: ' + value
                fields[field].append(value)
                traces.append({**_citation(bound, ordinal, location, line), 'field': field, 'value': value})
        # Source wording, not the uploader's label, must identify technical material.
        prior_kinds = set(kinds)
        if re.search(r'\b(policy|recovery plan|plan objectives?|planned exercise|proposed test)\b', line, re.I): kinds.add('policy')
        if re.search(r'\b(configuration|config export)\b', line, re.I): kinds.add('configuration')
        if re.search(r'\b(scan results?|scan report|exercise results?|test results?|completed (?:recovery |DR )?(?:exercise|test)|(?:exercise|test) (?:was )?completed)\b', line, re.I): kinds.add('test')
        for kind in kinds - prior_kinds:
            traces.append({**_citation(bound, ordinal, location, line), 'field': 'kind', 'value': kind})
    extracted = {k: values[0] if len(set(v.casefold() for v in values)) == 1 else None for k, values in fields.items()}
    extracted['kind'] = next(iter(kinds)) if len(kinds) == 1 else None
    declared = dict(service=bound.source.service, environment=bound.source.environment,
                    date=bound.source.observed_on.isoformat() if bound.source.observed_on else None,
                    kind=bound.source.evidence_kind)
    issues = (['Candidate extraction is incomplete: line/context budget exceeded; manually review the full original.']
              if truncated or len(traces) > MAX_FACTS else [])
    traces = traces[:MAX_FACTS]
    for field in ('service', 'environment', 'date', 'kind'):
        value = extracted[field]
        if value is None: issues.append('Source-stated ' + field + ' is missing or ambiguous; uploader declaration is not verification.')
        elif str(value).casefold() != str(declared[field]).casefold():
            issues.append(f'Source-stated {field} ({value}) differs from uploader declaration ({declared[field]}).')
    if extracted['service'] and extracted['service'].casefold() != intake.service.casefold(): issues.append('Source service differs from assessed service.')
    if extracted['environment'] and extracted['environment'].casefold() != intake.environment.casefold(): issues.append('Source environment differs from assessed environment.')
    try:
        observed = date.fromisoformat(extracted['date'])
    except (TypeError, ValueError):
        observed = None
    if observed is None or not 0 <= (intake.as_of-observed).days <= age:
        issues.append(f'Source-stated date is missing, invalid, future or older than {age} days.')
    acceptable = ('configuration', 'test') if family == 'ENC-01' else ('test',)
    if extracted['kind'] not in acceptable or bound.source.evidence_kind not in acceptable:
        issues.append('Policy, plan, assertion or unknown type is not technical operating proof for this requirement.')
    return rows, extracted, declared, traces, tuple(dict.fromkeys(issues)), observed


def evaluate_uploads(intake, bounds, requirement_id, threshold):
    """Return source-bound Observation candidates and a separate if-confirmed preview.

    No complete-scope coverage is inferred, including from claims of full coverage.
    This narrow extractor consequently cannot propose a whole-control Met.
    """
    evaluator = TLS if requirement_id == 'ENC-01' else DR
    observations, facts, sources, eligible = [], [], [], []
    for bound in bounds:
        rows, extracted, declared, traces, issues, observed = _context(bound, intake, requirement_id, 90 if requirement_id == 'ENC-01' else threshold.max_test_age_days)
        source_record = dict(document_id=bound.source.document_id, filename=bound.document.filename,
                             extracted=extracted, declared=declared, context_citations=traces, uncertainties=list(issues))
        sources.append(source_record)

        first_fact = len(facts)

        def add(dimension, value, ordinal, location, quote, subject, uncertainty=()):
            if len(facts) - first_fact >= MAX_FACTS:
                message = 'Candidate extraction is incomplete: fact budget exceeded; manually review the full original.'
                if message not in source_record['uncertainties']: source_record['uncertainties'].append(message)
                return
            direction_source = replace(bound.source, evidence_kind=extracted['kind'] or 'assertion', observed_on=observed)
            observation = Observation(f'{requirement_id}-{bound.source.document_id}-{len(observations)}', dimension,
                value, segment_id(bound.source.document_id, ordinal), bound.fingerprint, location, quote, subject,
                True, '')
            direction = evaluator.direction(threshold, observation, direction_source)
            observation = replace(observation, concern='potential_exception' if direction == 'adverse' else '')
            observations.append(observation)
            limitation = tuple(dict.fromkeys((*issues, *uncertainty)))
            facts.append({**asdict(observation), 'document_id': bound.source.document_id,
                          'filename': bound.document.filename, 'confirmed': False, 'direction': direction,
                          'confidence': 'explicit phrase candidate; meaning unverified', 'uncertainties': list(limitation),
                          'comparison': _comparison(observation, threshold, direction),
                          'eligible_for_preview': not limitation})
            if not limitation and (direction != 'unknown' or dimension in ('enabled_version', 'disabled_version')): eligible.append((observation, direction_source))

        for ordinal, location, line in rows:
            # Keep limitations and exclusions even when metric extraction is unavailable.
            excluded = bool(re.search(r'\b(exclud\w*|not tested|untested|incomplete)\b', line, re.I)) and not re.search(r'\b(no exclusions?|none excluded|not excluded)\b', line, re.I)
            if requirement_id == 'ENC-01':
                versions = list(re.finditer(r'\bTLS\s*v?\s*1\.([0-3])\b', line, re.I))
                if not versions: continue
                listener = re.search(r'\b(listener|endpoint)\s+([a-z0-9][a-z0-9_.:/-]*)', line, re.I)
                subject = listener.group(1).lower() + ' ' + listener.group(2).rstrip(':,.') if listener else 'unspecified endpoint'
                uncertainty = [] if listener else ['Listener/endpoint identity is missing; do not infer fleet coverage.']
                if re.search(r'\b(?:historical|previously|formerly|example|hypothetical|planned|proposed|scheduled|will|should|target|may|might|not enabled|not supported|not allowed|not accepted|not disabled|not rejected)\b', line, re.I):
                    uncertainty.append('Historical, negated, hypothetical or ambiguous statement; validate current technical meaning.')
                if re.search(r'\b(?:test|staging|development) (?:listener|endpoint)\b', line, re.I) and intake.environment == 'production':
                    uncertainty.append('Endpoint wording is outside the production environment.')
                enabled, disabled = [], []
                for i, match in enumerate(versions):
                    # Restrict verb association to this version's clause. Unknown is not enabled.
                    tail = line[match.end():versions[i+1].start() if i+1 < len(versions) else len(line)]
                    head = line[:match.start()]
                    version = 10 + int(match.group(1))
                    state = _tls_state(tail, head)
                    if state == 'disabled': disabled.append(version)
                    elif state == 'enabled': enabled.append(version)
                if len(list(re.finditer(r'\b(listener|endpoint)\s+[a-z0-9][a-z0-9_.:/-]*', line, re.I))) > 1:
                    subject = 'ambiguous endpoints'
                    uncertainty.append('Multiple endpoint identities in one clause; review protocol-to-endpoint association.')
                # Share a state only across a bare protocol list. A support-only
                # clause beside an enabled clause must not become enabled evidence.
                bare_list = all(re.fullmatch(r'[\s,]*(?:and)?[\s,]*', line[a.end():b.start()], re.I)
                                for a,b in zip(versions, versions[1:]))
                if len(versions) > 1 and bare_list and not disabled:
                    trailing = line[versions[-1].end():]
                    leading = line[:versions[0].start()]
                    if _tls_state(trailing, leading) == 'enabled':
                        enabled = [10 + int(m.group(1)) for m in versions]
                for version in enabled:
                    add('enabled_version', version, ordinal, location, line, subject, uncertainty)
                for version in disabled:
                    add('disabled_version', version, ordinal, location, line, subject, uncertainty)
                if {10,11} <= set(disabled): add('legacy_rejected', True, ordinal, location, line, subject, uncertainty)
                if not enabled and not disabled:
                    add('reported_versions', ', '.join('TLS 1.'+m.group(1) for m in versions), ordinal, location, line, subject,
                        (*uncertainty, 'Supported-version wording is not enabled configuration or operating evidence.'))
                if excluded: add('scope_complete', False, ordinal, location, line, subject, uncertainty)
            else:
                subject = 'exercise for ' + (extracted['service'] or 'unspecified service')
                line_scope = ('Metric/exercise wording identifies a non-production environment.',) if intake.environment == 'production' and re.search(r'\b(?:test|staging|development|sandbox) environment\b', line, re.I) else ()
                if excluded:
                    add('scope_complete', False, ordinal, location, line, subject,
                        () if extracted['kind'] == 'test' else ('Exclusion is not tied to a recognized actual exercise record.',))
                if re.search(r'\b(?:exercise|test) (?:was )?completed|\bcompleted (?:recovery |DR )?(?:exercise|test)', line, re.I):
                    add('completed', not bool(re.search(r'\b(?:not|never)\s+completed\b', line, re.I)), ordinal, location, line, subject)
                if not re.search(r'\b(RTO|RPO)\b', line, re.I): continue
                for dimension, value, uncertainty in _dr_metrics(line, extracted['kind']):
                    add(dimension, value, ordinal, location, line, subject, (*line_scope, *uncertainty))
        if any('incomplete:' in message for message in source_record['uncertainties']):
            for fact in facts[first_fact:]:
                fact['eligible_for_preview'] = False
                fact['uncertainties'] = list(dict.fromkeys((*fact['uncertainties'], *source_record['uncertainties'])))
            eligible = [(f,s) for f,s in eligible if s.document_id != bound.source.document_id]
    result = evaluator.evaluate(threshold, tuple(eligible), intake.as_of)
    adverse = [f for f in facts if f['direction'] == 'adverse']
    missing = [c for c in result.checks if c.status == 'missing']
    next_action = (('Validate the cited noncompliant listener and obtain its dated configuration/protocol-rejection scan.' if requirement_id == 'ENC-01' else
                   'Validate the achieved objectives and exclusions; request a corrective exercise covering excluded dependencies.') if adverse else
                  'Resolve source date/type/scope discrepancies and confirm candidate meanings; obtain missing technical coverage or operating proof.')
    return tuple(observations), evaluator, {
        'requirement_id': requirement_id, 'extractor_version': VERSION, 'threshold': threshold.describe(),
        'status': 'Unverified threshold concern' if adverse else 'Unverified evidence review',
        'authoritative': False, 'semantic_confirmation': False, 'facts': facts, 'sources': sources,
        'preview': {'basis': 'Hypothetical comparison of eligible candidates only, if individually confirmed; not a control result.',
                    'outcome_if_confirmed': result.outcome, 'conflicts': [asdict(c) for c in result.checks if c.status == 'conflict'],
                    'missing_dimensions': [c.dimension for c in missing]},
        'next_action': next_action, 'limitations': LIMITATION,
    }


def _tls_state(tail, head=''):
    """Associate a state with the protocol itself, never another feature's verb."""
    clause = re.split(r';|(?<=[.!?])\s+', tail, maxsplit=1)[0]
    if re.search(r"\b(?:never|neither|nor|cannot|without|no longer)\b|n't\b", clause, re.I):
        return None
    state = re.match(r'\s*(?:(?:is|are|was|were|remains?)\s+)?(not\s+)?(enabled|allowed|accepted|disabled|rejected|blocked|prohibited)\b', clause, re.I)
    if state:
        negative, word = state.groups()
        if negative:
            return 'disabled' if word.lower() in ('enabled','allowed','accepted') else None
        return 'enabled' if word.lower() in ('enabled','allowed','accepted') else 'disabled'
    if re.search(r'\benabled(?: protocols?)?\s*[:=]\s*$', head, re.I):
        return 'enabled'
    return None


def _dr_metrics(line, kind):
    """Qualify each metric locally; simple coordinated achieved pairs may inherit.

    Compound/range durations and unsupported negation are unresolved, never a
    partially parsed favourable duration. Quote remains the complete original line.
    """
    for clause in re.split(r';|(?<=[.!?])\s+', line):
        matches = list(re.finditer(r'\b(RTO|RPO)\s*(?:was|of|:|=)?\s*(\d+(?:\.\d+)?)\s*(minutes?|mins?|hours?|hrs?)?\b', clause, re.I))
        inherited = False
        for i, metric in enumerate(matches):
            prefix = clause[matches[i-1].end() if i else 0:metric.start()]
            suffix = clause[metric.end():matches[i+1].start() if i+1<len(matches) else len(clause)]
            coordinated = bool(re.fullmatch(r'[\s,]*(?:and)?[\s,]*', prefix, re.I))
            actual = bool(re.search(r'\b(?:achieved|actual|measured|observed)\s*$', prefix, re.I)
                          or re.match(r'\s*(?:(?:was|is)\s+)?(?:achieved|measured|observed)\b', suffix, re.I)
                          or (i and inherited and coordinated))
            uncertain = bool(re.search(r"\b(?:not|never|unmeasured|unobserved|target|objective|planned|example|hypothetical|goal|approximately|approximate|about|around|no longer|without)\b|n't\b", prefix + ' ' + suffix, re.I))
            compound = bool(re.match(r'\s*[,+]?\s*(?:and\s+)?\d', suffix)
                            or re.search(r'\d+(?:\.\d+)?\s*(?:minutes?|mins?|hours?|hrs?|seconds?|secs?)\b|\b(?:half|quarter|plus)\b', suffix, re.I))
            simple_suffix = bool(re.fullmatch(r'\s*(?:(?:was|is)\s+)?(?:(?:achieved|measured|observed)\s*)?(?:and\s*)?[.,:!?\s]*', suffix, re.I))
            unit = metric.group(3)
            value = Decimal(metric.group(2)) * (60 if unit and unit.lower().startswith('h') else 1)
            resolved = actual and kind == 'test' and simple_suffix and not uncertain and not compound and unit and value == value.to_integral_value()
            inherited = bool(resolved)
            if resolved:
                yield 'achieved_'+metric.group(1).lower()+'_minutes', int(value), ()
            else:
                yield 'unresolved_metric', metric.group(0), ('Achieved metric, actual exercise context, full duration or unambiguous units are missing; confirm the entire metric clause.',)


def _comparison(fact, threshold, direction):
    suffix = 'candidate exception; unconfirmed' if direction == 'adverse' else 'candidate only; unconfirmed'
    if isinstance(threshold, TlsThreshold) and fact.dimension in ('minimum_version', 'enabled_version'):
        return f'{fact.subject}: observed enabled TLS {fact.value//10}.{fact.value%10} vs customer minimum TLS {threshold.minimum_version//10}.{threshold.minimum_version%10} — {suffix}'
    if isinstance(threshold, DrThreshold) and fact.dimension.startswith('achieved_'):
        metric = 'RTO' if 'rto' in fact.dimension else 'RPO'
        maximum = threshold.max_rto_minutes if metric == 'RTO' else threshold.max_rpo_minutes
        return f'Achieved {metric} {fact.value} minutes vs customer maximum {maximum} minutes — {suffix}'
    return f'{fact.subject}: {fact.dimension}={fact.value} — {suffix}'
