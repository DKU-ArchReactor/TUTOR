"""Local FE integration only: deployed BE/CORE plus the local TUTOR service.

Run on loopback. Never deploy this proxy as the production BE.
"""
import base64
from collections import OrderedDict
from contextlib import asynccontextmanager
from hashlib import sha256
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from starlette.concurrency import run_in_threadpool
import grpc
from service.server import create_server
from tutor_contract.v1 import tutor_pb2 as pb, tutor_pb2_grpc as rpc
from archreactor_tutor.models import ExplainRequest


def create_app(upstream="https://d1j3nkcez6kncs.cloudfront.net", *, transport=None):
    upstream = upstream.rstrip('/')
    parsed = urlsplit(upstream)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Configure an HTTPS backend base URL')
    artifacts = OrderedDict()

    @asynccontextmanager
    async def lifespan(app):
        server, _, port = create_server('127.0.0.1:0')
        server.start()
        app.state.channel = grpc.insecure_channel(f'127.0.0.1:{port}', options=[
            ('grpc.max_receive_message_length', 32 * 1024 * 1024),
            ('grpc.max_send_message_length', 16 * 1024 * 1024),
        ])
        try:
            async with httpx.AsyncClient(timeout=60, transport=transport, trust_env=False) as client:
                app.state.client = client
                yield
        finally:
            app.state.channel.close()
            server.stop(1).wait()
            artifacts.clear()

    app = FastAPI(title='Local TUTOR integration gateway', lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=[
        f'http://{host}:{port}' for host in ('localhost', '127.0.0.1') for port in (5173, 5174, 5175)
    ], allow_methods=['*'], allow_headers=['*'], expose_headers=['X-Local-Tutor'])

    def artifact_key(payload, authorization):
        identifier = payload.get('build_id') or payload.get('simulation_token')
        return sha256((authorization + ':' + str(identifier)).encode()).hexdigest() if identifier else None

    def local_call(path, payload):
        request_id = str(uuid4())
        stub = rpc.TutorStub(app.state.channel)
        if path.endswith('/explain'):
            body = ExplainRequest.model_validate(payload)
            message = pb.ExplainRequest(request_id=request_id, items=[
                pb.ExplainItem(**item.model_dump(exclude_none=True)) for item in body.items
            ])
            response = stub.Explain(message, timeout=15)
        elif path.endswith('/compile'):
            message = pb.CompileRequest(request_id=request_id, source=payload['source'], lang=payload['lang'])
            response = stub.Compile(message, timeout=15)
        else:
            message = pb.AnalyzeRequest(request_id=request_id,
                source=payload.get('source', ''), source_file=payload.get('source_file') or '',
                result_json=json.dumps(payload['result'], ensure_ascii=False),
                elf=base64.b64decode(payload.get('elf_base64', '')))
            response = stub.Analyze(message, timeout=15)
        return json.loads(response.result_json)

    async def tutor(path, payload):
        try:
            return await run_in_threadpool(local_call, path, payload)
        except (grpc.RpcError, ValueError, TypeError):
            raise HTTPException(502, 'Local TUTOR analysis failed') from None

    @app.get('/health')
    async def health():
        return {'status': 'ok', 'service': 'local-tutor-gateway', 'local_only': True}

    @app.api_route('/api/{path:path}', methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
    async def proxy(path: str, request: Request):
        now = time.monotonic()
        for key in list(artifacts):
            if now - artifacts[key]['created'] > 600:
                del artifacts[key]
        raw = await request.body()
        try:
            body = json.loads(raw) if raw else {}
        except ValueError:
            body = {}
        if not isinstance(body, dict):
            body = {}
        authorization = request.headers.get('authorization', '')
        headers = {name: request.headers[name] for name in ('authorization', 'content-type', 'accept') if name in request.headers}
        if path == 'v1/tutor/explain' and request.method == 'POST':
            bundle = await tutor('/api/v1/tutor/explain', body)
            return JSONResponse(bundle, headers={'X-Local-Tutor': 'true'})
        if path == 'v1/assistant/chat' and request.method == 'POST':
            outbound = app.state.client.build_request('POST', upstream + '/api/' + path,
                content=raw, headers=headers)
            try:
                streamed = await app.state.client.send(outbound, stream=True)
            except httpx.HTTPError:
                raise HTTPException(503, 'Deployed BE unavailable') from None

            async def chunks():
                try:
                    async for chunk in streamed.aiter_bytes():
                        yield chunk
                finally:
                    await streamed.aclose()
            return StreamingResponse(chunks(), status_code=streamed.status_code,
                media_type=streamed.headers.get('content-type'), headers={'Cache-Control': 'no-store'})
        try:
            response = await app.state.client.request(request.method, upstream + '/api/' + path,
                params=list(request.query_params.multi_items()), content=raw, headers=headers)
        except httpx.HTTPError:
            raise HTTPException(503, 'Deployed BE unavailable') from None
        if response.status_code >= 400:
            return Response(response.content, status_code=response.status_code, media_type=response.headers.get('content-type'))
        try:
            document = response.json()
        except ValueError:
            return Response(response.content, status_code=response.status_code, media_type=response.headers.get('content-type'))
        status = None
        if isinstance(document, dict) and request.method == 'POST':
            if path == 'v1/build/compile' and document.get('status') == 'success' and body.get('compile_profile', 'rv32im') == 'rv32im':
                source = body.get('content', '')
                lang = body.get('lang', 'c')
                bundle = await tutor('/api/v1/tutor/compile', {'source': source, 'lang': lang, 'assembly': None})
                document['tutor'] = bundle
                status = 'true' if bundle else 'unavailable'
                elf = None
                binary_url = document.get('binary_url')
                if isinstance(binary_url, str) and urlsplit(binary_url).scheme == 'https':
                    try:
                        async with app.state.client.stream('GET', binary_url) as binary:
                            binary.raise_for_status()
                            data = bytearray()
                            async for chunk in binary.aiter_bytes():
                                data.extend(chunk)
                                if len(data) > 256 * 1024:
                                    break
                            if len(data) <= 256 * 1024:
                                elf = bytes(data)
                    except httpx.HTTPError:
                        pass
                key = artifact_key(document, authorization)
                if key:
                    artifacts[key] = {'created': now, 'source': source if lang == 'c' else '',
                                      'source_file': 'source.c' if lang == 'c' else 'source.s', 'elf': elf}
                    while len(artifacts) > 32:
                        artifacts.popitem(last=False)
            elif path == 'v1/simulation/run' and isinstance(document.get('result'), dict):
                artifact = artifacts.get(artifact_key(body, authorization), {})
                payload = {'result': document['result'], 'source': artifact.get('source', ''),
                           'source_file': artifact.get('source_file')}
                if artifact.get('elf') is not None:
                    payload['elf_base64'] = base64.b64encode(artifact['elf']).decode('ascii')
                bundle = await tutor('/api/v1/tutor/analyze', payload)
                document['tutor'] = bundle
                status = 'true' if bundle else 'unavailable'
        return JSONResponse(document, status_code=response.status_code, headers={'X-Local-Tutor': status} if status else {})

    return app


app = create_app()


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=8101, access_log=False)
