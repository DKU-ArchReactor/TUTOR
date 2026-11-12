import pytest
from archreactor_tutor import ExplainItem, explain, compile_explanations
from archreactor_tutor.asm import explain_asm


@pytest.mark.parametrize('text,category', [
    ('', 'empty'), ('// comment', 'comment'), ('#define VALUE 3', 'preprocessor'),
    ('int main(void) {', 'function'), ('int f(int x);', 'function'),
    ('return value;', 'return'), ('if (x)', 'if'), ('} else if (y) {', 'else_if'),
    ('} else {', 'else'), ('for (;;) {', 'for'), ('while (x)', 'while'), ('do {', 'do'),
    ('switch(x) {', 'switch'), ('case 1:', 'case'), ('default:', 'default'),
    ('break;', 'break'), ('continue;', 'continue'), ('goto done;', 'goto'), ('done:', 'label'),
    ('int x = 2;', 'initialization'), ('volatile unsigned int x;', 'declaration'),
    ('volatile int *p = values;', 'initialization'), ('int a[4];', 'declaration'),
    ('*p = 5;', 'assignment'), ('a[i] += 3;', 'assignment'), ('++x;', 'increment'),
    ('puts("a=b // not a comment");', 'call'), ('typedef unsigned int word;', 'typedef'),
    ('struct Pair {', 'type_definition'), ('}', 'scope'),
])
def test_c_constructs(text, category):
    assert explain(ExplainItem(kind='c', text=text)).category == category


def test_source_comment_context_and_strings():
    source = '/* start\n * not code\n */\nint *p;\n*p = 5;\nputs("// literal");'
    lines = compile_explanations(source, 'c', None)['c_lines']
    assert [item['explanation']['category'] for item in lines] == ['comment', 'comment', 'comment', 'declaration', 'assignment', 'call']
    assert lines[-1]['text'] == 'puts("// literal");'


def test_c_explanations_do_not_invent_machine_outcomes():
    for text in ('int x;', 'int x = 0;', '{', '}'):
        assert '반드시' not in explain(ExplainItem(kind='c', text=text)).summary
    result = explain(ExplainItem(kind='c', text='if (p && *p) {'))
    assert '단락 평가' in result.detail
    assert '예측 실패' not in result.detail


@pytest.mark.parametrize('instruction,reads,writes', [
    ('add a0, a1, a2', ['x11', 'x12'], ['x10']),
    ('add x0, x1, x2', ['x1', 'x2'], []),
    ('addi sp, sp, -16', ['x2'], ['x2']),
    ('lw a0, -4(s0)', ['x8'], ['x10']),
    ('sw a0, 0(sp)', ['x10', 'x2'], []),
    ('beq a0, a1, 8', ['x10', 'x11'], []),
    ('jal zero, 12', [], []),
    ('jalr ra, 20(ra)', ['x1'], ['x1']),
    ('jalr ra, ra, 20', ['x1'], ['x1']),
    ('ret', ['x1'], []),
])
def test_register_roles(instruction, reads, writes):
    result = explain_asm(instruction)
    assert result.supported
    assert result.reads == reads and result.writes == writes


@pytest.mark.parametrize('opcode,extension,width', [('lb', 'sign', 8), ('lbu', 'zero', 8), ('lh', 'sign', 16), ('lhu', 'zero', 16), ('lw', 'none', 32)])
def test_load_width_and_extension(opcode, extension, width):
    result = explain_asm(f'{opcode} a0, -4(sp)')
    assert result.memory['extension'] == extension and result.memory['width_bits'] == width
    assert result.memory['address_expression'] == 'u32(sp + -4)'


@pytest.mark.parametrize('op', ['sll', 'srl', 'sra', 'slt', 'sltu', 'and', 'or', 'xor', 'mul', 'mulh', 'mulhsu', 'mulhu', 'div', 'divu', 'rem', 'remu'])
def test_rv32_integer_operations_have_specific_semantics(op):
    result = explain_asm(f'{op} a0, a1, a2')
    assert result.supported and result.operation
    assert result.reads == ['x11', 'x12']
    assert result.writes == ['x10']


def test_jalr_pc_rules_and_auipc_whole_pc():
    result = explain_asm('jalr zero, 4(ra)')
    assert result.control_flow['target_expression'] == '(ra + 4) & ~1'
    assert result.control_flow['link_register'] is None
    assert 'PC + 4' in result.operation
    assert explain_asm('auipc a0, 1').operation == 'a0 = PC + (1 << 12)'


def test_division_edge_semantics():
    result = explain_asm('div a0, a1, a2')
    assert '0xFFFFFFFF' in result.detail and 'INT_MIN' in result.detail
    assert '0 방향' in result.detail


@pytest.mark.parametrize('text', ['addi a0', 'add a0, bad, a1', 'addi a0, a1, 2048', 'slli a0, a1, 32', 'lw a0, 9999(sp)', 'jalr a0, 4096(a1)', 'mv a0', 'ret a0'])
def test_invalid_operands_are_not_explained_as_valid(text):
    result = explain_asm(text)
    assert result.category == 'invalid' and not result.supported


def test_unknown_instructions_and_runtime_do_not_guess():
    assert not explain_asm('ld a0, 0(sp)').supported
    result = explain(ExplainItem(kind='crt', text='auipc ra, 0', pc='0x10000'))
    assert 'main 호출·초기화 여부' in result.detail
    assert 'PC 0x10000' in result.detail


@pytest.mark.parametrize('text', ['beq a0,a1,8', 'bne a0,a1,8', 'blt a0,a1,8', 'bge a0,a1,8', 'bltu a0,a1,8', 'bgeu a0,a1,8'])
def test_static_branch_never_claims_it_was_taken(text):
    result = explain_asm(text)
    assert result.control_flow['conditional'] is True
    assert result.writes == []
    assert '실제 taken' in result.detail
