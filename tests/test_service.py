from uuid import uuid4
import grpc
import pytest
from grpc_health.v1 import health_pb2, health_pb2_grpc
from service.server import create_server, SERVICE
from tutor_contract.v1 import tutor_pb2 as pb, tutor_pb2_grpc as rpc

@pytest.fixture
def channel():
    server, _, port = create_server('127.0.0.1:0')
    server.start()
    with grpc.insecure_channel(f'127.0.0.1:{port}') as channel:
        yield channel
    server.stop(0).wait()

def test_sample_roundtrip_and_health(channel):
    request = pb.SampleRequest(request_id=str(uuid4()), message='안녕하세요 TUTOR')
    response = rpc.TutorStub(channel).Sample(request, timeout=2)
    assert response.request_id == request.request_id
    assert response.message == request.message
    assert response.sample and response.schema_version == '1.0' and response.tutor_version
    assert 'AI 해설이 아닌' in response.reply
    result = health_pb2_grpc.HealthStub(channel).Check(health_pb2.HealthCheckRequest(service=SERVICE), timeout=2)
    assert result.status == health_pb2.HealthCheckResponse.SERVING

@pytest.mark.parametrize('message', ['', '  ', 'a'*257])
def test_invalid_message(channel, message):
    with pytest.raises(grpc.RpcError) as error:
        rpc.TutorStub(channel).Sample(pb.SampleRequest(request_id=str(uuid4()), message=message), timeout=2)
    assert error.value.code() == grpc.StatusCode.INVALID_ARGUMENT

def test_invalid_request_id(channel):
    with pytest.raises(grpc.RpcError) as error:
        rpc.TutorStub(channel).Sample(pb.SampleRequest(request_id='bad', message='hello'), timeout=2)
    assert error.value.code() == grpc.StatusCode.INVALID_ARGUMENT
