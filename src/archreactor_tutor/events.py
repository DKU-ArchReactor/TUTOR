"""Explain actual engine events, preserving the original clock and history index."""
from copy import deepcopy
from .asm import REGISTER_OPS, IMMEDIATE_OPS, MULTIPLY_OPS, LOADS, STORES

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


def instruction_observations(cycle, retired_pc, locations):
    stages = activity(cycle)
    observations = []
    for name in ('EX', 'MEM', 'WB'):
        stage = stages[name]
        opcode = str(stage.get('assembly', '')).split(' ', 1)[0].lower()
        address = pc(stage.get('pc'))
        if (not address or stage.get('status') in ('empty', 'bubble', 'flushed', 'error', 'stall', 'stalled')
                or obj(stage.get('flush_info')).get('is_flushed')):
            continue
        control = obj(obj(cycle.get('cycle_events')).get('control_hazard'))
        if (name == 'EX' and control.get('has_control_instruction') is True
                and control.get('stage') == 'EX' and control.get('assembly') == stage.get('assembly')):
            taken = control.get('taken')
            if taken is True:
                destination = control.get('target_pc')
                summary = f"실제 판정은 분기·점프함이며 목적지는 {destination or '미제공'}입니다."
            elif taken is False:
                destination = control.get('fallthrough_pc')
                summary = f"실제 판정은 분기하지 않음이며 다음 위치는 {destination or '미제공'}입니다."
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
            operation = stage.get('alu_operation')
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
                summary = f"실제 계산은 {value_text(stage['operand_1'])} {symbol} {value_text(stage['operand_2'])} = {value_text(stage['alu_result'])}입니다."
            else:
                summary = f"ALU {operation or '연산'}의 실제 입력은 {operands}이며 결과는 {value_text(stage['alu_result'])}입니다."
        elif name == 'MEM' and stage.get('memory_operation') in ('load', 'store') and stage.get('target_address') is not None:
            load = stage['memory_operation'] == 'load'
            value = stage.get('read_data' if load else 'write_data')
            if value is None:
                continue
            if load:
                summary = f"주소 {stage['target_address']}의 읽기 결과는 {value_text(value)}입니다."
            else:
                opcode = str(stage.get('assembly', '')).split(' ', 1)[0]
                width = {'sb': 8, 'sh': 16, 'sw': 32}.get(opcode)
                if width and isinstance(value, str) and value.lower().startswith('0x'):
                    try:
                        value = f'0x{int(value, 16) & ((1 << width) - 1):0{width // 4}X}'
                    except ValueError:
                        pass
                summary = f"주소 {stage['target_address']}에 {value_text(value)}을 저장했습니다."
        elif name == 'WB' and retired_pc == address and stage.get('will_write_reg') is True and stage.get('final_write_data') is not None:
            summary = f"{stage.get('destination_register') or '목적지 레지스터'}에 {value_text(stage['final_write_data'])}을 기록했습니다."
        else:
            continue
        opcode = str(stage.get('assembly', '')).split(' ', 1)[0]
        address_calculation = name == 'EX' and opcode in ('lb', 'lbu', 'lh', 'lhu', 'lw', 'sb', 'sh', 'sw')
        if address_calculation:
            summary = f"기준 주소 {stage['operand_1']}에 오프셋 {stage['operand_2']}을 더해 접근 주소 {stage['alu_result']}을 계산했습니다."
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
                summary = evidence.get('stall_desc') or 'CORE가 현재 클록에서 스톨을 보고했습니다.'
                detail = str(summary) + ' 소비 명령어의 진행이 지연됩니다. 이 이벤트 하나만으로 전체 스톨 횟수나 모든 해저드 종류를 확정하지 않습니다.'
            elif kind == 'forwarding':
                summary = evidence.get('forwarding_desc') or '레지스터 기록을 기다리지 않고 준비된 값을 피연산자 경로로 전달합니다.'
                info = obj(evidence.get('forwarding_info'))
                paths = [str(x) for x in info.get('forwarded_from', [])]
                targets = [str(x) for x in info.get('target_register', [])]
                detail = str(summary) + f" 전달 출발: {', '.join(paths) or '미제공'}. 대상 레지스터: {', '.join(targets) or '미제공'}. 피연산자 전달 수: {evidence.get('forwarded_operand_count', '미제공')}."
            elif kind == 'branch':
                taken = evidence.get('taken')
                summary = '실제로 분기/점프했습니다.' if taken is True else ('분기하지 않고 순차 실행했습니다.' if taken is False else '제어 명령어가 처리됐지만 taken 값은 제공되지 않았습니다.')
                detail = f"{summary} 목적지: {evidence.get('target_pc') or '미제공'}, 순차 PC: {evidence.get('fallthrough_pc') or '미제공'}. C 조건의 참/거짓과 어셈블리 taken은 분기 방향에 따라 반대일 수 있습니다."
            else:
                summary = evidence.get('message') or evidence.get('reason') or 'CORE가 실행 오류를 보고했습니다.'
                detail = f"{summary} 오류 코드: {evidence.get('code') or '미제공'}, 단계: {evidence.get('stage') or '미제공'}. 실패한 명령어를 완료된 명령어로 세지 않습니다."
            explanations.append({'type': kind, 'title': title, 'summary': str(summary), 'detail': detail, 'evidence': deepcopy(evidence)})
        control = obj(events.get('control_hazard'))
        if control.get('has_flush') is True:
            summary = '제어 흐름 변경으로 후속 명령어를 비웁니다.'
            detail = f"비운 단계: {', '.join(str(x) for x in control.get('flushed_stages', [])) or '미제공'}. 이동 PC: {control.get('redirect_pc') or '미제공'}. 원인: {control.get('flush_reason') or '미제공'}. 분기 예측 실패로 단정하지 않습니다."
            explanations.append({'type': 'flush', 'title': '제어 흐름 변경 / 플러시', 'summary': summary, 'detail': detail, 'evidence': deepcopy(control)})

        count = obj(state.get('metrics')).get('accumulated_instructions')
        delta = count - previous_retired if type(count) is int and type(previous_retired) is int else None
        wb = stages['WB']
        retired_pc = pc(wb.get('pc')) if delta == 1 and not obj(wb.get('flush_info')).get('is_flushed') and wb.get('status') not in ('error', 'empty', 'bubble', 'flushed') else None
        memory = stages['MEM']
        transfer = None
        if memory.get('memory_operation') in ('load', 'store') and memory.get('target_address') and memory.get('status') != 'error' and not obj(memory.get('flush_info')).get('is_flushed'):
            transfer = {key: deepcopy(memory.get(key)) for key in ('memory_operation', 'target_address', 'read_data', 'write_data', 'pc', 'assembly')}
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
