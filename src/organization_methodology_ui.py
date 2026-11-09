"""Session-only organization configuration, separate from requester intake."""
import streamlit as st
from src.organization_methodology import OrganizationMethodology, MethodologyRegistry, default_definition, MAX_POLICY_BYTES

KEY='pilot_methodology:'


def render_methodology_settings():
    if KEY+'registry' not in st.session_state:
        registry=MethodologyRegistry();policy=OrganizationMethodology.from_dict(default_definition())
        registry.publish(policy,'pilot-default');st.session_state[KEY+'registry']=registry
    registry=st.session_state[KEY+'registry']
    pending=st.session_state.pop(KEY+'pending_org',None)
    if pending:st.session_state[KEY+'selected']=pending
    with st.sidebar.expander('Organization methodology',expanded=False):
        st.info('Synthetic pilot configuration · session memory only. This is not production tenant administration or an authorization boundary. Export settings to reuse them in another session.')
        selected=st.selectbox('Pilot organization',registry.organizations+('Create pilot organization',),key=KEY+'selected')
        creating=selected=='Create pilot organization'
        target=st.text_input('New pilot organization ID',max_chars=80,key=KEY+'new_org') if creating else selected
        current=OrganizationMethodology.from_dict(default_definition('new-pilot')) if creating else registry.get(selected)
        d=current.definition;prefix=KEY+selected+':'+current.fingerprint+':'
        st.caption('Active version: '+d['version']+' · '+d['strategy'])
        st.download_button('Download methodology JSON',current.json_text,'lma_methodology.json',mime='application/json',key=prefix+'download')
        mode=st.radio('Configure methodology',('Common settings','Import full configuration'),key=prefix+'mode')
        candidate=None
        if mode=='Common settings':
            version=st.text_input('New methodology version',value=d['version']+'.next',max_chars=80,key=prefix+'version')
            strategy=st.selectbox('Tiering method',('scale_uplift','weighted'),index=('scale_uplift','weighted').index(d['strategy']),key=prefix+'strategy',
                format_func=lambda v:'Single scale uplift (default)' if v=='scale_uplift' else 'Weighted scoring — no scale uplift')
            st.caption('Changing settings affects future assessments only. Full configuration also includes data weights, requirement criteria, evidence types and freshness.')
            with st.expander('Adoption and record bands'):
                low_users=st.number_input('Low adoption: fewer than users',min_value=1,max_value=10**12,value=d['adoption']['low_count'],key=prefix+'ul')
                high_users=st.number_input('High adoption: at least users',min_value=1,max_value=10**12,value=d['adoption']['high_count'],key=prefix+'uh')
                low_pct=st.number_input('Low adoption: workforce percent below',min_value=1,max_value=100,value=d['adoption']['low_percent'],key=prefix+'pl')
                high_pct=st.number_input('High adoption: workforce percent at least',min_value=1,max_value=100,value=d['adoption']['high_percent'],key=prefix+'ph')
                days=st.number_input('Active-user measurement days',min_value=1,max_value=3650,value=d['adoption']['window_days'],key=prefix+'days')
                low_records=st.number_input('Low record volume: maximum records',min_value=1,max_value=10**12,value=d['volume']['low_max'],key=prefix+'rl')
                moderate_records=st.number_input('Moderate record volume: maximum records',min_value=1,max_value=10**12,value=d['volume']['moderate_max'],key=prefix+'rm')
            with st.expander('Tier boundaries and supported assurance thresholds'):
                cutoffs={t:st.number_input(t+' minimum baseline score',min_value=1,max_value=100,value=d['tier_thresholds'][t],key=prefix+t) for t in ('T3','T2','T1')}
                tls=st.selectbox('Minimum TLS version',(12,13),index=(12,13).index(d['assurance']['tls_minimum_version']),format_func=lambda n:f'TLS {n//10}.{n%10}',key=prefix+'tls')
                tls_age=st.number_input('TLS evidence freshness days',min_value=1,max_value=3650,value=next(r['max_age_days'] for r in d['requirements'] if r['id']=='ENC-01'),key=prefix+'tls_age')
                interval=st.number_input('Recovery exercise interval days',min_value=1,max_value=3650,value=d['assurance']['dr_max_test_age_days'],key=prefix+'interval')
                rto=st.number_input('Maximum achieved RTO minutes (blank means not applicable)',min_value=0,value=d['assurance']['rto_minutes'],step=1,key=prefix+'rto')
                rpo=st.number_input('Maximum achieved RPO minutes (blank means not applicable)',min_value=0,value=d['assurance']['rpo_minutes'],step=1,key=prefix+'rpo')
            if st.button('Apply pilot methodology',key=prefix+'apply'):
                d.update(organization_id=target,version=version,strategy=strategy)
                d['adoption'].update(low_count=low_users,high_count=high_users,low_percent=low_pct,high_percent=high_pct,window_days=days)
                d['volume'].update(low_max=low_records,moderate_max=moderate_records)
                d['tier_thresholds'].update(cutoffs)
                d['assurance'].update(tls_minimum_version=tls,dr_max_test_age_days=interval,rto_minutes=rto,rpo_minutes=rpo)
                for r in d['requirements']:
                    if r['id']=='ENC-01':r['max_age_days']=tls_age
                    if r['id']=='BCP-01':r['max_age_days']=interval
                candidate=d
        else:
            st.caption('Import a complete exported JSON configuration for the selected pilot organization. A new version is required for changed settings; unknown fields and invalid definitions are rejected.')
            uploaded=st.file_uploader('Methodology JSON',type=['json'],key=prefix+'import',max_upload_size=1)
            if st.button('Apply imported methodology',disabled=uploaded is None,key=prefix+'import_apply'):
                try:
                    if uploaded.size>MAX_POLICY_BYTES:raise ValueError('Methodology exceeds the 128 KB limit.')
                    policy=OrganizationMethodology(uploaded.getvalue().decode('utf-8'))
                    registry.publish(policy,target)
                except (ValueError,UnicodeError) as exc:st.error(str(exc))
                else:
                    st.session_state[KEY+'pending_org']=target;st.rerun()
        if candidate is not None:
            try:
                policy=OrganizationMethodology.from_dict(candidate);registry.publish(policy,target)
            except ValueError as exc:st.error(str(exc))
            else:
                st.session_state[KEY+'pending_org']=target;st.rerun()
    return None if creating else registry.get(selected)
