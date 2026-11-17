from copy import deepcopy
from archreactor_tutor import analyze_execution, simulation_explanations


def test_shift_observations_show_effective_amount_and_preserve_core_values():
    stage = {'pc': '0x10000', 'assembly': 'srai a0, t0, 1025', 'status': 'normal',
             'operand_1': '0xFFFFFFF8', 'operand_2': '0x00000401',
             'alu_result': '0xFFFFFFFC', 'alu_operation': 'srai'}
    result = {'history': [{'clock': 0, 'stage_activity': {'EX': stage}, 'global_result': {}}]}
    before = deepcopy(result)
    tutor = simulation_explanations(result)
    text = tutor['execution_steps'][0]['instruction_observations'][0]['summary']
    assert '오른쪽으로 1비트' in text and '0xFFFFFFFC' in text
    assert '부호 비트' in text and '1025' not in text and '0x00000401' not in text
    assert result == before


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


def test_line_flow_exists_when_be_only_supplies_elf_line_metadata():
    result = {'program': {'code_mapping': {
        '0x10000': {'assembly': 'lw a4,-20(s0)', 'source_line': 4},
        '0x10004': {'assembly': 'lw a5,-24(s0)', 'source_line': 4},
        '0x10008': {'assembly': 'add a5,a4,a5', 'source_line': 4},
        '0x1000c': {'assembly': 'sw a5,-28(s0)', 'source_line': 4},
    }}}
    flow = simulation_explanations(result)['line_explanations'][0]
    assert flow['source_line'] == 4
    assert flow['summary'] == '메모리 읽기 → 덧셈 → 메모리 쓰기'
    assert len(flow['steps']) == 4
    assert 'a4' in flow['steps'][0]['summary']


def test_actual_forwarded_operands_are_explained_without_guessing_from_registers():
    frame = cycle(0, 0)
    frame['global_result']['registers'] = {'x14': '0xDEADBEEF'}
    frame['stage_activity']['EX'] = {'pc': '0x10008', 'assembly': 'add a5,a4,a5', 'status': 'forwarding_active',
        'operand_1': '0x00000003', 'operand_2': '0x00000005', 'alu_result': '0x00000008', 'alu_operation': 'add'}
    observations = simulation_explanations({'history': [frame]})['execution_steps'][0]['instruction_observations']
    assert len(observations) == 1
    assert '3 (0x00000003)' in observations[0]['summary']
    assert '5 (0x00000005)' in observations[0]['summary']
    assert '8 (0x00000008)' in observations[0]['summary']
    assert 'DEADBEEF' not in observations[0]['summary']
    frame['stage_activity']['EX']['flush_info'] = {'is_flushed': True}
    assert not simulation_explanations({'history': [frame]})['execution_steps'][0]['instruction_observations']


def test_byte_store_observation_uses_only_the_bits_that_were_stored():
    frame = cycle(0, 0)
    frame['stage_activity']['MEM'] = {'pc': '0x10004', 'assembly': 'sb a5,0(a0)', 'status': 'normal',
        'memory_operation': 'store', 'target_address': '0x20000', 'write_data': '0x12345678'}
    observation = simulation_explanations({'history': [frame]})['execution_steps'][0]['instruction_observations'][0]
    assert '120 (0x78)' in observation['summary']
    assert '12345678' not in observation['summary']


def test_instruction_roles_and_static_connections_retain_all_c_line_instructions():
    result = {'program': {'code_mapping': {
        '0x10000': {'assembly': 'lw a4,-20(s0)', 'source_line': 4},
        '0x10004': {'assembly': 'lw a5,-24(s0)', 'source_line': 4},
        '0x10008': {'assembly': 'add a5,a4,a5', 'source_line': 4},
        '0x1000c': {'assembly': 'sw a5,-28(s0)', 'source_line': 4},
        '0x10010': {'assembly': 'lw a0,0(a1)'},
    }}}
    bundle = simulation_explanations(result)
    instructions = bundle['asm_instructions']
    assert len(bundle['line_explanations'][0]['steps']) == 4
    add = instructions[2]['teaching']
    assert [item['register'] for item in add['register_connections']] == ['x14', 'x15']
    assert '기존 값' in add['principle']
    assert add['operand_roles'][0]['operand'] == 'a5'
    assert instructions[-1]['teaching']['operand_roles'][0]['operand'] == 'a0'


def test_actual_branch_observation_reports_both_paths_and_target_source_line():
    frame = cycle(0, 0)
    frame['stage_activity']['EX'] = {'pc': '0x10000', 'assembly': 'beq a0,a1,8',
        'operand_1': '0x3', 'operand_2': '0x3', 'status': 'normal'}
    frame['cycle_events'] = {'control_hazard': {'has_control_instruction': True, 'stage': 'EX',
        'assembly': 'beq a0,a1,8', 'taken': True, 'target_pc': '0x10008', 'fallthrough_pc': '0x10004'}}
    result = {'program': {'code_mapping': {
        '0x10000': {'assembly': 'beq a0,a1,8', 'source_line': 1},
        '0x10004': {'assembly': 'addi a0,zero,1', 'source_line': 2},
        '0x10008': {'assembly': 'addi a0,zero,2', 'source_line': 3},
    }}, 'history': [frame]}
    observation = simulation_explanations(result)['execution_steps'][0]['instruction_observations'][0]
    assert observation['kind'] == 'control'
    assert '실제 비교 입력' in observation['summary'] and 'C 3줄' in observation['summary']
    frame['cycle_events']['control_hazard']['taken'] = False
    observation = simulation_explanations(result)['execution_steps'][0]['instruction_observations'][0]
    assert '분기하지 않음' in observation['summary'] and 'C 2줄' in observation['summary']


def test_environment_instruction_placeholder_fields_are_not_taught_as_alu_calculations():
    frame = cycle(0, 1)
    frame['stage_activity']['EX'] = {'pc': '0x10000', 'assembly': 'ecall', 'status': 'normal',
        'alu_operation': 'ecall', 'operand_1': '0x0', 'operand_2': '0x0', 'alu_result': '0x0'}
    assert simulation_explanations({'history': [frame]})['execution_steps'][0]['instruction_observations'] == []
