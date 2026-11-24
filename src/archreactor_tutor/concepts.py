"""Source-backed learning prompts; examples are never execution evidence."""
from .asm import ALIASES, IMMEDIATE_OPS, MULTIPLY_OPS, register

ISA = ('RISC-V 공식 RV32I 명세', 'https://docs.riscv.org/reference/isa/v20260120/unpriv/rv32.html')
ABI = ('RISC-V 공식 호출 규약', 'https://docs.riscv.org/reference/abi/v1.0/riscv-cc-procedure-calling-convention.html')
CALLS = ('Cornell CS 3410 · 함수 호출', 'https://www.cs.cornell.edu/courses/cs3410/2026sp/notes/asm-call.html')
M_EXT = ('RISC-V 공식 M 확장 명세', 'https://docs.riscv.org/reference/isa/v20260120/unpriv/m-st-ext.html')
C_STANDARD = ('C11 공개 초안 · 정수 연산 (§6.5, §6.5.5)', 'https://www.open-std.org/jtc1/sc22/wg14/www/docs/n1570.pdf')
DATA_TRANSFER = ('Berkeley CS61C · 메모리와 레지스터 사이의 데이터 이동', 'https://notes.cs61c.org/content/rv-data-transfer/')

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
            '계산할 데이터가 메모리에 있다면 먼저 레지스터로 읽습니다(load). 계산 결과를 메모리에 남기려면 다시 저장합니다(store). 괄호 밖 숫자는 기준 주소에서 이동할 거리이며, 단위는 바이트입니다.',
            'lw a0, 4(a1)에서 a1에 1000이 들어 있다면 1004번 위치를 찾습니다. 그 위치에 값 7이 4바이트로 저장되어 있다면 a0에 담기는 값은 1004가 아니라 7입니다.',
            'int가 4바이트인 배열에서 다음 원소로 이동하려면 주소를 얼마나 바꿀까요?',
            '4바이트입니다. 예를 들어 첫 원소의 주소가 1000이면 다음 원소는 1004에 있습니다.', (ISA, DATA_TRANSFER)))
        if op in ('lb', 'lbu', 'lh', 'lhu'):
            topics.append(concept('load-extension', '부호 확장과 0 확장',
                '메모리에서 1바이트나 2바이트만 읽어도 레지스터에는 4바이트 크기로 담습니다. lb·lh는 원래의 양수·음수 의미를 유지하도록 남는 왼쪽 자리를 채웁니다. lbu·lhu는 남는 자리를 0으로 채워 음수 없는 값으로 읽습니다.',
                '메모리의 한 바이트에 8개의 비트가 모두 1이라고 가정해 보세요. lb는 이를 음수 -1로 읽고, lbu는 음수 없이 읽어 255로 받아들입니다. 저장된 비트는 같고 읽는 규칙만 다릅니다.',
                '같은 바이트인데 결과가 다른 이유는 무엇일까요?',
                '원래의 8비트는 같습니다. 하지만 레지스터의 나머지 24비트를 lb는 원래 부호에 맞게, lbu는 0으로 채우므로 최종 숫자가 달라집니다.'))
    elif control.get('conditional') or op in ('slt', 'sltu', 'slti', 'sltiu'):
        topics.append(concept('signed-compare', '같은 비트도 비교 방식에 따라 달라집니다',
            '레지스터에는 0과 1만 저장됩니다. 그 비트를 음수가 될 수 있는 숫자로 읽을지, 0 이상의 숫자로 읽을지는 명령어가 정합니다.',
            '32개의 비트가 모두 1인 값을 생각해 보세요. 음수를 허용하면 -1이므로 1보다 작습니다. 음수 없이 읽으면 4294967295이므로 1보다 큽니다. 같은 비트라도 크기 비교가 달라질 수 있습니다.',
            'beq로 두 값이 같은지 비교할 때도 음수를 허용하는지 구분해야 할까요?',
            '필요하지 않습니다. 같은 비트열인지 비교하므로 부호 해석에 따라 같음의 결과가 바뀌지 않습니다.'))
        if control.get('conditional'):
            topics.append(concept('branch-pc', '분기 기준은 현재 명령어의 PC',
                '분기는 조건에 따라 실행할 위치를 바꾸는 동작입니다. 숫자로 적힌 이동 거리는 현재 명령어가 놓인 주소에 더합니다. 조건이 맞지 않으면 바로 다음 명령어로 갑니다.',
                'beq a0, a1, 8이 1000번 주소에 있다고 가정해 보세요. a0와 a1의 값이 같으면 8바이트 뒤인 1008번으로, 다르면 바로 다음 명령어가 있는 1004번으로 갑니다.',
                '어셈블리에서 분기했다는 사실만으로 C의 if 조건도 참이었다고 할 수 있을까요?',
                '아닙니다. 컴파일러가 반대 조건으로 건너뛰게 만들 수 있으므로 실제 명령어와 C 매핑을 함께 봐야 합니다.'))
    elif op in ('jal', 'jalr', 'ret', 'call', 'tail', 'jr', 'j'):
        topics.append(concept('call-return', '점프와 함수 호출의 차이',
            '다른 위치로 이동한 뒤 돌아오려면 돌아올 주소도 기억해야 합니다. jal·jalr는 그 주소를 레지스터에 넣을 수 있습니다. 결과를 넣는 곳이 x0이면 돌아올 주소를 저장하지 않고 이동만 합니다.',
            'jal ra, target이 1000번 주소에 있다면 ra에 다음 명령어의 주소인 1004를 넣고 target으로 이동합니다. 나중에 ret으로 돌아오면 ra에 기억해 둔 위치에서 실행을 이어갑니다.',
            '함수 안에서 다른 함수를 호출하면 기존 ra는 어떻게 보존할까요?',
            '중첩 호출이 ra를 덮어쓸 수 있어, 필요한 기존 복귀 주소를 보통 스택에 저장했다가 복원합니다.', (ISA, CALLS)))
    elif op in ('sll', 'slli'):
        topics.append(concept('shift-left', '왼쪽 시프트와 원소 주소 계산',
            '비트를 왼쪽으로 한 칸 옮기면 2배, 두 칸 옮기면 4배가 됩니다. 다만 32비트 밖으로 넘친 부분은 버립니다. 배열에서 원소 하나가 4바이트라면 몇 바이트 이동할지 계산할 때 쓸 수 있습니다.',
            'slli a0, a1, 2에서 a1에 3이 있다고 가정해 보세요. 두 칸 왼쪽으로 옮긴 값은 3의 4배인 12이고, 이 결과를 a0에 넣습니다. 4바이트 원소 3개만큼의 거리는 12바이트입니다.',
            '왼쪽 시프트가 언제나 원래 수의 정확한 곱셈 결과를 보존할까요?',
            '아닙니다. 32비트 밖으로 나가는 비트는 버려집니다. C에서는 피연산자 타입과 시프트 크기 등도 확인해야 합니다.', (ISA, C_STANDARD)))
    elif op in ('srl', 'sra', 'srli', 'srai'):
        topics.append(concept('shift', '오른쪽 시프트의 빈자리는 무엇으로 채울까요?',
            '비트를 오른쪽으로 옮기면 왼쪽에 빈자리가 생깁니다. 논리 이동은 그곳을 0으로 채우고, 산술 이동은 원래 맨 왼쪽 비트로 채워 양수·음수의 구분을 유지합니다.',
            '-8을 한 칸 오른쪽으로 옮긴다고 가정해 보세요. srai는 음수라는 의미를 유지해 -4가 됩니다. srli는 왼쪽 빈자리를 0으로 채우므로 같은 비트에서 시작해도 2147483644라는 양수가 됩니다.',
            'sra로 음수를 오른쪽 이동하면 C의 음수 나눗셈과 항상 같을까요?',
            '아닙니다. 예를 들어 -3의 1비트 산술 시프트는 -2지만, C 정수 나눗셈 -3 / 2는 0 방향 절삭으로 -1입니다.', (ISA, C_STANDARD)))
    elif op in MULTIPLY_OPS:
        topics.append(concept('m-extension', '곱셈·나눗셈은 M 확장',
            'M 확장은 기본 명령어에 정수 곱셈·나눗셈을 추가한 것입니다. mul은 긴 곱셈 결과의 오른쪽 32비트를, mulh 계열은 왼쪽 32비트를 레지스터에 넣습니다.',
            '-7을 3으로 나누면 div는 몫 -2를, rem은 나머지 -1을 구합니다. 몫의 소수 부분은 0에 가까운 쪽으로 버립니다. 이름 끝에 u가 붙은 divu·remu는 입력을 음수 없이 읽습니다.',
            'RISC-V div의 0 나누기 규칙을 C의 0 나누기에도 적용해도 될까요?',
            '안 됩니다. CPU 명령어에는 0으로 나눴을 때의 결과 규칙이 있지만, C에서 정수를 0으로 나누는 코드는 정상적인 결과를 보장하지 않습니다. C에서는 정의되지 않은 동작으로 다룹니다.', (M_EXT, C_STANDARD)))
    elif op in ('add', 'sub', 'addi'):
        topics.append(concept('word-result', '32비트 결과와 C의 정수 규칙',
            '이 시뮬레이터의 레지스터는 숫자를 32개의 비트로 저장합니다. 덧셈 결과가 이 공간보다 길면 오른쪽 32비트만 남고 넘친 왼쪽 부분은 버려집니다. C의 int 계산에도 항상 같은 규칙을 적용할 수 있는 것은 아닙니다.',
            '32비트를 음수 없이 읽을 때 가장 큰 수는 4294967295입니다. 여기에 1을 더한 수학적 결과는 4294967296이지만, 저장 공간을 넘어간 왼쪽 비트가 버려져 레지스터에는 0이 남습니다.',
            'C의 int 최댓값에 1을 더하는 동작도 항상 순환한다고 가정할 수 있을까요?',
            '아닙니다. C에서 int가 표현할 수 있는 범위를 넘는 계산은 특정 결과를 보장하지 않습니다. 이를 정의되지 않은 동작이라고 하며, 컴파일러가 다르게 처리할 수 있습니다. CPU의 비트 계산 규칙과 구분해야 합니다.', (ISA, C_STANDARD)))
    elif op in ('and', 'or', 'xor', 'andi', 'ori', 'xori'):
        topics.append(concept('bitwise', '비트 연산과 마스크',
            'AND는 두 비트가 모두 1일 때, OR는 하나라도 1일 때, XOR는 두 비트가 다를 때 1입니다. AND 마스크는 원하는 비트만 남기는 데 쓰입니다.',
            'AND가 어떻게 동작하는지 13과 7로 살펴보세요. 두 수를 각각 0과 1로 펼쳐 같은 자리에서 둘 다 1인 부분만 남기면, 결과는 5가 됩니다.',
            'C의 &와 &&는 같은 연산일까요?',
            '아닙니다. &는 각 비트를 계산하고, &&는 조건의 참·거짓을 계산하며 왼쪽이 거짓이면 오른쪽을 평가하지 않습니다.', (ISA, C_STANDARD)))
    elif op in ('lui', 'auipc'):
        topics.append(concept('upper-immediate', '큰 상수와 PC 기준 주소 만들기',
            'lui와 auipc는 명령어에 적힌 숫자에 4096을 곱해서 값을 준비합니다. lui는 그 값을 그대로 저장하고, auipc는 현재 명령어가 놓인 주소에 더해 저장합니다.',
            'lui a0, 1은 a0에 4096을 넣습니다. auipc a0, 1은 현재 명령어의 주소가 1024라고 가정하면, 여기에 4096을 더한 5120을 a0에 넣습니다.',
            'lui만 보고 그 값이 반드시 전역 변수의 주소라고 할 수 있을까요?',
            '아닙니다. 큰 정수 상수일 수도 있습니다. 후속 명령어와 심볼·디버그 정보를 확인해야 합니다.'))
    if op in IMMEDIATE_OPS and op not in ('slli', 'srli', 'srai'):
        topics.append(concept('immediate', '즉치값은 명령어 안의 상수',
            'addi 같은 명령어에서는 계산할 숫자를 명령어 안에 직접 적을 수 있습니다. 이 숫자를 즉치값이라고 부릅니다. 숫자를 적을 공간이 12비트이므로 -2048부터 2047까지만 한 명령어에 담을 수 있습니다.',
            'addi a0, a1, 5\n두 번째 항목인 a1에 7이 들어 있다고 가정해 보세요. 여기에 세 번째 항목인 숫자 5를 더한 결과 12를 맨 앞의 a0에 넣습니다. 여기서 5는 레지스터 이름이 아니라 직접 적힌 숫자입니다.',
            'addi a0, a1, 5000을 단일 I형 명령어로 표현할 수 있을까요?',
            '5000은 -2048~2047 범위를 벗어납니다. 상수를 레지스터에 준비하는 등의 명령어 조합이 필요합니다.'))
    if op in ALIASES:
        topics.append(concept('pseudo', '의사 명령어와 기계어',
            '의사 명령어는 자주 쓰는 동작을 짧게 적는 이름입니다. 어셈블리 코드를 변환하는 도구가 이를 CPU가 실행할 한 개 또는 여러 개의 명령어로 바꿉니다.',
            'mv a0, a1은 a1의 값을 a0에 복사하라는 뜻입니다. CPU는 a1에 0을 더해 a0에 넣는 addi a0, a1, 0으로 같은 일을 할 수 있습니다.',
            '어셈블리 텍스트 줄 수를 실행 명령어 수로 써도 될까요?',
            '안 됩니다. 어떤 줄은 이름표나 작성 도구에 주는 지시일 뿐이고, 어떤 줄은 여러 명령어로 바뀝니다. 실제로 실행한 명령어 수를 확인해야 합니다.'))
    registers = set(explanation.get('reads', [])) | set(explanation.get('writes', []))
    if 'x2' in registers or any('(' in part and register(part.split('(')[-1].rstrip(')')) == 'x8' for part in parts):
        topics.append(concept('stack-abi', 'sp와 s0는 어떤 역할을 할까요?',
            '함수들이 함께 동작하려면 레지스터를 사용하는 약속이 필요합니다. 이 약속에서 sp는 함수가 값을 잠시 보관하는 메모리 공간인 스택의 위치를 가리킵니다. s0는 함수 안에서 기준 주소로 쓰이기도 하지만, 항상 그런 역할인 것은 아닙니다.',
            'addi sp, sp, -16에서는 두 번째 sp에서 읽은 주소를 16 줄인 뒤 첫 번째 sp에 넣습니다. 함수가 값을 잠시 저장할 자리를 확보할 때 자주 쓰며, 함수를 끝내기 전 원래 주소로 되돌립니다.',
            '-20(s0)만 보고 특정 C 변수의 저장 위치라고 확정할 수 있을까요?',
            '확정할 수 없습니다. 앞뒤 코드와 C 변수의 위치를 연결한 정보가 있어야 합니다. 함수끼리 값을 주고받는 표준 약속에서는 스택 주소를 16의 배수로 맞추도록 정하고 있습니다.', (ABI, CALLS)))
    elif registers & {'x1', 'x10', 'x11'}:
        topics.append(concept('argument-abi', '인자·반환값·복귀 주소를 구분합니다',
            '함수에 건네는 정수 입력값은 보통 a0부터 a7에 담습니다. 함수가 계산한 결과는 크기에 따라 a0 또는 a0와 a1에 담아 돌려줍니다. ra는 계산 결과가 아니라 함수가 끝난 뒤 돌아갈 명령어의 주소입니다.',
            'int add(int x, int y)의 단순한 호출에서 x·y는 a0·a1로 전달되고, int 결과는 a0로 돌아올 수 있습니다.',
            '함수 중간에 a0를 쓰면 언제나 C의 반환값일까요?',
            '아닙니다. 호출 전 인자나 중간 계산값으로도 사용됩니다. 호출·복귀 시점과 주변 명령어를 함께 봅니다.', (ABI, CALLS)))
    if 'x0' in explanation.get('reads', []) or (parts and register(parts[0]) == 'x0'):
        topics.append(concept('zero-register', 'x0는 항상 0인 레지스터',
            'zero와 x0는 같은 레지스터입니다. 읽으면 0이고 기록 결과는 버립니다. 하지만 목적지가 x0라는 이유로 명령어의 다른 동작까지 사라지는 것은 아닙니다.',
            'addi a0, zero, 7은 0 + 7로 상수를 만듭니다. lw zero, 0(a0)는 값을 보존하지 않아도 메모리에 접근합니다.',
            '잘못된 주소를 lw zero로 읽으면 메모리 오류를 피할 수 있을까요?',
            '아닙니다. 읽은 값을 버리더라도 메모리를 읽는 동작은 실제로 수행합니다. 따라서 잘못된 주소를 읽으면 오류가 날 수 있습니다.'))
    return topics
