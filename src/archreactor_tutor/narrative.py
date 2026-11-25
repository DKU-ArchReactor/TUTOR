"""Instruction sequences and value evidence tied to the engine's actual stages."""
from collections import defaultdict
import re
from .asm import register, with_particle
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
        address = re.fullmatch(r'(-?(?:0[xX][\da-fA-F]+|\d+))\s*\(\s*(\w+)\s*\)', parts[1])
        location = '괄호 안 레지스터에 든 주소에서 괄호 밖 숫자만큼 이동한 위치를 찾습니다.'
        if address:
            distance = int(address[1], 0)
            location = (f'{address[2]}에 담긴 주소가 출발점입니다. '
                        + (f"여기서 {'앞쪽(작은 주소)' if distance < 0 else '뒤쪽(큰 주소)'}으로 {abs(distance)}바이트 이동합니다." if distance else '거리가 0이므로 그 주소를 그대로 사용합니다.'))
        portion = '값 전체' if memory['width_bits'] == 32 else f"값의 오른쪽 {memory['width_bits']}비트"
        return [
            {'title': '메모리에서 어디를 찾나요?', 'text': location},
            {'title': '어떤 데이터를 옮기나요?', 'text': f"찾은 위치에서 {memory['width_bits'] // 8}바이트를 읽습니다. 주소 자체가 아니라 그 위치에 들어 있는 내용을 읽습니다." if load else f"{parts[0]}에 담긴 {portion}({memory['width_bits'] // 8}바이트)를 찾은 메모리 위치에 복사합니다."},
            {'title': '결과', 'text': ('x0 쓰기는 버리지만 메모리 읽기·예외 처리는 수행합니다.' if register(parts[0]) == 'x0' else f'읽은 값을 {parts[0]}에 담습니다.') if load else '메모리가 바뀝니다. 데이터를 준 레지스터 값은 이 명령어로 바뀌지 않습니다.'},
        ]
    if control.get('conditional'):
        return [{'title': '값 읽기', 'text': '비교에 사용할 레지스터 값을 읽습니다.'},
                {'title': '조건 검사', 'text': explanation['summary']},
                {'title': '다음 위치', 'text': '참이면 분기 목적지로, 거짓이면 다음 명령어로 진행합니다. 실제 선택은 실행 이력에서 확인합니다.'}]
    if explanation['category'] in ('arithmetic', 'stack') and len(parts) == 3:
        rhs = f'{parts[2]}에 든 값' if register(parts[2]) else f'명령어에 적힌 숫자 {parts[2]} (즉치값)'
        operation = {
            'add': '두 입력값을 더합니다.', 'addi': '레지스터의 값에 명령어에 적힌 숫자를 더합니다.',
            'sub': '첫 번째 입력값에서 두 번째 입력값을 뺍니다.',
            'and': '같은 자리의 두 비트가 모두 1일 때만 그 자리를 1로 만듭니다.',
            'or': '같은 자리의 두 비트 중 하나라도 1이면 그 자리를 1로 만듭니다.',
            'xor': '같은 자리의 두 비트가 서로 다를 때만 그 자리를 1로 만듭니다.',
        }.get(op) or explanation['summary']
        return [{'title': '입력 읽기', 'text': f'{parts[1]}에 든 값과 {with_particle(rhs)} 사용합니다.'},
                {'title': '어떤 계산을 하나요?', 'text': operation},
                {'title': '결과 담기', 'text': '목적지가 x0이므로 결과 쓰기는 버립니다.' if register(parts[0]) == 'x0' else f'결과를 {parts[0]}에 담습니다. 기존에 담겨 있던 값은 새 결과로 바뀝니다.'}]
    if op in ('lui', 'auipc') and len(parts) == 2:
        try:
            number = int(parts[1], 0)
            prepared = (number * 4096) & 0xFFFFFFFF
            calculation = f'명령어의 숫자 {number}에 4096을 곱하고, 레지스터에 들어가는 32비트만 남깁니다. 준비한 값을 0 이상의 정수로 읽으면 {prepared}입니다.'
        except ValueError:
            calculation = '프로그램을 만들 때 이 이름에 대응하는 숫자가 정해집니다. 숫자가 정해지면 4096을 곱해 계산에 사용할 값을 준비합니다.'
        return [{'title': '어떤 숫자를 사용하나요?', 'text': f'명령어에 적힌 숫자 {with_particle(parts[1])} 사용합니다.'},
                {'title': '계산에 쓸 값을 어떻게 준비하나요?', 'text': calculation},
                {'title': '무엇을 저장하나요?', 'text': '목적지가 항상 0인 x0이므로 계산 결과를 보관하지 않습니다.' if register(parts[0]) == 'x0' else f"{'만든 숫자를 현재 명령어의 주소에 더한 결과에서 32비트만 남긴 값' if op == 'auipc' else '만든 숫자'}를 {parts[0]}에 저장합니다."}]
    if op == 'ecall':
        return [{'title': '누구에게 부탁하나요?', 'text': 'CPU가 실행 환경에 처리를 맡깁니다. 계산이나 메모리 복사 명령어가 아닙니다.'},
                {'title': '무엇을 부탁하나요?', 'text': '출력이나 프로그램 종료 같은 서비스입니다. 어떤 서비스를 고를지는 실행 환경의 약속으로 정합니다.'},
                {'title': '항상 프로그램이 끝나나요?', 'text': '아닙니다. 종료 요청을 받은 경우에만 끝납니다. ecall이라는 명령어 이름만으로 출력이나 종료를 단정할 수 없습니다.'}]
    if op in ('jal', 'jalr', 'ret', 'call', 'tail', 'jr', 'j'):
        return [{'title': '이동 위치', 'text': '이 명령어가 지정한 주소로 실행 위치를 옮깁니다.'},
                {'title': '복귀 주소', 'text': '목적지 레지스터가 있으면 다음 명령어의 주소를 기록합니다. 목적지가 x0이면 기록은 버립니다.'},
                {'title': '다음 실행', 'text': '이동한 위치의 명령어를 실행합니다. 함수 호출 여부는 목적지와 주변 코드도 함께 확인합니다.'}]
    return []


