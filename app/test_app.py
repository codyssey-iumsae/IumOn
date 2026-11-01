import copy
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from analysis import validate_analysis,validate_tree,valid_evidence,money_in_quote,documents,fingerprint,cache_set
import batch
import db
from engine import create,merge,assess,eval_tree,application_access,application_period,next_questions,finalize,semantic_merge,load_catalog,personalize
from server import Profile,RecommendRequest,QUESTION_BANK,BASIC_QUESTIONS,status
from journey import understand_story,prepare,intake_plan

PROFILE={'age':72,'region':'청양군','priority':'건강','needs':['건강'],'household':'alone','income':'unknown',
         'mobility':'no','digital':'yes','answered':['age','household']}
def policy(**kw):
    p={'id':'gov-x','title':'어르신 건강 지원','scope':'청양군','agency':'청양군',
       'summary':'어르신 건강 지원','target':'청양군 거주 만 70세 이상 또는 만 65세 이상 생계급여 수급자',
       'criteria':'','benefit':'매월 최대 3만원 지원','method':'방문 또는 온라인 신청',
       'period':'상시신청','phone':'','url':'','updated':'20261031','topics':['건강'],
       'senior':True,'conditions':{},'conflicts':[],
       'sources':[{'source':'gov','label':'정부24','id':'x'}]}
    p.update(kw);return p
def evidence(field='target',quote='만 70세 이상'):return {'field':'v0.'+field,'quote':quote}
def atom(field='age',cmp='gte',value=70,quote='만 70세 이상'):
    return {'op':'condition','field':field,'cmp':cmp,'value':value,'label':field,'evidence':evidence(quote=quote)}
def analysis(**kw):
    a={'senior_possible':True,'audience_evidence':evidence(),'topics':['건강'],
       'eligibility':atom(),'complete':True,
       'benefit':{'kind':'cash','amount_krw':30000,'cycle':'monthly','duration':'','copayment':'',
                  'description':'월 최대 3만원','evidence':evidence('benefit','매월 최대 3만원 지원')},
       'routes':[{'kind':'visit','evidence':evidence('method','방문')},
                 {'kind':'online','evidence':evidence('method','온라인 신청')}],
       'application':{'state':'always','start':None,'end':None,'evidence':evidence('period','상시신청')},'notes':[]}
    a.update(kw);return a

