"""Check Sample and analysis RPCs from a host allowed by the service group."""
import json
import sys
from pathlib import Path
from uuid import uuid4
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import grpc
from tutor_contract.v1 import tutor_pb2 as pb, tutor_pb2_grpc as rpc

def check(stub):
    request = pb.SampleRequest(request_id=str(uuid4()), message='Hello TUTOR')
    result = stub.Sample(request, timeout=5)
    assert result.request_id == request.request_id and result.message == request.message and result.sample
    def parsed(call, message):
        response = call(message, timeout=5)
        assert response.request_id == message.request_id and response.schema_version == '1.0'
        assert response.tutor_version == result.tutor_version
        return json.loads(response.result_json)
    bundle = parsed(stub.Explain, pb.ExplainRequest(request_id=str(uuid4()), items=[pb.ExplainItem(kind='asm', text='lbu a0,0(a1)')]))
    assert bundle['items'][0]['memory']['extension'] == 'zero'
    source = 'int main() {\n return 7;\n}'
    bundle = parsed(stub.Compile, pb.CompileRequest(request_id=str(uuid4()), source=source, lang='c'))
    assert bundle['c_lines'][1]['explanation']['category'] == 'return'
    bundle = parsed(stub.Analyze, pb.AnalyzeRequest(request_id=str(uuid4()), source=source,
        result_json=json.dumps({'history': [], 'program': {'code_mapping': {
            '0x10000': {'assembly': 'lui a5,65536', 'raw_instruction': '0x000107B7', 'source_line': 2},
        }}})))
    assert bundle['source_mapping']['lines'][1]['instructions'][0]['explanation']['operation'] == 'x15 = (16 << 12)'
    return {'passed': True, 'tutor_version': result.tutor_version, 'checks': ['Sample', 'Explain', 'Compile', 'Analyze']}


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else '127.0.0.1:50051'
    with grpc.insecure_channel(target) as channel:
        print(json.dumps(check(rpc.TutorStub(channel))))

if __name__ == '__main__':
    main()
