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

VERSION = 'M5B-candidates-8'
MAX_LINES = 2000
MAX_LINE_CHARS = 2000
MAX_FACTS = 128
CLAUSE_BREAKS = r';|(?<!\bhr\.)(?<!\bhrs\.)(?<!\bmin\.)(?<!\bmins\.)(?<=[.!?])\s+|\s+but\s+'
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
        line_uncertainty = ()

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
            limitation = tuple(dict.fromkeys((*issues, *line_uncertainty, *uncertainty)))
            facts.append({**asdict(observation), 'document_id': bound.source.document_id,
                          'filename': bound.document.filename, 'confirmed': False, 'direction': direction,
                          'confidence': 'explicit phrase candidate; meaning unverified', 'uncertainties': list(limitation),
                          'comparison': _comparison(observation, threshold, direction),
                          'eligible_for_preview': not limitation})
            if not limitation and (direction != 'unknown' or dimension in ('enabled_version', 'disabled_version')): eligible.append((observation, direction_source))

        for ordinal, location, line in _clauses(rows):
            line_uncertainty = _line_uncertainties(line, intake.environment, observed, intake.as_of, 90 if requirement_id == 'ENC-01' else threshold.max_test_age_days)
            # Keep limitations and exclusions even when metric extraction is unavailable.
            scope_marker = bool(re.search(r'\b(exclud\w*|not tested|untested|incomplete)\b', line, re.I))
            negated_scope = scope_marker and bool(re.search(r"\b(?:no|none|never|not|neither|without|cannot)\b[^;.!?]*\b(?:exclud\w*|untested|incomplete)\b|n't\b[^;.!?]*\bexclud\w*", line, re.I))
            excluded = scope_marker and not negated_scope
            if negated_scope:
                add('unresolved_exclusion', line, ordinal, location, line, 'unresolved scope statement',
                    ('Negated or ambiguous exclusion clause; it cannot establish an exercise deficiency or full coverage.',))
            if requirement_id == 'ENC-01':
                versions = list(re.finditer(r'\bTLS\s*v?\s*1\.([0-3])\b', line, re.I))
                if not versions: continue
                listener = re.search(r'\b(listener|endpoint)\s+([a-z0-9][a-z0-9_.:/-]*)', line, re.I)
                subject = listener.group(1).lower() + ' ' + listener.group(2).rstrip(':,.') if listener else 'unspecified endpoint'
                uncertainty = [] if listener else ['Listener/endpoint identity is missing; do not infer fleet coverage.']
                heading = line[:versions[0].start()]
                known_heading = (r'\s*(?:(?:primary|alternate|production|test|staging|development|sandbox)\s+){0,2}'
                                 r'(?:listener|endpoint)\s+[A-Za-z0-9][A-Za-z0-9_.:/-]*\s*:?\s*')
                if not (re.fullmatch(r'\s*', heading) or re.fullmatch(known_heading + r'(?:enabled(?: protocols?)?\s*[:=]\s*)?', heading, re.I)
                        or re.fullmatch(r'\s*enabled(?: protocols?)?\s*[:=]\s*', heading, re.I)):
                    uncertainty.append('Unrecognized protocol-clause prefix; validate its qualification before comparing current activation.')
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
                if len(versions) > 1 and bare_list:
                    trailing = line[versions[-1].end():]
                    leading = line[:versions[0].start()]
                    shared_state = _tls_state(trailing, leading)
                    if shared_state == 'enabled':
                        enabled = [10 + int(m.group(1)) for m in versions]
                    elif shared_state == 'disabled':
                        disabled = [10 + int(m.group(1)) for m in versions]
                for version in enabled:
                    add('enabled_version', version, ordinal, location, line, subject, uncertainty)
                for version in disabled:
                    add('disabled_version', version, ordinal, location, line, subject, uncertainty)
                if {10,11} <= set(disabled): add('legacy_rejected', True, ordinal, location, line, subject, uncertainty)
                if not enabled and not disabled:
                    add('reported_versions', ', '.join('TLS 1.'+m.group(1) for m in versions), ordinal, location, line, subject,
                        (*uncertainty, 'Supported-version wording is not enabled configuration or operating evidence.'))
                if excluded:
                    add('unresolved_exclusion', line, ordinal, location, line, subject, (*uncertainty, 'TLS inventory/scan coverage effect requires manual source interpretation.'))
            else:
                subject = 'exercise for ' + (extracted['service'] or 'unspecified service')
                if excluded:
                    exercise_scope = bool(re.search(r'\bfrom (?:the )?(?:(?:recovery|DR|completed) )?(?:exercise|test|testing)\b(?!\s+(?:results?|reports?|documents?))|\b(?:exercise|test|testing) (?:scope )?exclud|\b(?:exercise|test) (?:scope|exclusions?)\s*:|\b(?:not tested|untested)\b', line, re.I))
                    if extracted['kind'] == 'test' and exercise_scope and _affirmative_exclusion(line):
                        add('scope_complete', False, ordinal, location, line, subject)
                    else:
                        add('unresolved_exclusion', line, ordinal, location, line, subject, ('Exclusion is not explicitly associated with actual exercise/testing scope; report omissions are not operating deficiencies.',))
                if re.search(r'\b(?:exercise|test) (?:was )?completed|\bcompleted (?:recovery |DR )?(?:exercise|test)', line, re.I):
                    add('completed', not bool(re.search(r'\b(?:not|never)\s+completed\b', line, re.I)), ordinal, location, line, subject)
                if not re.search(r'\b(RTO|RPO)\b', line, re.I): continue
                for dimension, value, uncertainty in _dr_metrics(line, extracted['kind']):
                    add(dimension, value, ordinal, location, line, subject, uncertainty)
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


