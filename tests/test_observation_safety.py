import pytest
from archreactor_tutor.events import instruction_observations, execution_steps


def memory_stage(**overrides):
    return {'pc': '0x10000', 'assembly': 'sb a0,0(sp)', 'status': 'normal',
            'memory_operation': 'store', 'target_address': '0x20000',
            'write_data': '511', **overrides}


@pytest.mark.parametrize('status', ['flush', 'flushed', 'bubble', 'error', 'stall'])
def test_cancelled_or_inactive_memory_stage_does_not_claim_a_store(status):
    assert instruction_observations({'stage_activity': {'MEM': memory_stage(status=status)}}, None, {}) == []


def test_memory_error_does_not_claim_success_even_if_stage_status_is_normal():
    cycle = {'stage_activity': {'MEM': memory_stage()}, 'cycle_events': {
        'runtime_error': {'has_error': True, 'stage': 'MEM', 'code': 'unaligned'},
    }}
    assert instruction_observations(cycle, None, {}) == []


@pytest.mark.parametrize('value', ['511', '0x1FF', 511, -1, '-1'])
def test_byte_store_explains_only_the_byte_written_for_every_value_format(value):
    observations = instruction_observations({'stage_activity': {'MEM': memory_stage(write_data=value)}}, None, {})
    assert len(observations) == 1
    assert '255 (0xFF)' in observations[0]['summary']
    assert '1바이트' in observations[0]['summary']


@pytest.mark.parametrize('status', ['flush', 'flushed', 'bubble', 'error', 'stall', 'stalled'])
def test_inactive_stages_do_not_emit_completion_or_memory_transfer(status):
    stage=memory_stage(status=status,will_write_reg=True,final_write_data='1',destination_register='a0')
    result={'initial_state': {'metrics': {'accumulated_instructions': 0}}, 'history': [{
        'stage_activity': {'WB': stage, 'MEM': stage},
        'global_result': {'metrics': {'accumulated_instructions': 1}},
    }]}
    step=execution_steps(result)[0]
    assert step['retired_pc'] is None
    assert step['register_write'] is None
    assert step['memory_transfer'] is None


def test_runtime_memory_error_does_not_emit_transfer():
    step=execution_steps({'history': [{'stage_activity': {'MEM': memory_stage()},
        'cycle_events': {'runtime_error': {'has_error': True, 'stage': 'MEM'}},
    }]})[0]
    assert step['memory_transfer'] is None


def test_byte_transfer_and_readable_observation_agree_on_the_value_stored():
    step=execution_steps({'history': [{'stage_activity': {'MEM': memory_stage(write_data='511')}}]})[0]
    assert step['memory_transfer']['write_data'] == '255'
    assert '255 (0xFF)' in step['instruction_observations'][0]['summary']
