import json
from uuid import uuid4
import grpc
import pytest
from service.server import create_server
from tutor_contract.v1 import tutor_pb2 as pb, tutor_pb2_grpc as rpc


@pytest.fixture
def stub():
    server, _, port = create_server('127.0.0.1:0')
    server.start()
    with grpc.insecure_channel(f'127.0.0.1:{port}') as channel:
        yield rpc.TutorStub(channel)
    server.stop(0).wait()


def test_explain_compile_and_analyze_real_roundtrip(stub):
    identifier = str(uuid4())
    result = stub.Explain(pb.ExplainRequest(request_id=identifier, items=[
        pb.ExplainItem(kind='asm', text='lbu a0,0(a1)'),
        pb.ExplainItem(kind='c', text='if (x) {', line=2),
    ]), timeout=3)
    assert result.request_id == identifier and result.schema_version == '1.0' and result.tutor_version
    bundle = json.loads(result.result_json)
    assert bundle['items'][0]['memory']['extension'] == 'zero'
    assert bundle['items'][0]['reads'] == ['x11']
    assert bundle['items'][1]['category'] == 'if'
    compiled = stub.Compile(pb.CompileRequest(request_id=identifier, source='int main() {\n return 7;\n}', lang='c'), timeout=3)
    assert json.loads(compiled.result_json)['c_lines'][1]['explanation']['category'] == 'return'
    original = {'history': [], 'program': {'code_mapping': {
        '0x10000': {'assembly': 'lui a5, 65536', 'raw_instruction': '0x000107B7', 'source_line': 2},
        '0x10004': {'assembly': 'ecall', 'source_line': None},
    }}}
    analyzed = stub.Analyze(pb.AnalyzeRequest(request_id=identifier, source='int main() {\n return 7;\n}', result_json=json.dumps(original)), timeout=3)
    data = json.loads(analyzed.result_json)
    assert data['source_mapping']['lines'][1]['instructions'][0]['pc'] == '0x00010000'
    assert data['asm_instructions'][0]['explanation']['operation'] == 'x15 = (16 << 12)'
    assert data['asm_instructions'][1]['runtime_explanation']['category'] == 'unmapped'
    assert original['program']['code_mapping']['0x10000']['assembly'] == 'lui a5, 65536'


@pytest.mark.parametrize('method,message', [
    ('Explain', pb.ExplainRequest(request_id='bad')),
    ('Explain', pb.ExplainRequest(request_id=str(uuid4()))),
    ('Explain', pb.ExplainRequest(request_id=str(uuid4()), items=[pb.ExplainItem(kind='c', text='x'*4097)])),
    ('Explain', pb.ExplainRequest(request_id=str(uuid4()), items=[pb.ExplainItem(kind='c', line=0)])),
    ('Explain', pb.ExplainRequest(request_id=str(uuid4()), items=[pb.ExplainItem(kind='invalid')])),
    ('Explain', pb.ExplainRequest(request_id=str(uuid4()), items=[pb.ExplainItem(kind='c')]*129)),
    ('Compile', pb.CompileRequest(request_id=str(uuid4()), source='x'*65537, lang='c')),
    ('Compile', pb.CompileRequest(request_id=str(uuid4()), lang='python')),
    ('Analyze', pb.AnalyzeRequest(request_id=str(uuid4()), result_json='not json')),
    ('Analyze', pb.AnalyzeRequest(request_id=str(uuid4()), result_json='[]')),
    ('Analyze', pb.AnalyzeRequest(request_id=str(uuid4()), result_json='{"extra":'+'['*10000+'0'+']'*10000+'}')),
    ('Analyze', pb.AnalyzeRequest(request_id=str(uuid4()), result_json='{"history":[NaN]}')),
    ('Analyze', pb.AnalyzeRequest(request_id=str(uuid4()), result_json=json.dumps({'history': [{}]*2001}))),
    ('Analyze', pb.AnalyzeRequest(request_id=str(uuid4()), result_json='{}', elf=b'not ELF')),
    ('Analyze', pb.AnalyzeRequest(request_id=str(uuid4()), result_json='{}', elf=b'x'*(256*1024+1))),
])
def test_invalid_rpc_inputs_are_bounded_and_do_not_echo_source(stub, method, message):
    with pytest.raises(grpc.RpcError) as error:
        getattr(stub, method)(message, timeout=3)
    assert error.value.code() == grpc.StatusCode.INVALID_ARGUMENT
    assert error.value.details() == 'Invalid tutor input or analysis limits'


def test_transport_rejects_oversized_request(stub):
    with pytest.raises(grpc.RpcError) as error:
        stub.Analyze(pb.AnalyzeRequest(request_id=str(uuid4()), result_json='x'*(16*1024*1024)), timeout=3)
    assert error.value.code() == grpc.StatusCode.RESOURCE_EXHAUSTED


def test_container_smoke_checks_all_four_rpcs(stub):
    from scripts.smoke import check
    assert check(stub)['checks'] == ['Sample', 'Explain', 'Compile', 'Analyze']