def _clauses(rows):
    """Keep independent assertions/negations separate; retain exact source spans."""
    for ordinal, location, line in rows:
        for clause in re.split(CLAUSE_BREAKS, line, flags=re.I):
            if clause.strip():
                yield ordinal, location, clause.strip()


def _line_uncertainties(line, assessed_environment, source_date, as_of, max_age_days):
    """Every fact type inherits local scope/time limitations, not just metrics."""
    issues = []
    for match in re.finditer(r'\b\d{4}-\d{2}-\d{2}\b', line):
        try: clause_date = date.fromisoformat(match.group())
        except ValueError:
            issues.append('Clause-local date is invalid; establish the observation date.')
            continue
        if clause_date != source_date or not 0 <= (as_of-clause_date).days <= max_age_days:
            issues.append('Clause-local date differs from the source observation date or is stale/future; do not re-date this fact from the document header.')
    if re.search(r'\b(?:in|during|from|year)\s+(?:19|20)\d{2}\b(?!-\d)|\b(?:19|20)\d{2}\s+(?:exercise|test|results)\b', line, re.I):
        issues.append('Clause-local year does not establish its own complete current observation date; verify the exercise/date binding.')
    environments = re.findall(r'\b(production|test|staging|development|sandbox)\s+(?:environment|listener|endpoint)\b', line, re.I)
    if (any(value.casefold() != assessed_environment.casefold() for value in environments)
            or re.search(r'\bnon-production\b', line, re.I)):
        issues.append('Source clause states an environment outside the assessed environment or an unspecified non-production scope.')
    if re.search(r'\b(?:historical|previously|formerly|past|old|example|hypothetical|planned|proposed|scheduled|will|should|target|can|could|would|may|might|unless|if|when|potential|possible|potentially|possibly|maybe|perhaps|pending)\b|\bonly (?:if|when)\b', line, re.I):
        issues.append('Historical, hypothetical, conditional or ambiguous source clause; establish its own date and current meaning.')
    if re.search(r"\b(?:no|none|never|neither|nor|cannot|without|not supported|not disabled|not rejected)\b|n't\b", line, re.I):
        issues.append('Negated source clause; verify its meaning explicitly before any current comparison.')
    return tuple(issues)


def _affirmative_exclusion(clause):
    """A test-labelled file is not evidence that every mentioned exclusion occurred.

    Only direct passive/active occurrence wording is eligible for comparison;
    other scope mentions remain source-cited unresolved observations.
    """
    passive = re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 _./()\-]{0,200}\s+(?:was|were|is|are)\s+(?:excluded|not tested|untested)\b.*', clause, re.I)
    active = re.match(r'(?:(?:the|completed|recovery|DR|production)\s+){0,3}(?:exercise|test|testing)\s+(?:scope\s+)?exclud(?:ed|es)\b|^excluded\b', clause, re.I)
    return bool(passive or active)