class GroundedTests(unittest.TestCase):
    def test_under65_rejected(self):
        with self.assertRaises(ValueError):Profile(age=64)
    def test_age65_accepted(self):
        self.assertEqual(Profile(age=65).age,65)
    def test_age69_accepted(self):
        self.assertEqual(Profile(age=69).age,69)
    def test_story_cannot_invent_evidence(self):
        with patch('journey.chat_json',return_value={'issues':[{'label':'의료비 부담','topic':'건강','evidence':'암 진단'}]}):
            self.assertEqual(understand_story('병원에 가는 택시비가 부담돼요.')['issues'],[])
    def test_story_understanding_needs_confirmation(self):
        with patch('journey.chat_json',return_value={'issues':[{'label':'이동 비용이 부담돼요','topic':'이동','evidence':'택시비가 부담돼요'}]}):
            r=understand_story('병원에 가는 택시비가 부담돼요.')
        self.assertTrue(r['requires_confirmation']);self.assertEqual(r['issues'][0]['topic'],'이동')
    def test_story_evidence_outer_quotes_accepted(self):
        with patch('journey.chat_json',return_value={'issues':[{'label':'이동비 부담','topic':'이동','evidence':'"택시비가 부담돼요"'}]}):
            self.assertEqual(len(understand_story('택시비가 부담돼요.')['issues']),1)
    def test_preparation_does_not_invent_documents(self):
        p=assess(policy(),PROFILE,analysis())
        r=prepare(p,PROFILE)
        self.assertEqual(r['documents_status'],'unknown');self.assertEqual(r['documents'],[])
        self.assertTrue(any('서류' in q for q in r['questions']))
    def test_preparation_preserves_official_documents(self):
        p=assess(policy(documents='신청서 1부'),PROFILE,analysis())
        r=prepare(p,{**PROFILE,'story_summary':['병원비가 부담돼요']})
        self.assertEqual(r['documents'][0]['text'],'신청서 1부')
        self.assertIn('병원비가 부담돼요',r['consultation_note'])
    def test_invalid_region_rejected(self):
        with self.assertRaises(ValueError):Profile(age=72,region='서울')
    def test_old_weights_api_rejected(self):
        with self.assertRaises(ValueError):RecommendRequest(profile=PROFILE,weights={'ease':100})
    def test_verified_quote(self):self.assertIsNotNone(valid_evidence(evidence(),documents(policy())))
    def test_invented_quote_rejected(self):self.assertIsNone(valid_evidence(evidence(quote='무조건 지원'),documents(policy())))
    def test_whitespace_quote_rejected(self):self.assertIsNone(valid_evidence(evidence(quote=' '),documents(policy())))
    def test_fabricated_cutoff_unknown(self):
        self.assertEqual(validate_tree(atom(value=75),documents(policy()))['op'],'unknown')
    def test_number_substring_not_accepted(self):
        self.assertEqual(validate_tree(atom(value=7),documents(policy()))['op'],'unknown')
    def test_money_validation(self):
        self.assertTrue(money_in_quote(30000,'월 3만원'))
        self.assertFalse(money_in_quote(300000,'월 3만원'))
    def test_unverified_money_removed(self):
        a=analysis();a['benefit']['amount_krw']=999999
        self.assertIsNone(validate_analysis(a,policy())['benefit']['amount_krw'])
    def test_invented_route_removed(self):
        a=analysis();a['routes']=[{'kind':'phone','evidence':evidence('method','전화 신청')}]
        self.assertEqual(validate_analysis(a,policy())['routes'],[])
    def test_hallucinated_period_removed(self):
        a=analysis();a['application']={'state':'dated','start':'2026-01-01','end':'2026-12-31','evidence':evidence('period','상시신청')}
        self.assertEqual(validate_analysis(a,policy())['application']['state'],'unknown')
    def test_and_unknown(self):
        t={'op':'all','children':[atom(),{'op':'unknown','label':'재산'}]}
        self.assertEqual(eval_tree(t,PROFILE)['state'],'unknown')
    def test_or_match_not_and(self):
        t={'op':'any','children':[atom(),atom(field='income',cmp='eq',value='basic')]}
        self.assertEqual(eval_tree(t,PROFILE)['state'],'match')
    def test_unknown_not_mismatch(self):
        self.assertEqual(eval_tree(atom(field='disability',cmp='eq',value='yes'),PROFILE)['state'],'unknown')
    def test_llm_audience_hint_cannot_exclude(self):
        r=assess(policy(),PROFILE,analysis(senior_possible=False,eligibility={'op':'unknown','label':'수급 여부 확인'}))
        self.assertNotEqual(r['group'],'excluded')
    def test_loan_not_compared_as_cash_grant(self):
        self.assertEqual(validate_analysis(analysis(),policy(title='노후긴급자금 대부사업'))['benefit']['kind'],'loan')
    def test_other_region_mismatch(self):
        self.assertEqual(eval_tree(atom(field='region',cmp='eq',value='서울특별시'),PROFILE)['state'],'mismatch')
    def test_province_region_match(self):
        self.assertEqual(eval_tree(atom(field='region',cmp='eq',value='충청남도'),PROFILE)['state'],'match')
    def test_basic_not_livelihood(self):
        self.assertEqual(eval_tree(atom(field='livelihood',cmp='eq',value='yes'),{**PROFILE,'income':'basic'})['state'],'unknown')
    def test_access_is_not_eligibility(self):
        a=analysis(routes=[{'kind':'visit','evidence':evidence('method','방문')}])
        result=assess(policy(),{**PROFILE,'mobility':'yes'},a)
        self.assertEqual(result['eligibility_state'],'match')
        self.assertEqual(result['group'],'assistance')
    def test_alternative_application_path(self):
        r=application_access(analysis()['routes'],{**PROFILE,'mobility':'yes','digital':'yes'})
        self.assertEqual(r['state'],'available')
        self.assertEqual(r['available'][0]['kind'],'online')
    def test_proxy_not_assumed_available(self):
        self.assertEqual(application_access([{'kind':'proxy'}],PROFILE)['state'],'unknown')
    def test_unknown_does_not_lower_rank(self):
        a=analysis();p1=assess(policy(id='a'),PROFILE,a);p2=assess(policy(id='b'),{**PROFILE,'age':None},a)
        self.assertEqual([p['id'] for p in finalize([p1,p2],PROFILE)],['a','b'])
        self.assertNotIn('scores',p2)
    def test_mobility_never_changes_ranking(self):
        a=analysis();ps=[policy(id='a'),policy(id='b',title='다른 건강 지원')]
        p1=finalize([assess(p,PROFILE,a) for p in ps],PROFILE)
        p2=finalize([assess(p,{**PROFILE,'mobility':'yes','digital':'no'},a) for p in ps],PROFILE)
        self.assertEqual([p['id'] for p in p1],[p['id'] for p in p2])
    def test_incomplete_kept_unknown(self):
        r=assess(policy(),PROFILE,analysis(complete=False))
        self.assertEqual(r['eligibility_state'],'unknown')
        self.assertEqual(r['group'],'check')
    def test_missing_veteran_condition_not_claimed_matching(self):
        p=policy(target='청양군 거주 만 70세 이상 참전유공자')
        a=validate_analysis(analysis(),p)
        r=assess(p,PROFILE,a)
        self.assertEqual(r['group'],'check')
        self.assertTrue(any(c.get('field')=='veteran' for c in r['checks']))
    def test_invented_route_kind_rejected(self):
        a=analysis();a['routes']=[{'kind':'phone','evidence':evidence('method','방문')}]
        self.assertEqual(validate_analysis(a,policy())['routes'],[])
    def test_conflicting_sources_not_auto_eligible(self):
        self.assertEqual(assess(policy(conflicts=['연령 상충']),PROFILE,analysis())['eligibility_state'],'unknown')
    def test_no_repeat_unknown_answer(self):
        r=assess(policy(),PROFILE,analysis(eligibility=atom(field='disability',cmp='eq',value='yes')))
        qs=next_questions([r],{**PROFILE,'answered':['disability','mobility','digital']},QUESTION_BANK)
        self.assertFalse(any(q['field']=='disability' for q in qs))
    def test_dont_ask_other_or_branch(self):
        a=analysis(eligibility={'op':'any','children':[atom(),atom(field='disability',cmp='eq',value='yes')]})
        r=assess(policy(),PROFILE,a)
        self.assertFalse(any(q['field']=='disability' for q in next_questions([r],PROFILE,QUESTION_BANK)))
    def test_no_child_title_blacklist(self):
        p=create('gov',{'서비스ID':'x','서비스명':'조손가정 아동 양육 지원','소관기관명':'충청남도 청양군','소관기관유형':'지방자치단체','사용자구분':'개인'})
        self.assertIsNotNone(p)
    def test_exact_duplicate_keeps_versions(self):
        a,b=policy(),policy(id='national-y',sources=[{'source':'national','label':'복지로','id':'y'}])
        r=merge([a,b]);self.assertEqual(len(r),1);self.assertEqual(len(r[0]['versions']),2)
    def test_local_addition_not_merged(self):
        self.assertEqual(len(merge([policy(),policy(scope='충청남도')])),2)
    def test_dedup_supplement_preserved(self):
        a,b=policy(),policy(id='b',title='어르신 건강 지원 추가사업')
        with patch('engine.cache_get',return_value={'relation':'supplement','reason':'추가지원'}):
            r,relations=semantic_merge([a,b],False)
        self.assertEqual(len(r),2)
    def test_cache_invalidates_on_text_change(self):
        self.assertNotEqual(fingerprint(policy()),fingerprint(policy(benefit='연 10만원')))
    def test_explicit_closed_period(self):
        a=analysis(application={'state':'dated','start':'2025-01-01','end':'2025-12-31','evidence':evidence()})
        self.assertEqual(application_period(policy(),a,'2026-10-31')['state'],'closed')
    def test_undated_period_not_fabricated(self):
        self.assertEqual(application_period(policy(),analysis(application={'state':'unknown'}))['state'],'unknown')
    def test_real_sources_available(self):
        catalog,meta=load_catalog();self.assertTrue(catalog)
        self.assertTrue({'gov_list','national','local'}<=meta['counts'].keys())
        self.assertTrue(all(p.get('versions') for p in catalog))
    def test_ai_cannot_promote_unknown_to_confirmed(self):
        p=assess(policy(),PROFILE,analysis(complete=False))
        response={'items':[{'id':p['id'],'state':'match','reason':'연령 기준을 확인했어요.','evidence':evidence()}]}
        with patch('engine.chat_json',return_value=response) as model:
            personalize([p],PROFILE)
            self.assertNotIn('mobility',model.call_args.args[1]['user'])
            self.assertNotIn('digital',model.call_args.args[1]['user'])
        self.assertEqual(p['eligibility_state'],'unknown')
        self.assertEqual(p['group'],'check')
    def test_ai_rule_disagreement_stays_unknown(self):
        p=assess(policy(),PROFILE,analysis())
        response={'items':[{'id':p['id'],'state':'unknown','reason':'추가 조건 확인이 필요해요.','evidence':evidence()}]}
        with patch('engine.chat_json',return_value=response):personalize([p],PROFILE)
        self.assertEqual(p['eligibility_state'],'unknown')
    def test_existing_pension_separate_from_new_recommendations(self):
        r=assess(policy(title='기초연금'),{**PROFILE,'pension':'yes'},analysis())
        self.assertEqual(r['group'],'receiving')


    def test_knee_questions_precede_basic_eligibility(self):
        issues=[{'label':'무릎이 아파요','topic':'건강'},{'label':'택시비 부담','topic':'이동'}]
        r=intake_plan(issues,'0',QUESTION_BANK,BASIC_QUESTIONS)
        self.assertEqual([q['field'] for q in r['questions']],['knee_care','age','town'])
        self.assertEqual(r['focus_summary'],['무릎이 아파요'])
    def test_mobility_focus_asks_transport_first(self):
        issues=[{'label':'무릎이 아파요','topic':'건강'},{'label':'택시비 부담','topic':'이동'}]
        r=intake_plan(issues,'1',QUESTION_BANK,BASIC_QUESTIONS)
        self.assertEqual([q['field'] for q in r['questions']],['transport_mode','age','town'])
    def test_all_and_unknown_intake_options(self):
        issues=[{'label':'무릎이 아파요','topic':'건강'},{'label':'택시비 부담','topic':'이동'}]
        for selected in ('all','unknown'):
            r=intake_plan(issues,selected,QUESTION_BANK,BASIC_QUESTIONS)
            self.assertEqual(len(r['focus_summary']),2)
            self.assertEqual(r['priority_mode'],selected)
    def test_story_quote_retains_specific_problem(self):
        r=intake_plan([{'label':'병원에 가기 어려움','topic':'건강','evidence':'무릎이 아파요'}],'0',QUESTION_BANK,BASIC_QUESTIONS)
        self.assertIn('무릎',r['focus_summary'][0])
        self.assertEqual(r['questions'][0]['field'],'knee_care')
    def test_knee_before_eye_regardless_of_amount(self):
        user={**PROFILE,'focus_summary':['무릎 치료비가 필요해요']}
        knee=assess(policy(id='knee',title='노인 무릎인공관절 수술 지원'),user,analysis())
        eye=assess(policy(id='eye',title='노인 개안수술비 지원'),user,analysis())
        eye['benefit_info']['amount_krw']=99999999
        self.assertEqual(finalize([eye,knee],user)[0]['id'],'knee')
        self.assertEqual(knee['eligibility_state'],'unknown')
    def test_criteria_questions_ignore_unrelated_policies_and_access(self):
        user={**PROFILE,'focus_summary':['무릎 치료비가 필요해요']}
        knee=assess(policy(id='knee',title='노인 무릎인공관절 수술 지원'),user,analysis())
        unrelated=assess(policy(id='vet',title='보훈 지원'),user,analysis(eligibility=atom(field='veteran',cmp='eq',value='yes')))
        qs=next_questions([knee,unrelated],user,QUESTION_BANK)
        self.assertNotIn('veteran',[q['field'] for q in qs])
        self.assertNotIn('mobility',[q['field'] for q in qs])
    def test_application_preparation_uses_latest_access_answers(self):
        p=assess(policy(),PROFILE,analysis(routes=[{'kind':'visit','evidence':evidence('method','방문')}]))
        r=prepare(p,{**PROFILE,'mobility':'yes'})
        self.assertTrue(any('이용하기 어렵' in q for q in r['questions']))

    def test_status_towns_are_the_accepted_profile_towns(self):
        towns=status()['towns']
        self.assertIn('정산면',towns)
        for town in towns:self.assertEqual(Profile(age=72,town=town).town,town)
        with self.assertRaises(ValueError):Profile(age=72,town='서면')
    def test_own_town_policy_ranks_above_county_wide(self):
        user={**PROFILE,'town':'정산면'}
        town=assess(policy(id='z-town',target='청양군 정산면 거주 만 70세 이상'),user,analysis())
        ranked=finalize([assess(policy(id='a-county'),user,analysis()),town],user)
        self.assertEqual([p['id'] for p in ranked],['z-town','a-county'])
        self.assertEqual(ranked[0]['region_fit'],'here')
    def test_other_town_policy_needs_check_not_mismatch(self):
        user={**PROFILE,'town':'운곡면'}
        town=assess(policy(id='a-town',target='청양군 정산면 거주 만 70세 이상'),user,analysis())
        self.assertEqual((town['region_fit'],town['eligibility_state']),('elsewhere','unknown'))
        ranked=finalize([town,assess(policy(id='z-county'),user,analysis())],user)
        self.assertEqual([p['id'] for p in ranked],['z-county','a-town'])
    def test_town_named_only_as_exclusion_claims_nothing(self):
        p=policy(target='청양읍을 제외한 면 지역 거주 만 70세 이상')
        for town in ('청양읍','정산면'):
            r=assess(p,{**PROFILE,'town':town},analysis())
            self.assertEqual((r['region_fit'],r['eligibility_state']),('청양군','match'))
    def test_town_name_inside_another_word_is_not_a_town(self):
        p=policy(criteria='진료비 본인부담 항목면제, 연말정산면제 대상')
        self.assertEqual(assess(p,{**PROFILE,'town':'운곡면'},analysis())['region_fit'],'청양군')
        self.assertEqual(assess(policy(target='청양군목면 거주'),{**PROFILE,'town':'목면'},analysis())['region_fit'],'here')
    def test_town_region_condition_compares_user_town(self):
        node=atom(field='region',cmp='eq',value='청양군 정산면',quote='정산면')
        states=[eval_tree(node,{**PROFILE,'town':t})['state'] for t in ('정산면','운곡면','unknown')]
        self.assertEqual(states,['match','mismatch','unknown'])
        self.assertNotEqual(eval_tree(atom(field='region',cmp='eq',value='청양읍'),{**PROFILE,'town':'청양읍'})['state'],'mismatch')
    def test_town_condition_without_town_name_stays_unknown(self):
        self.assertEqual(eval_tree(atom(field='town',cmp='eq',value='면 지역'),{**PROFILE,'town':'정산면'})['state'],'unknown')
    def test_story_words_rank_beyond_synonym_table(self):
        user={**PROFILE,'focus_summary':['보청기가 필요해요']}
        hearing=assess(policy(id='hear',title='보청기 구입비 지원'),user,analysis())
        teeth=assess(policy(id='teeth',title='노인 틀니 지원'),user,analysis())
        self.assertEqual([p['id'] for p in finalize([teeth,hearing],user)],['hear','teeth'])
    def test_direct_need_outranks_confirmed_unrelated_policy(self):
        user={**PROFILE,'focus_summary':['보청기가 필요해요']}
        hearing=assess(policy(id='hear',title='보청기 구입비 지원'),user,analysis(complete=False))
        job=assess(policy(id='job',title='노인 일자리 지원',topics=['일자리']),user,analysis(topics=['일자리']))
        self.assertEqual((hearing['eligibility_state'],job['eligibility_state']),('unknown','match'))
        self.assertEqual([p['id'] for p in finalize([job,hearing],user)],['hear','job'])
    def test_open_application_breaks_ties(self):
        always=assess(policy(id='always'),PROFILE,analysis())
        unknown=assess(policy(id='unknown',title='가 건강 지원'),PROFILE,analysis(application={'state':'unknown'}))
        self.assertEqual([p['id'] for p in finalize([unknown,always],PROFILE)],['always','unknown'])
    def test_preparation_note_names_town(self):
        user={**PROFILE,'town':'정산면'}
        r=prepare(assess(policy(),user,analysis()),user)
        self.assertIn('청양군 정산면에 거주하는 만 72세입니다.',r['consultation_note'])
    def test_preparation_names_office_only_when_source_does(self):
        user={**PROFILE,'town':'정산면'}
        office=policy(method='주소지 행정복지센터 방문 신청')
        r=prepare(assess(office,user,analysis()),user)
        self.assertEqual(r['office'],'정산면 행정복지센터')
        self.assertIn('정산면 행정복지센터',r['next_action'])
        self.assertEqual(prepare(assess(office,PROFILE,analysis()),PROFILE)['office'],'주소지 읍·면 행정복지센터')
        self.assertIsNone(prepare(assess(policy(),user,analysis()),user)['office'])

