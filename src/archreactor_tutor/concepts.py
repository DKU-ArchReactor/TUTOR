"""Source-backed learning prompts; examples are never execution evidence."""
from .asm import ALIASES, IMMEDIATE_OPS, MULTIPLY_OPS, register

ISA = ('RISC-V 공식 RV32I 명세', 'https://docs.riscv.org/reference/isa/v20260120/unpriv/rv32.html')
ABI = ('RISC-V 공식 호출 규약', 'https://docs.riscv.org/reference/abi/v1.0/riscv-cc-procedure-calling-convention.html')
CALLS = ('Cornell CS 3410 · 함수 호출', 'https://www.cs.cornell.edu/courses/cs3410/2026sp/notes/asm-call.html')
M_EXT = ('RISC-V 공식 M 확장 명세', 'https://docs.riscv.org/reference/isa/v20260120/unpriv/m-st-ext.html')
C_STANDARD = ('C11 공개 초안 · 정수 연산 (§6.5, §6.5.5)', 'https://www.open-std.org/jtc1/sc22/wg14/www/docs/n1570.pdf')

# First reading requires no prior knowledge of the technical heading.
PLAIN = {
    'load-store': '주소는 메모리에서 찾을 위치이고, 값은 그 위치에 들어 있는 내용입니다.',
    'load-extension': '작은 데이터를 더 큰 저장 공간에 담을 때, 남는 자리를 채우는 두 가지 방법입니다.',
    'signed-compare': '같은 0과 1도 음수를 허용해 읽는지에 따라 크기 비교가 달라집니다.',
    'branch-pc': '조건을 검사해서 다음에 실행할 명령어의 위치를 고릅니다. PC는 명령어의 주소입니다.',
    'call-return': '함수로 이동할 때는 일이 끝난 뒤 돌아올 위치도 기억해야 합니다.',
    'shift': '시프트는 0과 1로 된 비트열을 왼쪽이나 오른쪽으로 옮기는 연산입니다.',
    'm-extension': '곱셈은 곱을, 나눗셈은 몫이나 나머지를 구합니다. RISC-V에서는 M 확장이 이 명령어들을 제공합니다.',
    'word-result': '레지스터는 CPU 안에서 값을 담는 작은 저장 공간입니다. RV32 레지스터 하나에는 32개의 비트가 들어갑니다.',
    'immediate': '즉치값은 명령어에 직접 적어 넣은 숫자입니다. 레지스터에 담긴 값과 구분해서 읽으면 됩니다.',
    'pseudo': '자주 쓰는 동작에 붙인 편리한 이름입니다. 어셈블러가 CPU가 실행할 실제 명령어로 바꿉니다.',
    'stack-abi': '스택은 함수가 필요한 값을 잠시 보관하는 메모리 공간입니다. sp는 스택의 현재 경계를 가리킵니다.',
    'argument-abi': '함수에 건네는 입력, 함수가 돌려주는 결과, 함수가 끝나고 돌아갈 위치는 서로 다른 정보입니다.',
    'zero-register': 'x0는 언제 읽어도 0인 특별한 레지스터입니다. zero는 x0의 다른 이름입니다.',
    'shift-left': '비트열을 왼쪽으로 옮기고 오른쪽 빈자리에 0을 채웁니다. 범위를 넘는 왼쪽 비트는 사라집니다.',
    'bitwise': '숫자를 0과 1의 자리로 나누어, 같은 위치의 비트끼리 계산합니다.',
    'upper-immediate': '큰 상수나 주소는 한 번에 준비하기 어려워 여러 명령어를 이어서 만들 수 있습니다.',
}


def concept(key, title, explanation, example, question, answer, sources=(ISA,)):
    return {'id': key, 'title': title, 'explanation': explanation, 'example': example,
            'plain': PLAIN[key],
            'question': question, 'answer': answer,
            'sources': [{'title': title, 'url': url} for title, url in sources]}


