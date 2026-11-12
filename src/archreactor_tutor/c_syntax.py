"""Conservative source hints with lexical comment/string context, not a C compiler."""
import re
from .models import RuleExplanation

TYPES = r"(?:(?:static|extern|register|auto|const|volatile|signed|unsigned|short|long)\s+)*(?:int|char|void|float|double|_Bool|bool|size_t|u?int(?:8|16|32|64)_t|struct\s+\w+|enum\s+\w+|union\s+\w+)(?:\s+(?:long|int|const|volatile))*"


def strip_comments(source: str) -> list[str]:
    """Keep positions/newlines and quoted text while erasing actual comments."""
    output = []
    i, block, quote = 0, False, None
    while i < len(source):
        char = source[i]
        pair = source[i:i + 2]
        if block:
            if pair == "*/":
                output.extend("  "); block = False; i += 2; continue
            output.append("\n" if char == "\n" else " ")
        elif quote:
            output.append(char)
            if char == "\\" and i + 1 < len(source):
                i += 1; output.append(source[i])
            elif char == quote:
                quote = None
        elif pair == "/*":
            output.extend("  "); block = True; i += 2; continue
        elif pair == "//":
            end = source.find("\n", i)
            if end == -1:
                output.extend(" " * (len(source) - i)); break
            output.extend(" " * (end - i)); i = end; continue
        else:
            output.append(char)
            if char in ('"', "'"):
                quote = char
        i += 1
    return "".join(output).splitlines()


