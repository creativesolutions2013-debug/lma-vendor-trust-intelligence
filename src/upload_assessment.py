"""Development-only upload adapter, not a document-understanding or decision engine."""
from dataclasses import dataclass, field, replace
from datetime import date
from hashlib import sha256
from io import BytesIO
import re
import zlib
from lzma import LZMAError
from zipfile import ZipFile, BadZipFile, ZIP_BZIP2

from src.applicability import ApplicabilityDecision, VendorRiskContext, evaluate_applicability
from src.assessment_worklist import AssessmentScope, AssuranceLink, EvidenceNeed, RequirementMapping, build_assessment_worklist
from src.assessment_worklist_pilot import WorklistScenario
from src.control_assurance import ControlCase, CustomerThreshold, EvidenceExpectation, RequirementContext, bind_relevance
from src.evidence_intelligence_mvp import evaluate_pilot_requirements
from src.evidence_source_validation import bind_evidence, reuse_evidence_bindings
from src.guided_assessment_demo import DemoAssessment, RoleEvidenceInput, SourceRole
from src.scoring import DATA_SENSITIVITY_POINTS, InherentRiskInput, calculate_inherent_risk, rating_from_score, tier_from_score
from src.tiering import CONTROL_LIBRARY, get_tier_profile
from src.tls_assurance import TlsThreshold
from src.dr_assurance import DrThreshold
from src.upload_evaluation import evaluate_uploads, LIMITATION as EVALUATION_LIMITATION

MAX_FILES = 10
MAX_UPLOAD_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 10 * 1024 * 1024
LIMITATION = 'Local synthetic/nonconfidential documents only. ' + EVALUATION_LIMITATION

# Map dataset categories to existing legacy-intake classifications, not new weights.
DATA_TYPE_CLASSIFICATIONS = {
    'Public data': 'Public', 'Internal business data': 'Internal',
    'Confidential business data': 'Confidential', 'Personal data (PII)': 'PII',
    'Sensitive personal data': 'Sensitive PII', 'Health data (PHI)': 'PHI / PCI / Credentials',
    'Payment card data (PCI)': 'PHI / PCI / Credentials',
    'Authentication credentials': 'PHI / PCI / Credentials',
    'Financial records': 'Confidential', 'Other / not yet classified': None, 'Unknown': None,
}
DATA_TYPES = tuple(DATA_TYPE_CLASSIFICATIONS)


@dataclass(frozen=True)
class Intake:
    assessment_id: str
    vendor: str
    service: str
    use_case: str
    data: str = 'Confidential'
    access: str = 'Production'
    criticality: str = 'Important'
    environment: str = 'production'
    as_of: date = field(default_factory=date.today)
    data_types: tuple[str, ...] = ('Unknown',)

    def __post_init__(self):
        for value in (self.assessment_id, self.vendor, self.service, self.use_case, self.environment):
            if not isinstance(value, str) or not value.strip() or len(value) > 500 or any(ord(c) < 32 for c in value):
                raise ValueError('Enter a vendor, service and business use case (up to 500 characters each).')
        if self.data not in ('Public', 'Confidential', 'Restricted') or self.access not in ('None', 'Production', 'Privileged') or self.criticality not in ('Limited', 'Important', 'Critical'):
            raise ValueError('Choose the supported risk-context options.')
        if (not isinstance(self.data_types, tuple) or not self.data_types
                or any(not isinstance(t, str) or t not in DATA_TYPES for t in self.data_types)
                or len(set(self.data_types)) != len(self.data_types)):
            raise ValueError('Select the data types in scope, or Unknown if not yet determined.')
        object.__setattr__(self, 'data_types', tuple(t for t in DATA_TYPES if t in self.data_types))


def data_scope(intake):
    classifications = [DATA_TYPE_CLASSIFICATIONS[t] for t in intake.data_types]
    declared = {'Public': 5, 'Confidential': 10, 'Restricted': 20}[intake.data]
    minimum = max((DATA_SENSITIVITY_POINTS[c] for c in classifications if c), default=0)
    uncertainties = (['Data types are not fully classified; score and tier are provisional and may increase after clarification.']
                     if None in classifications else [])
    return {'data_types': list(intake.data_types), 'declared_sensitivity': intake.data,
            'declared_sensitivity_points': declared, 'data_type_minimum_points': minimum,
            'effective_sensitivity_points': max(declared, minimum),
            'regulated_data_review': 'PHI / PCI / Credentials' in classifications,
            'uncertainties': uncertainties,
            'basis': 'Highest existing legacy-intake classification or higher declared sensitivity; not additive per data type. Example policy, not a regulatory determination.'}


