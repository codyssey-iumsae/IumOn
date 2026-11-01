"""OpenAI-compatible JSON adapter. No user answers are persisted here."""
import json
import os
import re
import threading
import urllib.error
import urllib.request
from config import load_env

_slots = threading.BoundedSemaphore(4)

class ModelUnavailable(RuntimeError):
    pass

class ModelRejected(ModelUnavailable):
    """The provider refused the request itself (key, permission, quota): retrying other inputs cannot help."""

def configured():
    return bool(os.getenv('LLM_API_KEY') and os.getenv('LLM_BASE_URL'))

def chat_json(system, payload, max_tokens=3500, *, usage_scope=None):
    if not configured():
        raise ModelUnavailable('AI 연결 설정을 확인해 주세요.')
    body = {'model': os.getenv('LLM_MODEL', 'gpt-5.4-mini'),
            'messages': [{'role': 'system', 'content': system},
                         {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}],
            'max_completion_tokens': max_tokens}
    url = os.environ['LLM_BASE_URL'].rstrip('/') + '/chat/completions'
    with _slots:
        for attempt in range(2):
            request = urllib.request.Request(url, data=json.dumps(body).encode(), headers={
                'Authorization': 'Bearer ' + os.environ['LLM_API_KEY'], 'Content-Type': 'application/json'})
            try:
                with urllib.request.urlopen(request, timeout=65) as response:
                    obj = json.load(response)
                if usage_scope and isinstance(obj.get('usage'), dict):
                    try:
                        import db
                        db.record_usage(usage_scope, body['model'], obj['usage'])
                    except Exception:
                        pass  # Telemetry failure must not repeat a paid, successful request.
                message = obj['choices'][0]['message']['content']
                message = re.sub(r'^```(?:json)?\s*|\s*```$', '', message.strip())
                result = json.loads(message)
                if not isinstance(result, dict):
                    raise ValueError('JSON object required')
                return result
            except urllib.error.HTTPError as exc:
                raise ModelRejected('AI 요청에 실패했어요. 잠시 후 다시 시도해 주세요.', exc.code) from None
            except Exception:
                if attempt == 1:
                    raise ModelUnavailable('AI 답변을 검증하지 못했어요. 다시 시도해 주세요.') from None
    raise ModelUnavailable('AI 요청을 완료하지 못했어요.')
