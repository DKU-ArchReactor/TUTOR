import pytest
from archreactor_tutor.asm import explain_asm


@pytest.mark.parametrize('instruction', [
    'jalr ra, ra, 20', 'jalr zero, 0(ra)', 'jal ra, 16',
    'bltu a0, a1, 8', 'bge a0, a1, 8', 'lw a0, -4(sp)',
    'addi sp, sp, -16', 'mul a0, a1, a2', 'divu a0, a1, a2',
])
def test_reading_summary_uses_words_instead_of_internal_formulas(instruction):
    explanation = explain_asm(instruction)
    assert explanation.supported
    for formula in ('old(', 's32(', 'u32(', 'low32(', 'high32(', 'quotient(', '& ~', '<<'):
        assert formula not in explanation.summary
        assert formula not in explanation.detail


def test_same_register_jump_explains_input_before_overwrite_and_address_bit():
    explanation = explain_asm('jalr ra, ra, 20')
    assert '실행 전 ra' in explanation.summary
    assert '20바이트' in explanation.summary
    assert '맨 오른쪽 비트를 0' in explanation.summary
    assert '바로 다음 명령어의 주소를 ra에 저장' in explanation.summary
    assert '4바이트 정렬까지 보장하지' in explanation.detail
    assert 'old(ra)' in explanation.operation  # structured semantics remain unchanged
