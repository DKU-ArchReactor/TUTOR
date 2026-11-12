"""Package only service/build inputs; exclude credentials and local artifacts."""
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
ROOT = Path(__file__).resolve().parents[1]

def main():
    files=[]
    for folder in ['service','tutor_contract','proto','tests','scripts','infrastructure']:
        files.extend(p for p in (ROOT/folder).rglob('*') if p.is_file()
            and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.pyo'))
    files.extend(ROOT/p for p in ['Dockerfile','.dockerignore','requirements.txt','requirements-dev.txt','requirements-deploy.txt','pytest.ini'])
    output=ROOT/'dist/source.zip'; output.parent.mkdir(exist_ok=True)
    with ZipFile(output,'w',ZIP_DEFLATED) as archive:
        for p in sorted(files):
            if p.is_symlink(): raise ValueError('Source symlinks are forbidden')
            archive.write(p,p.relative_to(ROOT))
    tag='tutor-'+hashlib.sha256(output.read_bytes()).hexdigest()[:16]
    print(json.dumps({'file':str(output),'tag':tag}))

if __name__=='__main__': main()
