"""RV32IM semantics and common assembler aliases; never execute submitted code."""
import re
from .models import RuleExplanation

ABI = ["zero", "ra", "sp", "gp", "tp", "t0", "t1", "t2", "s0", "s1", *[f"a{i}" for i in range(8)], *[f"s{i}" for i in range(2, 12)], "t3", "t4", "t5", "t6"]
REGISTERS = {name: f"x{i}" for i, name in enumerate(ABI)} | {f"x{i}": f"x{i}" for i in range(32)} | {"fp": "x8"}
BRANCHES = {"beq": ("==", False), "bne": ("!=", False), "blt": ("<", True), "bge": (">=", True), "bltu": ("<", False), "bgeu": (">=", False)}
REGISTER_OPS = {
    "add": ("+", "덧셈"), "sub": ("-", "뺄셈"), "and": ("&", "비트 AND"), "or": ("|", "비트 OR"), "xor": ("^", "비트 XOR"),
    "sll": ("<<", "논리 왼쪽 시프트"), "srl": (">>u", "논리 오른쪽 시프트"), "sra": (">>s", "산술 오른쪽 시프트"),
    "slt": ("<s", "부호 있는 비교"), "sltu": ("<u", "부호 없는 비교"),
}
IMMEDIATE_OPS = {"addi": "add", "andi": "and", "ori": "or", "xori": "xor", "slli": "sll", "srli": "srl", "srai": "sra", "slti": "slt", "sltiu": "sltu"}
MULTIPLY_OPS = {"mul", "mulh", "mulhsu", "mulhu", "div", "divu", "rem", "remu"}
LOADS = {"lb": (8, "sign"), "lbu": (8, "zero"), "lh": (16, "sign"), "lhu": (16, "zero"), "lw": (32, "none")}
STORES = {"sb": 8, "sh": 16, "sw": 32}
ALIASES = {"li", "la", "lla", "mv", "not", "neg", "nop", "j", "jr", "ret", "call", "tail", "beqz", "bnez", "bltz", "bgez", "blez", "bgtz", "bgt", "ble", "bgtu", "bleu", "seqz", "snez", "sltz", "sgtz"}


def register(token: str) -> str | None:
    return REGISTERS.get(token.strip().lower())


def with_particle(text, closed='을', opened='를'):
    """Attach a Korean particle to readable values, including hex annotations."""
    ending = re.sub(r'\s*\(0[xX][\da-fA-F]+\)$', '', str(text)).rstrip()[-1:]
    final = (ord(ending) - 0xAC00) % 28 if ending and '가' <= ending <= '힣' else None
    has_final = final != 0 if final is not None else ending in '013678'
    rieul = final == 8 if final is not None else ending in '178'
    return str(text) + (closed if has_final and not (closed == '으로' and rieul) else opened)


def pc_target(target: str) -> str:
    """Numeric displacements are PC-relative; labels name the resolved target."""
    try:
        int(target, 0)
    except ValueError:
        return target
    return f"PC + {target}"


def explain_encoded_asm(text: str, raw_instruction) -> RuleExplanation:
    """Recover U fields and shift amounts from verified instruction encodings."""
    try:
        word = int(raw_instruction, 16) if isinstance(raw_instruction, str) else None
    except ValueError:
        word = None
    tokens = text.split(None, 1)
    op = tokens[0].lower() if tokens else ''
    shift_fields = {'slli': (1, 0), 'srli': (5, 0), 'srai': (5, 0x20)}
    if op in shift_fields and word is not None and 0 <= word <= 0xFFFFFFFF:
        funct3, funct7 = shift_fields[op]
        if word & 0x7F == 0x13 and (word >> 12) & 7 == funct3 and word >> 25 == funct7:
            rd, rs1, amount = (word >> 7) & 31, (word >> 15) & 31, (word >> 20) & 31
            result = explain_asm(f'{op} x{rd}, x{rs1}, {amount}')
            displayed = explain_asm(text)
            # Preserve ABI register names when the displayed operands are already correct.
            if displayed.supported and displayed.reads == result.reads and displayed.writes == result.writes:
                try:
                    if int((displayed.operands or '').split(',')[-1], 0) == amount:
                        return displayed
                except ValueError:
                    pass
            note = f'실제로 비트를 옮기는 크기는 {amount}칸입니다. 화면에 다른 숫자가 적혀 있어도, 실행되는 명령어 안에 들어 있는 이동 크기를 확인해서 설명합니다.'
            result.notes.append(note)
            result.detail += ' ' + note
            result.summary += f' 실제 이동 크기는 {amount}비트입니다.'
            return result
    expected = {'lui': 0x37, 'auipc': 0x17}.get(op)
    if expected is not None and word is not None and 0 <= word <= 0xFFFFFFFF and word & 0x7F == expected:
        rd, immediate = (word >> 7) & 31, word >> 12
        displayed = explain_asm(text)
        destination = (displayed.operands or '').split(',')[0].strip()
        if register(destination) != f'x{rd}':
            destination = f'x{rd}'
        result = explain_asm(f'{op} {destination}, {immediate}')
        # Keep the existing structured operation stable; reading text uses aliases.
        result.operation = explain_asm(f'{op} x{rd}, {immediate}').operation
        try:
            displayed_number = int((displayed.operands or '').split(',')[-1], 0)
        except ValueError:
            displayed_number = None
        if displayed_number != immediate:
            note = f'이 계산에 사용하는 숫자는 {immediate}입니다. 화면에 적힌 숫자 대신 실제로 실행되는 명령어의 숫자를 확인해서 설명합니다.'
            result.notes.append(note)
            result.detail += ' ' + note
        return result
    return explain_asm(text)


