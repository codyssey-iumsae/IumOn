"""Senior self-benefit recommendations must not be filled with school-pupil benefits."""
import unittest
from unittest.mock import patch
from engine import audience_exclusion, retrieve, assess
from test_app import policy, PROFILE


def school(**updates):
    return policy(**{'title':'초·중·고 교육비 지원','summary':'학교급식비·고교 학비 지원',
                     'target':'기준에 해당하는 학생','criteria':'소득 인정액 기준','senior':False,**updates})


class AudienceTests(unittest.TestCase):
    def test_school_tuition_is_removed_before_lexical_and_vector_search(self):
        child=school(id='child');adult=policy(id='adult')
        with patch('embeddings.rerank',side_effect=lambda catalog,profile,lexical:lexical) as vector:
            result=retrieve([child,adult],PROFILE)
        self.assertEqual([p['id'] for p in result],['adult'])
        self.assertEqual([p['id'] for p in vector.call_args.args[0]],['adult'])

    def test_school_meals_are_excluded_even_before_llm_analysis(self):
        for title,target in [('학교급식비 지원','저소득 초등학생'),('학교우유급식',''),
                             ('고등학교생 무상급식(조,석식) 지원','관내 고등학교 재학생'),
                             ('초중고 교육비 지원사업(고교학비 지원)','')]:
            with self.subTest(title=title),patch('engine.analyze',side_effect=AssertionError('LLM used')):
                result=assess(school(title=title,target=target),PROFILE)
                self.assertEqual(result['group'],'excluded')

    def test_generic_student_status_does_not_exclude_older_learners(self):
        for title,target in [('대학생 장학금','대학 재학생'),('방송통신고등학교','중학교 졸업자'),
                             ('혼합 장학금','초등학생 및 대학교 재학생'),
                             ('성인 학습자 교육비 지원','고등학교 재학생'),
                             ('교육급여','초등학교부터 학교 형태의 평생교육 시설에 재학하는 자')]:
            with self.subTest(title=title):
                self.assertIsNone(audience_exclusion(school(title=title,target=target),PROFILE))

    def test_school_venue_or_job_does_not_remove_senior_program(self):
        for title,target in [('어르신 급식 지원','65세 이상 노인'),('학교급식 조리원 일자리','급식 종사자'),
                             ('무료 식사 지원','주민센터 방문자')]:
            p=policy(title=title,target=target,criteria='',summary='초등학교에서 진행')
            self.assertIsNone(audience_exclusion(p,PROFILE))

    def test_unknown_or_mixed_source_audiences_are_preserved(self):
        self.assertIsNone(audience_exclusion(policy(versions=[school(),policy()]),PROFILE))
        self.assertIsNone(audience_exclusion(policy(title='생활비 지원',target='',criteria=''),PROFILE))
        self.assertIsNotNone(audience_exclusion(policy(versions=[school(),school()]),PROFILE))

    def test_guard_applies_to_senior_self_search_only(self):
        self.assertIsNone(audience_exclusion(school(),{'age':17}))
        self.assertIsNone(audience_exclusion(school(),{}))

    def test_student_exclusions_and_mixed_beneficiaries_do_not_exclude_adults(self):
        for title,target,criteria in [
            ('국민내일배움카드','국민 누구나','지원 제외: 고등학생'),
            ('농식품바우처 지원','아동·초등학생과 노인을 포함한 저소득 가구',''),
            ('무료 관람','어린이, 초등학생, 만 65세 이상 국민',''),
            ('학부모온누리','초중고 학생 학부모',''),
            ('장애학생 가족 참여 국외체험 연수 지원','초등학생 및 가족','')]:
            with self.subTest(title=title):
                self.assertIsNone(audience_exclusion(policy(title=title,target=target,criteria=criteria),PROFILE))
