from copy import deepcopy

import pytest

from archreactor_tutor.asm import explain_asm, explain_encoded_asm
from archreactor_tutor.events import instruction_observations


@pytest.mark.parametrize('instruction, expected', [
    ('lw a5,-24(s0)', ('앞쪽으로 24바이트', '4바이트', 'a5 레지스터')),
    ('sw ra,28(sp)', ('뒤쪽으로 28바이트', '데이터를 준 레지스터의 값은 바뀌지')),
    ('addi sp,sp,-32', ('작은 주소', '32바이트', '메모리의 데이터를 옮기는 명령어는 아닙니다')),
    ('srai a0,a1,3', ('오른쪽', '3칸', '부호 비트')),
    ('and a0,a1,a2', ('둘 다 1인 자리', 'a0 레지스터')),
    ('sltiu a0,a1,-1', ('0 이상의 정수', '아니면 0')),
])
def test_instruction_meaning_names_the_inputs_action_and_destination(instruction, expected):
    text = explain_asm(instruction).summary
    assert all(fragment in text for fragment in expected)


def observe(stage, name='MEM', retired=None):
    cycle = {'stage_activity': {name: {'status': 'normal', 'pc': '0x10000', **stage}}}
    before = deepcopy(cycle)
    result = instruction_observations(cycle, retired, {})[0]['summary']
    assert cycle == before
    return result


def test_store_distinguishes_memory_location_value_source_and_width():
    text = observe({'assembly': 'sw ra,28(sp)', 'memory_operation': 'store',
                    'target_address': '0x7FFFEFF8', 'write_data': '0x00010008'})
    assert '0x7FFFEFF8번 위치' in text
    assert 'ra 레지스터에서 가져온 값 65544' in text
    assert '4바이트 크기로 저장' in text
    assert '레지스터의 값은 그대로' in text


def test_address_calculation_explains_negative_offset_without_claiming_a_transfer():
    text = observe({'assembly': 'lw a5,-24(s0)', 'operand_1': '0x2000',
                    'operand_2': '0xFFFFFFE8', 'alu_result': '0x1FE8'}, 'EX')
    assert 's0 레지스터에 담긴 주소' in text
    assert '앞쪽으로 24바이트' in text
    assert '아직 데이터를 읽거나 쓴 단계는 아닙니다' in text


def test_zero_write_does_not_claim_the_register_changed():
    text = observe({'assembly': 'addi zero,a0,1', 'will_write_reg': True,
                    'destination_register': 'x0', 'final_write_data': '0x00000005'}, 'WB', '0x00010000')
    assert '항상 0' in text
    assert '바꿨습니다' not in text


def test_encoded_upper_immediate_explains_the_number_without_internal_jargon():
    result = explain_encoded_asm('auipc ra,0', '0x00000097')
    text = result.summary + result.detail
    assert '주소를 ra 레지스터에 복사' in result.summary
    assert '숫자가 0' in result.summary
    assert result.operands == 'ra, 0'
    assert result.operation == 'x1 = PC + (0 << 12)'
    assert '상위 즉치 필드' not in text
    assert 'CORE 표시 문자열' not in text


@pytest.mark.parametrize('instruction, operands', [
    ('addi sp,sp,-32', ['sp','sp','-32']),
    ('add a0,a0,a0', ['a0','a0','a0']),
    ('sw sp,0(sp)', ['sp','0(sp)']),
    ('jalr ra,ra,20', ['ra','ra','20']),
    ('beq a0,a0,8', ['a0','a0','8']),
    ('lui a0,1', ['a0','1']),
    ('mv a0,a0', ['a0','a0']),
])
def test_operand_roles_preserve_written_order_even_when_names_repeat(instruction, operands):
    from archreactor_tutor.narrative import instruction_context
    explanation = explain_asm(instruction).model_dump()
    roles = instruction_context({'explanation': explanation}, {})['operand_roles']
    assert [role['operand'] for role in roles] == operands
    assert all(role['role'] for role in roles)
    if instruction.startswith('addi'):
        assert '결과를 넣을' in roles[0]['role']
        assert '실행하기 전' in roles[1]['role']


@pytest.mark.parametrize('instruction', [
    'lb a0,0(a1)', 'lbu a0,0(a1)', 'slt a0,a1,a2', 'beq a0,a1,8',
    'jal ra,8', 'slli a0,a1,2', 'srai a0,a1,1', 'div a0,a1,a2',
    'addi sp,sp,-16', 'and a0,a1,a2', 'lui a0,1', 'mv a0,a1',
])
def test_all_reading_layers_avoid_internal_notation_and_unexplained_developer_names(instruction):
    import json
    from archreactor_tutor.narrative import instruction_context
    explanation = explain_asm(instruction).model_dump()
    teaching = instruction_context({'explanation': explanation}, {})
    text = explanation['summary'] + explanation['detail'] + json.dumps(teaching, ensure_ascii=False)
    for fragment in ('CORE', 'DWARF', 'INT_MIN', 'old(', 'u32(', 's32(', 'low32(', 'high32(', 'quotient('):
        assert fragment not in text


@pytest.mark.parametrize('instruction, expected', [
    ('mv t0,t1', 't1의 값을'), ('li t0,7', '숫자 7'), ('ret', 'ra에 기억해 둔 주소'),
    ('not t0,t1', '0은 1로'), ('neg t0,t1', '0에서 t1'), ('seqz t0,t1', '0이면'),
])
def test_common_short_instruction_names_describe_the_actual_action(instruction, expected):
    explanation = explain_asm(instruction)
    assert expected in explanation.summary
    assert 'rd' not in explanation.detail and ' rs' not in explanation.detail
