# 튜터 시연 방법

시연 코드는 튜터가 무엇을 가르치는지 보여주는 작은 프로그램입니다. 시연 테스트는 예상 결과뿐 아니라 C–ASM 연결, 실제 실행 기록, 필요한 학습 개념이 제공되는지도 검사합니다.

로컬 FE에서 파일 내용을 C 편집기에 붙여 넣고 컴파일합니다. C 줄과 ASM 줄을 선택해 ‘이 명령어를 읽는 순서’를 보고, ‘관련 핵심 개념’을 펼칩니다. 스텝을 진행하면 실제 실행값을 볼 수 있습니다. 마지막에는 반환값 레지스터 a0(x10)를 확인합니다. 이 표의 반환값은 10진수입니다.


| 순서 | 코드 | 볼 부분 | 기대 결과 |
|---|---|---|---|
| 1 | [immediate_shift.c](immediate_shift.c) | `input << 2`, `& 15u`, `+ 5u` 줄. slli·andi·addi의 숫자와 입력·출력 레지스터 구분 | 13 → 52 → 4 → 반환 9 |
| 2 | [signed_load.c](signed_load.c) | lb·lbu. 0xFF를 음수/양수로 읽는 차이 | -1 + 255 = 반환 254 |
| 3 | [halfword_extension.c](halfword_extension.c) | lh·lhu. 16비트를 32비트로 채우는 방식 | -2 + 65534 = 반환 65532 |
| 4 | [function_arguments.c](function_arguments.c) | bump 호출과 복귀. a0는 인자·반환값, ra는 복귀 주소 | 7 + 5 = 반환 12 |
| 5 | [branches.c](branches.c) | if·else if·else의 비교 명령어와 실제 taken 이력 | 반환 111 |
| 6 | [loop_control.c](loop_control.c) | 반복문·continue·break로 실행 경로가 바뀌는 지점 | 반환 13 |
| 7 | [recursion.c](recursion.c) | 재귀 호출, 스택 확보·복원, 복귀 주소 보존 | 4 + 3 + 2 + 1 = 반환 10 |

single과 pipeline에서 같은 코드를 각각 확인합니다. 완료 시 최종 레지스터·메모리는 같아야 하지만, 파이프라인의 겹쳐 실행·대기·취소 때문에 클록 수는 다를 수 있습니다. 학습 예제의 숫자는 현재 실행값과 별개이며, 정확한 명령어 순서는 컴파일 설정에 따라 달라질 수 있습니다.

전체 자동 검증은 저장소 루트에서 `python scripts/run_demos.py`를 실행합니다. 18개 코드 × 두 엔진의 36건을 검사하며 보고서는 `artifacts/report.json`에 저장합니다. 정렬 오류·클록 제한 예제는 예상된 오류 상태에 도달하면 통과합니다.

일부 예제만 확인하려면 `python scripts/run_demos.py --case immediate_shift --case function_arguments`처럼 지정합니다. 선택 검사의 보고서는 `artifacts/report-selected.json`입니다. 중단되면 보고서의 `passed`는 false로 남고 완료된 검사까지 저장됩니다. 서버가 429를 반환하면 자동 재시도하지 않습니다.