class BatchPipelineTests(unittest.TestCase):
    """Daily batch writes the store; requests only read it. Each test uses its own temporary database."""
    def setUp(self):
        import tempfile,engine
        self.tmp=tempfile.TemporaryDirectory()
        self.patches=[patch('db.PATH',Path(self.tmp.name)/'iumon.sqlite3'),patch('batch._migrated',True),
                      patch('batch.LOCK',Path(self.tmp.name)/'.refresh.lock')]
        for x in self.patches:x.start()
        engine._load.cache_clear()
    def tearDown(self):
        import engine
        for x in self.patches:x.stop()
        engine._load.cache_clear();self.tmp.cleanup()
    def publish(self,policies,relations=()):
        with db.connect() as conn:
            run_id=db.start_run(conn);db.publish(conn,run_id,policies,list(relations),{'collected_at':'2026-11-01T00:00:00+00:00','errors':[],'sources':{},'counts':{}})
        return run_id
    def test_recommendation_and_preparation_never_use_network(self):
        import server
        docs=[{'text':'신청서 1부','source':[{'source':'gov','label':'정부24','id':'x'}],'field':'정부24 상세.구비서류'}]
        self.publish([policy(official_documents=docs)])
        offline=AssertionError('network used during a request')
        with patch('urllib.request.urlopen',side_effect=offline),patch('engine.chat_json',side_effect=offline), \
             patch('analysis.chat_json',side_effect=offline):
            body=RecommendRequest(profile=PROFILE,consent=False,limit=6)
            server._jobs['t']={'state':'running','created':time.monotonic()}
            server.run_recommendation('t',body)
            job=server._jobs.pop('t')
            self.assertEqual(job['state'],'done')
            p=job['result']['policies'][0]
            self.assertEqual((p['analysis_state'],job['result']['meta']['analysis_failed']),('pending',1))
            self.assertEqual(prepare(p,PROFILE,fetch_documents=True)['documents'],docs)
        self.assertEqual(db.demand(),{'gov-x':1})
    def test_stored_analysis_is_used_without_network(self):
        import server
        self.publish([policy()])
        cache_set(fingerprint(policy()),'policy',analysis())
        with patch('urllib.request.urlopen',side_effect=AssertionError),patch('analysis.chat_json',side_effect=AssertionError):
            server._jobs['t']={'state':'running','created':time.monotonic()}
            server.run_recommendation('t',RecommendRequest(profile=PROFILE,limit=6))
            p=server._jobs.pop('t')['result']['policies'][0]
        self.assertEqual(p['analysis_state'],'grounded')
    def test_failed_publish_keeps_previous_catalog(self):
        first=self.publish([policy()])
        with self.assertRaises(KeyError):
            with db.connect() as conn:
                run_id=db.start_run(conn);db.publish(conn,run_id,[policy(id='new')],[{'a':'x'}],{})
        catalog,meta=load_catalog()
        self.assertEqual((meta['run_id'],[p['id'] for p in catalog]),(first,['gov-x']))
    def test_failed_or_empty_source_keeps_previous_rows(self):
        with db.connect() as conn:
            for name,_,_ in batch.SOURCES:db.replace_source(conn,name,[{'서비스ID':'old','servId':'old'}],'servId')
        client=type('Client',(),{'gov':staticmethod(lambda ep:[] if ep=='serviceList' else [{'서비스ID':'new'}]),
                                 'welfare':staticmethod(lambda local=False:(_ for _ in ()).throw(RuntimeError('down')))})
        with patch.dict('sys.modules',{'collect':client}):batch.collect()
        with db.connect() as conn:rows,status=db.source_rows(conn),db.source_status(conn)
        self.assertEqual(rows['gov_list'][0]['서비스ID'],'old');self.assertEqual(rows['gov_detail'][0]['서비스ID'],'new')
        self.assertEqual(rows['national'][0]['servId'],'old')
        self.assertEqual({k:v['state'] for k,v in status.items()},
                         {'gov_list':'stale','gov_conditions':'ok','gov_detail':'ok','national':'stale','local':'stale'})
    def test_detail_requests_respect_daily_budget(self):
        rows=[{'servId':f'N{i}','servNm':f'노인 지원 {i}','lastModYmd':'20261101'} for i in range(10)]
        with db.connect() as conn:db.replace_source(conn,'national',rows,'servId')
        calls=[]
        client=type('Client',(),{'detail':staticmethod(lambda source,sid:calls.append(sid) or {'servId':sid})})
        with patch.dict('sys.modules',{'collect':client}),patch.dict('os.environ',{'NATIONAL_DETAIL_DAILY_BUDGET':'9'}):
            batch.details();batch.details()
        self.assertEqual(len(calls),3)
    def test_official_documents_do_not_change_analysis_fingerprint(self):
        p=policy();before=fingerprint(p)
        batch.attach_official_documents([p],[{'서비스ID':'x','구비서류':'신청서'}])
        self.assertEqual((p['official_documents'][0]['text'],fingerprint(p)),('신청서',before))
    def test_ai_merge_is_independent_of_input_order(self):
        a=policy(id='gov-a',title='어르신 건강 지원');b=policy(id='gov-b',title='어르신 건강지원사업',benefit='월 3만원')
        with patch('engine.cache_get',return_value={'relation':'same','reason':'같은 사업'}):
            one,_=semantic_merge([a,b],False,None);two,_=semantic_merge([b,a],False,None)
        self.assertEqual((len(one),one[0]['id'],fingerprint(one[0])),(1,two[0]['id'],fingerprint(two[0])))
    def test_daily_schedule(self):
        kst=batch.KST;today=datetime(2026,11,2,5,tzinfo=kst)
        with patch.dict('os.environ',{'DATA_GO_KR_KEY':'k','AUTO_REFRESH':'1','BATCH_HOUR':'4'}), \
             patch('db.active_run',return_value=(1,{})):
            with patch('db.last_attempt',return_value=('2026-11-01T19:30:00+00:00','published')):
                self.assertFalse(batch.due(today))  # already ran at 04:30 KST today
            with patch('db.last_attempt',return_value=('2026-11-01T10:00:00+00:00','published')):
                self.assertTrue(batch.due(today))
                self.assertFalse(batch.due(today.replace(hour=3)))
        with patch.dict('os.environ',{'AUTO_REFRESH':'0','DATA_GO_KR_KEY':'k'}):self.assertFalse(batch.due(today))
    def test_batch_publishes_and_analyzes_with_limit(self):
        rows=[{'servId':f'N{i}','servNm':f'노인 지원 {i}','lastModYmd':'20261101'} for i in range(3)]
        with db.connect() as conn:
            db.replace_source(conn,'national',rows,'servId');db.set_source_status(conn,'national','ok',rows=3)
        with patch('analysis.chat_json',return_value=analysis()):
            batch.run(('publish','analyze'),llm_limit=2,dedup_limit=0)
        catalog,meta=load_catalog()
        self.assertEqual((len(catalog),meta['counts']),(3,{'national':3}))
        self.assertEqual(len(db.analyzed_keys()),2)
        self.assertFalse(batch.LOCK.exists())
    def test_rejected_key_stops_analysis_without_blaming_policies(self):
        from llm import ModelRejected
        rows=[{'servId':f'N{i}','servNm':f'노인 지원 {i}','lastModYmd':'20261101'} for i in range(5)]
        with db.connect() as conn:db.replace_source(conn,'national',rows,'servId')
        with patch('analysis.chat_json',side_effect=ModelRejected('denied',403)) as model:
            result=batch.run(('publish',),dedup_limit=0) or batch.analyze(5,workers=1)
        self.assertTrue(result['rejected']);self.assertEqual(db.failures(),{})
        self.assertLess(model.call_count,5)
    def test_merged_policy_is_analyzed_first_with_inherited_demand(self):
        merged=policy(id='gov-a',title='나 지원',merge_reason='AI 원문 비교: 같은 사업',senior=False,
                      sources=[{'source':'gov','label':'정부24','id':'a'},{'source':'national','label':'복지로','id':'b'}])
        self.publish([policy(id='gov-z',title='가 지원'),merged])
        db.record_demand(['national-b'])
        seen=[]
        with patch('analysis.chat_json',side_effect=lambda *a,**k:seen.append(a[1]['title']) or analysis()):
            batch.analyze(1,workers=1)
        self.assertEqual((seen,db.demand()),(['나 지원'],{}))

if __name__=='__main__':unittest.main(verbosity=2)
