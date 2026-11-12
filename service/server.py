"""Bounded connectivity sample, without model calls or user data storage."""
import logging
import json
import os
import signal
from concurrent import futures
from uuid import UUID
import grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc
from tutor_contract.v1 import tutor_pb2 as pb, tutor_pb2_grpc as rpc
from archreactor_tutor.models import ExplainItem, ExplainRequest, CompileRequest, AnalyzeRequest
from archreactor_tutor.service import explain, compile_explanations, analyze_execution

SERVICE = 'archreactor.tutor.v1.Tutor'
MAX_MESSAGE = 16 * 1024 * 1024
MAX_RESPONSE = 32 * 1024 * 1024
REPLY = 'TUTOR gRPC 연결이 정상입니다. 이 응답은 AI 해설이 아닌 연동 확인용 샘플입니다.'

class Tutor(rpc.TutorServicer):
    def _respond(self, request_id, context, build):
        try:
            UUID(request_id)
            bundle = build()
            encoded = json.dumps(bundle, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
        except (ValueError, TypeError, KeyError, AttributeError, IndexError, RecursionError):
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, 'Invalid tutor input or analysis limits')
        if len(encoded.encode('utf-8')) > MAX_RESPONSE - 1024:
            context.abort(grpc.StatusCode.RESOURCE_EXHAUSTED, 'Tutor response exceeds 32 MiB')
        return pb.TutorResponse(request_id=request_id, schema_version='1.0',
            tutor_version=os.getenv('TUTOR_VERSION', 'development'), result_json=encoded)

    def Explain(self, request, context):
        def build():
            if not 1 <= len(request.items) <= 128:
                raise ValueError('Explain requires 1-128 items')
            items = [ExplainItem(kind=item.kind, text=item.text,
                line=item.line if item.HasField('line') else 1, pc=item.pc if item.HasField('pc') else None) for item in request.items]
            validated = ExplainRequest(items=items)
            return {'schema_version': '1.0', 'items': [explain(item).model_dump() for item in validated.items]}
        return self._respond(request.request_id, context, build)

    def Compile(self, request, context):
        def build():
            body = CompileRequest(source=request.source, lang=request.lang,
                assembly=request.assembly if request.HasField('assembly') else None)
            return compile_explanations(body.source, body.lang, body.assembly)
        return self._respond(request.request_id, context, build)

    def Analyze(self, request, context):
        def build():
            if len(request.elf) > 256 * 1024:
                raise ValueError('ELF exceeds 256 KiB')
            def invalid_constant(value):
                raise ValueError('Non-finite JSON')
            result = json.loads(request.result_json, parse_constant=invalid_constant)
            body = AnalyzeRequest(source=request.source, source_file=request.source_file or None, result=result)
            return analyze_execution(body.source, body.result, body.source_file, elf_bytes=request.elf or None)
        return self._respond(request.request_id, context, build)

    def Sample(self, request, context):
        try:
            UUID(request.request_id)
        except (ValueError, AttributeError):
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, 'request_id must be a UUID')
        if not request.message.strip() or len(request.message) > 256 or len(request.message.encode('utf-8')) > 1024:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, 'message must contain 1-256 characters, at most 1024 bytes')
        return pb.SampleResponse(request_id=request.request_id, schema_version='1.0',
            tutor_version=os.getenv('TUTOR_VERSION', 'development'), message=request.message,
            reply=REPLY, sample=True)

def create_server(address='[::]:50051'):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4), maximum_concurrent_rpcs=16,
        options=[('grpc.max_receive_message_length', MAX_MESSAGE), ('grpc.max_send_message_length', MAX_RESPONSE)])
    rpc.add_TutorServicer_to_server(Tutor(), server)
    status = health.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(status, server)
    status.set(SERVICE, health_pb2.HealthCheckResponse.SERVING)
    port = server.add_insecure_port(address)
    if not port:
        raise RuntimeError('Cannot bind gRPC port')
    return server, status, port

def main():
    logging.basicConfig(level=logging.INFO)
    server, status, _ = create_server()
    def shutdown(*_):
        status.enter_graceful_shutdown()
        server.stop(5)
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    server.start()
    logging.info('TUTOR gRPC service started on port 50051')
    server.wait_for_termination()

if __name__ == '__main__':
    main()
