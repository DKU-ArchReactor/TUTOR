import pytest
from archreactor_tutor.asm import explain_asm

INSTRUCTIONS = (
    [f'{op} a0, a1, a2' for op in ('add','sub','sll','slt','sltu','xor','srl','sra','or','and')]
    + [f'{op} a0, a1, 3' for op in ('addi','slti','sltiu','xori','ori','andi','slli','srli','srai')]
    + [f'{op} a0, 4(a1)' for op in ('lb','lh','lw','lbu','lhu','sb','sh','sw')]
    + [f'{op} a0, a1, target' for op in ('beq','bne','blt','bge','bltu','bgeu')]
    + ['lui a0, 1','auipc a0, 1','jal ra, target','jalr ra, 0(a0)','ecall','ebreak','fence']
)

@pytest.mark.parametrize('instruction', INSTRUCTIONS)
def test_all_40_base_instruction_names_have_meaningful_explanations(instruction):
    result = explain_asm(instruction)
    assert result.category != 'unsupported' or instruction in ('fence', 'ebreak')
    assert result.title and result.summary and result.detail
    assert result.summary != f'{instruction} 명령어입니다.'


def test_environment_call_describes_the_request_without_assuming_an_abi():
    result = explain_asm('ecall')
    assert '서비스' in result.summary
    assert '규약' in result.detail
    assert 'RISC-V ISA 자체가 a7=10을 종료로 정의하지 않습니다' in result.detail


@pytest.mark.parametrize('instruction', INSTRUCTIONS)
def test_supported_base_instructions_explain_a_readable_sequence(instruction):
    from archreactor_tutor.narrative import instruction_context
    explanation = explain_asm(instruction).model_dump()
    teaching = instruction_context({'explanation': explanation}, {})
    assert len(teaching['walkthrough']) == (3 if explanation['supported'] else 0)
    assert all(step['title'] and step['text'] for step in teaching['walkthrough'])
    assert not any(step['text'] == explanation['title'] + ' 연산을 수행합니다.' for step in teaching['walkthrough'])