def _tls_state(tail, head=''):
    """Associate a state with the protocol itself, never another feature's verb."""
    clause = re.split(r';|(?<=[.!?])\s+', tail, maxsplit=1)[0]
    if re.search(r"\b(?:never|neither|nor|cannot|without|no longer)\b|n't\b", clause, re.I):
        return None
    # Accept the whole state expression, not an enabled prefix followed by an
    # unknown condition, alternative or exception. Explicit local scope is allowed.
    scope = (r'(?:\s+in\s+(?:the\s+)?(?:production|test|staging|development|sandbox)\s+environment'
             r'|\s+on\s+(?:(?:a|an|the)\s+)?(?:(?:primary|alternate)\s+)?'
             r'(?:(?:production|test|staging|development|sandbox)\s+)?(?:listeners?|endpoints?)'
             r'(?:\s+[A-Za-z0-9][A-Za-z0-9_.:/-]*)?)?')
    state = re.fullmatch(r'\s*(?:(?:is|are|was|were|remains?)\s+)?(not\s+)?'
                         r'(enabled|allowed|accepted|disabled|rejected|blocked|prohibited)'
                         + scope + r'\s*[.,:!?]?\s*(?:and\s*)?', clause, re.I)
    if state:
        negative, word = state.groups()
        if negative:
            return 'disabled' if word.lower() in ('enabled','allowed','accepted') else None
        return 'enabled' if word.lower() in ('enabled','allowed','accepted') else 'disabled'
    if (re.search(r'(?:^|:)\s*enabled(?: protocols?)?\s*[:=]\s*$', head, re.I)
            and re.fullmatch(r'[\s.,:!?]*(?:and[\s.,:!?]*)?', clause, re.I)):
        if re.search(r"\b(?:not|never|no|none|neither|without|cannot)\b|n't\b", head, re.I):
            return None
        return 'enabled'
    return None


def _dr_metrics(line, kind):
    """Qualify each metric locally; simple coordinated achieved pairs may inherit.

    Compound/range durations and unsupported negation are unresolved, never a
    partially parsed favourable duration. Quote remains the complete original line.
    """
    for clause in re.split(CLAUSE_BREAKS, line, flags=re.I):
        matches = list(re.finditer(r'\b(RTO|RPO)\s*(?:was|of|:|=)?\s*(\d+(?:\.\d+)?)\s*(minutes?|mins?|hours?|hrs?)?\b', clause, re.I))
        inherited = False
        for i, metric in enumerate(matches):
            prefix = clause[matches[i-1].end() if i else 0:metric.start()]
            suffix = clause[metric.end():matches[i+1].start() if i+1<len(matches) else len(clause)]
            coordinated = bool(re.fullmatch(r'[\s,]*(?:and)?[\s,]*', prefix, re.I))
            # Only known affirmative achievement syntax may qualify a metric.
            # Unknown actors/modals/qualifiers before the verb are not actual results.
            actor = r'(?:(?:a|the)\s+)?(?:completed\s+)?(?:(?:recovery|DR|disaster recovery)\s+)?(?:exercise|test)'
            subject = r'(?:(?:we|' + actor + r')\s+)?'
            lead = r'[\s,]*(?:and\s+)?' + subject
            direct = bool(re.fullmatch(lead + r'(?:achieved|actual|measured|observed)\s*', prefix, re.I))
            postfix = bool(re.fullmatch(lead, prefix, re.I) and re.match(r'\s*(?:(?:was|is)\s+)?(?:achieved|measured|observed)\b', suffix, re.I))
            actual = direct or postfix or bool(i and inherited and coordinated)
            uncertain = bool(re.search(r"\b(?:not|never|unmeasured|unobserved|target|objective|planned|example|hypothetical|goal|historical|previously|formerly|past|old|approximately|approximate|about|around|no longer|without)\b|n't\b", prefix + ' ' + suffix, re.I))
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