def instruction_context(entry, previous_writes):
    explanation = entry['explanation']
    parts = [part.strip() for part in (explanation.get('operands') or '').split(',')]
    category = explanation['category']
    op = explanation.get('opcode')
    roles = []
    principle = ''
    memory = explanation.get('memory')
    control = explanation.get('control_flow') or {}
    if memory and len(parts) == 2:
        load = memory['access'] == 'load'
        roles = [
            {'operand': parts[0], 'role': '메모리에서 읽은 값을 넣을 레지스터입니다.' if load else '메모리에 복사할 값이 들어 있는 레지스터입니다. 읽기만 하므로 이 레지스터의 값은 바뀌지 않습니다.'},
            {'operand': parts[1], 'role': '괄호 안 레지스터의 주소에서 괄호 밖 숫자만큼 이동한 메모리 위치. 음수면 앞쪽, 양수면 뒤쪽으로 이동하며 거리는 바이트 단위입니다.'},
        ]
        principle = ('메모리의 값을 산술 연산에 사용하려면 먼저 레지스터로 읽습니다. '
                     if load else '레지스터에 계산해 둔 값을 메모리에 반영합니다. ')
        principle += f"이번 명령어의 메모리 접근 크기는 {memory['width_bits'] // 8}바이트입니다."
        if load and register(parts[0]) == 'x0':
            roles[0]['role'] = '읽기 결과에 대한 쓰기를 버리는 목적지 x0'
            principle += ' 메모리 읽기는 수행하지만 읽은 값을 x0에 보존하지 않습니다.'
    elif category in ('arithmetic', 'stack') and len(parts) == 3:
        roles = [
            {'operand': parts[0], 'role': '계산을 마친 뒤 결과를 넣을 레지스터입니다.'},
            {'operand': parts[1], 'role': f'계산에 사용할 값을 읽는 곳입니다. 명령어를 실행하기 전 {parts[1]}에 들어 있던 값을 사용합니다.'},
            {'operand': parts[2], 'role': '계산에 함께 사용할 또 다른 값을 읽는 레지스터입니다.' if register(parts[2]) else f'레지스터 이름이 아니라 계산에 바로 사용하는 숫자 {parts[2]}입니다. 이런 숫자를 즉치값이라고 부릅니다.'},
        ]
        if register(parts[0]) in explanation['reads']:
            principle = f"같은 레지스터 이름이 반복되어도 역할은 다릅니다. 입력으로 적힌 {parts[0]}에서는 기존 값을 먼저 읽습니다. 계산을 마치면 맨 앞에 적힌 {parts[0]}에 새 결과를 넣습니다."
        else:
            principle = '입력값으로 연산하고 목적지 레지스터에 결과를 기록합니다.'
        if register(parts[0]) == 'x0':
            principle = '목적지가 x0이므로 계산 결과에 대한 레지스터 쓰기는 버려집니다.'
    elif control.get('conditional') and parts:
        roles = [{'operand': operand, 'role': '조건을 비교하기 위해 값을 읽는 레지스터입니다.'} for operand in parts[:-1]]
        roles.append({'operand': parts[-1], 'role': '조건이 맞을 때 이동할 위치입니다. 숫자는 현재 명령어 주소에서 이동할 바이트 거리이고, 이름은 이동할 위치에 붙인 이름표입니다.'})
        principle = explanation['summary']
        if 's32(' in control['condition']:
            principle += ' 두 값을 음수가 될 수 있는 정수로 읽고 크기를 비교합니다.'
        elif 'u32(' in control['condition']:
            principle += ' 두 값을 0 이상의 정수로 읽고 크기를 비교합니다.'
    elif op in ('lui', 'auipc') and len(parts) == 2:
        roles = [{'operand': parts[0], 'role': '만든 결과를 넣을 레지스터입니다.'},
                 {'operand': parts[1], 'role': '4096을 곱해서 큰 수를 만들 때 사용하는 숫자입니다.'}]
        principle = 'auipc는 현재 명령어가 놓인 주소를 계산에 사용합니다. 맨 앞의 레지스터는 입력값이 아니라 계산 결과를 받는 곳입니다.' if op == 'auipc' else 'lui는 입력 레지스터를 읽지 않고, 명령어에 적힌 숫자로 결과를 만듭니다.'
    elif op in ('jal', 'jalr'):
        if op == 'jal' and len(parts) == 1:
            roles = [{'operand': parts[0], 'role': '이동할 위치입니다. 돌아올 주소는 생략된 ra 레지스터에 저장합니다.'}]
        elif len(parts) >= 2:
            roles = [{'operand': parts[0], 'role': '돌아올 때 사용할 주소를 넣는 곳입니다. zero 또는 x0이면 이 주소를 저장하지 않습니다.'},
                     {'operand': parts[1], 'role': '이동할 위치입니다. 숫자는 현재 주소에서 이동할 거리이고, 이름은 위치에 붙인 이름표입니다.' if op == 'jal' else ('괄호 안 레지스터의 실행 전 주소에 괄호 밖 숫자를 더해 이동할 위치를 구합니다.' if len(parts) == 2 else '이동할 주소를 계산할 때 값을 읽는 레지스터입니다. 결과를 넣기 전의 값을 먼저 읽습니다.')}]
            if len(parts) == 3:
                roles.append({'operand': parts[2], 'role': '두 번째 항목의 주소에 더할 바이트 거리입니다.'})
        principle = '입력값으로 이동할 주소를 먼저 구한 뒤, 돌아올 주소를 결과 레지스터에 넣습니다. 입력과 결과의 레지스터 이름이 같아도 바꾸기 전의 값으로 이동할 주소를 구합니다.'
    elif op in ('mv', 'not', 'neg', 'seqz', 'snez', 'sltz', 'sgtz') and len(parts) == 2:
        roles = [{'operand': parts[0], 'role': '결과를 넣을 레지스터입니다.'},
                 {'operand': parts[1], 'role': '명령어를 실행하기 전의 값을 읽는 레지스터입니다.'}]
    elif op in ('li', 'la', 'lla') and len(parts) == 2:
        roles = [{'operand': parts[0], 'role': '준비한 값을 넣을 레지스터입니다.'},
                 {'operand': parts[1], 'role': '레지스터에 넣을 숫자입니다.' if op == 'li' else '주소를 구할 데이터나 코드에 붙인 이름입니다.'}]
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
