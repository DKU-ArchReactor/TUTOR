"""Explain actual engine events, preserving the original clock and history index."""
from copy import deepcopy


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
            ('stall', 'has_stall', 'stall', '데이터 의존성 / 스톨'),
            ('forwarding', 'has_forwarded', 'forwarding', '피연산자 포워딩'),
            ('control_hazard', 'has_control_instruction', 'branch', '제어 흐름 판단'),
            ('runtime_error', 'has_error', 'runtime_error', '실행 오류'),
        ]:
            evidence = obj(events.get(name))
            if evidence.get(flag) is not True:
                continue
            if kind == 'stall':
                summary = evidence.get('stall_desc') or 'CORE가 데이터 의존성에 따른 스톨을 보고했습니다.'
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
        previous, previous_retired = state, count
    if output and result.get('status') == 'error' and not any(event['type'] == 'runtime_error' for event in output[-1]['events']):
        message = result.get('console_output') or '실행이 오류 상태로 종료됐습니다. 구체적인 오류 근거는 제공되지 않았습니다.'
        limit = 'clock limit' in str(message).lower()
        output[-1]['events'].append({'type': 'cycle_limit' if limit else 'execution_error', 'title': '사이클 제한' if limit else '실행 오류', 'summary': str(message), 'detail': str(message), 'evidence': {'status': result.get('status'), 'console_output': result.get('console_output')}})
    return output
