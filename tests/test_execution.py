from copy import deepcopy
from archreactor_tutor import analyze_execution, simulation_explanations


def cycle(clock, retired, pc='0x00010000', events=None, value='0x00000001'):
    return {'clock': clock, 'stage_activity': {'WB': {'pc': pc, 'assembly': 'addi a0,a0,1', 'status': 'normal'}},
            'cycle_events': events or {}, 'global_result': {'registers': {'x10': value}, 'memory_snapshot': {}, 'metrics': {'accumulated_instructions': retired}}}


def test_repeated_pc_counts_dynamic_retirements_and_preserves_input():
    result = {'initial_state': {'registers': {'x10': '0x00000000'}, 'metrics': {'accumulated_instructions': 0}},
              'program': {'code_mapping': {'0x10000': {'assembly': 'addi a0,a0,1', 'source_line': 1}}},
              'history': [cycle(0, 1), cycle(1, 2, value='0x00000002')]}
    before = deepcopy(result)
    tutor = analyze_execution('x++;', result)
    assert result == before
    assert tutor['asm_instructions'][0]['retire_count'] == 2
    assert tutor['source_mapping']['lines'][0]['retire_count'] == 2
    assert tutor['execution_steps'][1]['register_changes'] == [{'key': 'x10', 'before': '0x00000001', 'after': '0x00000002'}]
    assert tutor['execution_steps'][0]['display_clock'] == 1 and tutor['execution_steps'][0]['cycle'] == 0


def test_all_events_coexist_with_evidence_and_no_prediction_claim():
    events = {'stall': {'has_stall': True, 'stall_desc': 'load-use'},
              'forwarding': {'has_forwarded': True, 'forwarded_operand_count': 2, 'forwarding_info': {'target_register': ['x5', 'x6'], 'forwarded_from': ['MEM', 'WB']}},
              'control_hazard': {'has_control_instruction': True, 'taken': False, 'has_flush': True, 'redirect_pc': '0x10020', 'flushed_stages': ['IF', 'ID']},
              'runtime_error': {'has_error': True, 'stage': 'MEM', 'code': 'unaligned', 'message': 'bad address'}}
    tutor = simulation_explanations({'history': [cycle(12, 0, events=events)]})
    explained = tutor['cycle_explanations'][0]
    assert {item['type'] for item in explained['events']} == {'stall', 'forwarding', 'branch', 'flush', 'runtime_error'}
    assert explained['cycle'] == 12 and explained['history_index'] == 0
    assert '순차 실행' in next(item['summary'] for item in explained['events'] if item['type'] == 'branch')
    assert next(item['evidence'] for item in explained['events'] if item['type'] == 'forwarding') == events['forwarding']


def test_unexecuted_static_code_remains_and_missing_line_is_not_crt():
    result = {'program': {'code_mapping': {
        '0x10000': {'assembly': 'addi a0,zero,1', 'source_line': 1},
        '0x10004': {'assembly': 'addi a0,zero,2', 'source_line': 2},
        '0x10008': {'assembly': 'jalr zero,0(ra)'},
    }}, 'history': []}
    tutor = analyze_execution('x = 1;\nx = 2;', result)
    assert len(tutor['asm_instructions']) == 3
    assert all(item['retire_count'] == 0 for item in tutor['asm_instructions'])
    unmapped = tutor['source_mapping']['unmapped_instructions'][0]
    assert unmapped['runtime_explanation']['category'] == 'unmapped'
    assert '단정하지 않습니다' in unmapped['runtime_explanation']['detail']


def test_out_of_range_or_other_file_lines_are_not_assigned_to_user_source():
    result = {'program': {'code_mapping': {
        '0x10000': {'assembly': 'addi a0,zero,1', 'source_line': 500},
        '0x10004': {'assembly': 'addi a0,zero,2', 'source_line': 1, 'source_file': 'start.S'},
    }}}
    tutor = analyze_execution('int x;', result, 'source.c')
    assert len(tutor['source_mapping']['unmapped_instructions']) == 2
    assert not tutor['source_mapping']['lines'][0]['instructions']


def test_flushed_fetch_is_not_retirement():
    item = cycle(0, 0)
    item['stage_activity']['IF'] = {'pc': '0x10004', 'assembly': 'add a0,a0,a0', 'status': 'flushed'}
    item['stage_activity']['WB']['flush_info'] = {'is_flushed': True}
    tutor = simulation_explanations({'history': [item], 'initial_state': {'metrics': {'accumulated_instructions': 0}}, 'program': {'code_mapping': {'0x10004': {'assembly': 'add a0,a0,a0'}}}})
    assert tutor['asm_instructions'][0]['observed_in_history'] is True
    assert tutor['asm_instructions'][0]['retire_count'] == 0


def test_limit_error_after_final_snapshot_is_visible():
    tutor = simulation_explanations({'history': [cycle(19, 4)], 'status': 'error', 'console_output': '[Error] Execution clock limit exceeded'})
    assert tutor['execution_steps'][-1]['events'][-1]['type'] == 'cycle_limit'


def test_memory_transfer_uses_actual_mem_fields_not_current_register_guess():
    item = cycle(0, 1)
    item['stage_activity']['MEM'] = {'pc': '0x10000', 'assembly': 'lw a0,0(a0)', 'memory_operation': 'load', 'target_address': '0x20000', 'read_data': '0x0000002A', 'write_data': None}
    tutor = simulation_explanations({'history': [item]})
    assert tutor['execution_steps'][0]['memory_transfer']['target_address'] == '0x20000'
    assert tutor['execution_steps'][0]['memory_transfer']['read_data'] == '0x0000002A'


def test_empty_legacy_result_is_supported():
    assert simulation_explanations({})['cycle_explanations'] == []
    assert simulation_explanations({'program': None})['asm_instructions'] == []
