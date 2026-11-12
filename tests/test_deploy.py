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


@pytest.mark.parametrize('key,value', [
    ('GITHUB_ACTIONS', 'false'), ('GITHUB_REPOSITORY', 'someone/fork'),
    ('GITHUB_REF', 'refs/pull/2/merge'), ('GITHUB_REF', 'refs/heads/main'),
    ('GITHUB_EVENT_NAME', 'pull_request_target'), ('AWS_SESSION_TOKEN', ''),
])
def test_ci_rejects_untrusted_context_before_aws(tmp_path, monkeypatch, key, value):
    config = {k: 'test' for k in ('account_id', 'region', 'bucket', 'repository', 'stack', 'build_project', 'cluster', 'service')}
    path = tmp_path/'config.json'
    path.write_text(json.dumps(config))
    env = {'GITHUB_ACTIONS':'true', 'GITHUB_REPOSITORY':'DKU-ArchReactor/TUTOR',
           'GITHUB_REF':'refs/heads/develop', 'GITHUB_EVENT_NAME':'push',
           'AWS_ACCESS_KEY_ID':'test', 'AWS_SECRET_ACCESS_KEY':'test', 'AWS_SESSION_TOKEN':'test'}
    env[key] = value
    for name, val in env.items(): monkeypatch.setenv(name, val)
    monkeypatch.setattr(sys, 'argv', ['deploy.py', '--github-actions', '--config', str(path)])
    def forbidden(**kwargs): raise AssertionError('Must not create a session')
    monkeypatch.setattr(deploy.boto3, 'Session', forbidden)
    with pytest.raises(RuntimeError, match='GitHub deployment requires'): deploy.main()


def test_ci_uses_oidc_session_and_still_checks_account(tmp_path, monkeypatch):
    config = {k:'test' for k in ('region','bucket','repository','stack','build_project','cluster','service')}
    config['account_id']='111111111111'
    path=tmp_path/'config.json'; path.write_text(json.dumps(config))
    for name, value in {'GITHUB_ACTIONS':'true', 'GITHUB_REPOSITORY':'DKU-ArchReactor/TUTOR',
        'GITHUB_REF':'refs/heads/develop','GITHUB_EVENT_NAME':'push',
        'AWS_ACCESS_KEY_ID':'test','AWS_SECRET_ACCESS_KEY':'test','AWS_SESSION_TOKEN':'test'}.items():
        monkeypatch.setenv(name,value)
    monkeypatch.setattr(sys,'argv',['deploy.py','--github-actions','--config',str(path)])
    def session(**kwargs):
        assert kwargs == {'region_name':'test'}
        def client(name, **kwargs):
            assert name == 'sts'
            return SimpleNamespace(get_caller_identity=lambda:{'Account':'222222222222'})
        return SimpleNamespace(client=client)
    monkeypatch.setattr(deploy.boto3,'Session',session)
    with pytest.raises(RuntimeError,match='Wrong account'): deploy.main()
