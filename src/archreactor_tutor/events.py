"""Explain actual engine events, preserving the original clock and history index."""
from copy import deepcopy
import re
from .asm import REGISTER_OPS, IMMEDIATE_OPS, MULTIPLY_OPS, LOADS, STORES, with_particle

ALU_INSTRUCTIONS = set(REGISTER_OPS) | set(IMMEDIATE_OPS) | MULTIPLY_OPS | set(LOADS) | set(STORES) | {'lui', 'auipc'}


def obj(value):
    return value if isinstance(value, dict) else {}


def pc(value):
    try:
        number = int(value, 16) if isinstance(value, str) else None
        return f"0x{number:08X}" if number is not None and 0 <= number <= 0xFFFFFFFF else None
    except ValueError:
        return None


def activity(cycle):
    source = cycle.get('stage_activity')
    if not isinstance(source, dict):
        source = cycle.get('buffers')
    source = obj(source)
    return {stage: obj(source.get(stage) or cycle.get(stage.lower() + '_stage')) for stage in ('IF', 'ID', 'EX', 'MEM', 'WB')}


def diff(before, after):
    return [{'key': key, 'before': before.get(key), 'after': value}
            for key, value in after.items() if before.get(key) != value]


def value_text(value):
    if isinstance(value, str) and value.lower().startswith('0x'):
        try:
            number = int(value, 16)
        except ValueError:
            return value
        if 0 <= number < 0x80000000:
            return f'{number} ({value})'
    return str(value)


def memory_operands(assembly):
    """Names only; actual values always come from the stage, never registers."""
    match = re.fullmatch(r'\s*(?:lb|lbu|lh|lhu|lw|sb|sh|sw)\s+(\w+)\s*,\s*-?(?:0[xX][\da-fA-F]+|\d+)\s*\(\s*(\w+)\s*\)\s*', assembly)
    return match.groups() if match else (None, None)


def offset_text(value):
    try:
        number = int(value, 0) if isinstance(value, str) else int(value)
        if 0x80000000 <= number <= 0xFFFFFFFF:
            number -= 1 << 32
        return ('앞쪽으로' if number < 0 else '뒤쪽으로') + f' {abs(number)}바이트'
    except (ValueError, TypeError):
        return f'거리 {value_text(value)}바이트만큼'


