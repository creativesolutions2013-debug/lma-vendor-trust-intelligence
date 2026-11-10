"""Organization policies, scale conditions and immutable assessment snapshots."""
from dataclasses import replace
from datetime import date, timedelta
from io import BytesIO
from zipfile import ZipFile
from hashlib import sha256
import json
import pytest

from src.organization_methodology import (OrganizationMethodology, MethodologyRegistry, default_definition,
    adoption_band, volume_band)
from src.upload_assessment import Intake, build_assessment, read_upload
from src.guided_assessment_demo import complete_review, completion_is_current, package_bytes, record_action


def policy(org='org-a', version='1', **changes):
    d=default_definition(org,version);d.update(changes)
    return OrganizationMethodology.from_dict(d)


def intake(p=None, **changes):
    p=p or policy()
    values=dict(assessment_id='synthetic-case',vendor='Synthetic Vendor',service='Synthetic Portal',use_case='Synthetic processing',
        as_of=date(2026,11,8),data_types=('Confidential business data',),access='Production',criticality='Important',
        system_data_criticality='Hosts or processes critical data',network_access='None',data_volume_records=0,
        service_dependency='No operational dependency',organization_id=p.definition['organization_id'],methodology=p,
        active_client_users=0,critical_consequence=False,scale_already_counted=False)
    values.update(changes);return Intake(**values)


def decision(i):return build_assessment(i).customer_context['tier_decision']


def test_default_scale_uplift_is_single_not_additive_and_already_counted_is_not_reused():
    i=intake(data_volume_records=100001,active_client_users=1000,workforce_size=2000,service_dependency='Material operational disruption')
    m=build_assessment(i);d=m.customer_context['tier_decision']
    assert m.inherent_score==41 and d['baseline_tier']=='T3' and d['final_tier']=='T2'
    assert d['record_band']==d['adoption_band']==3
    assert m.customer_context['exposure_scope']['data_volume_points_applied']==0
    assert decision(replace(i,scale_already_counted=True,scale_overlap_reason='Baseline criticality already reflects this reach.'))['final_tier']=='T3'


def test_tier2_needs_critical_consequence_not_just_counts_and_override_has_a_reason():
    i=intake(data_types=('Health data (PHI)',),data_volume_records=100001)
    assert decision(i)['baseline_tier']=='T2' and decision(i)['final_tier']=='T2'
    assert decision(replace(i,critical_consequence=True,critical_consequence_reason='Synthetic critical confidentiality consequence under policy.'))['final_tier']=='T1'
    with pytest.raises(ValueError,match='Explain'):replace(i,critical_consequence=True)
    # Critical consequences can independently require reassessment from any tier.
    low=intake(access='None',criticality='Limited',critical_consequence=True,critical_consequence_reason='Synthetic essential service consequence.')
    assert decision(low)['final_tier']=='T1'


def test_high_records_with_few_users_and_public_records_without_material_dependency():
    assert decision(intake(data_volume_records=100001,active_client_users=3,workforce_size=10000))['final_tier']=='T2'
    public=intake(data='Public',data_types=('Public data',),data_volume_records=10**9,criticality='Limited',access='None')
    assert not decision(public)['candidate_scale_uplift']
    adoption=replace(public,active_client_users=1000,workforce_size=2000)
    assert not decision(adoption)['candidate_scale_uplift']
    assert decision(replace(adoption,service_dependency='Material operational disruption'))['candidate_scale_uplift']


@pytest.mark.parametrize('users,workforce,expected', [(0,None,0),(99,1000,1),(100,10000,2),(999,10000,2),(1000,None,3),(10,20,3),(10,None,None),(None,10000,None)])
def test_absolute_and_relative_adoption_boundaries(users, workforce, expected):
    assert adoption_band(policy(),users,workforce)==expected


@pytest.mark.parametrize('count,expected', [(0,0),(1000,1),(1001,2),(100000,2),(100001,3),(None,None)])
def test_record_boundaries(count, expected):assert volume_band(policy(),count)==expected


def test_weighted_method_charges_scale_once_without_uplift_and_gates_public_records():
    p=policy(strategy='weighted')
    m=build_assessment(intake(p,data_volume_records=100001,active_client_users=1000,workforce_size=2000))
    d=m.customer_context['tier_decision']
    assert m.inherent_score==51 and d['baseline_tier']=='T3' and d['final_tier']=='T2'
    assert d['score_tier']=='T2'
    assert m.customer_context['exposure_scope']['data_volume_points_applied']==10
    public=build_assessment(intake(p,data='Public',data_types=('Public data',),criticality='Limited',access='None',data_volume_records=10**9))
    assert public.customer_context['exposure_scope']['data_volume_points_applied']==0


