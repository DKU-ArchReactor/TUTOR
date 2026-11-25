import pytest
from archreactor_tutor import analyze_execution


@pytest.mark.parametrize('asm', ['lui zero,-1', 'auipc x0,1048575'])
def test_u_instruction_walkthrough_respects_discarded_destination_and_32_bit_result(asm):
    item=analyze_execution('', {'program': {'code_mapping': {'0x10000': {'assembly': asm}}}})['asm_instructions'][0]
    steps=item['teaching']['walkthrough']
    assert '4294963200' in steps[1]['text']
    assert '보관하지 않습니다' in steps[2]['text']
    assert '저장합니다' not in steps[2]['text']