def instruction_observations(cycle, retired_pc, locations):
    stages = activity(cycle)
    observations = []
    for name in ('EX', 'MEM', 'WB'):
        stage = stages[name]
        opcode = str(stage.get('assembly', '')).split(' ', 1)[0].lower()
        address = pc(stage.get('pc'))
        error = obj(obj(cycle.get('cycle_events')).get('runtime_error'))
        if (not address or stage.get('status') in ('empty', 'bubble', 'flush', 'flushed', 'error', 'stall', 'stalled')
                or (error.get('has_error') is True and error.get('stage') == name)
                or obj(stage.get('flush_info')).get('is_flushed')):
            continue
        control = obj(obj(cycle.get('cycle_events')).get('control_hazard'))
        if (name == 'EX' and control.get('has_control_instruction') is True
                and control.get('stage') == 'EX' and control.get('assembly') == stage.get('assembly')):
            taken = control.get('taken')
            if taken is True:
                destination = control.get('target_pc')
                summary = f"다음에 실행할 명령어의 위치를 {destination or '미제공'} 주소로 바꿨습니다."
            elif taken is False:
                destination = control.get('fallthrough_pc')
                summary = f"조건이 맞지 않아 분기하지 않음: 바로 다음 명령어가 있는 {destination or '미제공'} 주소로 진행합니다."
            else:
                destination = None
                summary = '제어 명령어가 처리됐으며 분기 판정값은 제공되지 않았습니다.'
            target_line = obj(locations.get(pc(destination))).get('source_line')
            if target_line is not None:
                summary += f' 이동 위치는 C {target_line}줄에 연결됩니다.'
            conditional = str(stage.get('assembly', '')).split(' ', 1)[0] in ('beq', 'bne', 'blt', 'bge', 'bltu', 'bgeu')
            if conditional and stage.get('operand_1') is not None and stage.get('operand_2') is not None:
                summary = f"실제 비교 입력은 {value_text(stage['operand_1'])}, {value_text(stage['operand_2'])}입니다. " + summary
            observations.append({'pc': address, 'stage': name, 'summary': summary, 'kind': 'control'})
            continue
        if name == 'EX' and opcode in ALU_INSTRUCTIONS and all(stage.get(key) is not None for key in ('operand_1', 'operand_2', 'alu_result')):
            operands = f"{value_text(stage['operand_1'])}, {value_text(stage['operand_2'])}"
            operation = str(stage.get('alu_operation') or opcode).lower()
            operation = IMMEDIATE_OPS.get(operation, operation)
            symbol = {'add': '+', 'sub': '-', 'and': '&', 'or': '|', 'xor': '^'}.get(operation)
            try:
                shift_amount = int(str(stage['operand_2']), 0) & 31
            except ValueError:
                shift_amount = None
            if opcode in ('sll', 'slli', 'srl', 'srli', 'sra', 'srai') and shift_amount is not None:
                direction = '왼쪽' if opcode in ('sll', 'slli') else '오른쪽'
                summary = f"실제 입력 {value_text(stage['operand_1'])}을 {direction}으로 {shift_amount}비트 이동한 결과는 {value_text(stage['alu_result'])}입니다."
                summary += ' 부호 비트로 빈자리를 채웁니다.' if opcode in ('sra', 'srai') else ' 빈자리는 0으로 채웁니다.'
            elif symbol:
                first, second, result = (value_text(stage[key]) for key in ('operand_1', 'operand_2', 'alu_result'))
                if operation in ('add', 'sub'):
                    verb = '더했습니다' if operation == 'add' else '뺐습니다'
                    summary = f"계산 장치(ALU)가 첫 번째 값 {first}{'에' if operation == 'add' else '에서'} 두 번째 값 {with_particle(second)} {verb}. 계산 결과는 {result}입니다."
                else:
                    rule = {'and': '둘 다 1인 자리', 'or': '하나라도 1인 자리', 'xor': '두 비트가 다른 자리'}[operation]
                    summary = f"계산 장치(ALU)가 입력값 {first}, {second}을 비트별로 비교해 {rule}를 1로 만들었습니다. 결과는 {result}입니다."
            else:
                meaning = REGISTER_OPS.get(operation, ('', ''))[1] or {'mul': '곱셈', 'mulh': '곱셈 결과의 왼쪽 부분 구하기', 'mulhsu': '곱셈 결과의 왼쪽 부분 구하기', 'mulhu': '곱셈 결과의 왼쪽 부분 구하기', 'div': '나눗셈의 몫 구하기', 'divu': '나눗셈의 몫 구하기', 'rem': '나눗셈의 나머지 구하기', 'remu': '나눗셈의 나머지 구하기', 'lui': '큰 숫자 만들기', 'auipc': '현재 명령어 주소에 숫자 더하기'}.get(opcode, '명령어에 맞는 계산')
                summary = f"계산 장치(ALU)가 {with_particle(meaning)} 수행합니다. 이번 입력값은 {operands}이고, 결과는 {value_text(stage['alu_result'])}입니다."
        elif name == 'MEM' and stage.get('memory_operation') in ('load', 'store') and stage.get('target_address') is not None:
            load = stage['memory_operation'] == 'load'
            value = stage.get('read_data' if load else 'write_data')
            if value is None:
                continue
            data_register, _ = memory_operands(str(stage.get('assembly', '')))
            width = (LOADS.get(opcode) or (STORES.get(opcode),))[0]
            size = f'{width // 8}바이트' if width else '데이터'
            if load:
                summary = f"메모리의 {stage['target_address']}번 위치에서 {size}를 읽었습니다. 읽은 값은 {value_text(value)}입니다."
                if data_register:
                    summary += f' 이 값을 {data_register} 레지스터에 전달합니다.'
            else:
                opcode = str(stage.get('assembly', '')).split(' ', 1)[0]
                width = {'sb': 8, 'sh': 16, 'sw': 32}.get(opcode)
                if width:
                    try:
                        number = int(value, 0) if isinstance(value, str) else int(value)
                        value = f'0x{number & ((1 << width) - 1):0{width // 4}X}'
                    except (ValueError, TypeError):
                        pass
                source = f'{data_register} 레지스터에서 가져온 ' if data_register else ''
                summary = f"메모리의 {stage['target_address']}번 위치에 {source}값 {with_particle(value_text(value))} {size} 크기로 저장했습니다. 저장 위치의 내용이 바뀌며, 데이터를 준 레지스터의 값은 그대로입니다."
        elif name == 'WB' and retired_pc == address and stage.get('will_write_reg') is True and stage.get('final_write_data') is not None:
            if stage.get('destination_register') in ('x0', 'zero'):
                summary = '계산 결과를 x0에 쓰려는 동작은 버립니다. x0 레지스터의 값은 항상 0입니다.'
            else:
                summary = f"{stage.get('destination_register') or '결과를 받는'} 레지스터의 값을 {with_particle(value_text(stage['final_write_data']), '으로', '로')} 바꿨습니다. 이후 명령어는 이 새 값을 읽을 수 있습니다."
        else:
            continue
        opcode = str(stage.get('assembly', '')).split(' ', 1)[0]
        address_calculation = name == 'EX' and opcode in ('lb', 'lbu', 'lh', 'lhu', 'lw', 'sb', 'sh', 'sw')
        if address_calculation:
            _, base = memory_operands(str(stage.get('assembly', '')))
            summary = f"{base or '기준'} 레지스터에 담긴 주소 {value_text(stage['operand_1'])}에서 {offset_text(stage['operand_2'])} 이동한 위치를 계산했습니다. 찾은 메모리 주소는 {value_text(stage['alu_result'])}입니다. 아직 데이터를 읽거나 쓴 단계는 아닙니다."
        observations.append({'pc': address, 'stage': name, 'summary': summary,
                             'kind': 'address' if address_calculation else 'value'})
    return observations