def explain_asm(raw: str) -> RuleExplanation:
    text = raw.split("#", 1)[0].strip()
    tokens = text.split(None, 1)
    op = tokens[0].lower() if tokens else ""
    operands = re.sub(r",\s*", ", ", tokens[1]) if len(tokens) > 1 else ""
    parts = [part.strip() for part in operands.split(",")] if operands else []
    result = RuleExplanation(kind="asm", category="instruction", title=f"RISC-V 명령어 ({op})", summary=text, detail="", opcode=op, operands=operands)
    discarded_write = False

    def finish(category, title, summary, operation=None, notes=()):
        if discarded_write:
            summary += ' 목적지 x0에 대한 쓰기는 버려지며 x0는 0을 유지합니다.'
        result.category, result.title, result.summary, result.operation = category, title, summary, operation
        result.notes.extend(notes)
        result.detail = " ".join(result.notes)
        return result

    def registers(reads=(), writes=()):
        nonlocal discarded_write
        result.reads = list(dict.fromkeys(register(x) for x in reads if register(x)))
        result.writes = list(dict.fromkeys(register(x) for x in writes if register(x) not in (None, "x0")))
        if any(register(x) == "x0" for x in writes):
            discarded_write = True
            result.notes.append("목적지 x0에 쓰는 값은 버려지며 x0는 항상 0입니다.")

    def invalid(reason):
        result.supported = False
        return finish("invalid", "명령어에 적힌 항목을 확인해 주세요", reason, notes=("명령어 이름 뒤에 적은 레지스터·숫자·주소의 개수와 순서를 확인해 주세요.",))

    if not text:
        return finish("empty", "빈 어셈블리 줄", "실행할 명령어가 없습니다.")
    if text.endswith(":"):
        return finish("label", "레이블", f"{text[:-1]}은 명령어나 데이터의 위치를 나타내는 이름입니다.", notes=("레이블 자체는 CPU 명령어가 아닙니다.",))
    if text.startswith("."):
        return finish("directive", "어셈블러 지시어", "섹션·심볼·디버그 정보 또는 데이터 배치를 지정합니다.", notes=("지시어 자체는 CPU가 실행하지 않습니다. .word와 같은 지시어는 바이트를 생성할 수 있습니다.",))

    if op in REGISTER_OPS or op in IMMEDIATE_OPS or op in MULTIPLY_OPS:
        if len(parts) != 3 or not register(parts[0]) or not register(parts[1]):
            return invalid("결과를 넣을 레지스터, 값을 읽을 레지스터, 함께 계산할 숫자 또는 레지스터가 순서대로 필요합니다.")
        rd, rs1, rhs = parts
        immediate = op in IMMEDIATE_OPS
        if not immediate and not register(rhs):
            return invalid("세 번째 피연산자는 레지스터여야 합니다.")
        if immediate:
            try:
                imm = int(rhs, 0)
            except ValueError:
                return invalid("명령어에 직접 적는 숫자는 정수여야 합니다. 이름으로 적힌 주소는 프로그램을 완성할 때 실제 숫자가 정해져야 해석할 수 있습니다.")
            if op in ("slli", "srli", "srai") and not 0 <= imm < 32:
                return invalid("RV32 즉치 시프트 크기는 0~31이어야 합니다.")
            if op not in ("slli", "srli", "srai") and not -2048 <= imm <= 2047:
                return invalid("이 명령어에 직접 적을 수 있는 숫자는 -2048부터 2047까지입니다. 범위를 넘는 수는 여러 명령어를 이용해 준비해야 합니다.")
        registers((rs1,) if immediate else (rs1, rhs), (rd,))
        if op in MULTIPLY_OPS:
            if op == "mul":
                operation = f"{rd} = low32({rs1} × {rhs})"
                notes = ("곱셈 결과가 길어져도 결과 레지스터에는 오른쪽 32비트만 담습니다. 왼쪽으로 넘친 부분은 버립니다.",)
            elif op.startswith("mulh"):
                signs = {"mulh": "두 입력을 모두 음수가 될 수 있는 숫자", "mulhsu": "첫 입력은 음수가 될 수 있는 숫자, 두 번째 입력은 음수 없는 숫자", "mulhu": "두 입력을 모두 음수 없는 숫자"}[op]
                operation = f"{rd} = high32({rs1} × {rhs})"
                notes = (f"{signs}으로 읽고 곱합니다. 최대 64비트인 곱셈 결과 중 왼쪽 32비트를 선택해 결과 레지스터에 넣습니다.",)
            else:
                unsigned = op.endswith("u")
                operation = f"{rd} = {'quotient' if op.startswith('div') else 'remainder'}({'u32' if unsigned else 's32'}({rs1}), {'u32' if unsigned else 's32'}({rhs}))"
                notes = ('입력을 음수 없이 읽는 정수 나눗셈입니다. 몫의 소수 부분은 버립니다.' if unsigned else '입력을 음수가 될 수 있는 숫자로 읽고 나눕니다. 음수의 몫도 소수 부분은 0 방향으로 버립니다. 예를 들어 -7을 3으로 나누면 몫은 -2, 나머지는 -1입니다.',
                         "CPU 명령어에서 0으로 나누면, 몫은 음수를 허용하는 명령어에서는 -1이고 음수 없이 읽는 명령어에서는 4294967295입니다. 나머지는 나누기 전 첫 번째 값 그대로입니다. C에서 0으로 나누는 코드에도 이 결과를 기대해선 안 됩니다.",
                         "음수를 허용하는 명령어에서 가장 작은 수 -2147483648을 -1로 나누면, 양수 결과가 범위를 넘으므로 몫은 -2147483648, 나머지는 0이 됩니다.")
            summary = (f"{rs1}와 {rhs}에 든 값을 곱해 결과의 {'왼쪽' if op.startswith('mulh') else '오른쪽'} 32비트를 {rd}에 저장합니다." if op.startswith('mul') else f"{rs1}에 든 값을 {rhs}에 든 값으로 나눈 {'몫을' if op.startswith('div') else '나머지를'} {rd}에 저장합니다. 두 입력은 {'음수 없는 숫자' if op.endswith('u') else '음수가 될 수 있는 숫자'}로 읽습니다.")
            return finish("arithmetic", "RV32M 곱셈·나눗셈", summary, operation, notes)
        base = IMMEDIATE_OPS.get(op, op)
        symbol, title = REGISTER_OPS[base]
        operation = f"{rd} = {rs1} {symbol} {rhs}"
        notes = ["레지스터 한 개에는 32비트가 들어갑니다. 계산 결과가 더 길면 오른쪽 32비트만 저장하고 왼쪽으로 넘친 부분은 버립니다."]
        if immediate and op not in ("slli", "srli", "srai"):
            notes.append("명령어에 적힌 숫자는 계산하기 전에 32비트 크기로 맞춥니다. 음수라면 음수의 의미가 유지되도록 왼쪽 빈자리를 채웁니다.")
            if op == 'sltiu':
                notes.append('sltiu는 이렇게 만든 비트들을 음수 없는 숫자로 읽고 비교합니다. 예를 들어 명령어에 -1을 적으면 비교할 때는 4294967295로 읽습니다.')
        if base in ("sll", "srl", "sra"):
            notes.append("RV32 즉치 시프트 크기는 명령어에 들어 있는 0~31의 값입니다." if immediate else "RV32 레지스터 시프트는 두 번째 레지스터의 하위 5비트만 사용합니다.")
            notes.append("산술 오른쪽 시프트는 부호 비트를 채우고 논리 오른쪽 시프트는 0을 채웁니다.")
        if base in ("slt", "sltu"):
            notes.append("비교 조건이 참이면 1, 거짓이면 0을 기록합니다.")
        if op == "addi" and register(rd) == register(rs1) == "x2":
            notes.append("sp 조정은 보통 스택 프레임 확보·반환에 쓰이지만, 이 명령어만으로 함수 시작·끝을 확정할 수 없습니다.")
            direction = '앞쪽(작은 주소)' if imm < 0 else '뒤쪽(큰 주소)'
            return finish("stack", "스택 포인터 조정", f"스택 위치를 가리키는 sp 레지스터의 주소를 {direction}으로 {abs(imm)}바이트 옮깁니다. 바뀐 주소를 sp에 다시 저장합니다. 메모리의 데이터를 옮기는 명령어는 아닙니다.", operation, notes)
        left, right = f'{rs1} 레지스터에 든 값', (f'명령어에 적힌 숫자 {rhs}' if immediate else f'{rhs} 레지스터에 든 값')
        action = {
            'add': f'{left}에 {with_particle(right)} 더합니다.',
            'sub': f'{left}에서 {with_particle(right)} 뺍니다.',
            'and': f'{left}과 {right}을 비트별로 비교해, 둘 다 1인 자리만 1로 만듭니다.',
            'or': f'{left}과 {right}을 비트별로 비교해, 하나라도 1인 자리는 1로 만듭니다.',
            'xor': f'{left}과 {right}을 비트별로 비교해, 서로 다른 자리만 1로 만듭니다.',
        }.get(base)
        summary = f"{action} 결과를 {rd} 레지스터에 저장합니다." if action else f"{rs1}와 {rhs}의 {title} 결과를 {rd} 레지스터에 저장합니다."
        if base in ('sll', 'srl', 'sra'):
            distance = f'{imm}칸' if immediate else f'{rhs} 레지스터의 하위 5비트가 나타내는 칸 수(0~31칸)'
            direction = '왼쪽' if base == 'sll' else '오른쪽'
            fill = '원래 맨 왼쪽의 부호 비트' if base == 'sra' else '0'
            summary = f'{left}의 비트들을 {direction}으로 {distance} 옮기고, 빈자리는 {fill}로 채웁니다. 결과를 {rd} 레지스터에 저장합니다.'
        if base in ('slt', 'sltu'):
            summary = f"{left}이 {right}보다 작으면 {rd} 레지스터에 1, 아니면 0을 저장합니다. 두 입력은 {'음수를 허용하는 정수' if base == 'slt' else '0 이상의 정수'}로 해석해 비교합니다."
        return finish("arithmetic", title, summary, operation, notes)

    if op in LOADS or op in STORES:
        if len(parts) != 2 or not register(parts[0]):
            return invalid("데이터를 주거나 받을 레지스터와 메모리 위치가 필요합니다. 예를 들어 4(sp)는 sp에 담긴 주소보다 4바이트 뒤의 위치입니다.")
        address = re.fullmatch(r"(-?(?:0[xX][0-9a-fA-F]+|\d+))\s*\(\s*(\w+)\s*\)", parts[1])
        if not address or not register(address[2]):
            return invalid("메모리 위치는 4(sp)처럼 적어 주세요. 괄호 안에는 주소가 담긴 레지스터를, 밖에는 이동할 바이트 거리를 적습니다.")
        try:
            offset, base = int(address[1], 0), address[2]
        except ValueError:
            return invalid("메모리 오프셋을 정수로 해석할 수 없습니다.")
        if not -2048 <= offset <= 2047:
            return invalid("메모리 오프셋은 부호 있는 12비트 범위여야 합니다.")
        load = op in LOADS
        width, extension = LOADS[op] if load else (STORES[op], "low_bits")
        registers((base,) if load else (parts[0], base), (parts[0],) if load else ())
        expression = f"u32({base} + {offset})"
        result.memory = {"access": "load" if load else "store", "width_bits": width, "extension": extension, "address_expression": expression}
        notes = [f"{base}에 담긴 주소에 {offset}바이트를 더해 접근 주소를 구합니다. 주소 계산 결과는 32비트로 유지합니다.", f"{width // 8}바이트를 접근하며, 여러 바이트 값은 낮은 주소부터 하위 바이트를 저장합니다(little-endian)."]
        if load:
            notes.append({"sign": "읽은 값의 부호 비트를 확장해 32비트로 만듭니다.", "zero": "상위 비트를 0으로 채워 32비트로 만듭니다.", "none": "32비트 워드를 그대로 읽습니다."}[extension])
        else:
            notes.append(f"원본 레지스터의 하위 {width}비트만 저장합니다. Store는 레지스터에 결과를 쓰지 않습니다.")
        notes.append("실제 접근 주소·값·정렬 오류는 MEM 단계와 runtime_error 이벤트에서 확인합니다.")
        operation = f"{parts[0]} ← MEM{width}[{expression}]" if load else f"MEM{width}[{expression}] ← {parts[0]}"
        location = f"{base} 레지스터에 든 주소에서 {'앞쪽으로' if offset < 0 else '뒤쪽으로'} {abs(offset)}바이트 떨어진 메모리 위치"
        stored_part = f'값 전체({width // 8}바이트)' if width == 32 else f'값에서 오른쪽 {width}비트({width // 8}바이트)'
        summary = (f"메모리에서 {width // 8}바이트를 읽어 {parts[0]} 레지스터에 담습니다. 읽을 곳은 {location}입니다."
                   if load else f"{parts[0]} 레지스터의 {with_particle(stored_part)} 메모리에 복사합니다. 저장할 곳은 {location}입니다. 데이터를 준 레지스터의 값은 바뀌지 않습니다.")
        if load and register(parts[0]) == 'x0':
            summary = f"{location}에서 {width // 8}바이트를 읽습니다. 결과를 받는 곳이 항상 0인 x0이므로 읽은 값은 보관하지 않습니다."
        return finish("load" if load else "store", "메모리 읽기" if load else "메모리 쓰기", summary, operation, notes)

    if op in BRANCHES:
        if len(parts) != 3 or not all(register(x) for x in parts[:2]):
            return invalid("두 비교 레지스터와 분기 목적지가 필요합니다.")
        rs1, rs2, target = parts
        symbol, signed = BRANCHES[op]
        interpretation = "s32" if signed else "u32"
        condition = f"{interpretation}({rs1}) {symbol} {interpretation}({rs2})"
        registers((rs1, rs2))
        result.control_flow = {"conditional": True, "condition": condition, "target_expression": pc_target(target), "link_register": None}
        relation = {'beq': '같으면', 'bne': '다르면', 'blt': '작으면', 'bltu': '작으면', 'bge': '크거나 같으면', 'bgeu': '크거나 같으면'}[op]
        summary = f"{rs1}의 값이 {rs2}의 값과 {relation}" if op in ('beq', 'bne') else f"{rs1}의 값이 {rs2}의 값보다 {relation}"
        summary += f" 분기 목적지 {target}로 이동합니다. 조건이 거짓이면 바로 다음 명령어로 진행합니다."
        if op not in ('beq', 'bne'):
            summary += f" 두 값은 {'부호 있는' if signed else '부호 없는'} 정수로 비교합니다."
        return finish("branch", "조건 분기", summary, notes=("분기 목적지의 숫자는 현재 명령어 주소에서 바이트 단위로 얼마나 이동할지를 나타냅니다. 레이블은 어셈블러가 실제 거리로 변환합니다.", "조건이 거짓이면 현재 주소보다 4바이트 뒤의 명령어로 진행합니다."))

    if op in ("lui", "auipc"):
        if len(parts) != 2 or not register(parts[0]):
            return invalid("목적지 레지스터와 20비트 상위 즉치값이 필요합니다.")
        try:
            if not -(1 << 19) <= int(parts[1], 0) < (1 << 20):
                return invalid("U형 상위 즉치값은 20비트로 표현할 수 있어야 합니다.")
        except ValueError:
            if not re.fullmatch(r'%[a-z_]+\([^()]+\)', parts[1]):
                return invalid("상위 즉치값 또는 재배치 표현식을 확인하세요.")
        registers(writes=(parts[0],))
        operation = f"{parts[0]} = " + ("PC + " if op == "auipc" else "") + f"({parts[1]} << 12)"
        try:
            number = int(parts[1], 0)
            amount = number * 4096
            summary = (f"명령어에 적힌 {number}에 4096을 곱해 {with_particle(str(amount))} 만듭니다. 이 값을 현재 명령어의 주소에 더해 {parts[0]} 레지스터에 저장합니다."
                       if op == 'auipc' else f"명령어에 적힌 {number}에 4096을 곱한 값 {with_particle(str(amount))} {parts[0]} 레지스터에 저장합니다.")
            if op == 'auipc' and number == 0:
                summary = f'현재 명령어가 놓인 주소를 {parts[0]} 레지스터에 복사합니다. 명령어에 적힌 숫자가 0이므로 주소에 더하는 값도 0입니다.'
        except ValueError:
            summary = f'프로그램을 만들 때 정해지는 주소 정보를 이용해 {parts[0]} 레지스터에 값을 준비합니다.'
        return finish("address", "PC 상대 주소 계산" if op == "auipc" else "상위 즉치값 적재", summary, operation,
                      ("auipc는 현재 명령어의 주소를 계산에 사용합니다. 주소에 숫자를 더할 뿐, 그 주소의 메모리 내용을 읽는 것은 아닙니다." if op == "auipc" else "lui는 숫자로 값을 만들 뿐, 메모리의 내용을 읽는 명령어가 아닙니다.", "4096을 곱하는 것은 비트를 왼쪽으로 12칸 옮기는 것과 같습니다. 결과는 레지스터 크기에 맞게 오른쪽 32비트만 저장합니다."))

    if op in ("jal", "jalr"):
        if op == "jal":
            if len(parts) == 1:
                parts = ["ra", parts[0]]
            if len(parts) != 2 or not register(parts[0]):
                return invalid("jal은 목적지 레지스터와 PC 상대 목적지가 필요합니다.")
            rd, target = parts
            reads, expression = (), pc_target(target)
        else:
            if len(parts) == 2:
                memory = re.fullmatch(r"(-?(?:0[xX][0-9a-fA-F]+|\d+))\((\w+)\)", parts[1])
                if memory:
                    parts = [parts[0], memory[2], memory[1]]
            if len(parts) != 3 or not register(parts[0]) or not register(parts[1]):
                return invalid("jalr은 rd, rs1, imm 또는 rd, imm(rs1) 형식이어야 합니다.")
            rd, rs1, imm = parts
            try:
                if not -2048 <= int(imm, 0) <= 2047:
                    return invalid("jalr 즉치값은 부호 있는 12비트 범위여야 합니다.")
            except ValueError:
                return invalid("jalr 즉치값은 정수여야 합니다. 심볼 재배치는 링크 결과를 확인하세요.")
            base = f"old({rs1})" if register(rd) == register(rs1) else rs1
            reads, expression = (rs1,), f"({base} + {imm}) & ~1"
        registers(reads, (rd,))
        result.control_flow = {"conditional": False, "condition": None, "target_expression": expression, "link_register": register(rd) if register(rd) != "x0" else None}
        summary = (f"현재 명령어 주소에서 {target}만큼 이동한 위치로 점프합니다." if op == 'jal' and re.fullmatch(r'-?(?:0[xX][0-9a-fA-F]+|\d+)', target) else f"{target} 레이블이 가리키는 위치로 점프합니다.") if op == 'jal' else f"명령어 실행 전 {rs1} 값에 {imm}바이트를 더해 이동할 주소를 구합니다. 그 주소의 맨 오른쪽 비트를 0으로 만든 뒤, 해당 주소로 점프합니다."
        summary += (" 복귀 주소는 저장하지 않습니다." if register(rd) == 'x0' else f" 바로 다음 명령어의 주소를 {rd}에 저장해 돌아올 위치를 남깁니다.")
        return finish("control", "점프 및 복귀 주소 기록", summary, f"{rd} = PC + 4; PC = {expression}",
                      ("복귀 주소는 현재 명령어보다 4바이트 뒤의 주소입니다. 목적지가 x0이면 이 주소는 저장하지 않습니다.", "목적지와 기준 레지스터가 같아도, 이동 주소 계산에는 덮어쓰기 전의 값을 사용합니다. 맨 오른쪽 비트를 지우는 것은 주소를 짝수로 맞추는 동작이며, 4바이트 정렬까지 보장하지는 않습니다."))

    if op in ALIASES:
        conditional_aliases = {
            'beqz': ('beq', False), 'bnez': ('bne', False),
            'bltz': ('blt', False), 'bgez': ('bge', False),
            'blez': ('bge', True), 'bgtz': ('blt', True),
            'bgt': ('blt', True), 'ble': ('bge', True),
            'bgtu': ('bltu', True), 'bleu': ('bgeu', True),
        }
        expansion = {"mv": "addi rd, rs, 0", "not": "xori rd, rs, -1", "neg": "sub rd, zero, rs", "nop": "addi zero, zero, 0", "ret": "jalr zero, 0(ra)", "j": "jal zero, target", "jr": "jalr zero, 0(rs)", "seqz": "sltiu rd, rs, 1", "snez": "sltu rd, zero, rs", "sltz": "slt rd, rs, zero", "sgtz": "slt rd, zero, rs"}.get(op)
        if op in ("ret", "nop") and parts:
            return invalid("이 의사 명령어는 피연산자를 받지 않습니다.")
        if op not in ("ret", "nop") and not parts:
            return invalid("의사 명령어의 피연산자가 필요합니다.")
        required = 0 if op in ("ret", "nop") else (1 if op in ("j", "jr", "call", "tail") else (3 if op in ("bgt", "ble", "bgtu", "bleu") else 2))
        if len(parts) != required:
            return invalid(f"{op}에는 {required}개의 피연산자가 필요합니다.")
        if op in ("mv", "not", "neg", "seqz", "snez", "sltz", "sgtz") and not all(register(x) for x in parts):
            return invalid("두 피연산자는 레지스터여야 합니다.")
        if op in ('li', 'la', 'lla') and not register(parts[0]):
            return invalid("목적지는 레지스터여야 합니다.")
        if op == 'jr' and not register(parts[0]):
            return invalid("jr의 피연산자는 기준 레지스터여야 합니다.")
        if op in ('beqz', 'bnez', 'bltz', 'bgez', 'blez', 'bgtz', 'bgt', 'ble', 'bgtu', 'bleu'):
            if not all(register(x) for x in parts[:-1]):
                return invalid("조건 분기의 비교 피연산자는 레지스터여야 합니다.")
            registers(parts[:-1])
            result.control_flow = {'conditional': True, 'condition': op, 'target_expression': parts[-1], 'link_register': None}
        if op == "ret":
            registers(("ra",))
            result.control_flow = {'conditional': False, 'condition': None, 'target_expression': 'ra & ~1', 'link_register': None}
        elif op == 'jr':
            registers((parts[0],))
            result.control_flow = {'conditional': False, 'condition': None, 'target_expression': f'{parts[0]} & ~1', 'link_register': None}
        elif op in ('j', 'call', 'tail'):
            registers(writes=('ra',) if op == 'call' else ())
            result.control_flow = {'conditional': False, 'condition': None, 'target_expression': parts[0], 'link_register': 'x1' if op == 'call' else None}
        elif op in ("mv", "not", "neg", "seqz", "snez", "sltz", "sgtz") and len(parts) == 2:
            registers((parts[1],), (parts[0],))
        elif op in ("li", "la", "lla") and parts:
            registers(writes=(parts[0],))
        concrete = expansion
        if concrete:
            substitutions = {'rd': parts[0] if parts else '', 'rs': parts[1] if len(parts) > 1 else parts[0] if parts else '', 'target': parts[-1] if parts else ''}
            concrete = re.sub(r'\b(rd|rs|target)\b', lambda match: substitutions[match[0]], concrete)
        notes = [f"CPU가 실행할 명령어로 쓰면 {concrete}에 해당합니다." if concrete else "한 줄을 CPU가 실행할 한 개 또는 여러 개의 명령어로 바꿉니다. 숫자나 주소의 크기에 따라 필요한 명령어 수가 달라집니다.", "짧게 적는 편의 이름이며, 같은 이름의 하드웨어 장치가 따로 있는 것은 아닙니다."]
        if op in conditional_aliases:
            base, reverse = conditional_aliases[op]
            operands = parts[:-1] if len(parts) == 3 else [parts[0], 'zero']
            if reverse:
                operands = list(reversed(operands))
            expansion = f"{base} {operands[0]}, {operands[1]}, {parts[-1]}"
            canonical = explain_asm(expansion)
            result.control_flow = canonical.control_flow
            notes = [f'기본 명령어로 {expansion}에 해당합니다.', *canonical.notes]
            return finish('pseudo', '조건 분기 의사 명령어', canonical.summary, expansion, notes)
        meanings = {
            'ret': 'ra에 기억해 둔 주소로 돌아가 실행을 이어갑니다.',
            'nop': '프로그램의 레지스터나 메모리 값을 바꾸지 않고 이 명령어를 지나갑니다.',
        }
        if parts:
            meanings.update({'j': f'{parts[0]}이 가리키는 위치로 이동합니다. 돌아올 주소는 저장하지 않습니다.',
                             'jr': f'{parts[0]} 레지스터에 든 주소로 이동합니다. 돌아올 주소는 저장하지 않습니다.',
                             'call': f'돌아올 주소를 ra에 기억한 뒤 {parts[-1]} 함수로 이동합니다.',
                             'tail': f'{parts[-1]} 함수로 이동합니다. 이 이동을 위해 ra에 새로운 복귀 주소를 넣지는 않습니다.'})
        if len(parts) == 2:
            meanings.update({'mv': f'두 번째 항목인 {parts[1]}의 값을 읽어 맨 앞의 {parts[0]}에 복사합니다.',
                             'li': f'명령어에 적힌 숫자 {with_particle(parts[1])} {parts[0]} 레지스터에 넣습니다.',
                             'la': f'{parts[1]}이라는 이름이 가리키는 주소를 구해 {parts[0]}에 넣습니다.',
                             'lla': f'{parts[1]}이라는 이름이 가리키는 주소를 구해 {parts[0]}에 넣습니다.',
                             'not': f'{parts[1]}에 든 값의 각 비트에서 0은 1로, 1은 0으로 바꿔 {parts[0]}에 넣습니다.',
                             'neg': f'0에서 {parts[1]}의 값을 뺀 결과를 {parts[0]}에 넣습니다.',
                             'seqz': f'{parts[1]}의 값이 0이면 {parts[0]}에 1, 아니면 0을 넣습니다.',
                             'snez': f'{parts[1]}의 값이 0이 아니면 {parts[0]}에 1, 0이면 0을 넣습니다.',
                             'sltz': f'{parts[1]}의 값이 음수이면 {parts[0]}에 1, 아니면 0을 넣습니다.',
                             'sgtz': f'{parts[1]}의 값이 0보다 크면 {parts[0]}에 1, 아니면 0을 넣습니다.'})
        return finish("pseudo", "짧게 적는 명령어 이름 · 의사 명령어", meanings.get(op, f'{text}에 해당하는 동작을 실행합니다.'), expansion, notes)

    if op in ("ecall", "ebreak", "fence"):
        if op != 'ecall':
            result.supported = False
            meaning = '실행을 중단하고 디버거 등에 제어를 넘기는 환경 예외 요청' if op == 'ebreak' else '메모리 접근의 관찰 순서를 제약하는 명령어'
            return finish('unsupported', '시뮬레이터에서 실행할 수 없는 명령어', f'{op}는 {meaning}입니다. 현재 시뮬레이터에서는 실행을 지원하지 않습니다.',
                          notes=('RISC-V에 정의된 명령어라도 이 시뮬레이터에서 모두 실행할 수 있는 것은 아닙니다. FENCE와 EBREAK는 실행을 지원하지 않습니다.',))
        return finish("environment", "실행 환경에 서비스 요청", "프로그램이 실행 환경에 서비스를 요청합니다. 화면 출력이나 실행 종료처럼 프로그램 바깥의 도움이 필요할 때 사용합니다.", notes=("CPU는 ECALL 환경 호출 예외를 발생시켜 실행 환경에 처리를 넘깁니다. 어떤 서비스를 요청하는지는 운영체제나 시뮬레이터의 규약으로 정합니다.", "ecall 번호·출력·종료는 실행 환경의 규약에 따르며, RISC-V ISA 자체가 a7=10을 종료로 정의하지 않습니다."))
    result.supported, result.evidence_level = False, "unknown"
    return finish("unsupported", "지원 범위 확인 필요", f"'{op}'에 대한 RV32IM 상세 해설이 없습니다.", notes=("RV64·부동소수점·특권 명령어 등을 RV32IM 지원 명령어로 단정하지 않습니다.",))