@dataclass(frozen=True)
class Upload:
    evidence: object
    requirements: tuple[str, ...]


@dataclass(frozen=True)
class UploadAssessment(DemoAssessment):
    customer_context: dict


def risk_and_applicability(intake):
    scope = data_scope(intake)
    points = (scope['effective_sensitivity_points'],
              {'None': 0, 'Production': 16, 'Privileged': 25}[intake.access],
              {'Limited': 5, 'Important': 15, 'Critical': 20}[intake.criticality], 0, 0, 0, 0, 0)
    score = calculate_inherent_risk(InherentRiskInput(*points))
    context = VendorRiskContext(sensitive_data=points[0] >= 10,
                                regulated_data=scope['regulated_data_review'], system_access=intake.access != 'None',
                                privileged_access=intake.access == 'Privileged', internet_facing=intake.access != 'None',
                                business_critical=intake.criticality != 'Limited')
    profile = get_tier_profile(score, privileged_access=context.privileged_access, regulated_data=context.regulated_data)
    applicable = evaluate_applicability(profile, context)
    if scope['uncertainties']:
        reason = 'Data scope is not fully classified; retain data-protection review pending clarification, not a confirmed sensitive-data assertion.'
        controls = {c.control_id: c for c in applicable.controls}
        controls.setdefault('DATA-01', CONTROL_LIBRARY['DATA-01'])
        applicable = replace(applicable, controls=tuple(controls.values()), review_required=True,
            review_reasons=applicable.review_reasons + (reason,),
            decisions=applicable.decisions + (ApplicabilityDecision('INTAKE-DATA-UNKNOWN', True, 'control', 'DATA-01', reason),))
    return score, points, applicable


def safe_upload_name(filename):
    if not isinstance(filename, str) or len(filename) > 250 or any(ord(c) < 32 for c in filename):
        raise ValueError('Use a short filename without control characters.')
    name = filename.replace('\\', '/').rsplit('/', 1)[-1]
    if not name or name in ('.', '..') or not name.lower().endswith(('.txt', '.pdf', '.docx')):
        raise ValueError('Upload a PDF, DOCX or UTF-8 TXT document.')
    return name


