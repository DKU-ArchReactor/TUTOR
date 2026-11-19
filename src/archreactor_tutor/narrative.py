"""Instruction sequences and value evidence tied to the engine's actual stages."""
from collections import defaultdict
from .asm import register
from .concepts import instruction_concepts


def instruction_walkthrough(explanation, parts):
    """Read the selected operands, without inventing dynamic values or C bindings."""
    if not explanation.get('supported', True):
        return []
    memory = explanation.get('memory')
    control = explanation.get('control_flow') or {}
    op = explanation.get('opcode')
    if memory and len(parts) == 2:
        load = memory['access'] == 'load'
        return [
            {'title': '위치 찾기', 'text': f'{parts[1]}로 메모리 주소를 계산합니다. 괄호 밖 숫자는 바이트 단위의 거리입니다.'},
            {'title': '읽기' if load else '쓰기', 'text': f"그 주소에서 {memory['width_bits'] // 8}바이트를 읽습니다." if load else f"{parts[0]}의 하위 {memory['width_bits']}비트를 그 주소에 저장합니다."},
            {'title': '결과', 'text': ('x0 쓰기는 버리지만 메모리 읽기·예외 처리는 수행합니다.' if register(parts[0]) == 'x0' else f'읽은 값을 {parts[0]}에 담습니다.') if load else '메모리가 바뀝니다. 데이터를 준 레지스터 값은 이 명령어로 바뀌지 않습니다.'},
        ]
    if control.get('conditional'):
        return [{'title': '값 읽기', 'text': '비교에 사용할 레지스터 값을 읽습니다.'},
                {'title': '조건 검사', 'text': f"조건식 {control['condition']}을 검사합니다."},
                {'title': '다음 위치', 'text': '참이면 분기 목적지로, 거짓이면 다음 명령어로 진행합니다. 실제 선택은 실행 이력에서 확인합니다.'}]
    if explanation['category'] in ('arithmetic', 'stack') and len(parts) == 3:
        rhs = f'{parts[2]}에 든 값' if register(parts[2]) else f'명령어에 적힌 숫자 {parts[2]} (즉치값)'
        return [{'title': '입력 읽기', 'text': f'{parts[1]}에 든 값과 {rhs}을 사용합니다.'},
                {'title': '연산', 'text': f"{explanation['title']} 연산을 수행합니다."},
                {'title': '결과 담기', 'text': '목적지가 x0이므로 결과 쓰기는 버립니다.' if register(parts[0]) == 'x0' else f'결과를 {parts[0]}에 담습니다. 기존에 담겨 있던 값은 새 결과로 바뀝니다.'}]
    if op in ('jal', 'jalr', 'ret', 'call', 'tail', 'jr', 'j'):
        return [{'title': '이동 위치', 'text': '이 명령어가 지정한 주소로 실행 위치를 옮깁니다.'},
                {'title': '복귀 주소', 'text': '목적지 레지스터가 있으면 다음 명령어의 주소를 기록합니다. 목적지가 x0이면 기록은 버립니다.'},
                {'title': '다음 실행', 'text': '이동한 위치의 명령어를 실행합니다. 함수 호출 여부는 목적지와 주변 코드도 함께 확인합니다.'}]
    return []


def instruction_context(entry, previous_writes):
    explanation = entry['explanation']
    parts = [part.strip() for part in (explanation.get('operands') or '').split(',')]
    category = explanation['category']
    roles = []
    principle = ''
    memory = explanation.get('memory')
    control = explanation.get('control_flow') or {}
    if memory and len(parts) == 2:
        load = memory['access'] == 'load'
        roles = [
            {'operand': parts[0], 'role': '읽은 값을 받는 레지스터' if load else '저장할 데이터를 가진 레지스터'},
            {'operand': parts[1], 'role': '기준 레지스터에 바이트 오프셋을 더한 메모리 주소'},
        ]
        principle = ('메모리의 값을 산술 연산에 사용하려면 먼저 레지스터로 읽습니다. '
                     if load else '레지스터에 계산해 둔 값을 메모리에 반영합니다. ')
        principle += f"이번 명령어의 메모리 접근 크기는 {memory['width_bits'] // 8}바이트입니다."
        if load and register(parts[0]) == 'x0':
            roles[0]['role'] = '읽기 결과에 대한 쓰기를 버리는 목적지 x0'
            principle += ' 메모리 읽기는 수행하지만 읽은 값을 x0에 보존하지 않습니다.'
    elif category in ('arithmetic', 'stack') and len(parts) == 3:
        roles = [
            {'operand': parts[0], 'role': '계산 결과를 받는 레지스터'},
            {'operand': parts[1], 'role': '첫 번째 입력값을 가진 레지스터'},
            {'operand': parts[2], 'role': '두 번째 입력값을 가진 레지스터' if register(parts[2]) else '명령어에 직접 적힌 숫자 (즉치값)'},
        ]
        if register(parts[0]) in explanation['reads']:
            principle = f"{parts[0]}의 기존 값을 입력으로 읽은 뒤, 계산 결과로 같은 레지스터를 갱신합니다."
        else:
            principle = '입력값으로 연산하고 목적지 레지스터에 결과를 기록합니다.'
        if register(parts[0]) == 'x0':
            principle = '목적지가 x0이므로 계산 결과에 대한 레지스터 쓰기는 버려집니다.'
    elif control.get('conditional') and parts:
        roles = [{'operand': operand, 'role': '비교에 사용할 레지스터 값'} for operand in parts[:-1]]
        roles.append({'operand': parts[-1], 'role': '분기 조건이 참일 때의 목적지'})
        principle = f"분기 조건은 {control['condition']}입니다. 조건이 거짓이면 현재 명령어 다음 PC + 4로 진행합니다."
        if 's32(' in control['condition']:
            principle += ' s32는 레지스터 값을 부호 있는 32비트 정수로 해석한다는 뜻입니다.'
        elif 'u32(' in control['condition']:
            principle += ' u32는 레지스터 값을 부호 없는 32비트 정수로 해석한다는 뜻입니다.'
    connections = []
    for operand in explanation['reads']:
        producer = previous_writes.get(operand)
        if producer:
            connections.append({'register': operand, 'pc': producer['pc'], 'text': producer['text']})
    return {'operand_roles': roles, 'principle': principle, 'register_connections': connections,
            'walkthrough': instruction_walkthrough(explanation, parts),
            'concepts': instruction_concepts(explanation)}


def line_explanations(instructions):
    grouped = defaultdict(list)
    for instruction in instructions:
        if instruction['source_line'] is not None:
            grouped[instruction['source_line']].append(instruction)
    output = []
    for line, entries in sorted(grouped.items()):
        phases = []
        previous_writes = {}
        for entry in entries:
            explanation = entry['explanation']
            entry['teaching'] = instruction_context(entry, previous_writes)
            for operand in explanation['writes']:
                previous_writes[operand] = entry
            if explanation.get('control_flow'):
                previous_writes.clear()
            phase = explanation['title']
            if not phases or phases[-1] != phase:
                phases.append(phase)
        output.append({
            'source_line': line,
            'summary': ' → '.join(phases),
            'detail': '컴파일러가 이 C 줄에 연결한 명령어를 주소 순서로 보여줍니다. 실제 실행 경로와 반복 횟수는 선택한 클록의 이력에서 확인할 수 있습니다.',
            'steps': [{'pc': entry['pc'], 'text': entry['text'], 'summary': entry['explanation']['summary']} for entry in entries],
        })
    return output
