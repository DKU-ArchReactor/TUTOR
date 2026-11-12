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


def explain_encoded_asm(text: str, raw_instruction) -> RuleExplanation:
    """CORE displays U immediates already shifted; use encoding when available."""
    try:
        word = int(raw_instruction, 16) if isinstance(raw_instruction, str) else None
    except ValueError:
        word = None
    tokens = text.split(None, 1)
    op = tokens[0].lower() if tokens else ''
    expected = {'lui': 0x37, 'auipc': 0x17}.get(op)
    if expected is not None and word is not None and 0 <= word <= 0xFFFFFFFF and word & 0x7F == expected:
        rd, immediate = (word >> 7) & 31, word >> 12
        result = explain_asm(f'{op} x{rd}, {immediate}')
        note = f'기계어 {raw_instruction}의 상위 즉치 필드는 {immediate}입니다. CORE 표시 문자열은 이미 12비트 이동한 값을 사용할 수 있으므로, 연산 해설은 기계어를 기준으로 작성합니다.'
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

    def finish(category, title, summary, operation=None, notes=()):
        result.category, result.title, result.summary, result.operation = category, title, summary, operation
        result.notes.extend(notes)
        result.detail = " ".join(result.notes)
        return result

    def registers(reads=(), writes=()):
        result.reads = list(dict.fromkeys(register(x) for x in reads if register(x)))
        result.writes = list(dict.fromkeys(register(x) for x in writes if register(x) not in (None, "x0")))
        if any(register(x) == "x0" for x in writes):
            result.notes.append("목적지 x0에 쓰는 값은 버려지며 x0는 항상 0입니다.")

    def invalid(reason):
        result.supported = False
        return finish("invalid", "피연산자 확인 필요", reason, notes=("정상 명령어로 해석하지 않았습니다. 어셈블러 문법과 피연산자를 확인하세요.",))

    if not text:
        return finish("empty", "빈 어셈블리 줄", "실행할 명령어가 없습니다.")
    if text.endswith(":"):
        return finish("label", "레이블", f"{text[:-1]}은 명령어나 데이터의 위치를 나타내는 이름입니다.", notes=("레이블 자체는 CPU 명령어가 아닙니다.",))
    if text.startswith("."):
        return finish("directive", "어셈블러 지시어", "섹션·심볼·디버그 정보 또는 데이터 배치를 지정합니다.", notes=("지시어 자체는 CPU가 실행하지 않습니다. .word와 같은 지시어는 바이트를 생성할 수 있습니다.",))

    if op in REGISTER_OPS or op in IMMEDIATE_OPS or op in MULTIPLY_OPS:
        if len(parts) != 3 or not register(parts[0]) or not register(parts[1]):
            return invalid("목적지·첫 피연산자 레지스터와 세 번째 피연산자가 필요합니다.")
        rd, rs1, rhs = parts
        immediate = op in IMMEDIATE_OPS
        if not immediate and not register(rhs):
            return invalid("세 번째 피연산자는 레지스터여야 합니다.")
        if immediate:
            try:
                imm = int(rhs, 0)
            except ValueError:
                return invalid("즉치값은 정수여야 합니다. 재배치 표현식은 이 정적 해설에서 판정하지 않습니다.")
            if op in ("slli", "srli", "srai") and not 0 <= imm < 32:
                return invalid("RV32 즉치 시프트 크기는 0~31이어야 합니다.")
            if op not in ("slli", "srli", "srai") and not -2048 <= imm <= 2047:
                return invalid("I형 산술 즉치값은 부호 있는 12비트 범위여야 합니다.")
        registers((rs1,) if immediate else (rs1, rhs), (rd,))
        if op in MULTIPLY_OPS:
            if op == "mul":
                operation = f"{rd} = low32({rs1} × {rhs})"
                notes = ("곱의 하위 32비트를 기록합니다. 상위 비트는 저장하지 않습니다.",)
            elif op.startswith("mulh"):
                signs = {"mulh": "두 피연산자 모두 부호 있는 값", "mulhsu": "첫 값은 부호 있는 값, 두 번째 값은 부호 없는 값", "mulhu": "두 값 모두 부호 없는 값"}[op]
                operation = f"{rd} = high32({rs1} × {rhs})"
                notes = (f"{signs}으로 해석한 64비트 곱의 상위 32비트를 기록합니다.",)
            else:
                unsigned = op.endswith("u")
                operation = f"{rd} = {'quotient' if op.startswith('div') else 'remainder'}({'u32' if unsigned else 's32'}({rs1}), {'u32' if unsigned else 's32'}({rhs}))"
                notes = (("부호 없는" if unsigned else "부호 있는") + " 정수 나눗셈입니다. 부호 있는 몫은 0 방향으로 절삭하며 나머지의 부호는 피제수를 따릅니다.",
                         "0으로 나누면 몫은 0xFFFFFFFF, 나머지는 피제수입니다. RV32M은 이 경우 산술 예외를 발생시키지 않습니다.",
                         "부호 있는 INT_MIN / -1의 몫은 INT_MIN, 나머지는 0입니다.")
            return finish("arithmetic", "RV32M 곱셈·나눗셈", operation, operation, notes)
        base = IMMEDIATE_OPS.get(op, op)
        symbol, title = REGISTER_OPS[base]
        operation = f"{rd} = {rs1} {symbol} {rhs}"
        notes = ["결과는 32비트로 기록합니다. 실제 기록 값과 시점은 CORE 실행 이력을 근거로 확인합니다."]
        if immediate and op not in ("slli", "srli", "srai"):
            notes.append("즉치값은 부호 확장됩니다. sltiu도 먼저 즉치값을 부호 확장한 뒤 부호 없는 비교를 합니다.")
        if base in ("sll", "srl", "sra"):
            notes.append("RV32 레지스터 시프트는 두 번째 레지스터의 하위 5비트만 사용합니다. 산술 오른쪽 시프트는 부호 비트를 채우고 논리 오른쪽 시프트는 0을 채웁니다.")
        if base in ("slt", "sltu"):
            notes.append("비교 조건이 참이면 1, 거짓이면 0을 기록합니다.")
        if op == "addi" and register(rd) == register(rs1) == "x2":
            notes.append("sp 조정은 보통 스택 프레임 확보·반환에 쓰이지만, 이 명령어만으로 함수 시작·끝을 확정할 수 없습니다.")
            return finish("stack", "스택 포인터 조정", operation, operation, notes)
        return finish("arithmetic", title, operation, operation, notes)

    if op in LOADS or op in STORES:
        if len(parts) != 2 or not register(parts[0]):
            return invalid("레지스터와 offset(base) 형태의 주소가 필요합니다.")
        address = re.fullmatch(r"(-?(?:0[xX][0-9a-fA-F]+|\d+))\s*\(\s*(\w+)\s*\)", parts[1])
        if not address or not register(address[2]):
            return invalid("주소는 정수 오프셋과 기준 레지스터로 해석할 수 있어야 합니다.")
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
        notes = [f"유효 주소는 {expression}입니다. 주소를 추정해 스택·전역 변수로 단정하지 않습니다.", f"{width // 8}바이트를 접근하며 ArchReactor는 little-endian으로 바이트를 배치합니다."]
        if load:
            notes.append({"sign": "읽은 값의 부호 비트를 확장해 32비트로 만듭니다.", "zero": "상위 비트를 0으로 채워 32비트로 만듭니다.", "none": "32비트 워드를 그대로 읽습니다."}[extension])
        else:
            notes.append(f"원본 레지스터의 하위 {width}비트만 저장합니다. Store는 레지스터에 결과를 쓰지 않습니다.")
        notes.append("실제 접근 주소·값·정렬 오류는 MEM 단계와 runtime_error 이벤트에서 확인합니다.")
        operation = f"{parts[0]} ← MEM{width}[{expression}]" if load else f"MEM{width}[{expression}] ← {parts[0]}"
        return finish("load" if load else "store", "메모리 읽기" if load else "메모리 쓰기", operation, operation, notes)

    if op in BRANCHES:
        if len(parts) != 3 or not all(register(x) for x in parts[:2]):
            return invalid("두 비교 레지스터와 분기 목적지가 필요합니다.")
        rs1, rs2, target = parts
        symbol, signed = BRANCHES[op]
        interpretation = "s32" if signed else "u32"
        condition = f"{interpretation}({rs1}) {symbol} {interpretation}({rs2})"
        registers((rs1, rs2))
        result.control_flow = {"conditional": True, "condition": condition, "target_expression": f"PC + {target}", "link_register": None}
        return finish("branch", "조건 분기", f"{condition}이면 {target}로 분기합니다.", notes=("분기 즉치값은 현재 명령어 PC 기준 상대 오프셋입니다. 레이블은 어셈블러가 실제 오프셋으로 변환합니다.", "조건이 거짓이면 다음 명령어 PC + 4로 진행합니다. 실제 taken 여부·플러시는 CORE 이벤트를 사용합니다. 예측 실패로 단정하지 않습니다."))

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
        return finish("address", "PC 상대 주소 계산" if op == "auipc" else "상위 즉치값 적재", operation, operation,
                      ("auipc는 현재 PC 전체 값에 상위 즉치값을 더합니다. PC 상위 비트만 더하는 연산이 아닙니다." if op == "auipc" else "상위 20비트를 설정하고 하위 12비트는 0으로 만듭니다.", "심볼·재배치 표현식의 실제 주소는 링크 결과와 코드 매핑을 확인합니다."))

    if op in ("jal", "jalr"):
        if op == "jal":
            if len(parts) == 1:
                parts = ["ra", parts[0]]
            if len(parts) != 2 or not register(parts[0]):
                return invalid("jal은 목적지 레지스터와 PC 상대 목적지가 필요합니다.")
            rd, target = parts
            reads, expression = (), f"PC + {target}"
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
            reads, expression = (rs1,), f"({rs1} + {imm}) & ~1"
        registers(reads, (rd,))
        result.control_flow = {"conditional": False, "condition": None, "target_expression": expression, "link_register": register(rd) if register(rd) != "x0" else None}
        return finish("control", "점프 및 복귀 주소 기록", f"PC를 {expression}로 변경합니다.", f"{rd} = PC + 4; PC = {expression}",
                      ("복귀 주소는 현재 명령어 주소 + 4입니다. rd가 x0이면 링크 값은 버려집니다.", "jalr의 목표 주소는 최하위 비트를 0으로 만듭니다. 실제 목표·분기/정렬 오류는 CORE 이벤트에서 확인합니다."))

    if op in ALIASES:
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
        notes = [f"일반적인 확장: {expansion}." if expansion else "실제 기본 명령어 수와 확장은 즉치값·심볼·재배치·링커 완화에 따라 달라집니다.", "의사 명령어 자체가 별도의 하드웨어 연산인 것은 아닙니다. 정확한 실행은 링크된 기계어를 확인하세요."]
        return finish("pseudo", "어셈블리 의사 명령어", f"{text}의 의미를 기본 RISC-V 명령어로 표현합니다.", expansion, notes)

    if op in ("ecall", "ebreak", "fence"):
        return finish("environment", "실행 환경 요청" if op != "fence" else "메모리 순서 제약", f"{op} 명령어입니다.", notes=("ecall 번호·출력·종료는 실행 환경의 규약에 따르며, RISC-V ISA 자체가 a7=10을 종료로 정의하지 않습니다." if op == "ecall" else "실행 환경 및 시뮬레이터의 지원 범위를 확인하세요.",))
    result.supported, result.evidence_level = False, "unknown"
    return finish("unsupported", "지원 범위 확인 필요", f"'{op}'에 대한 RV32IM 상세 해설이 없습니다.", notes=("RV64·부동소수점·특권 명령어 등을 RV32IM 지원 명령어로 단정하지 않습니다.",))
