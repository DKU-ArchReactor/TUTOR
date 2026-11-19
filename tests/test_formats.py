import pytest
from archreactor_tutor.formats import instruction_format
from archreactor_tutor import simulation_explanations


@pytest.mark.parametrize('word,name,immediate', [
    ('0x00C58533', 'R', None), ('0xFFF58513', 'I', -1),
    ('0xFEA42E23', 'S', -4), ('0xFE059CE3', 'B', -8),
    ('0x00001537', 'U', 4096), ('0x008000EF', 'J', 8),
    ('0x4025D513', 'I', 2), ('0x00000073', 'I', None),
])
def test_format_reconstructs_exact_word_and_immediate(word, name, immediate):
    result = instruction_format(word)
    assert result['name'] == name and result['immediate'] == immediate
    assert sum(field['width'] for field in result['fields']) == 32
    reconstructed = sum(field['value'] << field['low'] for field in result['fields'])
    assert reconstructed == int(word, 16)
    positions = [bit for field in result['fields'] for bit in range(field['low'], field['high'] + 1)]
    assert sorted(positions) == list(range(32))


def test_store_and_branch_have_no_destination_and_shift_excludes_function_bits():
    for word in ('0xFEA42E23', '0xFE059CE3'):
        assert 'rd' not in [field['name'] for field in instruction_format(word)['fields']]
    fields = {field['name']: field['value'] for field in instruction_format('0x4025D513')['fields']}
    assert fields['shamt'] == 2 and fields['funct7'] == 32
    assert instruction_format('invalid') is None
    assert instruction_format('0xFFFFFFFF') is None


def test_mapping_exposes_format_without_changing_core_input():
    core = {'program': {'code_mapping': {'0x10000': {'assembly': 'add a0,a1,a2', 'raw_instruction': '0x00C58533'}}}}
    tutor = simulation_explanations(core)
    assert tutor['asm_instructions'][0]['instruction_format']['name'] == 'R'
    assert 'instruction_format' not in core['program']['code_mapping']['0x10000']


@pytest.mark.parametrize('assembly,word', [
    ('add a0,a1,a2', '0x00C58533'), ('addi a0,a1,-1', '0xFFF58513'),
    ('sw a0,-4(s0)', '0xFEA42E23'), ('bne a1,zero,-8', '0xFE059CE3'),
    ('lui a0,4096', '0x00001537'), ('jal ra,8', '0x008000EF'),
    ('jalr ra,ra,8', '0x008080E7'), ('ecall', '0x00000073'),
])
def test_all_base_formats_have_operand_roles_and_a_walkthrough(assembly, word):
    core = {'program': {'code_mapping': {'0x10000': {'assembly': assembly, 'raw_instruction': word, 'source_line': 1}}}}
    item = simulation_explanations(core, 'int main(void) {')['asm_instructions'][0]
    assert item['instruction_format']
    assert item['teaching']['operand_roles'] and item['teaching']['principle']
    assert len(item['teaching']['walkthrough']) >= 3