def explain_c(raw: str, *, cleaned: str | None = None) -> RuleExplanation:
    line = raw.strip() if cleaned is None else cleaned.strip()
    line = re.sub(r"^(?:}\s*)+(?=(?:else|while)\b)", "", line)

    def out(category, title, summary, detail, notes=()):
        extra = list(notes)
        syntax = re.sub(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', '""', line)
        if '&&' in syntax or '||' in syntax:
            extra.append("&&와 ||는 왼쪽 조건으로 결과가 결정되면 오른쪽 표현식을 평가하지 않는 단락 평가를 합니다.")
        if '?' in syntax and ':' in syntax:
            extra.append("삼항 조건식은 조건에 따라 두 값 중 하나를 선택합니다. 구현이 반드시 분기 명령어라는 뜻은 아닙니다.")
        return RuleExplanation(kind="c", category=category, title=title, summary=summary,
            detail=' '.join([detail, *extra]), notes=extra)

    if not line:
        if raw.strip():
            return out("comment", "주석", "실행 문법이 없는 주석 구간입니다.", "전체 소스의 주석 문맥으로 판정했습니다. C 문자열 안의 // 또는 /*는 주석으로 지우지 않습니다.")
        return out("empty", "빈 줄", "실행할 구문이 없습니다.", "빈 줄 자체는 CPU 명령어를 만들지 않습니다.")
    if line.startswith(("//", "/*")):
        return out("comment", "주석", "개발자를 위한 설명입니다.", "한 줄만 받은 경우 여러 줄 주석의 끝을 확정할 수 없습니다.")
    if line.startswith("#"):
        directive = line[1:].lstrip().split(None, 1)[0] if line[1:].strip() else ""
        detail = {"include": "헤더의 선언·매크로를 전처리 입력에 포함합니다. 헤더 포함만으로 라이브러리 구현이 링크되는 것은 아닙니다.", "define": "매크로 치환 규칙을 정의합니다. 일반 변수 저장 명령어로 보지 않습니다.", "if": "컴파일할 소스 구간을 전처리 조건으로 선택합니다. 실행 중 CPU 분기와는 다릅니다.", "ifdef": "매크로 정의 여부에 따라 컴파일할 구간을 선택합니다.", "endif": "조건부 전처리 구간을 닫습니다."}.get(directive, "소스 전처리 구간을 지정합니다. 일반 CPU 명령어로 직접 실행하지 않습니다.")
        return out("preprocessor", "전처리기 지시문", f"#{directive} 지시문입니다.", detail)

    if re.match(r"^typedef\b", line):
        return out("typedef", "타입 별칭", "기존 타입에 사용할 새 이름을 선언합니다.", "타입 별칭 자체는 실행 중 값을 저장하는 변수가 아닙니다.")
    if re.match(r"^(struct|union|enum)\s+\w*\s*\{", line):
        return out("type_definition", "복합 타입 정의", "구조체·공용체·열거형의 구성을 선언합니다.", "필드 배치·크기·정렬은 타입과 ABI에 따릅니다. 이 줄만으로 메모리가 할당됐다고 단정하지 않습니다.")
    function = re.match(rf"^{TYPES}\s*\**\s*([A-Za-z_]\w*)\s*\([^;]*\)\s*([;{{]?)", line)
    if function:
        name = function[1]
        declaration = line.endswith(";")
        return out("function", "함수 선언" if declaration else "함수 정의/헤더", f"'{name}' 함수의 {'인터페이스를 선언' if declaration else '반환 타입과 매개변수를 정의'}합니다.", "정수 인자는 보통 a0~a7로 전달하고 정수 반환값은 보통 a0에 놓습니다. 실제 스택 프레임·ra 보존은 호출 구조·ABI·최적화에 따라 달라집니다. 생성된 명령어를 확인하세요.")
    if re.match(r"^return\b", line):
        expression = line[6:].split(";", 1)[0].strip()
        return out("return", "함수 반환", f"'{expression}'을 반환합니다." if expression else "값 없이 호출자로 복귀합니다.", "RV32 정수 반환값은 보통 a0를 사용합니다. main의 복귀는 프로그램 시작 코드로 돌아가는 것이며, 종료 ecall과 동일한 C 구문은 아닙니다. 함수 인라인·최적화에 따라 명령어가 달라질 수 있습니다.")
    patterns = [
        (r"^else\s+if\s*\(", "else_if", "추가 조건", "앞선 조건이 거짓인 경로에서 새 조건을 평가합니다."),
        (r"^if\s*\(", "if", "조건 분기", "조건이 0인지 아닌지에 따라 실행 경로를 선택합니다."),
        (r"^else\b", "else", "대체 경로", "연결된 if 조건이 거짓일 때 실행합니다."),
        (r"^for\s*\(", "for", "for 반복문", "초기화 후 조건 검사·본문·증감을 반복합니다. continue는 보통 증감 구간으로 이동합니다."),
        (r"^while\s*\(", "while", "while 반복문/종료 조건", "본문을 실행하기 전 조건을 검사합니다. do-while의 꼬리라면 본문 뒤 조건 검사입니다."),
        (r"^do\b", "do", "do-while 반복문", "본문을 먼저 실행한 뒤 꼬리의 조건을 검사하므로 최소 한 번 실행됩니다."),
        (r"^switch\s*\(", "switch", "다중 선택", "정수 표현식에 따라 case 또는 default 진입점을 선택합니다. break가 없으면 다음 구간으로 이어질 수 있습니다."),
        (r"^case\b", "case", "case 레이블", "switch 값과 일치할 때 선택할 진입점입니다. 이전 case에서 이어서 도달할 수도 있습니다."),
        (r"^default\s*:", "default", "기본 레이블", "일치하는 case가 없을 때 선택됩니다. 위치만으로 항상 마지막에 실행되는 것은 아닙니다."),
        (r"^break\s*;", "break", "반복/선택 종료", "가장 가까운 반복문 또는 switch를 빠져나갑니다."),
        (r"^continue\s*;", "continue", "다음 반복", "현재 반복의 남은 본문을 건너뜁니다. for는 증감 후 조건, while은 조건 검사로 이동합니다."),
        (r"^goto\b", "goto", "레이블 이동", "같은 함수 안의 지정 레이블로 이동합니다."),
    ]
    for pattern, category, title, summary in patterns:
        if re.match(pattern, line):
            return out(category, title, summary, "분기·비교·점프 등으로 구현될 수 있지만, 소스의 참/거짓 경로와 어셈블리 taken 값은 동일하지 않을 수 있습니다. 실제 실행 경로는 PC와 CORE 제어 이벤트를 연결해 확인합니다.")
    if re.match(r"^[A-Za-z_]\w*\s*:", line):
        return out("label", "C 레이블", "goto가 대상으로 삼을 수 있는 위치입니다.", "레이블 자체는 연산 명령어가 아닙니다.")

    declaration = re.match(rf"^{TYPES}\s+(.*)", line)
    if declaration:
        rest = declaration[1]
        name = re.search(r"([A-Za-z_]\w*)", rest)
        label = name[1] if name else "변수"
        category = "initialization" if re.search(r"=(?!=)", rest) else "declaration"
        array = "[" in rest
        pointer = rest.lstrip().startswith("*")
        title = "배열 선언" if array else ("포인터 선언" if pointer else ("변수 초기화" if category == "initialization" else "변수 선언"))
        return out(category, title, f"'{label}'의 타입과 {'초기값을 지정' if category == 'initialization' else '사용을 선언'}합니다.", "저장 위치는 레지스터·스택·정적 데이터 등일 수 있습니다. 초기화된 전역 값이 0이라고 무조건 BSS로 분류하지 않습니다. 포인터는 주소를 담고, 배열 선언은 원소들의 저장 공간을 표현합니다. 실제 크기와 배치는 ELF 메모리 영역과 명령어를 확인하세요.")

    if re.match(r"^(?:\+\+|--)", line) or re.search(r"(?:\+\+|--)\s*;", line):
        return out("increment", "증가/감소", "값을 1 증가 또는 감소시킵니다.", "전위와 후위는 표현식이 돌려주는 값이 다릅니다. 결과가 사용되는지에 따라 생성되는 명령어가 달라집니다.")
    syntax = re.sub(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', '""', line)
    if re.search(r"(?:\+=|-=|\*=|/=|%=|<<=|>>=|&=|\|=|\^=|(?<![=!<>])=(?!=))", syntax):
        return out("assignment", "대입/계산", "계산한 값을 왼쪽 대상에 반영합니다.", "왼쪽 대상은 변수·배열 원소·포인터 역참조일 수 있습니다. 모든 대입이 반드시 메모리 store를 만드는 것은 아닙니다. /와 %의 C 정의되지 않은 동작은 RV32M 하드웨어의 특수 결과와 구분해야 합니다.")
    call = re.match(r"^([A-Za-z_]\w*)\s*\(", line)
    if call:
        return out("call", "함수 호출", f"'{call[1]}' 함수를 호출합니다.", "a0~a7와 필요시 스택으로 인자를 전달할 수 있습니다. 인라인·꼬리 호출 최적화 때문에 call/ret이 없을 수도 있습니다.")
    if line in ("{", "}", "};"):
        return out("scope", "블록 경계", "블록 범위를 열거나 닫습니다.", "중괄호만으로 스택 할당·해제나 함수 복귀를 확정할 수 없습니다.")
    return out("statement", "문맥 확인 필요", "C 소스의 구문 일부입니다.", "이 해설은 보수적인 구문 힌트입니다. 여러 줄 선언·매크로 확장·여러 구문이 섞인 줄의 전체 의미를 C 파서처럼 확정하지 않습니다.")
