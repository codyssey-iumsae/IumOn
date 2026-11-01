"""Private, authenticated BGE-M3 encoder. Never logs inputs or persists query vectors."""
import os
import secrets
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field

MODEL = 'BAAI/bge-m3'
REVISION = os.environ['EMBEDDING_REVISION']
IDENTITY = f'{MODEL}@{REVISION}:dense:2048'
TOKEN = os.environ['EMBEDDING_API_KEY']
ALLOWED_IPS = set(os.getenv('EMBEDDING_ALLOWED_IPS', '10.1.1.25,10.1.2.25,127.0.0.1').split(','))
if len(TOKEN) < 32:
    raise RuntimeError('A strong embedding API key is required')
encoder = None
lock = threading.Lock()


@asynccontextmanager
async def lifespan(app):
    global encoder
    import torch
    from sentence_transformers import SentenceTransformer
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA GPU is required')
    encoder = SentenceTransformer(MODEL, revision=REVISION, device='cuda', trust_remote_code=False)
    encoder.max_seq_length = 2048
    encoder.half()
    yield


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware('http')
async def limit_body(request: Request, call_next):
    if request.client is None or request.client.host not in ALLOWED_IPS:
        from fastapi.responses import JSONResponse
        return JSONResponse({'detail': 'Client not allowed'}, status_code=403)
    # Inspect streamed bytes as well as Content-Length (chunked requests have no length).
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 120_000:
            from fastapi.responses import JSONResponse
            return JSONResponse({'detail': 'Request too large'}, status_code=413)
    request._body = bytes(body)
    return await call_next(request)


class EncodeRequest(BaseModel):
    model: str
    input: list[str] = Field(min_length=1, max_length=8)


@app.get('/health')
def health():
    return {'ready': encoder is not None, 'model': IDENTITY, 'dimensions': 1024}


@app.post('/v1/embeddings')
def embeddings(body: EncodeRequest, authorization: str = Header(default='')):
    if not secrets.compare_digest(authorization, 'Bearer ' + TOKEN):
        raise HTTPException(401, 'Unauthorized')
    if body.model != IDENTITY:
        raise HTTPException(409, 'Embedding model version mismatch')
    if any(not text.strip() or len(text) > 3500 for text in body.input):
        raise HTTPException(422, 'Each input must contain 1–3500 characters')
    if not lock.acquire(blocking=False):
        raise HTTPException(503, 'Encoder busy; retry later')
    try:
        vectors = encoder.encode(body.input, batch_size=4, normalize_embeddings=True,
                                 convert_to_numpy=True, show_progress_bar=False)
        return {'model': IDENTITY, 'data': [{'index': i, 'embedding': v.tolist()}
                                           for i, v in enumerate(vectors)]}
    finally:
        lock.release()
