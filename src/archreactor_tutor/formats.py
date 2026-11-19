"""RV32 field layouts from encoded words, separate from runtime control signals."""

ROLES = {
    'opcode': '명령어 종류를 고르는 기본 코드', 'rd': '결과를 받을 레지스터 번호',
    'rs1': '첫 번째 입력 레지스터 번호', 'rs2': '두 번째 입력 레지스터 번호',
    'funct3': '같은 종류 안에서 연산을 구분', 'funct7': '연산을 더 구체적으로 구분',
    'shamt': '이동할 비트 수 (0~31)',
}


def instruction_format(raw):
    try:
        word = int(raw, 16) if isinstance(raw, str) else None
    except ValueError:
        return None
    if word is None or not 0 <= word <= 0xFFFFFFFF:
        return None
    code, funct3, funct7 = word & 127, (word >> 12) & 7, word >> 25
    common = [('funct3', 14, 12), ('rd', 11, 7), ('opcode', 6, 0)]
    base = [('rs2', 24, 20), ('rs1', 19, 15)]
    immediate = None
    if code == 0x33:
        name, description = 'R', '레지스터 두 개를 입력으로 사용하고 결과를 목적지 레지스터에 기록합니다. M 확장도 같은 R형 배치를 사용합니다.'
        layout = [('funct7', 31, 25), *base, *common]
    elif code in (0x03, 0x13, 0x67, 0x73):
        name, description = 'I', '12비트 즉치 필드와 기준 레지스터를 사용합니다. 산술·로드·간접 점프·SYSTEM은 같은 비트 배치를 서로 다르게 해석합니다.'
        if code == 0x13 and ((funct3 == 1 and funct7 == 0) or (funct3 == 5 and funct7 in (0, 32))):
            layout = [('funct7', 31, 25), ('shamt', 24, 20), ('rs1', 19, 15), *common]
            immediate = (word >> 20) & 31
            description = 'I형 시프트에서는 상위 구분 비트와 5비트 이동 크기(shamt)를 나눕니다. 전체 12비트를 이동 크기로 사용하지 않습니다.'
        else:
            layout = [('imm[11:0]', 31, 20), ('rs1', 19, 15), *common]
            if code != 0x73:
                immediate = word >> 20
                if immediate & 0x800:
                    immediate -= 1 << 12
            else:
                description = 'SYSTEM 명령은 I형 비트 배치를 사용하지만 ECALL의 rs1·rd=0은 일반적인 레지스터 입력·결과 기록을 뜻하지 않습니다.'
    elif code == 0x23:
        name, description = 'S', 'rs2의 데이터를 rs1 + 부호 확장 오프셋 주소에 저장합니다. rd 필드는 없고 즉치값이 두 구간으로 나뉩니다.'
        layout = [('imm[11:5]', 31, 25), *base, ('funct3', 14, 12), ('imm[4:0]', 11, 7), ('opcode', 6, 0)]
        immediate = ((word >> 25) << 5) | ((word >> 7) & 31)
        if immediate & 0x800:
            immediate -= 1 << 12
    elif code == 0x63:
        name, description = 'B', '두 레지스터를 비교합니다. 분기 변위의 비트를 재조합하고 마지막 0비트를 붙여 현재 PC에 더합니다. 결과 레지스터는 없습니다.'
        layout = [('imm[12]', 31, 31), ('imm[10:5]', 30, 25), *base, ('funct3', 14, 12), ('imm[4:1]', 11, 8), ('imm[11]', 7, 7), ('opcode', 6, 0)]
        immediate = ((word >> 31) << 12) | (((word >> 7) & 1) << 11) | (((word >> 25) & 63) << 5) | (((word >> 8) & 15) << 1)
        if immediate & 0x1000:
            immediate -= 1 << 13
    elif code in (0x37, 0x17):
        name, description = 'U', '상위 20비트 필드를 12비트 왼쪽으로 이동합니다. LUI는 그 값을 기록하고 AUIPC는 현재 PC에 더한 값을 기록합니다.'
        layout = [('imm[31:12]', 31, 12), ('rd', 11, 7), ('opcode', 6, 0)]
        immediate = word & 0xFFFFF000
        if immediate & 0x80000000:
            immediate -= 1 << 32
    elif code == 0x6F:
        name, description = 'J', '분산된 점프 변위를 재조합해 현재 PC에 더합니다. rd에는 PC + 4를 기록하며 x0이면 기록을 버립니다.'
        layout = [('imm[20]', 31, 31), ('imm[10:1]', 30, 21), ('imm[11]', 20, 20), ('imm[19:12]', 19, 12), ('rd', 11, 7), ('opcode', 6, 0)]
        immediate = ((word >> 31) << 20) | (((word >> 12) & 255) << 12) | (((word >> 20) & 1) << 11) | (((word >> 21) & 1023) << 1)
        if immediate & 0x100000:
            immediate -= 1 << 21
    else:
        return None
    fields = []
    for field, high, low in layout:
        width = high - low + 1
        value = (word >> low) & ((1 << width) - 1)
        role = ROLES.get(field, '즉치값을 구성하는 비트 조각')
        if code == 0x73 and field in ('rs1', 'rd'):
            role = 'SYSTEM 명령 식별에 사용되는 고정 필드; 일반 레지스터 접근이 아님'
        fields.append({'name': field, 'high': high, 'low': low, 'width': width, 'value': value,
                       'binary': f'{value:0{width}b}', 'role': role})
    return {'name': name, 'word': f'0x{word:08X}', 'width_bits': 32,
            'description': description, 'fields': fields, 'immediate': immediate,
            'basis': 'machine_code', 'note': '형식의 필드 배치와 실제 사용 여부는 다릅니다. x0 쓰기는 버리고, 제어 신호와 실행값은 선택한 클록에서 확인합니다.'}
