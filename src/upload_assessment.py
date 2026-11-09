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
from src.tiering import CONTROL_LIBRARY, ControlRequirement, get_tier_profile, get_tier_profile_for_tier
from src.organization_methodology import OrganizationMethodology, scale_decision, weighted_scale_points, volume_band
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
SYSTEM_ACCESS_POINTS = {'None': 0, 'Production': 16, 'Privileged': 25, 'Unknown': None}
SYSTEM_DATA_CRITICALITY = ('Unknown', 'Hosts or processes critical data', 'Does not host or process critical data')
NETWORK_ACCESS_POINTS = {'None': 0, 'Network connectivity': 12, 'Unknown': None}
CRITICALITY_POINTS = {'Limited': 5, 'Important': 15, 'Critical': 20, 'Unknown': None}
# Pilot dependency descriptions reuse the existing criticality contribution.
SERVICE_DEPENDENCY_POINTS = {
    'No operational dependency': 0, 'Workaround available': 5,
    'Material operational disruption': 15,
    'Critical dependency / no viable workaround': 20, 'Unknown': None,
}
MAX_VOLUME_RECORDS = 10**12


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
    network_access: str = 'Unknown'
    data_volume_records: int | None = None
    service_dependency: str = 'Unknown'
    system_data_criticality: str = 'Unknown'
    organization_id: str | None = None
    methodology: OrganizationMethodology | None = None
    active_client_users: int | None = None
    workforce_size: int | None = None
    user_count_basis: str = 'Expected at rollout'
    scale_already_counted: bool | None = None
    scale_overlap_reason: str = ''
    critical_consequence: bool | None = None
    critical_consequence_reason: str = ''

    def __post_init__(self):
        if self.methodology is not None and (not isinstance(self.methodology, OrganizationMethodology)
                or self.organization_id != self.methodology.definition['organization_id']):
            raise ValueError('Use the methodology captured for this pilot organization.')
        for count in (self.active_client_users, self.workforce_size):
            if count is not None and (type(count) is not int or not 0 <= count <= MAX_VOLUME_RECORDS):
                raise ValueError('User/workforce estimates must be nonnegative whole numbers or unknown.')
        if self.active_client_users is not None and self.workforce_size is not None and self.active_client_users > self.workforce_size:
            raise ValueError('Active client users cannot exceed the defined workforce population.')
        if self.user_count_basis not in ('Observed active users', 'Expected at rollout'):
            raise ValueError('Choose observed or expected user counts.')
        for flag in (self.scale_already_counted, self.critical_consequence):
            if flag is not None and type(flag) is not bool: raise ValueError('Scale and critical conditions must be explicit or unknown.')
        for reason in (self.scale_overlap_reason, self.critical_consequence_reason):
            if not isinstance(reason, str) or len(reason)>1000 or any(ord(c)<32 for c in reason): raise ValueError('Use a short plain-text condition explanation.')
        if self.critical_consequence is True and not self.critical_consequence_reason.strip():
            raise ValueError('Explain the critical consequence under the organization methodology.')
        if self.scale_already_counted is True and not self.scale_overlap_reason.strip():
            raise ValueError('Explain which baseline factor already includes scale.')
        for value in (self.assessment_id, self.vendor, self.service, self.use_case, self.environment):
            if not isinstance(value, str) or not value.strip() or len(value) > 500 or any(ord(c) < 32 for c in value):
                raise ValueError('Enter a vendor, service and business use case (up to 500 characters each).')
        if (self.data not in ('Public', 'Confidential', 'Restricted')
                or any(not isinstance(value, str) or value not in options for value, options in (
                    (self.access, SYSTEM_ACCESS_POINTS), (self.criticality, CRITICALITY_POINTS),
                    (self.network_access, NETWORK_ACCESS_POINTS), (self.service_dependency, SERVICE_DEPENDENCY_POINTS),
                    (self.system_data_criticality, SYSTEM_DATA_CRITICALITY)))):
            raise ValueError('Choose the supported risk-context options.')
        if self.data_volume_records is not None and (type(self.data_volume_records) is not int
                or not 0 <= self.data_volume_records <= MAX_VOLUME_RECORDS):
            raise ValueError('Enter a nonnegative whole-record estimate, or leave volume unknown.')
        keys = self.methodology.definition['weights']['data_types'] if self.methodology else DATA_TYPE_CLASSIFICATIONS
        allowed_types = tuple(t for t in DATA_TYPES if t in keys) + tuple(sorted(set(keys)-set(DATA_TYPES)))
        if (not isinstance(self.data_types, tuple) or not self.data_types
                or any(not isinstance(t, str) or t not in allowed_types for t in self.data_types)
                or len(set(self.data_types)) != len(self.data_types)):
            raise ValueError('Select the data types in scope, or Unknown if not yet determined.')
        object.__setattr__(self, 'data_types', tuple(t for t in allowed_types if t in self.data_types))


