from archreactor_tutor import analyze_execution


def test_file_evidence_distinguishes_startup_from_missing_debug_without_guessing_from_function():
    result = {'program': {'code_mapping': {
        '0x10000': {'assembly': 'auipc ra,0', 'source_file': '/tmp/start.S', 'external_source_line': 4},
        '0x10004': {'assembly': 'jalr ra,ra,20', 'function': '_start'},
        '0x10008': {'assembly': 'addi a0,zero,1', 'source_file': 'source.c', 'source_line': 1},
    }}}
    items = analyze_execution('int a = 1;', result, 'source.c')['asm_instructions']
    assert [x['source_context'] for x in items] == ['startup_source', 'unknown', 'user_source']
    assert items[0]['mapping_status'] == items[1]['mapping_status'] == 'unmapped'
    assert items[0]['external_source_line'] == 4
    assert items[1]['source_line'] is None
    assert all(x['explanation']['summary'] for x in items)


def test_default_c_source_never_claims_startup_file_line_as_user_line():
    result = {'program': {'code_mapping': {'0x10000': {
        'assembly': 'auipc ra,0', 'source_file': 'start.S', 'source_line': 1,
    }}}}
    item = analyze_execution('int main(void) {', result)['asm_instructions'][0]
    assert item['source_line'] is None
    assert item['source_context'] == 'startup_source'


def test_missing_source_text_still_does_not_assign_startup_line_to_c():
    result = {'program': {'code_mapping': {'0x10000': {
        'assembly': 'auipc ra,0', 'source_file': 'start.S', 'source_line': 1,
    }}}}
    item = analyze_execution('', result)['asm_instructions'][0]
    assert item['source_line'] is None
    assert item['mapping_status'] == 'unmapped'


def test_unmapped_startup_instructions_have_plain_meaning_without_requiring_dwarf():
    result = {'program': {'code_mapping': {
        '0x10000': {'assembly': 'auipc ra,0', 'raw_instruction': '0x00000097'},
        '0x10004': {'assembly': 'jalr ra,ra,20'},
        '0x10008': {'assembly': 'addi a7,zero,10'},
        '0x1000c': {'assembly': 'ecall'},
    }}}
    items = analyze_execution('', result)['asm_instructions']
    assert all(x['source_context'] == 'unknown' and x['mapping_status'] == 'unmapped' for x in items)
    assert '현재 명령어가 놓인 주소' in items[0]['explanation']['summary']
    assert '복사' in items[0]['explanation']['summary']
    assert '점프' in items[1]['explanation']['summary']
    assert all(x['explanation']['summary'] != x['explanation'].get('operation') for x in items)
