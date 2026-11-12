import importlib.util
import json
from pathlib import Path
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]

def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT/'scripts'/f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ci_settings_drop_local_profile_and_reject_mismatch():
    config = {k: 'example' for k in ('bucket','repository','stack','build_project','cluster','service')}
    config.update(account_id='111111111111',region='ap-northeast-2',profile='local-only')
    env={'DEPLOYMENT_CONFIG':json.dumps(config),'AWS_REGION':'ap-northeast-2',
         'DEPLOY_ROLE_ARN':'arn:aws:iam::111111111111:role/test','BE_BASE_URL':'https://example.com'}
    prepare=load('prepare-ci-config').prepare
    assert 'profile' not in prepare(env)
    env['AWS_REGION']='us-east-1'
    with pytest.raises(ValueError,match='Seoul'): prepare(env)
    env['AWS_REGION']='ap-northeast-2'
    env['DEPLOY_ROLE_ARN']='arn:aws:iam::222222222222:role/test'
    with pytest.raises(ValueError,match='configured account'): prepare(env)


def test_public_smoke_rejects_old_service_version(tmp_path,monkeypatch):
    smoke=load('verify-public-api')
    record=tmp_path/'record.json';record.write_text(json.dumps({'version':'tutor-new'}))
    monkeypatch.setattr(sys,'argv',['verify-public-api.py','--base-url','https://example.com','--deployment-record',str(record)])
    monkeypatch.setattr(smoke,'request',lambda *args:(200,{
        'request_id':'2b963b44-605b-490a-bf65-a6414021ee15','schema_version':'1.0','sample':True,
        'message':'Hello TUTOR','tutor_version':'tutor-old','reply':'sample'}))
    with pytest.raises(AssertionError): smoke.main()
