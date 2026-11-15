from copy import deepcopy
from archreactor_tutor import simulation_explanations


def frame(index, retired, stall=False, flush=False, forward=False):
    return {'clock': 12, 'stage_activity': {
        'ID': {'pc': '0x10004', 'assembly': 'add a0,t0,a1', 'status': 'stalled' if stall else 'normal'},
        'EX': {'pc': '0x10000', 'assembly': 'lw t0,0(sp)', 'status': 'normal'},
        'MEM': {'pc': '0x10008', 'assembly': 'addi t0,t0,1', 'status': 'normal'},
        'WB': {'pc': '0x1000C', 'assembly': 'add a2,a2,a3', 'status': 'normal'}},
        'cycle_events': {'stall': {'has_stall': stall, 'stage': 'ID', 'assembly': 'add a0,t0,a1', 'stall_reason': 'load_use'},
                         'forwarding': {'has_forwarded': forward, 'stage': 'EX', 'assembly': 'lw t0,0(sp)'},
                         'control_hazard': {'has_control_instruction': flush, 'has_flush': flush, 'stage': 'EX', 'assembly': 'lw t0,0(sp)', 'taken': True}},
        'global_result': {'metrics': {'accumulated_instructions': retired}, 'registers': {}, 'memory_snapshot': {}}}


def result(frames):
    return {'simulator': {'mode': 'pipeline'}, 'initial_state': {'metrics': {'accumulated_instructions': 0}}, 'history': frames,
            'program': {'code_mapping': {'0x10000': {'assembly': 'lw t0,0(sp)', 'source_line': 1},
                                         '0x10004': {'assembly': 'add a0,t0,a1', 'source_line': 2}}}}


def test_overlapping_hazards_are_counted_once_per_history_frame_and_prefix():
    raw = result([frame(0, 0, stall=True, flush=True), frame(1, 1, stall=True, forward=True), frame(2, 1)])
    original = deepcopy(raw)
    analysis = simulation_explanations(raw)['performance_analysis']
    first, second, last = analysis['snapshots']
    assert first['hazard_cycles'] == 1 and first['overlap_cycles'] == 1
    assert second['hazard_cycles'] == 2 and second['completed'] == 1 and second['cpi'] == 2
    assert last['cycles'] == 3 and last['cpi'] == 3 and last['extra_cycles'] == 2
    assert last['stall_cycles'] == 2 and last['flush_cycles'] == 1 and last['forwarding_cycles'] == 1
    assert last['idle_cycles'] == 2 and last['hazard_idle_cycles'] == 1 and last['other_idle_cycles'] == 1
    assert raw == original


def test_stall_is_attached_to_consumer_and_nearest_register_writer():
    tutor = simulation_explanations(result([frame(0, 0, stall=True)]))
    record = tutor['performance_analysis']['records'][0]
    assert record['instruction']['pc'] == '0x00010004'
    assert record['instruction']['source_line'] == 2
    assert [(item['register'], item['stage'], item['pc']) for item in record['dependencies']] == [('x5', 'EX', '0x00010000')]
    assert 'lw t0,0(sp)' in record['detail'] and 'x5' in record['detail']
    assert tutor['cycle_explanations'][0]['events'][0]['detail'] == record['detail']


def test_generic_stall_does_not_claim_load_use_or_assign_a_data_cause():
    raw = result([frame(0, 0, stall=True)])
    raw['history'][0]['cycle_events']['stall']['stall_reason'] = 'structural'
    record = simulation_explanations(raw)['performance_analysis']['records'][0]
    assert record['title'] == '명령어 진행 대기' and record['dependencies'] == []
    assert 'load' not in record['title'].lower()


def test_mismatched_stage_assembly_is_not_assigned_to_a_program_pc():
    raw = result([frame(0, 0, stall=True)])
    raw['history'][0]['cycle_events']['stall']['assembly'] = 'different instruction'
    record = simulation_explanations(raw)['performance_analysis']['records'][0]
    assert record['instruction']['pc'] is None and record['dependencies'] == []


def test_missing_and_jumping_retirement_counters_do_not_become_zero_cost():
    raw = result([frame(0, 0), frame(1, 2)])
    del raw['history'][0]['global_result']['metrics']['accumulated_instructions']
    snapshots = simulation_explanations(raw)['performance_analysis']['snapshots']
    assert snapshots[0]['completed'] is None and snapshots[0]['cpi'] is None
    assert snapshots[1]['extra_cycles'] is None and snapshots[1]['unknown_completion_cycles'] == 2
    assert snapshots[1]['idle_cycles'] == 0


def test_initial_or_empty_history_has_no_future_performance_snapshot():
    assert simulation_explanations({})['performance_analysis']['snapshots'] == []


def test_forwarding_counts_observed_clocks_without_inventing_saved_clocks():
    analysis = simulation_explanations(result([frame(0, 1, forward=True)]))['performance_analysis']
    assert analysis['snapshots'][0]['forwarding_cycles'] == 1
    assert 'saved_cycles' not in analysis['snapshots'][0]
