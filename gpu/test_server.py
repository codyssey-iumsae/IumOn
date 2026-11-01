"""Encoder protocol/security tests with a fake model; no CUDA or model download."""
import asyncio
import importlib.util
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException, Request

spec = importlib.util.spec_from_file_location('gpu_encoder_test_module', Path(__file__).with_name('server.py'))
service = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = service
with patch.dict(os.environ, {'EMBEDDING_REVISION': 'synthetic-revision', 'EMBEDDING_API_KEY': 'x' * 48}):
    spec.loader.exec_module(service)


class EncoderTests(unittest.TestCase):
    def body(self, **updates):
        return service.EncodeRequest(**{'model': service.IDENTITY, 'input': ['synthetic text'], **updates})

    def assert_http(self, status, body, auth):
        with self.assertRaises(HTTPException) as caught:
            service.embeddings(body, auth)
        self.assertEqual(caught.exception.status_code, status)

    def test_auth_and_model_identity_are_required(self):
        self.assert_http(401, self.body(), '')
        self.assert_http(409, self.body(model='old-model'), 'Bearer ' + service.TOKEN)

    def test_busy_gpu_rejects_instead_of_queueing_queries(self):
        with service.lock:
            self.assert_http(503, self.body(), 'Bearer ' + service.TOKEN)

    def test_input_limits_prevent_large_inference(self):
        for text in ('', 'x' * 3501):
            self.assert_http(422, self.body(input=[text]), 'Bearer ' + service.TOKEN)

    def test_normalized_dense_output_preserves_input_order(self):
        fake = Mock()
        fake.encode.return_value = [Mock(tolist=Mock(return_value=[1.0] + [0.0] * 1023))]
        with patch.object(service, 'encoder', fake):
            result = service.embeddings(self.body(), 'Bearer ' + service.TOKEN)
        self.assertEqual(result['model'], service.IDENTITY)
        self.assertEqual(result['data'][0]['index'], 0)
        self.assertEqual(len(result['data'][0]['embedding']), 1024)
        self.assertTrue(fake.encode.call_args.kwargs['normalize_embeddings'])
        self.assertFalse(fake.encode.call_args.kwargs['show_progress_bar'])

    def test_source_ip_and_streamed_body_limits(self):
        async def receive():
            return {'type': 'http.request', 'body': b'x' * 120001, 'more_body': False}

        async def next_handler(request):
            self.fail('Rejected input must not reach inference')

        for host, expected in (('203.0.113.1', 403), ('10.1.1.25', 413)):
            request = Request({'type': 'http', 'method': 'POST', 'path': '/',
                               'headers': [], 'client': (host, 1000)}, receive)
            result = asyncio.run(service.limit_body(request, next_handler))
            self.assertEqual(result.status_code, expected)


if __name__ == '__main__':
    unittest.main()
