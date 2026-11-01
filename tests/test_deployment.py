"""Deployment selection tests without network, SSH, Docker, or real data."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('poller', Path(__file__).resolve().parents[1] / 'scripts/poll-deployment.py')
poller = importlib.util.module_from_spec(spec)
spec.loader.exec_module(poller)
SHA = 'a' * 40


def run_record(conclusion='success', status='completed', sha=SHA, run_id=1):
    return dict(id=run_id, head_sha=sha, status=status, conclusion=conclusion,
                head_repository={'full_name': 'codyssey-iumsae/IumOn'})


class DeploymentTests(unittest.TestCase):
    def execute(self, runs):
        with patch.object(poller, 'get', side_effect=[{'sha': SHA}, {'workflow_runs': runs}]), \
             patch.object(poller.subprocess, 'run', return_value=type('Result', (), {'returncode': 0})()) as command, \
             patch.object(poller.subprocess, 'check_output', return_value=b'echo deploy') as read:
            poller.main()
            return command.call_args_list, read.call_args_list

    def test_only_successful_exact_main_commit_deploys(self):
        calls, reads = self.execute([run_record()])
        self.assertEqual(calls[0].args[0], ['git', 'fetch', 'origin', 'main'])
        self.assertEqual(reads[0].args[0], ['git', 'show', f'{SHA}:scripts/deploy.sh'])
        self.assertEqual(calls[2].args[0], ['bash', '-s', '--', SHA])
        self.assertEqual(calls[2].kwargs['input'], b'echo deploy')

    def test_failed_pending_and_unrelated_runs_do_not_deploy(self):
        for runs in ([], [run_record('failure')], [run_record(None, 'in_progress')],
                     [run_record(sha='b' * 40)]):
            with self.subTest(runs=runs):
                self.assertEqual(self.execute(runs), ([], []))

    def test_newer_failure_overrides_older_success(self):
        self.assertEqual(self.execute([run_record(), run_record('failure', run_id=2)]), ([], []))

    def test_fetch_failure_never_executes_deployment(self):
        with patch.object(poller, 'get', side_effect=[{'sha': SHA}, {'workflow_runs': [run_record()]}]), \
             patch.object(poller.subprocess, 'run', side_effect=RuntimeError('fetch failed')), \
             patch.object(poller.subprocess, 'check_output') as read:
            with self.assertRaises(RuntimeError):
                poller.main()
            read.assert_not_called()
