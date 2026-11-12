"""Require generated stubs and descriptor to match the committed proto."""
from pathlib import Path
import subprocess
import sys
import tempfile
ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as tmp:
    subprocess.run([sys.executable, '-m', 'grpc_tools.protoc', '-Iproto', '--python_out='+tmp,
        '--grpc_python_out='+tmp, '--descriptor_set_out='+tmp+'/contract.pb',
        'proto/tutor_contract/v1/tutor.proto'], cwd=ROOT, check=True)
    for name in ['tutor_contract/v1/tutor_pb2.py','tutor_contract/v1/tutor_pb2_grpc.py']:
        if (ROOT/name).read_bytes() != (Path(tmp)/name).read_bytes():
            raise SystemExit('Regenerate contract: '+name)
    if (ROOT/'proto/contract.pb').read_bytes() != (Path(tmp)/'contract.pb').read_bytes():
        raise SystemExit('Regenerate proto/contract.pb')
print('Generated contract matches proto')