def test_unknown_scale_and_critical_condition_are_provisional_not_known_low():
    d=decision(intake(data_volume_records=100001,active_client_users=3,workforce_size=None,scale_already_counted=None,critical_consequence=None))
    assert d['provisional'] and len(d['missing_inputs'])==3
    with pytest.raises(ValueError):intake(active_client_users=101,workforce_size=100)
    with pytest.raises(ValueError):intake(scale_already_counted=True)


def test_profiles_are_separate_immutable_versioned_and_assessments_keep_snapshot():
    registry=MethodologyRegistry();a=policy();registry.publish(a,'org-a')
    bdef=default_definition('org-b');bdef['volume']['moderate_max']=200000
    b=OrganizationMethodology.from_dict(bdef);registry.publish(b,'org-b')
    assert decision(intake(a,data_volume_records=100001))['final_tier']=='T2'
    assert decision(intake(b,data_volume_records=100001))['final_tier']=='T3'
    with pytest.raises(ValueError):registry.publish(b,'org-a')
    with pytest.raises(ValueError):replace(intake(a),methodology=b)
    changed=a.definition;changed['volume']['moderate_max']=300000
    with pytest.raises(ValueError,match='new version'):registry.publish(OrganizationMethodology.from_dict(changed),'org-a')
    original=build_assessment(intake(a,data_volume_records=100001));done=complete_review(original,())
    changed['version']='2';registry.publish(OrganizationMethodology.from_dict(changed),'org-a')
    assert original.customer_context['methodology_snapshot']['version']=='1'
    assert completion_is_current(original,(),done)
    later=build_assessment(intake(registry.get('org-a'),data_volume_records=100001))
    assert later.customer_context['tier_decision']['final_tier']=='T3'
    assert not completion_is_current(later,(),done)
    copy=a.definition;copy['volume']['moderate_max']=999999
    assert a.definition['volume']['moderate_max']==100000


def test_custom_requirements_criteria_freshness_and_policy_file_survive_export():
    d=default_definition();d['requirements'].append({'id':'CUSTOM-01','title':'Customer custom requirement','domain':'Custom manual',
        'tiers':['T2','T3'],'criteria':'Require an in-scope synthetic control report.','max_age_days':17,'evidence_kinds':['test']})
    p=OrganizationMethodology.from_dict(d);i=intake(p)
    m=build_assessment(i);row=next(r for r in m.worklist.rows if r.requirement_id=='CUSTOM-01')
    assert not row.specialist_available and row.outcome=='Evidence Missing'
    assert row.requirement.max_age_days==17 and row.requirement.policy_version=='1'
    h=record_action(m,(),'CUSTOM-01','Create Finding','Synthetic manual review pending.')
    with ZipFile(BytesIO(package_bytes(m,h,complete_review(m,h)))) as z:
        config=z.read('methodology.json');report=json.loads(z.read('report.json'))
        assert sha256(config).hexdigest()==p.fingerprint==report['assessment_context']['methodology_sha256']
        assert json.loads(config)==p.definition
        assert 'Captured methodology configuration' in z.read('summary.html').decode()
        assert report['risk']['residual_score'] is None and not report['review_completion']['vendor_approved']
        assert not report['findings'][0]['resolved']


def test_typed_thresholds_freshness_and_evidence_kinds_use_captured_configuration():
    d=default_definition();d['assurance']['tls_minimum_version']=13
    rule=next(r for r in d['requirements'] if r['id']=='ENC-01');rule['max_age_days']=30;rule['evidence_kinds']=['test']
    i=intake(OrganizationMethodology.from_dict(d));observed=i.as_of-timedelta(days=60)
    content=f'Configuration export\nService: {i.service}\nEnvironment: production\nObservation date: {observed.isoformat()}\nListener 443: TLS 1.2 is enabled.\n'.encode()
    u=read_upload(i,'synthetic.txt',content,('ENC-01',),kind='configuration',observed_on=observed)
    m=build_assessment(i,(u,));e=next(e for e in m.customer_context['evaluations'] if e['requirement_id']=='ENC-01')
    assert 'TLS 1.3' in e['threshold']
    assert e['facts'] and not any(f['eligible_for_preview'] for f in e['facts'])
    assert any('not accepted' in s for s in e['sources'][0]['uncertainties'])
    with pytest.raises(ValueError):build_assessment(i,tls_threshold=object())


