"""Synthetic-only GPU retrieval tests. No model download or network required."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import embeddings as e


def vector(axis=0):
    return e.valid_vector([1.0 if i == axis else 0.0 for i in range(e.DIMENSIONS)])


def policy(i, title=None):
    return {'id': str(i), 'title': title or f'policy {i}', 'summary': '', 'target': '', 'benefit': ''}


class EmbeddingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.settings = patch.object(e, 'settings', return_value=('http://encoder', 'synthetic-key', 'model-v1'))
        self.settings.start()
        self.addCleanup(self.settings.stop)
        self.path = patch.object(e, 'DATA_DIR', Path(self.directory.name))
        self.path.start()
        self.addCleanup(self.path.stop)

    def test_only_changed_policy_text_is_reembedded(self):
        catalog = [policy(1), policy(2)]
        with patch.object(e, 'encode', side_effect=lambda texts, timeout: [vector() for _ in texts]) as encode:
            self.assertEqual(e.index_catalog(catalog), 2)
            self.assertEqual(e.index_catalog(catalog), 0)
            catalog[0]['benefit'] = 'changed public benefit'
            self.assertEqual(e.index_catalog(catalog), 1)
            self.assertEqual(encode.call_count, 2)

    def test_incomplete_or_different_model_index_uses_lexical_without_network(self):
        catalog = [policy(1), policy(2)]
        with patch.object(e, 'encode', return_value=[vector()]):
            e.index_catalog(catalog[:1])
        with patch.object(e, 'encode') as encode:
            self.assertIs(e.rerank(catalog, {'story_summary': ['synthetic query']}, catalog), catalog)
            encode.assert_not_called()

    def test_gpu_timeout_preserves_every_candidate_and_order(self):
        catalog = [policy(1), policy(2)]
        with patch.object(e, 'encode', return_value=[vector(), vector()]):
            e.index_catalog(catalog)
        with patch.object(e, 'encode', side_effect=TimeoutError):
            self.assertIs(e.rerank(catalog, {'story_summary': ['synthetic query']}, catalog), catalog)

    def test_semantic_candidate_is_recalled_and_query_is_not_stored(self):
        catalog = [policy(i) for i in range(80)]
        with patch.object(e, 'encode', side_effect=lambda texts, timeout:
                          [vector(1 if 'policy 79\n' in text else 0) for text in texts]):
            e.index_catalog(catalog)
        before = (Path(self.directory.name) / 'policy-vectors.sqlite3').read_bytes()
        with patch.object(e, 'encode', return_value=[vector(1)]):
            result = e.rerank(catalog, {'story_summary': ['private synthetic query']}, catalog)
        self.assertLess(result.index(catalog[79]), 79)
        self.assertEqual({p['id'] for p in result}, {p['id'] for p in catalog})
        self.assertEqual(before, (Path(self.directory.name) / 'policy-vectors.sqlite3').read_bytes())

    def test_invalid_vectors_are_rejected(self):
        for bad in ([0.0] * e.DIMENSIONS, [float('nan')] * e.DIMENSIONS, [1.0], [True] * e.DIMENSIONS):
            with self.subTest(bad=str(bad[:2])):
                with self.assertRaises(ValueError):
                    e.valid_vector(bad)

    def test_wrong_model_and_duplicate_indices_are_rejected(self):
        for payload in ({'model': 'old-model', 'data': []},
                        {'model': 'model-v1', 'data': [{'index': 0}, {'index': 0}]}):
            response = unittest.mock.MagicMock()
            response.__enter__.return_value.read.return_value = json.dumps(payload).encode()
            with patch.object(e.urllib.request, 'urlopen', return_value=response):
                with self.assertRaises(ValueError):
                    e.encode(['public a', 'public b'], timeout=2)

    def test_unconfigured_and_no_story_do_not_contact_gpu(self):
        catalog = [policy(1)]
        with patch.object(e, 'configured', return_value=False), patch.object(e, 'encode') as encode:
            self.assertIs(e.rerank(catalog, {}, catalog), catalog)
            encode.assert_not_called()


if __name__ == '__main__':
    unittest.main()