def read_upload(intake, filename, content, requirements=(), *, kind='assertion', observed_on=None, service=None, environment=None):
    name = safe_upload_name(filename)
    if not isinstance(content, bytes) or not content or len(content) > MAX_UPLOAD_BYTES:
        raise ValueError('File is empty or exceeds the 2 MB synthetic-upload limit.')
    if kind not in ('assertion', 'policy', 'configuration', 'test'):
        raise ValueError('Choose a document kind.')
    if name.lower().endswith('.txt'):
        try: content.decode('utf-8-sig')
        except UnicodeDecodeError as exc: raise ValueError('TXT must contain UTF-8 text.') from exc
    if name.lower().endswith('.docx'):
        try:
            with ZipFile(BytesIO(content)) as archive:
                if len(archive.infolist()) > 1000 or sum(i.file_size for i in archive.infolist()) > 10 * 1024 * 1024:
                    raise ValueError('DOCX expanded size exceeds the local parser limit.')
                info = archive.getinfo('word/document.xml')
                if info.file_size > MAX_UPLOAD_BYTES:
                    raise ValueError('DOCX text exceeds the local parser limit.')
                try:
                    with archive.open(info) as member:
                        xml = member.read(MAX_UPLOAD_BYTES + 1)
                except OSError as exc:
                    # BytesIO has no filesystem I/O. BZIP2 reports corrupt streams
                    # as this specific OSError; preserve unrelated server faults.
                    if info.compress_type != ZIP_BZIP2 or str(exc) != 'Invalid data stream':
                        raise
                    raise BadZipFile('Corrupt BZIP2 document stream.') from exc
                if len(xml) > MAX_UPLOAD_BYTES:
                    raise ValueError('DOCX text exceeds the local parser limit.')
                structural_xml = xml.replace(b'\x00', b'').upper()  # Also catches UTF-16/32 XML declarations.
                if b'<!DOCTYPE' in structural_xml or b'<!ENTITY' in structural_xml:
                    raise ValueError('DOCX entity declarations are not supported.')
        except (BadZipFile, KeyError, RuntimeError, NotImplementedError, EOFError, zlib.error, LZMAError) as exc:
            raise ValueError('Upload a readable, unencrypted DOCX using supported ZIP compression; re-save it locally and try again.') from exc
    if name.lower().endswith('.pdf') and not content.startswith(b'%PDF-'):
        raise ValueError('The file is not a PDF document.')
    digest = sha256(name.encode() + b'\0' + content).hexdigest()
    source_service = service if service is not None else intake.service
    source_environment = environment if environment is not None else intake.environment
    scope = f'{source_service} / {source_environment} (uploader-declared scope)'
    source = RoleEvidenceInput('upload-' + digest, name, content, sha256(content).hexdigest(),
        'User-selected synthetic file; scope/date/type are uploader declarations, not verified document facts',
        intake.as_of, source_service, source_environment, scope,
        observed_on, kind, SourceRole.VENDOR_EVIDENCE if requirements else SourceRole.VENDOR_CONTEXT)
    try:
        bound = bind_evidence(source, bounded_upload=True)
    except ValueError as exc:
        raise ValueError(f'Not attached: {exc} For scans, perform OCR locally and upload readable synthetic text.') from exc
    allowed = {c.control_id for c in risk_and_applicability(intake)[2].controls}
    if any(r not in allowed for r in requirements):
        raise ValueError('Select applicable requirements for this assessment.')
    return Upload(bound, tuple(dict.fromkeys(requirements)))


def suggested_requirements(document, applicable):
    """Routing hints only; the uploader can correct them before evaluation."""
    text = '\n'.join(s.text for s in document.segments)
    candidates = []
    tls = evaluate_pilot_requirements((document,))[0]
    if tls.citations: candidates.append('ENC-01')
    if re.search(r'\b(recovery|disaster|RTO|RPO)\b', text, re.I): candidates.append('BCP-01')
    return tuple(r for r in candidates if r in applicable)


def build_assessment(intake, uploads=(), *, tls_threshold=None, dr_threshold=None):
    # Relevance and worklist services rebind sources. Supply the already bounded
    # bindings for this build so neither path reparses untrusted original bytes.
    with reuse_evidence_bindings(u.evidence for u in uploads):
        return _build_assessment(intake, uploads, tls_threshold or TlsThreshold(12), dr_threshold or DrThreshold(365, 240, 60))


