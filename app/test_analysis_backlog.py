"""Regression tests for shared analysis, resumable backfill and usage accounting."""
from concurrent.futures import ThreadPoolExecutor
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import analysis as module
import batch
import db
import engine
from test_app import policy, analysis


class AnalysisBacklogTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for name,value in [('db.PATH',Path(self.tmp.name)/'store.sqlite3'),
                           ('batch.LOCK',Path(self.tmp.name)/'.refresh.lock'),('batch._migrated',True)]:
            mock=patch(name,value);mock.start();self.addCleanup(mock.stop)
        engine._load.cache_clear();self.addCleanup(engine._load.cache_clear)

    def publish(self,p):
        with db.connect() as conn:
            run=db.start_run(conn);db.publish(conn,run,[p],[],{})

    def test_simultaneous_requests_share_one_paid_analysis(self):
        def respond(*args,**kwargs):
            time.sleep(.08)
            return analysis()
        with patch('analysis.chat_json',side_effect=respond) as model,ThreadPoolExecutor(max_workers=6) as pool:
            results=list(pool.map(lambda _:module.analyze(policy()),range(6)))
        self.assertEqual(model.call_count,1)
        self.assertEqual(len(results),6)
        with db.connect() as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM analysis_claims').fetchone()[0],0)

    def test_failed_work_releases_claim_and_can_resume(self):
        with patch('analysis.chat_json',side_effect=RuntimeError('synthetic failure')):
            with self.assertRaises(RuntimeError):module.analyze(policy())
        with patch('analysis.chat_json',return_value=analysis()) as model:
            module.analyze(policy());module.analyze(policy())
        self.assertEqual(model.call_count,1)

    def test_claim_is_exclusive_and_expired_claim_can_be_taken_over(self):
        self.assertTrue(db.claim_analysis('key','first',100,lease=10))
        self.assertFalse(db.claim_analysis('key','second',105))
        db.release_analysis('key','wrong-owner')
        self.assertFalse(db.claim_analysis('key','second',105))
        self.assertTrue(db.claim_analysis('key','second',111))

    def test_exhausted_failures_still_count_as_unfinished(self):
        p=policy();self.publish(p)
        for _ in range(3):db.record_failure(module.fingerprint(p),p['id'],'ValidationError')
        with patch('analysis.chat_json') as model:
            result=batch.analyze(0)
        self.assertEqual(result['remaining'],1)
        model.assert_not_called()

    def test_backfill_selects_analysis_only_and_reports_incompletion(self):
        with patch('batch.run',return_value={'remaining':2}) as run:
            self.assertEqual(batch.main(['--backfill']),2)
        self.assertEqual(run.call_args.args[:2],(('analyze',),0))

    def test_status_uses_current_catalog_and_makes_no_llm_call(self):
        self.publish(policy())
        with patch('sys.stdout',new_callable=io.StringIO) as output,patch('analysis.chat_json') as model:
            self.assertEqual(batch.main(['--analysis-status']),0)
        self.assertEqual(json.loads(output.getvalue())['pending'],1)
        model.assert_not_called()

    def test_usage_stores_only_aggregate_counts(self):
        db.record_usage('policy_analysis','synthetic-model',{'prompt_tokens':100,'completion_tokens':20})
        db.record_usage('policy_analysis','synthetic-model',{'prompt_tokens':80,'completion_tokens':10})
        row=db.usage_summary()[0]
        self.assertEqual((row['requests'],row['input_tokens'],row['output_tokens']),(2,180,30))
        self.assertEqual(set(row),{'day','kind','model','requests','input_tokens','output_tokens'})

    def test_preanalysis_finishes_before_new_catalog_replaces_previous(self):
        old=policy(id='old');new=policy(id='new',title='new policy')
        self.publish(old)
        seen=[]
        def respond(*args,**kwargs):
            seen.append(engine.load_catalog()[0][0]['id'])
            return analysis()
        with patch('batch.build',return_value=([new],[],{})),patch('analysis.chat_json',side_effect=respond):
            batch.run(('publish','analyze'),llm_limit=0)
        self.assertEqual(seen,['old'])
        self.assertEqual(engine.load_catalog()[0][0]['id'],'new')

    def test_insufficient_coverage_keeps_previous_catalog_and_stats(self):
        self.publish(policy(id='old'))
        before=db.active_run()
        fresh=[policy(id='new-'+str(i),title='new '+str(i)) for i in range(3)]
        with patch('batch.build',return_value=(fresh,[],{})),patch('analysis.chat_json',return_value=analysis()):
            result=batch.run(('publish','analyze'),llm_limit=1)
        self.assertTrue(result['publication_deferred'])
        self.assertEqual(db.active_run(),before)
