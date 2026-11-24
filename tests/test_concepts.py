import pytest
from archreactor_tutor import analyze_execution
from archreactor_tutor.asm import explain_asm
from archreactor_tutor.concepts import instruction_concepts


@pytest.mark.parametrize('assembly, expected', [
    ('lw a5,-24(s0)', {'load-store', 'stack-abi'}),
    ('lbu a0,0(a1)', {'load-store', 'load-extension', 'argument-abi'}),
    ('bltu t0,t1,8', {'signed-compare', 'branch-pc'}),
    ('jal ra,8', {'call-return', 'argument-abi'}),
    ('srai t0,t1,1', {'shift'}),
    ('slli t0,t1,2', {'shift-left'}),
    ('andi t0,t1,7', {'bitwise', 'immediate'}),
    ('lui t0,1', {'upper-immediate'}),
    ('auipc t0,1', {'upper-immediate'}),
    ('div t0,t1,t2', {'m-extension'}),
    ('addi sp,sp,-16', {'word-result', 'immediate', 'stack-abi'}),
    ('mv t0,t1', {'pseudo'}),
    ('addi a0,zero,7', {'word-result', 'immediate', 'argument-abi', 'zero-register'}),
    ('lw zero,0(t0)', {'load-store', 'zero-register'}),
    ('flw a0,0(t0)', set()),
    ('addi t0,t1,5000', set()),
])
def test_topics_follow_supported_instruction_semantics(assembly, expected):
    topics = instruction_concepts(explain_asm(assembly).model_dump())
    assert {topic['id'] for topic in topics} == expected
    for topic in topics:
        assert all(topic[field] for field in ('title', 'plain', 'explanation', 'example', 'question', 'answer'))
        assert all(source['url'].startswith('https://') for source in topic['sources'])


def test_examples_are_static_and_do_not_modify_observed_state():
    result = {'program': {'code_mapping': {'0x10000': {'assembly': 'lb a0,0(t0)', 'source_line': 1}}}, 'history': []}
    bundle = analyze_execution('return *p;', result)
    item = bundle['asm_instructions'][0]
    extension = next(topic for topic in item['teaching']['concepts'] if topic['id'] == 'load-extension')
    assert '음수 -1' in extension['example'] and '255' in extension['example']
    assert '0x' not in extension['example']
    assert bundle['execution_steps'] == []
    assert item['retire_count'] == 0


def test_c_and_isa_rules_have_distinct_sources():
    topics = instruction_concepts(explain_asm('div t0,t1,t2').model_dump())
    assert any('n1570.pdf' in source['url'] for source in topics[0]['sources'])
    assert '정의되지 않은 동작' in topics[0]['answer']


@pytest.mark.parametrize('assembly, text', [
    ('addi a0,a1,5', '명령어에 적힌 숫자 5 (즉치값)'),
    ('add a0,a1,a2', 'a2에 든 값'),
    ('sw a0,4(sp)', '값 전체(4바이트)'),
    ('lh a0,0(t0)', '2바이트'),
    ('lw zero,0(t0)', '메모리 읽기·예외'),
    ('beq t0,t1,8', '실제 선택은 실행 이력'),
    ('jal ra,8', '복귀 주소'),
])
def test_beginner_walkthrough_uses_selected_operands_without_invented_values(assembly, text):
    from archreactor_tutor.narrative import instruction_context
    teaching = instruction_context({'explanation': explain_asm(assembly).model_dump()}, {})
    assert len(teaching['walkthrough']) == 3
    assert text in ' '.join(step['title'] + step['text'] for step in teaching['walkthrough'])


def test_invalid_instruction_does_not_get_confident_beginner_steps():
    from archreactor_tutor.narrative import instruction_context
    teaching = instruction_context({'explanation': explain_asm('addi a0,a1,5000').model_dump()}, {})
    assert teaching['walkthrough'] == []
