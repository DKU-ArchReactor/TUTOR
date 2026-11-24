"""Public, read-only package interface compatible with the merged BE tutor."""
from hashlib import sha256
from .asm import explain_asm
from .c_syntax import explain_c, strip_comments
from .events import execution_steps
from .mapping import source_mapping
from .models import ExplainItem
from .narrative import instruction_context, line_explanations
from .performance import performance_analysis


def explain(item: ExplainItem):
    if not isinstance(item, ExplainItem):
        item = ExplainItem.model_validate(item)
    if item.kind == 'c':
        return explain_c(item.text)
    result = explain_asm(item.text)
    if item.kind == 'crt':
        result.kind, result.category = 'crt', 'runtime_context'
        result.title = '실행 환경 문맥 확인'
        result.detail = (f'명령어가 저장된 주소: {item.pc}. ' if item.pc else '') + '프로그램 시작을 준비하는 코드인지 확인하려면 앞뒤 명령어와 함수 이름을 함께 봐야 합니다. 이 명령어 하나만으로 시작 코드라고 판단할 수는 없습니다.'
    return result


def compile_explanations(source: str, lang: str, assembly: str | None):
    cleaned = strip_comments(source)
    c_lines = [{'line': line, 'text': text, 'explanation': explain_c(text, cleaned=cleaned[line - 1] if line <= len(cleaned) else '').model_dump()}
               for line, text in enumerate(source.splitlines(), 1)] if lang.lower() == 'c' else []
    instructions = [{'line': line, 'text': text, 'explanation': explain_asm(text).model_dump()}
                    for line, text in enumerate((assembly or '').splitlines(), 1) if text.strip()]
    return {'schema_version': '1.0', 'source_sha256': sha256(source.encode()).hexdigest(), 'c_lines': c_lines, 'asm_instructions': instructions}


def simulation_explanations(result: dict, source: str = '', source_file: str | None = None, *, elf_bytes: bytes | None = None):
    if not isinstance(result, dict):
        raise ValueError('result must be a simulation JSON object')
    history = result.get('history') or []
    if not isinstance(history, list) or len(history) > 2000:
        raise ValueError('history must contain at most 2000 clocks')
    if elf_bytes is not None:
        from .dwarf import enrich_mapping
        result = enrich_mapping(result, elf_bytes, source_file or 'source.c')
    steps = execution_steps(result)
    mapping = source_mapping(source, result, steps, source_file)
    lines = line_explanations(mapping['instructions'])
    for instruction in mapping['instructions']:
        if 'teaching' not in instruction:
            instruction['teaching'] = instruction_context(instruction, {})
    performance = performance_analysis(result, steps, mapping['instructions'])
    return {
        'schema_version': '1.0', 'asm_instructions': mapping['instructions'],
        'performance_analysis': performance,
        'cycle_explanations': [{key: step[key] for key in ('history_index', 'cycle', 'display_clock', 'events')} for step in steps if step['events']],
        'execution_steps': steps, 'source_mapping': mapping,
        'line_explanations': lines,
        'source_sha256': sha256(source.encode()).hexdigest() if source else None,
        'limitations': ['코드와 실행 결과를 설명하는 기능이며, 설명을 읽는 것만으로 프로그램의 실행 상태가 바뀌지는 않습니다.',
                        '문법 규칙은 컴파일러·완전한 C 파서를 대신하지 않습니다. 관찰 값과 정적 의미를 구분합니다.'],
    }


def analyze_execution(source, result, source_file=None, *, elf_bytes=None):
    bundle = simulation_explanations(result, source, source_file, elf_bytes=elf_bytes)
    bundle['c_lines'] = compile_explanations(source, 'c', None)['c_lines']
    return bundle
