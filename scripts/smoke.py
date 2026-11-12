"""Call the sample RPC from a host allowed by the service security group."""
import json
import sys
from pathlib import Path
from uuid import uuid4
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import grpc
from tutor_contract.v1 import tutor_pb2 as pb, tutor_pb2_grpc as rpc

def main():
    target = sys.argv[1] if len(sys.argv) > 1 else '127.0.0.1:50051'
    request = pb.SampleRequest(request_id=str(uuid4()), message='Hello TUTOR')
    with grpc.insecure_channel(target) as channel:
        result = rpc.TutorStub(channel).Sample(request, timeout=5)
    assert result.request_id == request.request_id and result.message == request.message and result.sample
    print(json.dumps({'request_id':result.request_id, 'tutor_version':result.tutor_version, 'reply':result.reply}, ensure_ascii=False))

if __name__ == '__main__':
    main()