def data_scope(intake):
    if intake.methodology:
        d=intake.methodology.definition
        values=[d['weights']['data_types'][t] for t in intake.data_types]
        declared=d['weights']['sensitivity'][intake.data]
        minimum=max((v for v in values if v is not None),default=0)
        return {'data_types':list(intake.data_types),'declared_sensitivity':intake.data,
                'declared_sensitivity_points':declared,'data_type_minimum_points':minimum,
                'effective_sensitivity_points':max(declared,minimum),
                'regulated_data_review':bool(set(intake.data_types)&set(d['regulated_types'])),
                'uncertainties':['Data types are not fully classified; score and tier are provisional and may increase after clarification.'] if None in values else [],
                'basis':'Requester-declared scope under captured organization methodology; not verified assurance.'}
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


def exposure_scope(intake):
    weights=intake.methodology.definition['weights'] if intake.methodology else {
        'system':SYSTEM_ACCESS_POINTS,'network':NETWORK_ACCESS_POINTS,'criticality':CRITICALITY_POINTS,'dependency':SERVICE_DEPENDENCY_POINTS}
    unqualified_system = weights['system'][intake.access]
    if intake.access == 'None' or intake.system_data_criticality == 'Does not host or process critical data':
        system = 0
    elif intake.system_data_criticality == 'Hosts or processes critical data':
        system = unqualified_system
    else:
        system = None
    network = weights['network'][intake.network_access]
    criticality = weights['criticality'][intake.criticality]
    dependency = weights['dependency'][intake.service_dependency]
    records = intake.data_volume_records
    # Explicit pilot record-count bands within the engine's existing 0–10 range.
    volume = None if records is None else 0 if records == 0 else 2 if records <= 1_000 else 5 if records <= 100_000 else 10
    if intake.methodology:
        band=volume_band(intake.methodology,records)
        volume=None if band is None else intake.methodology.definition['volume']['points'][band]
    missing = [name for name, value in (
        ('system access', None if intake.access == 'Unknown' else system), ('network access', network), ('data volume', volume),
        ('business criticality', criticality), ('service dependency', dependency)) if value is None]
    if intake.access != 'None' and intake.system_data_criticality == 'Unknown':
        missing.append('critical-system scope')
    return {'policy': 'INTAKE-EXPOSURE-PILOT-2', 'system_access': intake.access,
            'system_data_criticality': intake.system_data_criticality,
            'system_access_unqualified_points': unqualified_system,
            'system_access_basis': 'Only access to a system declared to host or process critical data contributes system-access points. Known noncritical systems contribute zero; unknown critical-data scope is unassessed. No access needs no criticality qualification. Actual access-related review requirements remain separate from this scoring qualification.',
            'system_access_points': system, 'network_access': intake.network_access,
            'network_access_points': network, 'data_volume_records': records,
            'data_volume_unit': 'records in the assessed use case', 'data_volume_points': volume,
            'service_dependency': intake.service_dependency, 'service_dependency_points': dependency,
            'declared_criticality_points': criticality,
            'effective_access_points': max((p for p in (system, network) if p is not None), default=0),
            'effective_business_points': max((p for p in (criticality, dependency) if p is not None), default=0),
            'missing_inputs': missing,
            'uncertainties': (['Unknown exposure inputs: ' + ', '.join(missing) + '. Score is a known-input subtotal; tier is provisional, not a confirmed low-risk determination.'] if missing else []),
            'basis': 'Pilot example policy, not approved customer rules. Access=max(critical-data-system access, network); business=max(criticality, service dependency), not additive. Volume: 0 records=0; 1–1,000=2; 1,001–100,000=5; over 100,000=10. Unknown is unassessed, not a zero-risk input.'}


