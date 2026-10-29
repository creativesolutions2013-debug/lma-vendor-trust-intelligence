"""Development-only upload adapter, not a document-understanding or decision engine."""
from dataclasses import dataclass, field
from datetime import date
from hashlib import sha256
from io import BytesIO
import re
import zlib
from zipfile import ZipFile, BadZipFile

from src.applicability import VendorRiskContext, evaluate_applicability
from src.assessment_worklist import AssessmentScope, AssuranceLink, EvidenceNeed, RequirementMapping, build_assessment_worklist
from src.assessment_worklist_pilot import WorklistScenario
from src.control_assurance import ControlCase, CustomerThreshold, EvidenceExpectation, RequirementContext, Observation, bind_relevance
from src.evidence_intelligence_mvp import evaluate_pilot_requirements
from src.evidence_source_validation import bind_evidence, segment_id
from src.guided_assessment_demo import DemoAssessment, RoleEvidenceInput, SourceRole
from src.scoring import InherentRiskInput, calculate_inherent_risk, rating_from_score, tier_from_score
from src.tiering import get_tier_profile
from src.tls_assurance import TlsThreshold
from src.dr_assurance import DrThreshold

MAX_FILES = 10
MAX_UPLOAD_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 10 * 1024 * 1024
LIMITATION = ('Local synthetic/nonconfidential documents only. TLS uses existing deterministic text screening; '
              'recovery and other controls retain source-cited manual review. No automatic technical assurance, '
              'RTO/RPO extraction, compliance certification, AI calls, verified scope or vendor approval.')


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

    def __post_init__(self):
        for value in (self.assessment_id, self.vendor, self.service, self.use_case, self.environment):
            if not isinstance(value, str) or not value.strip() or len(value) > 500 or any(ord(c) < 32 for c in value):
                raise ValueError('Enter a vendor, service and business use case (up to 500 characters each).')
        if self.data not in ('Public', 'Confidential', 'Restricted') or self.access not in ('None', 'Production', 'Privileged') or self.criticality not in ('Limited', 'Important', 'Critical'):
            raise ValueError('Choose the supported risk-context options.')


@dataclass(frozen=True)
class Upload:
    evidence: object
    requirements: tuple[str, ...]


@dataclass(frozen=True)
class UploadAssessment(DemoAssessment):
    customer_context: dict


def risk_and_applicability(intake):
    points = ({'Public': 5, 'Confidential': 10, 'Restricted': 20}[intake.data],
              {'None': 0, 'Production': 16, 'Privileged': 25}[intake.access],
              {'Limited': 5, 'Important': 15, 'Critical': 20}[intake.criticality], 0, 0, 0, 0, 0)
    score = calculate_inherent_risk(InherentRiskInput(*points))
    context = VendorRiskContext(sensitive_data=intake.data != 'Public', system_access=intake.access != 'None',
                                privileged_access=intake.access == 'Privileged', internet_facing=intake.access != 'None',
                                business_critical=intake.criticality != 'Limited')
    profile = get_tier_profile(score, privileged_access=context.privileged_access)
    return score, points, evaluate_applicability(profile, context)


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
                with archive.open(info) as member:
                    xml = member.read(MAX_UPLOAD_BYTES + 1)
                if len(xml) > MAX_UPLOAD_BYTES:
                    raise ValueError('DOCX text exceeds the local parser limit.')
                structural_xml = xml.replace(b'\x00', b'').upper()  # Also catches UTF-16/32 XML declarations.
                if b'<!DOCTYPE' in structural_xml or b'<!ENTITY' in structural_xml:
                    raise ValueError('DOCX entity declarations are not supported.')
        except (BadZipFile, KeyError, RuntimeError, NotImplementedError, EOFError, zlib.error) as exc:
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


def build_assessment(intake, uploads=()):
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
    mappings, links = [], []
    for control in applicable.controls:
        criteria = {
            'ENC-01': TlsThreshold(12).describe() + ' Encryption at rest and key management also require manual review.',
            'BCP-01': DrThreshold(365, 240, 60).describe(),
        }.get(control.control_id, control.requirement + ': provide current in-scope implementation and operating evidence for manual assessment.')
        threshold = CustomerThreshold(criteria)
        requirement = RequirementContext(control.control_id, 'synthetic-example-requirements', '2026.1',
            'Synthetic local example; not organizational approval', intake.as_of, intake.service, intake.environment,
            scope_label, 90 if control.control_id == 'ENC-01' else 365,
            business_use_case=intake.use_case, required_evidence=(criteria,),
            evidence_expectation=EvidenceExpectation('2026.1', ('policy', 'assertion', 'configuration', 'test')))
        documents = tuple(u.evidence.source for u in uploads if control.control_id in u.requirements)
        proposals = []
        if control.control_id == 'ENC-01':
            bound_sources = tuple(u.evidence for u in uploads if control.control_id in u.requirements)
            tls = evaluate_pilot_requirements(tuple(b.document for b in bound_sources), today=intake.as_of)[0]
            if tls.outcome == 'Risk Identified':
                for citation in tls.citations:
                    for bound in bound_sources:
                        for ordinal, segment in enumerate(bound.document.segments, 1):
                            if bound.document.filename == citation.filename and segment.location == citation.location and citation.excerpt in segment.text:
                                proposals.append(Observation('tls-screen-' + bound.source.document_id + '-' + str(ordinal),
                                    'unverified_text_concern', None, segment_id(bound.source.document_id, ordinal),
                                    bound.fingerprint, segment.location, citation.excerpt,
                                    'Text screening only; service scope and technical meaning unverified', None, 'potential_exception'))
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
    context = {'vendor': intake.vendor, 'service': intake.service, 'use_case': intake.use_case,
        'environment': intake.environment, 'data': intake.data, 'access': intake.access, 'criticality': intake.criticality,
        'limitations': LIMITATION, 'uncollected_risk_inputs': 'Volume, regulation, fourth parties, geography and AI use are unassessed (zero illustrative points).',
        'criteria_basis': 'Predefined synthetic example requirements, not organization-approved customer policy. TLS and recovery threshold descriptions reuse the existing threshold services.',
        'applicability_policy': applicable.policy_version,
        'screening': [dict(requirement_id=r.requirement_id, draft_text_signal=r.outcome, not_control_result=True, reason=r.reason, follow_up=r.follow_up,
                           citations=[dict(filename=c.filename, location=c.location, excerpt=c.excerpt) for c in r.citations]) for r in screening]}
    return UploadAssessment(intake.assessment_id, bool(uploads), f'{intake.data} / {intake.access} / {intake.criticality}',
        scenario, worklist, score, rating_from_score(score), tier_from_score(score), drivers,
        tuple(u.evidence for u in uploads if u.requirements), tuple(u.evidence for u in uploads if not u.requirements), context)
