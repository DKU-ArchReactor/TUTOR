import importlib.util
from pathlib import Path
import pytest

httpx = pytest.importorskip('httpx', reason='Local preview dependencies are in requirements-preview.txt')
pytest.importorskip('fastapi', reason='Local preview dependencies are in requirements-preview.txt')
from fastapi.testclient import TestClient


def test_preview_compiles_and_analyzes_through_real_local_grpc():
    spec = importlib.util.spec_from_file_location('preview', Path(__file__).parents[1] / 'scripts/preview.py')
    preview = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(preview)
    result = {'program': {'code_mapping': {'0x10000': {'assembly': 'add a0,a1,a2', 'source_line': 1}}},
              'history': [{'clock': 0, 'stage_activity': {'EX': {'pc': '0x10000', 'assembly': 'add a0,a1,a2',
                  'operand_1': '0x3', 'operand_2': '0x5', 'alu_result': '0x8', 'alu_operation': 'add'}}}]}

    def upstream(request):
        if request.url.path == '/api/v1/build/compile':
            return httpx.Response(201, json={'status': 'success', 'simulation_token': 'synthetic-test-token'})
        assert request.url.path == '/api/v1/simulation/run'
        return httpx.Response(200, json={'execution_status': 'COMPLETED', 'result': result})

    with TestClient(preview.create_app(transport=httpx.MockTransport(upstream))) as client:
        build = client.post('/api/v1/build/compile', json={'content': 'int sum = a + b;', 'lang': 'c'})
        assert build.status_code == 201
        assert build.headers['x-local-tutor'] == 'true'
        assert 'a + b' in build.json()['tutor']['c_lines'][0]['explanation']['summary']
        run = client.post('/api/v1/simulation/run', json={'simulation_token': 'synthetic-test-token', 'mode': 'single'})
        assert run.json()['result'] == result
        bundle = run.json()['tutor']
        assert bundle['line_explanations'][0]['source_line'] == 1
        assert '8 (0x8)' in bundle['execution_steps'][0]['instruction_observations'][0]['summary']
