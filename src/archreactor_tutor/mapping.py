"""Use PC/line metadata, never align source rows by ordinal or instruction text."""
from collections import Counter
from .asm import explain_encoded_asm
from .events import obj, pc


def source_mapping(source, result, steps, source_file=None):
    program = obj(result.get('program'))
    mapping = obj(program.get('code_mapping'))
    basis = 'provided_code_mapping' if mapping else 'instruction_table_without_source_lines'
    if not mapping:
        mapping = {item['pc']: item for item in program.get('instructions', []) if isinstance(item, dict) and item.get('pc')}
    if len(mapping) > 16384:
        raise ValueError('Static mapping exceeds the 64 KiB instruction budget')
    if any(obj(entry).get('mapping_basis') == 'elf_dwarf' for entry in mapping.values()):
        basis = 'elf_dwarf'
    retire_counts = Counter(step['retired_pc'] for step in steps if step['retired_pc'])
    observed = {stage['pc'] for step in steps for stage in step['stages'] if stage['pc']}
    source_lines = source.splitlines()
    lines = {number: {'source_line': number, 'text': text, 'instructions': [], 'retire_count': 0} for number, text in enumerate(source_lines, 1)}
    entries, warnings = [], []
    if not mapping:
        warnings.append('정적 명령어 테이블이 없어 전체 C–ASM 매핑을 만들 수 없습니다. 실행 이력만으로 실행되지 않은 코드를 재구성하지 않습니다.')
    for raw_pc, raw_entry in sorted(mapping.items(), key=lambda pair: pc(pair[0]) or ''):
        entry = obj(raw_entry)
        address = pc(raw_pc)
        if not address or not isinstance(entry.get('assembly'), str):
            warnings.append('잘못된 PC 또는 명령어 정보가 있어 해당 매핑을 제외했습니다.')
            continue
        number = entry.get('source_line')
        file_name = entry.get('source_file') or entry.get('file')
        valid = type(number) is int and number > 0
        reason = None
        if source_file and isinstance(file_name, str) and file_name.replace('\\', '/').split('/')[-1] != source_file.replace('\\', '/').split('/')[-1]:
            valid, reason = False, 'different_source_file'
        elif valid and source_lines and number > len(source_lines):
            valid, reason = False, 'source_line_out_of_range'
        elif not valid:
            reason = 'missing_source_location'
        explanation = explain_encoded_asm(entry['assembly'], entry.get('raw_instruction')).model_dump()
        record = {
            'pc': address, 'raw_instruction': entry.get('raw_instruction'), 'text': entry['assembly'],
            'source_line': number if valid else None, 'reported_source_line': number,
            'source_file': file_name, 'source_column': entry.get('source_column'),
            'function': entry.get('function'), 'mapping_status': 'mapped' if valid else 'unmapped',
            'unmapped_reason': reason, 'mapping_basis': basis if valid else 'none',
            'retire_count': retire_counts[address], 'observed_in_history': address in observed,
            'explanation': explanation, 'runtime_explanation': None,
        }
        if not valid:
            record['runtime_explanation'] = {**explanation, 'kind': 'crt', 'category': 'unmapped', 'title': '소스 위치를 확인할 수 없는 명령어', 'summary': '실행 환경 코드 또는 디버그 정보가 없는 사용자 코드일 수 있습니다.', 'detail': 'C 줄 매핑이 없다는 사실만으로 CRT·main 호출·초기화라고 단정하지 않습니다. ' + explanation['detail']}
        entries.append(record)
        if valid and number in lines:
            lines[number]['instructions'].append(record)
            lines[number]['retire_count'] += record['retire_count']
    return {
        'basis': basis, 'lines': list(lines.values()), 'instructions': entries,
        'unmapped_instructions': [item for item in entries if item['mapping_status'] == 'unmapped'],
        'warnings': list(dict.fromkeys(warnings)),
        'notes': ['컴파일러 줄 정보는 소스와 명령어의 대응 근거이며, C 표현식 전체의 의미나 변수의 정확한 저장 위치를 보증하지 않습니다.',
                  'retire_count가 0인 명령어도 정적 테이블에 유지합니다. 인출된 적이 있어도 플러시됐다면 완료된 명령어로 세지 않습니다.',
                  'source_file이 제공되지 않으면 파일 간 동일 줄 번호를 완전히 구분할 수 없습니다.'],
    }