def execution_steps(result):
    output = []
    locations = {pc(key): obj(value) for key, value in obj(obj(result.get('program')).get('code_mapping')).items() if pc(key)}
    previous = obj(result.get('initial_state'))
    previous_retired = obj(previous.get('metrics')).get('accumulated_instructions')
    for index, raw in enumerate(result.get('history') or []):
        cycle = obj(raw)
        events, state = obj(cycle.get('cycle_events')), obj(cycle.get('global_result'))
        stages = activity(cycle)
        explanations = []
        for name, flag, kind, title in [
            ('stall', 'has_stall', 'stall', '명령어 진행 대기'),
            ('forwarding', 'has_forwarded', 'forwarding', '피연산자 포워딩'),
            ('control_hazard', 'has_control_instruction', 'branch', '제어 흐름 판단'),
            ('runtime_error', 'has_error', 'runtime_error', '실행 오류'),
        ]:
            evidence = obj(events.get(name))
            if evidence.get(flag) is not True:
                continue
            if kind == 'stall':
                reason = evidence.get('stall_reason')
                summary = ('앞선 명령어가 메모리에서 가져올 값을 현재 명령어가 필요로 하지만, 아직 읽기가 끝나지 않았습니다.' if reason == 'load_use'
                           else '앞선 명령어가 새 값을 레지스터에 넣을 때까지 현재 명령어가 기다립니다.' if reason == 'strict_dependency'
                           else '현재 명령어에 필요한 값이나 실행 자원이 준비되지 않아 진행을 잠시 멈춥니다.')
                detail = summary + ' 앞선 작업은 필요한 값이나 자원을 준비합니다. 대기 조건이 풀리면 멈춰 있던 명령어가 이어서 진행합니다.'
            elif kind == 'forwarding':
                summary = '현재 명령어가 레지스터의 오래된 값 대신 앞선 명령어가 만든 새 값을 직접 받아 사용합니다.'
                info = obj(evidence.get('forwarding_info'))
                paths = [str(x) for x in info.get('forwarded_from', [])]
                targets = [str(x) for x in info.get('target_register', [])]
                places = {'EX/MEM': '계산을 마친 결과를 보관하는 EX/MEM', 'MEM/WB': '레지스터에 넣을 결과를 보관하는 MEM/WB'}
                detail = summary + (' 값을 가져온 곳: ' + ', '.join(places.get(path, path) for path in paths) + '.' if paths else '')
                detail += (' 새 값이 필요한 레지스터: ' + ', '.join(targets) + '.' if targets else '')
                detail += ' 준비된 새 값을 바로 사용하므로, 앞선 명령어가 레지스터에 결과를 저장할 때까지 기다리지 않습니다.'
                if str(evidence.get('assembly', '')).split(' ', 1)[0] in ('sb', 'sh', 'sw'):
                    detail += ' 이 저장 명령어에서는 주소 계산에 필요한 값이나 메모리에 저장할 데이터를 전달받습니다.'
            elif kind == 'branch':
                taken = evidence.get('taken')
                summary = '실제로 분기/점프했습니다.' if taken is True else ('분기하지 않고 순차 실행했습니다.' if taken is False else '제어 명령어가 처리됐지만 taken 값은 제공되지 않았습니다.')
                detail = f"{summary} 목적지: {evidence.get('target_pc') or '미제공'}, 순차 PC: {evidence.get('fallthrough_pc') or '미제공'}. C 조건의 참/거짓과 어셈블리 taken은 분기 방향에 따라 반대일 수 있습니다."
            else:
                summary = evidence.get('message') or evidence.get('reason') or '시뮬레이션 도중 실행 오류가 발생했습니다.'
                detail = f"{summary} 오류 코드: {evidence.get('code') or '미제공'}, 단계: {evidence.get('stage') or '미제공'}. 실패한 명령어를 완료된 명령어로 세지 않습니다."
            explanations.append({'type': kind, 'title': title, 'summary': str(summary), 'detail': detail, 'evidence': deepcopy(evidence)})
        control = obj(events.get('control_hazard'))
        if control.get('has_flush') is True:
            summary = '다음에 실행할 위치가 바뀌어, 이전 경로에서 미리 가져온 명령어를 취소합니다.'
            detail = summary
            flushed = control.get('flushed_stages', [])
            if flushed:
                detail += f" 취소한 명령어가 있던 단계: {', '.join(str(x) for x in flushed)}."
            if control.get('redirect_pc'):
                detail += f" 이제 {control['redirect_pc']} 주소에서 명령어를 가져옵니다."
            detail += ' 취소한 명령어는 레지스터나 메모리를 바꾸지 못하게 하고, 실행표에서는 버블로 이어서 표시합니다.'
            explanations.append({'type': 'flush', 'title': '제어 흐름 변경 / 플러시', 'summary': summary, 'detail': detail, 'evidence': deepcopy(control)})

        count = obj(state.get('metrics')).get('accumulated_instructions')
        delta = count - previous_retired if type(count) is int and type(previous_retired) is int else None
        wb = stages['WB']
        error = obj(events.get('runtime_error'))
        inactive = ('error', 'empty', 'bubble', 'flush', 'flushed', 'stall', 'stalled')
        retired_pc = pc(wb.get('pc')) if delta == 1 and not obj(wb.get('flush_info')).get('is_flushed') and wb.get('status') not in inactive and not (error.get('has_error') is True and error.get('stage') == 'WB') else None
        memory = stages['MEM']
        transfer = None
        if memory.get('memory_operation') in ('load', 'store') and memory.get('target_address') is not None and memory.get('status') not in inactive and not obj(memory.get('flush_info')).get('is_flushed') and not (error.get('has_error') is True and error.get('stage') == 'MEM'):
            transfer = {key: deepcopy(memory.get(key)) for key in ('memory_operation', 'target_address', 'read_data', 'write_data', 'pc', 'assembly')}
            if transfer['memory_operation'] == 'store':
                width = STORES.get(str(memory.get('assembly', '')).split(' ', 1)[0])
                try:
                    value = transfer['write_data']
                    number = int(value, 0) if isinstance(value, str) else int(value)
                    if width and number != (number & ((1 << width) - 1)):
                        transfer['write_data'] = str(number & ((1 << width) - 1))
                except (ValueError, TypeError):
                    pass
        output.append({
            'history_index': index, 'cycle': cycle.get('clock'), 'display_clock': index + 1,
            'events': explanations, 'retired_pc': retired_pc, 'retired_delta': delta,
            'stages': [{'stage': stage, 'pc': pc(value.get('pc')), 'assembly': value.get('assembly'), 'status': value.get('status'), 'source_line': locations[pc(value.get('pc'))].get('source_line') if pc(value.get('pc')) in locations else value.get('source_line')} for stage, value in stages.items() if value.get('assembly')],
            'register_changes': diff(obj(previous.get('registers')), obj(state.get('registers'))) if previous else [],
            'memory_changes': diff(obj(previous.get('memory_snapshot')), obj(state.get('memory_snapshot'))) if previous else [],
            'memory_transfer': transfer,
            'register_write': {'register': wb.get('destination_register'), 'value': wb.get('final_write_data')} if delta == 1 and wb.get('will_write_reg') is True and retired_pc else None,
            'current_pc': state.get('current_pc'),
        })
        output[-1]['instruction_observations'] = instruction_observations(cycle, retired_pc, locations)
        previous, previous_retired = state, count
    if output and result.get('status') == 'error' and not any(event['type'] == 'runtime_error' for event in output[-1]['events']):
        message = result.get('console_output') or '실행이 오류 상태로 종료됐습니다. 구체적인 오류 근거는 제공되지 않았습니다.'
        limit = 'clock limit' in str(message).lower()
        output[-1]['events'].append({'type': 'cycle_limit' if limit else 'execution_error', 'title': '사이클 제한' if limit else '실행 오류', 'summary': str(message), 'detail': str(message), 'evidence': {'status': result.get('status'), 'console_output': result.get('console_output')}})
    return output