def instruction_concepts(explanation):
    if not explanation.get('supported', True):
        return []
    op = explanation.get('opcode')
    parts = [part.strip() for part in (explanation.get('operands') or '').split(',')]
    memory = explanation.get('memory')
    control = explanation.get('control_flow') or {}
    topics = []
    if memory:
        topics.append(concept('load-store', '주소와 값은 다릅니다',
            'RISC-V는 메모리에서 읽기·쓰기와 레지스터 연산을 나눕니다. 주소의 오프셋 단위는 바이트이며, C 배열의 원소 번호와 다릅니다.',
            'lw a0, 4(sp): sp가 0x2000이면 접근 주소는 0x2004입니다. 읽은 값이 4라는 뜻은 아닙니다.',
            'int가 4바이트인 배열에서 다음 원소로 이동하려면 주소를 얼마나 바꿀까요?',
            '4바이트입니다. 배열 인덱스에 원소 크기를 곱해 바이트 오프셋을 만듭니다.'))
        if op in ('lb', 'lbu', 'lh', 'lhu'):
            topics.append(concept('load-extension', '부호 확장과 0 확장',
                '작은 데이터를 32비트 레지스터에 담을 때 lb·lh는 부호 비트를 복제하고, lbu·lhu는 상위 비트를 0으로 채웁니다.',
                '메모리의 바이트 0xFF를 lb로 읽으면 0xFFFFFFFF(-1), lbu로 읽으면 0x000000FF(255)입니다.',
                '같은 바이트인데 결과가 다른 이유는 무엇일까요?',
                '원본 바이트는 같지만 상위 24비트를 채우는 규칙이 다르기 때문입니다.'))
    elif control.get('conditional') or op in ('slt', 'sltu', 'slti', 'sltiu'):
        topics.append(concept('signed-compare', '같은 비트도 비교 방식에 따라 달라집니다',
            '레지스터 자체에는 signed·unsigned 타입이 없습니다. 명령어가 비트열의 해석 방법을 결정합니다.',
            '0xFFFFFFFF와 1: signed 비교에서는 -1 < 1이 참이고, unsigned 비교에서는 4294967295 < 1이 거짓입니다.',
            'beq의 같음 비교에도 signed·unsigned 구분이 필요할까요?',
            '필요하지 않습니다. 같은 비트열인지 비교하므로 부호 해석에 따라 같음의 결과가 바뀌지 않습니다.'))
        if control.get('conditional'):
            topics.append(concept('branch-pc', '분기 기준은 현재 명령어의 PC',
                '조건이 참이면 현재 PC에 분기 변위를 더하고, 거짓이면 다음 명령어로 진행합니다. C의 if·반복문은 여러 비교·분기로 구현될 수 있습니다.',
                'PC 0x1000의 beq a0, a1, 8: 같으면 0x1008, 다르면 0x1004로 진행합니다.',
                'taken이 참이라는 사실만으로 C 조건식도 참이라고 단정할 수 있을까요?',
                '아닙니다. 컴파일러가 반대 조건으로 건너뛰게 만들 수 있으므로 실제 명령어와 C 매핑을 함께 봐야 합니다.'))
    elif op in ('jal', 'jalr', 'ret', 'call', 'tail', 'jr', 'j'):
        topics.append(concept('call-return', '점프와 함수 호출의 차이',
            'jal·jalr는 이동하면서 복귀 주소를 목적지 레지스터에 기록할 수 있습니다. 목적지가 x0이면 복귀 주소를 버립니다. 모든 점프가 함수 호출인 것은 아닙니다.',
            'jal ra, target은 ra에 PC + 4를 기록합니다. ret은 보통 jalr x0, 0(ra)로 복귀합니다.',
            '함수 안에서 다른 함수를 호출하면 기존 ra는 어떻게 보존할까요?',
            '중첩 호출이 ra를 덮어쓸 수 있어, 필요한 기존 복귀 주소를 보통 스택에 저장했다가 복원합니다.', (ISA, CALLS)))
    elif op in ('sll', 'slli'):
        topics.append(concept('shift-left', '왼쪽 시프트와 원소 주소 계산',
            'RV32 왼쪽 시프트는 하위 32비트만 남깁니다. 배열의 int 원소 크기가 4바이트라면 인덱스의 2비트 왼쪽 시프트를 바이트 오프셋 계산에 사용할 수 있습니다.',
            'slli a0, a1, 2에서 a1이 3이면 a0는 12입니다. 3번째 인덱스의 바이트 오프셋을 만드는 데 쓸 수 있습니다.',
            '왼쪽 시프트가 언제나 원래 수의 정확한 곱셈 결과를 보존할까요?',
            '아닙니다. 32비트 밖으로 나가는 비트는 버려집니다. C에서는 피연산자 타입과 시프트 크기 등도 확인해야 합니다.', (ISA, C_STANDARD)))
    elif op in ('srl', 'sra', 'srli', 'srai'):
        topics.append(concept('shift', '오른쪽 시프트의 빈자리는 무엇으로 채울까요?',
            '논리 오른쪽 시프트는 0을 채우고, 산술 오른쪽 시프트는 기존 부호 비트를 채웁니다. RV32 레지스터 시프트는 크기의 하위 5비트만 사용합니다.',
            '0xFFFFFFF8(-8)를 1비트 이동: srai는 0xFFFFFFFC(-4), srli는 0x7FFFFFFC입니다.',
            'sra로 음수를 오른쪽 이동하면 C의 음수 나눗셈과 항상 같을까요?',
            '아닙니다. 예를 들어 -3의 1비트 산술 시프트는 -2지만, C 정수 나눗셈 -3 / 2는 0 방향 절삭으로 -1입니다.', (ISA, C_STANDARD)))
    elif op in MULTIPLY_OPS:
        topics.append(concept('m-extension', '곱셈·나눗셈은 M 확장',
            'RV32IM의 M은 정수 곱셈·나눗셈 확장입니다. mul은 곱의 하위 32비트, mulh 계열은 상위 32비트를 선택합니다.',
            'div의 -7 / 3은 -2, rem의 -7 % 3은 -1입니다. divu·remu는 부호 없이 해석합니다.',
            'RISC-V div의 0 나누기 규칙을 C의 0 나누기에도 적용해도 될까요?',
            '안 됩니다. ISA에는 결과 규칙이 있지만 C에서 정수 0 나누기는 정의되지 않은 동작입니다.', (M_EXT, C_STANDARD)))
    elif op in ('add', 'sub', 'addi'):
        topics.append(concept('word-result', '32비트 결과와 C의 정수 규칙',
            'RV32 덧셈·뺄셈은 결과의 하위 32비트를 기록하며 정수 오버플로 자체로 예외를 내지 않습니다. 이것이 C signed 오버플로를 허용한다는 뜻은 아닙니다.',
            '0xFFFFFFFF + 1의 RV32 결과는 0x00000000입니다. C unsigned 32비트 연산도 이 범위에서 순환합니다.',
            'C의 int 최댓값에 1을 더하는 동작도 항상 순환한다고 가정할 수 있을까요?',
            '아닙니다. C signed 오버플로는 정의되지 않은 동작이므로 ISA의 비트 계산과 구분해야 합니다.', (ISA, C_STANDARD)))
    elif op in ('and', 'or', 'xor', 'andi', 'ori', 'xori'):
        topics.append(concept('bitwise', '비트 연산과 마스크',
            'AND는 두 비트가 모두 1일 때, OR는 하나라도 1일 때, XOR는 두 비트가 다를 때 1입니다. AND 마스크는 원하는 비트만 남기는 데 쓰입니다.',
            '13은 이진수 1101, 7은 0111입니다. 13 & 7은 0101이므로 5입니다.',
            'C의 &와 &&는 같은 연산일까요?',
            '아닙니다. &는 각 비트를 계산하고, &&는 조건의 참·거짓을 계산하며 왼쪽이 거짓이면 오른쪽을 평가하지 않습니다.', (ISA, C_STANDARD)))
    elif op in ('lui', 'auipc'):
        topics.append(concept('upper-immediate', '큰 상수와 PC 기준 주소 만들기',
            'lui는 20비트 즉치 필드를 12비트 왼쪽으로 옮겨 상위 부분을 만들고, auipc는 그 값을 현재 PC에 더합니다. CORE 표시 문자열의 숫자는 이미 이동된 값일 수 있어 원본 기계어 해설을 함께 봅니다.',
            '상위 필드 1인 lui는 0x00001000을 만듭니다. 뒤에 addi로 4를 더하면 0x00001004입니다.',
            'lui만 보고 그 값이 반드시 전역 변수의 주소라고 할 수 있을까요?',
            '아닙니다. 큰 정수 상수일 수도 있습니다. 후속 명령어와 심볼·디버그 정보를 확인해야 합니다.'))
    if op in IMMEDIATE_OPS and op not in ('slli', 'srli', 'srai'):
        topics.append(concept('immediate', '즉치값은 명령어 안의 상수',
            'I형 산술 즉치값은 부호 있는 12비트 값입니다. 음수 즉치값은 32비트로 부호 확장한 뒤 연산합니다.',
            'addi a0, a1, 5: a1에 든 값에 숫자 5를 더해 a0에 저장합니다. 여기서 5가 즉치값입니다.',
            'addi a0, a1, 5000을 단일 I형 명령어로 표현할 수 있을까요?',
            '5000은 -2048~2047 범위를 벗어납니다. 상수를 레지스터에 준비하는 등의 명령어 조합이 필요합니다.'))
    if op in ALIASES:
        topics.append(concept('pseudo', '의사 명령어와 기계어',
            '의사 명령어는 어셈블러가 실제 명령어로 바꾸는 편의 표기입니다. 하나의 표기가 여러 기계어로 확장될 수도 있습니다.',
            'mv a0, a1은 addi a0, a1, 0으로 표현할 수 있습니다. li의 확장 개수는 상수 값에 따라 달라집니다.',
            '어셈블리 텍스트 줄 수를 실행 명령어 수로 써도 될까요?',
            '안 됩니다. 지시어·레이블·의사 명령어 확장이 있으므로 실제 기계어와 CORE의 완료 기록을 확인합니다.'))
    registers = set(explanation.get('reads', [])) | set(explanation.get('writes', []))
    if 'x2' in registers or any('(' in part and register(part.split('(')[-1].rstrip(')')) == 'x8' for part in parts):
        topics.append(concept('stack-abi', 'sp·s0의 역할은 호출 규약',
            '표준 ABI에서 sp(x2)는 스택 포인터이고 s0(x8)는 보존 레지스터입니다. 프레임 포인터를 사용하면 s0가 그 역할을 맡습니다. s0가 언제나 프레임 포인터인 것은 아닙니다.',
            'addi sp, sp, -16은 스택을 낮은 주소로 16바이트 확장하는 전형적인 패턴입니다. 복귀 전 sp를 복원합니다.',
            '-20(s0)만 보고 특정 C 변수의 저장 위치라고 확정할 수 있을까요?',
            '확정할 수 없습니다. 함수 문맥과 디버그 정보가 필요합니다. 표준 RV32I ABI의 스택 정렬은 16바이트입니다.', (ABI, CALLS)))
    elif registers & {'x1', 'x10', 'x11'}:
        topics.append(concept('argument-abi', '인자·반환값·복귀 주소를 구분합니다',
            '표준 정수 호출 규약은 a0~a7로 인자를 전달하고 a0·a1로 반환값을 전달합니다. ra는 반환할 값이 아니라 복귀할 코드 주소입니다.',
            'int add(int x, int y)의 단순한 호출에서 x·y는 a0·a1로 전달되고, int 결과는 a0로 돌아올 수 있습니다.',
            '함수 중간에 a0를 쓰면 언제나 C의 반환값일까요?',
            '아닙니다. 호출 전 인자나 중간 계산값으로도 사용됩니다. 호출·복귀 시점과 주변 명령어를 함께 봅니다.', (ABI, CALLS)))
    if 'x0' in explanation.get('reads', []) or (parts and register(parts[0]) == 'x0'):
        topics.append(concept('zero-register', 'x0는 항상 0인 레지스터',
            'zero와 x0는 같은 레지스터입니다. 읽으면 0이고 기록 결과는 버립니다. 하지만 목적지가 x0라는 이유로 명령어의 다른 동작까지 사라지는 것은 아닙니다.',
            'addi a0, zero, 7은 0 + 7로 상수를 만듭니다. lw zero, 0(a0)는 값을 보존하지 않아도 메모리에 접근합니다.',
            '잘못된 주소를 lw zero로 읽으면 메모리 오류를 피할 수 있을까요?',
            '아닙니다. x0로의 load도 메모리 접근 예외와 부수 효과를 수행해야 합니다.'))
    return topics