@dataclass(frozen=True)
class Upload:
    evidence: object
    requirements: tuple[str, ...]


@dataclass(frozen=True)
class UploadAssessment(DemoAssessment):
    customer_context: dict


def risk_and_applicability(intake):
    scope = data_scope(intake)
    exposure = exposure_scope(intake)
    points = (scope['effective_sensitivity_points'],
              exposure['effective_access_points'], exposure['effective_business_points'],
              weighted_scale_points(intake,scope,exposure) if intake.methodology else exposure['data_volume_points'] if exposure['data_volume_points'] is not None else 0, 0, 0, 0, 0)
    score = calculate_inherent_risk(InherentRiskInput(*points))
    limits=intake.methodology.definition['uplift'] if intake.methodology else {'material_sensitivity_min':10,'material_dependency_min':15}
    context = VendorRiskContext(sensitive_data=points[0] >= limits['material_sensitivity_min'],
                                regulated_data=scope['regulated_data_review'],
                                system_access=intake.access in ('Production', 'Privileged') or intake.network_access == 'Network connectivity',
                                privileged_access=intake.access == 'Privileged', internet_facing=False,
                                business_critical=exposure['effective_business_points'] >= limits['material_dependency_min'])
    if intake.methodology:
        decision=scale_decision(intake,scope,exposure,score)
        d=intake.methodology.definition
        profile=get_tier_profile_for_tier(decision['final_tier'],privileged_access=context.privileged_access,regulated_data=context.regulated_data)
        profile=replace(profile,required_controls=tuple(ControlRequirement(r['id'],r['domain'],r['title'])
            for r in d['requirements'] if decision['final_tier'] in r['tiers']),policy_version=d['organization_id']+':'+d['version'])
    else:
        profile = get_tier_profile(score, privileged_access=context.privileged_access, regulated_data=context.regulated_data)
    library={r['id']:ControlRequirement(r['id'],r['domain'],r['title']) for r in intake.methodology.definition['requirements']} if intake.methodology else None
    applicable = evaluate_applicability(profile, context, control_library=library)
    if scope['uncertainties']:
        reason = 'Data scope is not fully classified; retain data-protection review pending clarification, not a confirmed sensitive-data assertion.'
        controls = {c.control_id: c for c in applicable.controls}
        controls.setdefault('DATA-01', (library or CONTROL_LIBRARY)['DATA-01'])
        applicable = replace(applicable, controls=tuple(controls.values()), review_required=True,
            review_reasons=applicable.review_reasons + (reason,),
            decisions=applicable.decisions + (ApplicabilityDecision('INTAKE-DATA-UNKNOWN', True, 'control', 'DATA-01', reason),))
    if exposure['missing_inputs']:
        # Retain precautionary review without asserting unprovided exposure facts.
        missing = exposure['missing_inputs']
        precautionary = []
        if 'system access' in missing or 'network access' in missing: precautionary += ['IAM-01', 'ENC-01']
        if 'data volume' in missing: precautionary += ['DATA-01']
        if 'business criticality' in missing or 'service dependency' in missing: precautionary += ['BCP-01']
        controls = {c.control_id: c for c in applicable.controls}
        decisions = list(applicable.decisions)
        reason = exposure['uncertainties'][0] + ' Precautionary review is not a confirmed exposure assertion.'
        for control_id in precautionary:
            controls.setdefault(control_id, (library or CONTROL_LIBRARY)[control_id])
            decisions.append(ApplicabilityDecision('INTAKE-UNKNOWN-' + control_id, True, 'control', control_id, reason))
        applicable = replace(applicable, controls=tuple(controls.values()), review_required=True,
                             review_reasons=applicable.review_reasons + (reason,), decisions=tuple(decisions))
    if intake.methodology and decision['missing_inputs']:
        applicable=replace(applicable,review_required=True,review_reasons=applicable.review_reasons+tuple(decision['missing_inputs']))
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
        if intake.methodology:
            a=intake.methodology.definition['assurance']
            if tls_threshold is not None or dr_threshold is not None:
                raise ValueError('Edit organization methodology thresholds rather than overriding its captured snapshot.')
            tls_threshold=TlsThreshold(a['tls_minimum_version'])
            dr_threshold=DrThreshold(a['dr_max_test_age_days'],a['rto_minutes'],a['rpo_minutes'])
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
        rule=next((r for r in intake.methodology.definition['requirements'] if r['id']==control.control_id),None) if intake.methodology else None
        criteria = {
            'ENC-01': tls_threshold.describe() + ' Encryption at rest and key management also require manual review.',
            'BCP-01': dr_threshold.describe(),
        }.get(control.control_id, control.requirement + ': provide current in-scope implementation and operating evidence for manual assessment.')
        if rule:
            criteria=(criteria+' Organization evidence expectation: '+rule['criteria']) if control.control_id in ('ENC-01','BCP-01') else rule['criteria']
        threshold = {'ENC-01': tls_threshold, 'BCP-01': dr_threshold}.get(control.control_id, CustomerThreshold(criteria))
        policy_id=intake.methodology.definition['organization_id'] if intake.methodology else 'synthetic-example-requirements'
        policy_version=intake.methodology.definition['version'] if intake.methodology else '2026.1'
        kinds=tuple(rule['evidence_kinds']) if rule else ('policy','assertion','configuration','test')
        requirement = RequirementContext(control.control_id, policy_id, policy_version,
            'Synthetic local example; not organizational approval', intake.as_of, intake.service, intake.environment,
            scope_label, rule['max_age_days'] if rule else 90 if control.control_id == 'ENC-01' else dr_threshold.max_test_age_days if control.control_id == 'BCP-01' else 365,
            business_use_case=intake.use_case, required_evidence=(criteria,),
            evidence_expectation=EvidenceExpectation(policy_version, kinds))
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
            kinds, max_age_days=requirement.max_age_days)
        mappings.append(RequirementMapping(control.control_id, requirement, threshold, (need,)))
        links.append(AssuranceLink(intake.assessment_id, control.control_id, case))
    scenario = WorklistScenario(intake.assessment_id, intake.vendor, scope, applicable, tuple(mappings), tuple(links))
    worklist = build_assessment_worklist(scope, applicable, tuple(mappings), tuple(links))
    # Existing deterministic text screening adds unverified TLS concerns with exact quotes;
    # no specialist factual interpretations or FactReviews are invented from free text.
    screening = evaluate_pilot_requirements(tuple(u.evidence.document for u in uploads),
                                          privileged_access=intake.access == 'Privileged', today=intake.as_of)
    if intake.methodology:screening=()  # Legacy fixed-policy screening is not organization policy.
    scope_data = data_scope(intake)
    exposure_data = exposure_scope(intake)
    displayed_points = (points[0],
        points[1] if exposure_data['system_access_points'] is not None or exposure_data['network_access_points'] is not None else None,
        points[2] if exposure_data['declared_criticality_points'] is not None or exposure_data['service_dependency_points'] is not None else None,
        exposure_data['data_volume_points'], None, None, None, None)
    drivers = tuple(f'{name}: {value} points' if value is not None else f'{name}: unassessed; not included in known-input subtotal'
        for name, value in zip(('Data sensitivity', 'System/network access', 'Business criticality/dependency', 'Data volume',
                               'Regulatory exposure', 'Fourth-party dependency', 'Geographic risk', 'AI autonomy'), displayed_points))
    drivers += ('Data types in scope: ' + ', '.join(intake.data_types),
                f"Data sensitivity uses max(declared {scope_data['declared_sensitivity_points']}, data-type minimum {scope_data['data_type_minimum_points']}); categories are not added together.")
    drivers += tuple(scope_data['uncertainties'])
    drivers += (f"System access: {intake.access}; critical-data scope: {intake.system_data_criticality}. Only systems hosting/processing critical data count toward system-access points. Network access: {intake.network_access}; its contribution remains separate. Access uses the higher known contribution, not their sum.",
                f"Data volume: {intake.data_volume_records if intake.data_volume_records is not None else 'Unknown'} records; pilot bands 0=0, 1–1,000=2, 1,001–100,000=5, over 100,000=10 points.",
                f"Service dependency: {intake.service_dependency}; business criticality: {intake.criticality}. Business exposure uses the higher known contribution, not their sum.")
    drivers += tuple(exposure_data['uncertainties'])
    decision=scale_decision(intake,scope_data,exposure_data,score) if intake.methodology else None
    if decision:
        # The legacy volume driver is potential weighted points, not another charge
        # under the scale-uplift strategy.
        drivers=tuple(d for d in drivers if not d.startswith('Data volume:')) + (
            'Data/user scale: '+('excluded from baseline; at most one tier uplift' if decision['strategy']=='scale_uplift' else str(points[3])+' points, highest eligible scale contribution only'),
            'Record volume: '+str(intake.data_volume_records)+' records; active client users: '+str(intake.active_client_users)+'; workforce: '+str(intake.workforce_size),)
        drivers=tuple(d for d in drivers if not d.startswith('Data volume:'))
        exposure_data=dict(exposure_data,policy=intake.organization_id+':'+intake.methodology.definition['version'],
                           data_volume_points_applied=points[3],basis='Captured organization methodology; scale is never counted both as points and uplift.')
        drivers += ('Organization methodology: '+intake.organization_id+' / '+intake.methodology.definition['version'],
            f"Baseline score {decision['baseline_score']}, {decision['baseline_tier']}; scored subtotal {decision['scored_subtotal']}; final tier {decision['final_tier']}. {decision['reason']}",
            'Methodology strategy: '+decision['strategy']+'. Volume/user scale is not also added as a second uplift.')
        drivers += tuple('Unassessed methodology input: '+m for m in decision['missing_inputs'])
    context = {'vendor': intake.vendor, 'service': intake.service, 'use_case': intake.use_case,
        'environment': intake.environment, 'data': intake.data, 'access': intake.access, 'criticality': intake.criticality,
        'data_scope': scope_data,
        'exposure_scope': exposure_data,
        'tier_status': 'Provisional — incomplete intake; known-input subtotal only' if scope_data['uncertainties'] or exposure_data['uncertainties'] else 'Illustrative tier based on requester-supplied inputs; not approved risk',
        'limitations': LIMITATION, 'uncollected_risk_inputs': 'Regulation, fourth parties, geography, AI use and internet exposure remain unassessed. Numeric uncollected dimensions use zero only in this illustrative subtotal.',
        'criteria_basis': 'Predefined synthetic example requirements, not organization-approved customer policy. TLS and recovery threshold descriptions reuse the existing threshold services.',
        'applicability_policy': applicable.policy_version, 'evaluations': evaluations,
        'screening': [dict(requirement_id=r.requirement_id, draft_text_signal=r.outcome, not_control_result=True, reason=r.reason, follow_up=r.follow_up,
                           citations=[dict(filename=c.filename, location=c.location, excerpt=c.excerpt) for c in r.citations]) for r in screening]}
    if decision:
        context.update(organization_id=intake.organization_id,methodology_snapshot=intake.methodology.definition,
            methodology_sha256=intake.methodology.fingerprint,tier_decision=decision,
            adoption_inputs={'active_client_users':intake.active_client_users,'workforce_size':intake.workforce_size,
                'basis':intake.user_count_basis,'measurement_days':intake.methodology.definition['adoption']['window_days'],
                'scale_overlap_reason':intake.scale_overlap_reason})
        context['tier_status']='Provisional — incomplete methodology inputs' if decision['provisional'] else 'Illustrative organization methodology result; not approved risk'
        context['criteria_basis']='Captured pilot organization methodology; requester declarations and supplied criteria, not verified compliance or approved vendor risk.'
    tier=(('Tier '+decision['final_tier'][1:]+' — '+intake.methodology.definition['tier_names'][decision['final_tier']]) if decision else tier_from_score(score))
    rating=({'T1':'Critical','T2':'High','T3':'Moderate','T4':'Low'}[decision['final_tier']] if decision else rating_from_score(score))
    return UploadAssessment(intake.assessment_id, bool(uploads), f'{intake.data} / {intake.access} / {intake.criticality}',
        scenario, worklist, score, rating, tier, drivers,
        tuple(u.evidence for u in uploads if u.requirements), tuple(u.evidence for u in uploads if not u.requirements), context)
