"""Prefix-safe performance facts and instruction attribution from CORE evidence."""
from .asm import explain_asm, register
from .events import activity, obj, pc


def counter(value):
    return value if type(value) is int and value >= 0 else None


def valid(stage):
    return bool(stage.get('assembly')) and stage.get('status') not in ('empty', 'bubble', 'flush', 'flushed', 'error') and not obj(stage.get('flush_info')).get('is_flushed')


def instruction(stage, locations):
    address = pc(stage.get('pc'))
    mapped = locations.get(address, {})
    return {'pc': address, 'assembly': stage.get('assembly'), 'source_line': mapped.get('source_line')}


def semantics(stage, locations):
    mapped = locations.get(pc(stage.get('pc')), {})
    return mapped.get('explanation') or explain_asm(str(stage.get('assembly', ''))).model_dump()


def dependencies(consumer, stages, locations):
    """The nearest older writer wins when several stages write the same register."""
    reads = set(semantics(consumer, locations).get('reads', [])) - {'x0'}
    found = []
    for name in ('EX', 'MEM', 'WB'):
        producer = stages[name]
        if not valid(producer):
            continue
        writes = set(semantics(producer, locations).get('writes', []))
        target = register(str(producer.get('destination_register', '')))
        if target and producer.get('will_write_reg') is True:
            writes.add(target)
        for value in sorted(reads & writes):
            found.append({'register': value, 'stage': name, **instruction(producer, locations)})
            reads.remove(value)
    return found


def performance_analysis(result, steps, instructions):
    locations = {pc(item['pc']): item for item in instructions}
    snapshots, records = [], []
    stalls = flushes = forwards = overlap = idle = hazard_idle = unknown = 0
    previous = counter(obj(obj(result.get('initial_state')).get('metrics')).get('accumulated_instructions'))
    consistent = previous == 0
    for raw, step in zip(result.get('history') or [], steps, strict=True):
        cycle = obj(raw)
        stages = activity(cycle)
        events = obj(cycle.get('cycle_events'))
        stalled = obj(events.get('stall')).get('has_stall') is True
        flushed = obj(events.get('control_hazard')).get('has_flush') is True
        forwarded = obj(events.get('forwarding')).get('has_forwarded') is True
        stalls += stalled
        flushes += flushed
        forwards += forwarded
        overlap += stalled and flushed
        completed = counter(obj(obj(cycle.get('global_result')).get('metrics')).get('accumulated_instructions'))
        delta = completed - previous if completed is not None and previous is not None else None
        known = delta in (0, 1)
        consistent = consistent and known
        if delta == 0:
            idle += 1
            hazard_idle += stalled or flushed
        if not known:
            unknown += 1
        previous = completed
        cycles = step['history_index'] + 1
        cpi = cycles / completed if completed else None
        snapshots.append({'history_index': step['history_index'], 'cycles': cycles, 'completed': completed, 'cpi': cpi,
                          'stall_cycles': stalls, 'flush_cycles': flushes, 'forwarding_cycles': forwards,
                          'overlap_cycles': overlap, 'hazard_cycles': stalls + flushes - overlap,
                          'idle_cycles': idle, 'hazard_idle_cycles': hazard_idle,
                          'other_idle_cycles': idle - hazard_idle, 'unknown_completion_cycles': unknown,
                          'extra_cycles': cycles - completed if consistent and completed is not None else None})
        for event in step['events']:
            kind = event['type']
            if kind not in ('stall', 'forwarding', 'flush'):
                continue
            evidence = event['evidence']
            name = evidence.get('stage')
            stage = stages.get(name, {})
            # A stage label without a matching instruction must not attach to a PC.
            matched = valid(stage) and bool(evidence.get('assembly')) and stage.get('assembly') == evidence.get('assembly')
            actor = instruction(stage, locations) if matched else {'pc': None, 'assembly': evidence.get('assembly'), 'source_line': None}
            reason = evidence.get('stall_reason') if kind == 'stall' else evidence.get('flush_reason') if kind == 'flush' else None
            related = dependencies(stage, stages, locations) if kind == 'stall' and matched and name == 'ID' and reason in ('load_use', 'data_hazard', 'raw_dependency') else []
            if kind == 'stall':
                blocking = [item for item in related if item['stage'] == 'EX' and
                            semantics(stages['EX'], locations).get('category') == 'load']
                if reason == 'load_use' and blocking:
                    names = ', '.join(item['register'] for item in blocking)
                    event['summary'] = f"바로 앞의 메모리 읽기 명령어가 아직 {names}에 넣을 값을 준비하지 못해, 이 값을 사용하는 명령어가 한 클록 기다립니다."
                event['title'] = 'Load-Use 데이터 의존성' if reason == 'load_use' else '명령어 진행 대기'
                event['detail'] = event['summary']
                if actor['pc']:
                    event['detail'] += f" 대기 명령어: PC {actor['pc']} · {actor['assembly']}."
                for dependency in related:
                    event['detail'] += (f" {dependency['stage']}의 PC {dependency['pc'] or '미제공'} · {dependency['assembly']}가 기록할 "
                                        f"{dependency['register']}를 대기 명령어가 읽습니다.")
            elif kind == 'flush' and actor['pc']:
                event['detail'] += f" 제어 명령어: PC {actor['pc']} · {actor['assembly']}."
            elif kind == 'forwarding' and actor['pc']:
                assembly = actor['assembly'].replace(',', ' ').split()
                if assembly and assembly[0] in ('sb', 'sh', 'sw') and len(assembly) == 3:
                    stored = register(assembly[1])
                    targets = obj(evidence.get('forwarding_info')).get('target_register', [])
                    if stored in {register(str(value)) for value in targets}:
                        event['detail'] += f" 전달받은 {assembly[1]}의 새 값을 메모리에 저장할 데이터로 사용합니다. 저장할 주소는 괄호 안 레지스터의 값에 바이트 거리를 더해 구합니다."
                event['detail'] += f" 값을 전달받은 명령어: PC {actor['pc']} · {actor['assembly']}."
            event['instruction'] = actor
            event['dependencies'] = related
            records.append({'history_index': step['history_index'], 'cycle': step['cycle'], 'kind': kind,
                            'reason': reason, 'instruction': actor, 'dependencies': related,
                            'title': event['title'], 'detail': event['detail']})
    return {'schema_version': '1.0', 'snapshots': snapshots, 'records': records,
            'notes': ['스톨·플러시는 이벤트가 관찰된 클록 수입니다. 같은 클록의 중복은 별도로 표시합니다.',
                      '포워딩 관찰 클록과 전달된 피연산자 횟수는 다를 수 있습니다. 한 클록에서 여러 입력을 전달할 수 있습니다.',
                      '완료가 없는 클록에는 초기 채우기·종료 비우기·해저드 등의 영향이 함께 나타날 수 있습니다.',
                      '포워딩이 절약한 클록 수와 개별 플러시의 순수 손실은 비교 실행 없이 확정하지 않습니다.']}
