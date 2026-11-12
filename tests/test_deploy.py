import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import pytest

spec = importlib.util.spec_from_file_location('tutor_deploy', Path(__file__).resolve().parents[1] / 'scripts/deploy.py')
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)

def test_wrong_account_stops_before_any_mutation(tmp_path, monkeypatch):
    config = {key:'test' for key in ['region','profile','bucket','repository','stack','build_project','cluster','service']}
    config['account_id']='111111111111'
    path=tmp_path/'config.json';path.write_text(json.dumps(config))
    monkeypatch.setattr(sys,'argv',['deploy.py','--config',str(path)])
    calls=[]
    def client(name, **kwargs):
        calls.append(name)
        assert name=='sts'
        return SimpleNamespace(get_caller_identity=lambda:{'Account':'222222222222'})
    def session(**kwargs):
        assert kwargs=={'profile_name':'test','region_name':'test'}
        return SimpleNamespace(client=client)
    monkeypatch.setattr(deploy.boto3,'Session',session)
    with pytest.raises(RuntimeError,match='Wrong account'): deploy.main()
    assert calls==['sts']

def test_incomplete_config_stops_before_creating_session(tmp_path, monkeypatch):
    path=tmp_path/'config.json';path.write_text('{}')
    monkeypatch.setattr(sys,'argv',['deploy.py','--config',str(path)])
    def forbidden(**kwargs): raise AssertionError('Must not create an AWS session')
    monkeypatch.setattr(deploy.boto3,'Session',forbidden)
    with pytest.raises(ValueError,match='Deployment config'): deploy.main()
