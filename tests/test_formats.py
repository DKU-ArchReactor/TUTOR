import pytest
from archreactor_tutor.formats import instruction_format
from archreactor_tutor import simulation_explanations
from archreactor_tutor.asm import explain_asm
from archreactor_tutor.narrative import instruction_context


# RV32I v2.1: 40 distinct base instructions, including FENCE and EBREAK.
BASE_CASES = [
    ('lui a0,1', 0x00001537, 'U'), ('auipc a0,1', 0x00001517, 'U'),
    ('jal ra,8', 0x008000EF, 'J'), ('jalr ra,a1,0', 0x000580E7, 'I'),
    *[(f'{op} a1,a2,0', 0x00C58063 | (funct << 12), 'B') for op, funct in [('beq',0),('bne',1),('blt',4),('bge',5),('bltu',6),('bgeu',7)]],
    *[(f'{op} a0,0(a1)', 0x00058503 | (funct << 12), 'I') for op, funct in [('lb',0),('lh',1),('lw',2),('lbu',4),('lhu',5)]],
    *[(f'{op} a0,0(a1)', 0x00A58023 | (funct << 12), 'S') for op, funct in [('sb',0),('sh',1),('sw',2)]],
    *[(f'{op} a0,a1,1', 0x00158513 | (funct << 12), 'I') for op, funct in [('addi',0),('slti',2),('sltiu',3),('xori',4),('ori',6),('andi',7),('slli',1),('srli',5)]],
    ('srai a0,a1,1', 0x4015D513, 'I'),
    *[(f'{op} a0,a1,a2', 0x00C58533 | (funct << 12), 'R') for op, funct in [('add',0),('sll',1),('slt',2),('sltu',3),('xor',4),('srl',5),('or',6),('and',7)]],
    ('sub a0,a1,a2', 0x40C58533, 'R'), ('sra a0,a1,a2', 0x40C5D533, 'R'),
    ('fence iorw,iorw', 0x0FF0000F, 'I'), ('ecall', 0x00000073, 'I'), ('ebreak', 0x00100073, 'I'),
]


@pytest.mark.parametrize('assembly,word,expected', BASE_CASES)
def test_all_40_base_instructions_have_format_semantics_and_teaching(assembly, word, expected):
    assert len(BASE_CASES) == 40
    explanation = explain_asm(assembly).model_dump()
    assert explanation['category'] != 'unsupported' or assembly.split()[0] in ('fence', 'ebreak')
    format = instruction_format(f'0x{word:08X}')
    assert format['name'] == expected
    assert sum(field['value'] << field['low'] for field in format['fields']) == word
    teaching = instruction_context({'explanation': explanation}, {})
    assert teaching['operand_roles'] and teaching['principle']
    assert len(teaching['walkthrough']) >= 3
    assert explanation['supported'] is (assembly.split()[0] not in ('fence', 'ebreak'))


def test_fence_fields_are_ordering_sets_not_an_arithmetic_immediate():
    format = instruction_format('0x0FF0000F')
    assert format['immediate'] is None
    assert {field['name']: field['value'] for field in format['fields']}['pred'] == 15
    assert 'CORE' in format['description']


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
