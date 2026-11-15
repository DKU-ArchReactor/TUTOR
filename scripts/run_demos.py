"""Compile owned demo sources through BE, then analyze returned evidence over real gRPC.

Transient simulation tokens and presigned URLs are never logged or saved.
"""
import argparse
import sys
from uuid import uuid4
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'src')]
import grpc
from tutor_contract.v1 import tutor_pb2 as pb, tutor_pb2_grpc as rpc


def rpc_json(call, message):
    response = call(message, timeout=10)
    assert response.request_id == message.request_id and response.schema_version == '1.0'
    return json.loads(response.result_json)


def post(base, path, body):
    request = Request(base + path, data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'}, method='POST')
    with urlopen(request, timeout=60) as response:
        return json.load(response)


def run(base, output, tutor_target, selected_cases=None):
    output.mkdir(parents=True, exist_ok=True)
    report = {'checked_at': datetime.now(timezone.utc).isoformat(), 'api_base': base, 'tutor_target': tutor_target, 'cases': []}
    cases = json.loads((ROOT / 'examples/manifest.json').read_text(encoding='utf-8'))
    if selected_cases:
        unknown = set(selected_cases) - {case['id'] for case in cases}
        if unknown:
            raise ValueError('Unknown demo case')
        cases = [case for case in cases if case['id'] in selected_cases]
    report['passed'] = False
    report['expected_runs'] = len(cases) * 2
    report_path = output / ('report-selected.json' if selected_cases else 'report.json')
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    channel = grpc.insecure_channel(tutor_target, options=[('grpc.max_receive_message_length', 32*1024*1024), ('grpc.max_send_message_length', 16*1024*1024)])
    stub = rpc.TutorStub(channel)
    for case in cases:
        source = (ROOT / 'examples' / case['file']).read_text(encoding='utf-8')
        build = post(base, '/api/v1/build/compile', {'content': source, 'lang': case['lang'], 'compile_profile': 'rv32im', 'compiler_opt': '-O0 -g' if case['lang'] == 'c' else ''})
        if build.get('status') != 'success' or not build.get('simulation_token'):
            raise RuntimeError(f"{case['id']}: demo compilation failed")
        deployed_compile = build.get('tutor')
        assert isinstance(deployed_compile, dict), 'Deployed BE did not return compile tutor explanations'
        assert bool(deployed_compile['c_lines']) == (case['lang'] == 'c')
        compiled_tutor = rpc_json(stub.Compile, pb.CompileRequest(request_id=str(uuid4()), source=source, lang=case['lang']))
        assert compiled_tutor['schema_version'] == '1.0'
        assert bool(compiled_tutor['c_lines']) == (case['lang'] == 'c')
        with urlopen(build['binary_url'], timeout=30) as response:
            elf = response.read(256 * 1024 + 1)
        finals = []
        for mode in ('single', 'pipeline'):
            envelope = post(base, '/api/v1/simulation/run', {'simulation_token': build['simulation_token'], 'mode': mode, 'max_cycles': case.get('max_cycles', 2000)})
            result = envelope['result']
            assert envelope['execution_status'] == case.get('status', 'COMPLETED'), f"{case['id']}: wrong status"
            original = deepcopy(result)
            tutor = rpc_json(stub.Analyze, pb.AnalyzeRequest(request_id=str(uuid4()), source=source if case['lang'] == 'c' else '',
                result_json=json.dumps(result, ensure_ascii=False), source_file='source.c' if case['lang'] == 'c' else 'source.s', elf=elf))
            deployed_tutor = envelope.get('tutor')
            assert isinstance(deployed_tutor, dict), 'Deployed BE did not return execution tutor explanations'
            assert deployed_tutor.get('schema_version') == '1.0'
            assert len(deployed_tutor['execution_steps']) == len(result['history'])
            # Compare evidence, allowing local wording fixes and additional source text.
            # BE filters for source.c; standalone ASM has source.s debug lines.
            # Only C line mappings have the same source-file contract here.
            for field in (('pc', 'source_line', 'retire_count') if case['lang'] == 'c' else ('pc', 'retire_count')):
                assert [item.get(field) for item in deployed_tutor['asm_instructions']] == [item.get(field) for item in tutor['asm_instructions']], f'Deployed/local {field} evidence differs'
            for remote_step, local_step in zip(deployed_tutor['execution_steps'], tutor['execution_steps'], strict=True):
                for field in ('history_index', 'cycle', 'display_clock', 'retired_pc', 'register_changes', 'memory_changes', 'memory_transfer'):
                    assert remote_step[field] == local_step[field], f'Deployed/local execution {field} evidence differs'
                assert [(event['type'], event.get('evidence')) for event in remote_step['events']] == [(event['type'], event.get('evidence')) for event in local_step['events']], 'Deployed/local event evidence differs'
            assert result == original, 'Tutor modified the engine result'
            performance = tutor['performance_analysis']
            assert len(performance['snapshots']) == len(result['history'])
            if performance['snapshots']:
                last = performance['snapshots'][-1]
                assert last['cycles'] == len(result['history'])
                assert last['completed'] == result['history'][-1]['global_result']['metrics']['accumulated_instructions']
                observed_stalls = sum(cycle['cycle_events']['stall']['has_stall'] is True for cycle in result['history'])
                observed_flushes = sum(cycle['cycle_events']['control_hazard']['has_flush'] is True for cycle in result['history'])
                observed_overlap = sum(cycle['cycle_events']['stall']['has_stall'] is True and cycle['cycle_events']['control_hazard']['has_flush'] is True for cycle in result['history'])
                assert (last['stall_cycles'], last['flush_cycles'], last['overlap_cycles']) == (observed_stalls, observed_flushes, observed_overlap)
                assert last['hazard_cycles'] == observed_stalls + observed_flushes - observed_overlap
            concept_ids = {concept['id'] for item in tutor['asm_instructions'] for concept in item.get('teaching', {}).get('concepts', [])}
            assert set(case.get('concepts', [])) <= concept_ids, f"{case['id']}: missing learning concepts"
            if case.get('walkthrough'):
                assert any(item.get('teaching', {}).get('walkthrough') for item in tutor['asm_instructions']), 'Missing beginner instruction walkthrough'
            final = result['history'][-1]['global_result']
            actual = int(final['registers']['x10'], 16)
            for reg, key in [('x10', 'a0'), ('x11', 'a1')]:
                if key in case:
                    assert int(final['registers'][reg], 16) == case[key] & 0xFFFFFFFF, f"{case['id']}: unexpected {reg}"
            if case['lang'] == 'c':
                assert any(line['instructions'] for line in tutor['source_mapping']['lines']), 'No C/ASM mapping produced'
                assert all(item['source_file'].replace('\\', '/').split('/')[-1] == 'source.c' for item in tutor['asm_instructions'] if item['source_line'] is not None), 'Runtime source was assigned to user C'
            assert len(tutor['execution_steps']) == len(result['history'])
            assert sum(item['retire_count'] for item in tutor['asm_instructions']) == result['summary']['instructions_executed']
            for item in tutor['asm_instructions']:
                if item['raw_instruction'] and item['text'].startswith(('lui ', 'auipc ')):
                    immediate = int(item['raw_instruction'], 16) >> 12
                    assert f'({immediate} << 12)' in item['explanation']['operation'], 'U immediate was shifted twice'
            if case['id'] == 'cycle_limit':
                assert any(event['type'] == 'cycle_limit' for event in tutor['execution_steps'][-1]['events'])
            if case['id'] == 'misaligned':
                assert any(event['type'] == 'runtime_error' for step in tutor['execution_steps'] for event in step['events'])
            document = {'id': case['id'], 'title': case['title'], 'source': source, 'mode': mode, 'execution_status': envelope['execution_status'],
                        'core_version': envelope['core_version'], 'final_a0': actual if actual < 0x80000000 else actual - 0x100000000,
                        'result': result, 'tutor': tutor, 'deployed_tutor': deployed_tutor, 'passed': True}
            (output / f"{case['id']}-{mode}.json").write_text(json.dumps(document, ensure_ascii=False), encoding='utf-8')
            summary = {key: document[key] for key in ('id', 'title', 'mode', 'execution_status', 'final_a0', 'passed')}
            summary.update({'cycles': len(result['history']), 'mapped_lines': sum(bool(line['instructions']) for line in tutor['source_mapping']['lines']),
                            'concepts_verified': sorted(set(case.get('concepts', [])) & concept_ids),
                            'performance_verified': True,
                            'events': sum(len(step['events']) for step in tutor['execution_steps']), 'deployed_tutor_verified': True})
            report['cases'].append(summary)
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps(summary, ensure_ascii=True))
            finals.append(final)
        if case.get('status', 'COMPLETED') == 'COMPLETED':
            assert finals[0]['registers'] == finals[1]['registers']
            assert finals[0]['memory_snapshot'] == finals[1]['memory_snapshot']
    report['passed'] = len(report['cases']) == len(cases) * 2
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    channel.close()
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--api-base', default='https://d1j3nkcez6kncs.cloudfront.net')
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts')
    parser.add_argument('--target', help='gRPC host:port; omitted starts an ephemeral local server')
    parser.add_argument('--case', action='append', dest='selected_cases', help='Run only this manifest case ID; may be repeated')
    args = parser.parse_args()
    server = None
    if not args.target:
        from service.server import create_server
        server, _, port = create_server('127.0.0.1:0')
        server.start()
        args.target = f'127.0.0.1:{port}'
    try:
        run(args.api_base.rstrip('/'), args.output, args.target, args.selected_cases)
    except Exception as error:
        # urllib exception strings can include signed URLs, so emit only the type/status.
        print(json.dumps({'error': type(error).__name__, 'http_status': error.code if isinstance(error, HTTPError) else None}))
        raise SystemExit(1)

    finally:
        if server is not None:
            server.stop(0).wait()