def _build_assessment(intake, uploads, tls_threshold, dr_threshold):
    if len(uploads) > MAX_FILES or sum(len(u.evidence.source.content) for u in uploads) > MAX_TOTAL_BYTES:
        raise ValueError('Keep at most 10 files and 10 MB total in this local assessment.')
    if len({u.evidence.source.document_id for u in uploads}) != len(uploads):
        raise ValueError('Duplicate uploaded document; attach each original once.')
    if len({u.evidence.document.filename for u in uploads}) != len(uploads):
        raise ValueError('Use distinct filenames so screening citations cannot be confused between files.')
    score, points, applicable = risk_and_applicability(intake)
    allowed = {c.control_id for c in applicable.controls}
    if any(r not in allowed for u in uploads for r in u.requirements):
        raise ValueError('Upload routing differs from current applicable requirements; review the file selections.')
    scope_label = f'{intake.service} / {intake.environment} (uploader-declared scope)'
    scope = AssessmentScope(intake.assessment_id, intake.service, intake.environment, intake.as_of)
    mappings, links, evaluations = [], [], []
    for control in applicable.controls:
        criteria = {
            'ENC-01': tls_threshold.describe() + ' Encryption at rest and key management also require manual review.',
            'BCP-01': dr_threshold.describe(),
        }.get(control.control_id, control.requirement + ': provide current in-scope implementation and operating evidence for manual assessment.')
        threshold = {'ENC-01': tls_threshold, 'BCP-01': dr_threshold}.get(control.control_id, CustomerThreshold(criteria))
        requirement = RequirementContext(control.control_id, 'synthetic-example-requirements', '2026.1',
            'Synthetic local example; not organizational approval', intake.as_of, intake.service, intake.environment,
            scope_label, 90 if control.control_id == 'ENC-01' else dr_threshold.max_test_age_days if control.control_id == 'BCP-01' else 365,
            business_use_case=intake.use_case, required_evidence=(criteria,),
            evidence_expectation=EvidenceExpectation('2026.1', ('policy', 'assertion', 'configuration', 'test')))
        documents = tuple(u.evidence.source for u in uploads if control.control_id in u.requirements)
        proposals = []
        if control.control_id in ('ENC-01', 'BCP-01'):
            bound_sources = tuple(u.evidence for u in uploads if control.control_id in u.requirements)
            proposals, _, evaluation = evaluate_uploads(intake, bound_sources, control.control_id, threshold)
            evaluations.append(evaluation)
        # All interpretations remain unconfirmed. The existing fallback review stays
        # the current session review; typed comparisons are a separate preview.
        case = ControlCase('local-' + control.control_id, control.requirement, control.domain, requirement, threshold,
            documents, tuple(proposals), intake.as_of, relevance=tuple(bind_relevance(requirement, threshold, d,
                rationale='Uploader selected this requirement for this file. This is routing for manual review, not proof of relevance or effectiveness.') for d in documents))
        need = EvidenceNeed('evidence-' + control.control_id, criteria, 'Current source evidence of: ' + criteria,
            f'Provide current {intake.service} evidence for {control.requirement}. {criteria}',
            ('policy', 'assertion', 'configuration', 'test'), max_age_days=requirement.max_age_days)
        mappings.append(RequirementMapping(control.control_id, requirement, threshold, (need,)))
        links.append(AssuranceLink(intake.assessment_id, control.control_id, case))
    scenario = WorklistScenario(intake.assessment_id, intake.vendor, scope, applicable, tuple(mappings), tuple(links))
    worklist = build_assessment_worklist(scope, applicable, tuple(mappings), tuple(links))
    # Existing deterministic text screening adds unverified TLS concerns with exact quotes;
    # no specialist factual interpretations or FactReviews are invented from free text.
    screening = evaluate_pilot_requirements(tuple(u.evidence.document for u in uploads),
                                          privileged_access=intake.access == 'Privileged', today=intake.as_of)
    drivers = tuple(f'{name}: {value} points' for name, value in zip(
        ('Data sensitivity', 'System access', 'Business criticality', 'Data volume', 'Regulatory exposure',
         'Fourth-party dependency', 'Geographic risk', 'AI autonomy'), points))
    scope_data = data_scope(intake)
    drivers += ('Data types in scope: ' + ', '.join(intake.data_types),
                f"Data sensitivity uses max(declared {scope_data['declared_sensitivity_points']}, data-type minimum {scope_data['data_type_minimum_points']}); categories are not added together.")
    drivers += tuple(scope_data['uncertainties'])
    context = {'vendor': intake.vendor, 'service': intake.service, 'use_case': intake.use_case,
        'environment': intake.environment, 'data': intake.data, 'access': intake.access, 'criticality': intake.criticality,
        'data_scope': scope_data,
        'limitations': LIMITATION, 'uncollected_risk_inputs': 'Volume, regulation, fourth parties, geography and AI use are unassessed (zero illustrative points).',
        'criteria_basis': 'Predefined synthetic example requirements, not organization-approved customer policy. TLS and recovery threshold descriptions reuse the existing threshold services.',
        'applicability_policy': applicable.policy_version, 'evaluations': evaluations,
        'screening': [dict(requirement_id=r.requirement_id, draft_text_signal=r.outcome, not_control_result=True, reason=r.reason, follow_up=r.follow_up,
                           citations=[dict(filename=c.filename, location=c.location, excerpt=c.excerpt) for c in r.citations]) for r in screening]}
    return UploadAssessment(intake.assessment_id, bool(uploads), f'{intake.data} / {intake.access} / {intake.criticality}',
        scenario, worklist, score, rating_from_score(score), tier_from_score(score), drivers,
        tuple(u.evidence for u in uploads if u.requirements), tuple(u.evidence for u in uploads if not u.requirements), context)
