"""Versioned, bounded organization methodology for the session-only synthetic pilot.

No persistence, authorization, expression evaluation or governed risk writes.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
import re

from src.tiering import CONTROL_LIBRARY, get_tier_profile

MAX_POLICY_BYTES = 128 * 1024
TIER_NAMES = {'T1': 'Critical', 'T2': 'High', 'T3': 'Moderate', 'T4': 'Low'}


def default_definition(organization_id='pilot-default', version='1'):
    from src.upload_assessment import (DATA_TYPE_CLASSIFICATIONS, SYSTEM_ACCESS_POINTS,
        NETWORK_ACCESS_POINTS, CRITICALITY_POINTS, SERVICE_DEPENDENCY_POINTS)
    from src.scoring import DATA_SENSITIVITY_POINTS
    requirements = []
    for cid, control in CONTROL_LIBRARY.items():
        tiers = [f'T{i}' for i, score in enumerate((75,50,25,0),1)
                 if cid in {c.control_id for c in get_tier_profile(score).required_controls}]
        requirements.append({'id':cid,'title':control.requirement,'domain':control.domain,'tiers':tiers,
            'criteria':control.requirement + ': provide current in-scope implementation and operating evidence for manual assessment.',
            'max_age_days':90 if cid=='ENC-01' else 365,
            'evidence_kinds':['policy','assertion','configuration','test']})
    return {'schema':1,'organization_id':organization_id,'version':version,'name':'Default pilot methodology',
        'strategy':'scale_uplift','tier_thresholds':{'T4':0,'T3':25,'T2':50,'T1':75},'tier_names':dict(TIER_NAMES),
        'weights':{'sensitivity':{'Public':5,'Confidential':10,'Restricted':20},
            'data_types':{t:DATA_SENSITIVITY_POINTS[c] if c else None for t,c in DATA_TYPE_CLASSIFICATIONS.items()},
            'system':dict(SYSTEM_ACCESS_POINTS),'network':dict(NETWORK_ACCESS_POINTS),
            'criticality':dict(CRITICALITY_POINTS),'dependency':dict(SERVICE_DEPENDENCY_POINTS)},
        'nonpublic_types':[t for t,c in DATA_TYPE_CLASSIFICATIONS.items() if c and c!='Public'],
        'regulated_types':[t for t,c in DATA_TYPE_CLASSIFICATIONS.items() if c=='PHI / PCI / Credentials'],
        'volume':{'low_max':1000,'moderate_max':100000,'points':[0,2,5,10]},
        'adoption':{'low_count':100,'high_count':1000,'low_percent':10,'high_percent':50,'window_days':30,'points':[0,2,5,10]},
        'uplift':{'material_sensitivity_min':10,'material_dependency_min':15,'tier4_to_tier3':True,'tier3_to_tier2':True,'tier2_to_tier1':True,'critical_override':True,'critical_condition_required':True},
        'assurance':{'tls_minimum_version':12,'dr_max_test_age_days':365,'rto_minutes':240,'rpo_minutes':60},
        'requirements':requirements}


def _keys(value, expected):
    if not isinstance(value,dict) or set(value)!=set(expected):
        raise ValueError('Methodology fields do not match the supported schema.')


def _text(value, maximum=2000):
    if not isinstance(value,str) or not value.strip() or len(value)>maximum or any(ord(c)<32 for c in value):
        raise ValueError('Methodology text must be nonempty, bounded and contain no control characters.')


def _integer(value, minimum=0, maximum=100):
    if type(value) is not int or not minimum<=value<=maximum:
        raise ValueError('Methodology numeric values must be bounded whole numbers.')


def _no_duplicates(pairs):
    result={}
    for key,value in pairs:
        if key in result: raise ValueError('Duplicate JSON methodology field.')
        result[key]=value
    return result


@dataclass(frozen=True)
class OrganizationMethodology:
    """Canonical immutable JSON snapshot; getters return detached copies."""
    json_text: str

    def __post_init__(self):
        try:self._validate()
        except (TypeError, KeyError, IndexError, UnicodeError) as exc:raise ValueError("Invalid methodology field types or structure.") from exc

    def _validate(self):
        if not isinstance(self.json_text,str) or len(self.json_text.encode())>MAX_POLICY_BYTES:
            raise ValueError('Methodology exceeds the 128 KB pilot limit.')
        try: d=json.loads(self.json_text,object_pairs_hook=_no_duplicates)
        except (json.JSONDecodeError, RecursionError) as exc: raise ValueError('Invalid methodology JSON.') from exc
        template=default_definition()
        _keys(d,template)
        if type(d['schema']) is not int or d['schema']!=1: raise ValueError('Unsupported methodology schema.')
        for key in ('organization_id','version'):
            if not isinstance(d[key],str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}',d[key]):
                raise ValueError('Organization and version IDs must be short stable identifiers.')
        _text(d['name'],120)
        if d['strategy'] not in ('weighted','scale_uplift'): raise ValueError('Choose weighted or scale_uplift.')
        _keys(d['tier_thresholds'],TIER_NAMES);_keys(d['tier_names'],TIER_NAMES)
        bounds=[d['tier_thresholds'][t] for t in ('T4','T3','T2','T1')]
        for x in bounds:_integer(x)
        if bounds[0]!=0 or any(a>=b for a,b in zip(bounds,bounds[1:])):raise ValueError('Tier thresholds must increase from T4=0 to T1.')
        for name in d['tier_names'].values():_text(name,80)
        _keys(d['weights'],template['weights'])
        for group,weights in d['weights'].items():
            if group=='data_types':
                if not isinstance(weights,dict) or not 2<=len(weights)<=64 or not {'Unknown','Other / not yet classified'}<=set(weights):raise ValueError('Include Unknown and Other data types; at most 64 categories.')
            else:_keys(weights,template['weights'][group])
            for label,points in weights.items():
                _text(label,120)
                if label in ('Unknown','Other / not yet classified'):
                    if points is not None:raise ValueError('Unknown classifications cannot receive known numeric weights.')
                else:_integer(points)
            if group in ('system','network') and weights['None']!=0:raise ValueError('No access must contribute zero.')
            if group=='dependency' and weights['No operational dependency']!=0:raise ValueError('No operational dependency must contribute zero.')
        for key in ('nonpublic_types','regulated_types'):
            if not isinstance(d[key],list) or len(d[key])>64 or any(not isinstance(t,str) or t not in d['weights']['data_types'] or d['weights']['data_types'][t] is None for t in d[key]):raise ValueError('Data classification groups must reference known categories.')
            if len(set(d[key]))!=len(d[key]):raise ValueError('Duplicate data classification.')
        for key in ('volume','adoption','uplift','assurance'):_keys(d[key],template[key])
        volume=d['volume'];adoption=d['adoption']
        for x in (volume['low_max'],volume['moderate_max'],adoption['low_count'],adoption['high_count']):_integer(x,1,10**12)
        if volume['low_max']>=volume['moderate_max'] or adoption['low_count']>=adoption['high_count']:raise ValueError('Scale bands must increase.')
        for x in (adoption['low_percent'],adoption['high_percent']):_integer(x,1,100)
        if adoption['low_percent']>=adoption['high_percent']:raise ValueError('Adoption percentage bands must increase.')
        _integer(adoption['window_days'],1,3650)
        for points in (volume['points'],adoption['points']):
            if not isinstance(points,list) or len(points)!=4:raise ValueError('Provide four scale weights.')
            for x in points:_integer(x,0,100)
            if points[0]!=0 or points!=sorted(points):raise ValueError('Scale weights must be monotonic from zero.')
        for key in ('material_sensitivity_min','material_dependency_min'):_integer(d['uplift'][key],1,100)
        for key in ('tier4_to_tier3','tier3_to_tier2','tier2_to_tier1','critical_override','critical_condition_required'):
            if type(d['uplift'][key]) is not bool:raise ValueError('Uplift switches must be booleans.')
        from src.tls_assurance import TlsThreshold
        from src.dr_assurance import DrThreshold
        a=d['assurance'];TlsThreshold(a['tls_minimum_version']);DrThreshold(a['dr_max_test_age_days'],a['rto_minutes'],a['rpo_minutes'])
        if not isinstance(d['requirements'],list) or not 1<=len(d['requirements'])<=64:raise ValueError('Provide 1–64 requirement definitions.')
        ids=[]
        for rule in d['requirements']:
            _keys(rule,('id','title','domain','tiers','criteria','max_age_days','evidence_kinds'))
            if not isinstance(rule['id'],str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}',rule['id']):raise ValueError('Invalid requirement ID.')
            ids.append(rule['id'])
            for k in ('title','domain','criteria'):_text(rule[k])
            if not isinstance(rule['tiers'],list) or any(t not in TIER_NAMES for t in rule['tiers']) or len(set(rule['tiers']))!=len(rule['tiers']):raise ValueError('Invalid requirement tiers.')
            _integer(rule['max_age_days'],1,3650)
            kinds=rule['evidence_kinds']
            if not isinstance(kinds,list) or not kinds or any(k not in ('policy','assertion','configuration','test') for k in kinds) or len(set(kinds))!=len(kinds):raise ValueError('Invalid evidence kinds.')
        if len(ids)!=len(set(ids)):raise ValueError('Duplicate requirement IDs.')
        dr_rule=next((r for r in d['requirements'] if r['id']=='BCP-01'),None)
        if dr_rule and dr_rule['max_age_days']!=a['dr_max_test_age_days']:raise ValueError('BCP freshness must match the configured recovery test interval.')
        # Contextual rules may add these families; their criteria must remain defined.
        if not set(CONTROL_LIBRARY)<=set(ids):raise ValueError('Retain definitions for all built-in contextual control families.')
        object.__setattr__(self,'json_text',json.dumps(d,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False))

    @classmethod
    def from_dict(cls, definition):
        try:return cls(json.dumps(definition,allow_nan=False))
        except (TypeError,OverflowError,RecursionError) as exc:raise ValueError('Invalid methodology definition.') from exc

    @property
    def definition(self):return json.loads(self.json_text)

    @property
    def fingerprint(self):return sha256(self.json_text.encode()).hexdigest()


class MethodologyRegistry:
    """Session-local pilot profiles, not production tenant authorization/storage."""
    def __init__(self):self._versions={};self._active={}

    def publish(self, policy, organization_id):
        d=policy.definition
        if d['organization_id']!=organization_id:raise ValueError('Methodology belongs to a different pilot organization.')
        key=(organization_id,d['version'])
        if key in self._versions and self._versions[key].fingerprint!=policy.fingerprint:raise ValueError('Use a new version; an existing version cannot be rewritten.')
        self._versions[key]=policy;self._active[organization_id]=d['version']

    def get(self, organization_id, version=None):
        try:return self._versions[(organization_id,version or self._active[organization_id])]
        except KeyError as exc:raise ValueError('No methodology for that pilot organization/version.') from exc

    @property
    def organizations(self):return tuple(self._active)


def tier_code(policy, score):
    thresholds=policy.definition['tier_thresholds']
    return next(t for t in ('T1','T2','T3','T4') if score>=thresholds[t])


def volume_band(policy, count):
    if count is None:return None
    v=policy.definition['volume']
    return 0 if count==0 else 1 if count<=v['low_max'] else 2 if count<=v['moderate_max'] else 3


def adoption_band(policy, users, workforce):
    if users is None:return None
    if users==0:return 0
    a=policy.definition['adoption']
    percent=100*users/workforce if workforce else None
    if users>=a['high_count'] or (percent is not None and percent>=a['high_percent']):return 3
    # A missing denominator could change a small absolute count to high adoption.
    if percent is None:return None
    return 1 if users<a['low_count'] and percent<a['low_percent'] else 2


def scale_decision(intake, data, exposure, baseline_score):
    policy=intake.methodology;d=policy.definition;u=d['uplift'];missing=[]
    record_band=volume_band(policy,intake.data_volume_records)
    user_band=adoption_band(policy,intake.active_client_users,intake.workforce_size)
    if user_band is None:missing.append('active client users or workforce denominator')
    nonpublic=(intake.data in ('Confidential','Restricted') or bool(set(intake.data_types)&set(d['nonpublic_types'])))
    material_records=nonpublic and data['effective_sensitivity_points']>=u['material_sensitivity_min']
    material_use=exposure['service_dependency_points'] is not None and exposure['service_dependency_points']>=u['material_dependency_min']
    eligible_records=record_band is not None and record_band>0 and material_records
    eligible_users=user_band is not None and user_band>0 and material_use
    candidate=(record_band==3 and material_records) or (user_band==3 and material_use)
    if (candidate or (d['strategy']=='weighted' and (eligible_records or eligible_users))) and intake.scale_already_counted is None:missing.append('whether scale is already counted in baseline')
    if intake.critical_consequence is None and (u['critical_override'] or u['critical_condition_required']):missing.append('critical consequence determination')
    from src.scoring import InherentRiskInput, calculate_inherent_risk
    core_score=calculate_inherent_risk(InherentRiskInput(data['effective_sensitivity_points'],exposure['effective_access_points'],exposure['effective_business_points'],0,0,0,0,0))
    baseline=tier_code(policy,core_score);scored_tier=tier_code(policy,baseline_score)
    final=scored_tier if d['strategy']=='weighted' else baseline;reason='No additional scale uplift.'
    if baseline=='T1':reason='Baseline already Tier 1; scale is retained for review depth and monitoring, not an additional increase.'
    if d['strategy']=='weighted' and scored_tier=='T1' and baseline!='T1' and u['critical_condition_required'] and intake.critical_consequence is not True:
        final='T2';reason='Weighted scale cannot establish Tier 1 without a critical consequence; numeric score is retained, classification is capped at Tier 2.'
    if intake.critical_consequence is True and u['critical_override']:
        final='T1';reason='Requester-declared critical consequence: '+intake.critical_consequence_reason
    elif d['strategy']=='scale_uplift' and candidate and intake.scale_already_counted is False:
        if baseline=='T4' and u['tier4_to_tier3']:final='T3';reason='One scale uplift for material exposure.'
        elif baseline=='T3' and u['tier3_to_tier2']:final='T2';reason='One scale uplift for material record exposure or operational adoption.'
        elif baseline=='T2' and u['tier2_to_tier1'] and (intake.critical_consequence is True or not u['critical_condition_required']):final='T1';reason='One scale uplift with explicit critical consequence.' if intake.critical_consequence is True else 'One scale uplift under organization policy permitting count-based criticality.'
        elif baseline=='T2':reason='High scale alone cannot establish Tier 1; critical consequence is required.'
    elif candidate and intake.scale_already_counted is True:reason='Scale already represented in baseline; no duplicate uplift.'
    return {'strategy':d['strategy'],'baseline_score':core_score,'scored_subtotal':baseline_score,'baseline_tier':baseline,'score_tier':scored_tier,'final_tier':final,
        'record_band':record_band,'adoption_band':user_band,'candidate_scale_uplift':candidate,
        'scale_already_counted':intake.scale_already_counted,'critical_consequence':intake.critical_consequence,
        'critical_consequence_reason':intake.critical_consequence_reason,'reason':reason,'missing_inputs':missing,
        'provisional':bool(missing or data['uncertainties'] or exposure['uncertainties']),
        'not_approval':True}


def weighted_scale_points(intake, data, exposure):
    d=intake.methodology.definition
    if d['strategy']!='weighted' or intake.scale_already_counted is not False:return 0
    from src.scoring import InherentRiskInput, calculate_inherent_risk
    core_score=calculate_inherent_risk(InherentRiskInput(data['effective_sensitivity_points'],exposure['effective_access_points'],exposure['effective_business_points'],0,0,0,0,0))
    if tier_code(intake.methodology,core_score)=='T1':return 0
    nonpublic=intake.data in ('Confidential','Restricted') or bool(set(intake.data_types)&set(d['nonpublic_types']))
    vb=volume_band(intake.methodology,intake.data_volume_records);ub=adoption_band(intake.methodology,intake.active_client_users,intake.workforce_size)
    volume=d['volume']['points'][vb] if vb is not None and nonpublic and data['effective_sensitivity_points']>=d['uplift']['material_sensitivity_min'] else 0
    users=d['adoption']['points'][ub] if ub is not None and exposure['service_dependency_points'] is not None and exposure['service_dependency_points']>=d['uplift']['material_dependency_min'] else 0
    return max(volume,users)