@pytest.mark.parametrize('change', [
    lambda d:d.update(unknown=1),lambda d:d['weights']['system'].update(Unknown=0),
    lambda d:d['weights']['dependency'].update({'No operational dependency':1}),
    lambda d:d['tier_thresholds'].update(T2=20),lambda d:d['adoption'].update(high_percent=0),
    lambda d:d['requirements'].append(d['requirements'][0]),lambda d:d['requirements'][0].update(tiers=[{}]),
    lambda d:d['volume'].update(points=[0,5,2,10]),lambda d:d['assurance'].update(tls_minimum_version=10),
    lambda d:d['requirements'].clear(),lambda d:d['uplift'].update(critical_override='yes'),
])
def test_invalid_policy_is_rejected_without_registry_change(change):
    registry=MethodologyRegistry();p=policy();registry.publish(p,'org-a');d=p.definition;change(d)
    with pytest.raises(ValueError):OrganizationMethodology.from_dict(d)
    assert registry.get('org-a').fingerprint==p.fingerprint


def test_duplicate_and_oversized_json_rejected():
    with pytest.raises(ValueError):OrganizationMethodology('{"schema":1,"schema":1}')
    with pytest.raises(ValueError):OrganizationMethodology(' '*131073)


def test_weighted_counts_alone_do_not_establish_critical_and_critical_baseline_gets_no_scale_points():
    p=policy(strategy='weighted')
    i=intake(p,data_types=('Health data (PHI)',),access='Privileged',criticality='Critical',data_volume_records=100001)
    m=build_assessment(i);d=m.customer_context['tier_decision']
    assert d['baseline_score']==70 and d['scored_subtotal']==80
    assert d['score_tier']=='T1' and d['final_tier']=='T2'
    assert m.inherent_rating=='High'
    assert decision(replace(i,critical_consequence=True,critical_consequence_reason='Synthetic critical consequence.'))['final_tier']=='T1'
    data=p.definition;data['weights']['data_types']['Health data (PHI)']=40
    critical=build_assessment(intake(OrganizationMethodology.from_dict(data),data_types=('Health data (PHI)',),access='Privileged',criticality='Critical',data_volume_records=100001))
    assert critical.customer_context['tier_decision']['baseline_tier']=='T1'
    assert critical.customer_context['exposure_scope']['data_volume_points_applied']==0


def test_custom_taxonomy_names_weights_and_unknown_requirement_titles_are_retained_safely():
    d=default_definition();d['weights']['data_types']['Organization secret']=30
    d['nonpublic_types'].append('Organization secret');d['tier_names']['T2']='<script>Elevated</script>'
    p=OrganizationMethodology.from_dict(d)
    m=build_assessment(intake(p,data_types=('Organization secret',)))
    assert m.inherent_score==61 and m.inherent_tier=='Tier 2 — <script>Elevated</script>'
    with ZipFile(BytesIO(package_bytes(m,(),complete_review(m,())))) as z:
        assert '<script>Elevated' not in z.read('summary.html').decode()
        assert '&lt;script&gt;Elevated' in z.read('summary.html').decode()
    row=next(r for r in d['requirements'] if r['id']=='DATA-01');row['title']='Organization data review';row['tiers']=[]
    unknown=build_assessment(intake(OrganizationMethodology.from_dict(d),access='None',criticality='Limited',data='Public',data_types=('Unknown',)))
    assert next(r for r in unknown.worklist.rows if r.requirement_id=='DATA-01').title=='Organization data review'


def test_organization_can_explicitly_configure_criticality_condition_without_false_reason():
    d=default_definition();d['uplift']['critical_condition_required']=False;d['uplift']['critical_override']=False
    i=intake(OrganizationMethodology.from_dict(d),data_types=('Health data (PHI)',),data_volume_records=100001)
    result=decision(i)
    assert result['final_tier']=='T1'
    assert 'permitting count-based criticality' in result['reason']
    assert not result['critical_consequence']
    unused=decision(replace(i,critical_consequence=None))
    assert 'critical consequence determination' not in unused['missing_inputs']


def test_adoption_requires_material_service_dependency_not_general_business_criticality():
    for strategy in ('scale_uplift','weighted'):
        p=policy(strategy=strategy)
        no_dependency=intake(p,active_client_users=1000,workforce_size=2000,data_volume_records=0)
        result=decision(no_dependency)
        assert not result['candidate_scale_uplift']
        assert result['final_tier']=='T3'
        assert build_assessment(no_dependency).inherent_score==41
        material=replace(no_dependency,service_dependency='Material operational disruption')
        assert decision(material)['final_tier']=='T2'
        unknown=replace(no_dependency,service_dependency='Unknown')
        assert not decision(unknown)['candidate_scale_uplift'] and decision(unknown)['provisional']


@pytest.mark.parametrize('field', ['rto_minutes','rpo_minutes'])
def test_recovery_objectives_are_bounded_before_profile_activation(field):
    registry=MethodologyRegistry();original=policy();registry.publish(original,'org-a')
    d=original.definition;d['version']='2';d['assurance'][field]=2**53
    with pytest.raises(ValueError):registry.publish(OrganizationMethodology.from_dict(d),'org-a')
    assert registry.get('org-a').fingerprint==original.fingerprint
