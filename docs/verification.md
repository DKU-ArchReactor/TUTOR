# 로컬 검증 기록

검증일: 2026-11-12. 운영 배포 전의 기능 브랜치 검증입니다.

| 검사 | 결과 |
| --- | --- |
| TUTOR `python -m pytest -q` | 127 passed |
| `python scripts/check-contract.py` | proto·생성 코드·descriptor 일치 |
| `python scripts/run_demos.py` | 실제 BE/CORE 실행 → 로컬 gRPC 분석 20/20 통과 |
| BE 클라이언트 → 실제 로컬 TUTOR | Sample/Explain/Compile/Analyze 양쪽 모드/AI 문맥 투영 통과 |
| BE `DEBUG=false`, `CORE_SOURCE` 지정, `python -X utf8 -m pytest -q` | 241 passed, 8 skipped, 기존 설정 deprecation warning 1개 |
| FE `npm run build` | TypeScript·Vite 빌드 통과 |
| FE `node --test tests/*.test.mjs` | 8 passed |
| FE 변경 파일 ESLint | 통과 |

BE의 기본 테스트는 독립 계약 fixture를 사용해 TUTOR 구현을 BE에 설치하지 않습니다.
별도로 BE `scripts/verify-tutor-local.py --tutor-source ../TUTOR-grpc`를 실행하여 실제 해설 서버와의 통신도 확인했습니다.
이 검사와 20건 시연은 배포된 BE의 컴파일·CORE 실행을 사용하고, 새 해설은 로컬 gRPC 서버가 처리합니다.
API 토큰과 서명 URL은 파일이나 로그에 저장하지 않습니다.

시연 예제는 산술(-32), 조건 분기(111), 반복·break·continue(13), switch·함수(15),
부호 확장(254), 재귀(10), 배열·포인터(25), 정렬 오류, 사이클 제한, 0 나눗셈(-1/19)입니다.
각각 single/pipeline으로 실행했습니다. 정상 종료 예제의 최종 레지스터·메모리가 같고,
전체 PC 완료 횟수의 합계가 CORE 완료 명령어 수와 일치함을 확인했습니다.

BE 전체 검사 중 기존 채팅 취소 테스트의 5ms 고정 대기가 Windows에서 실패했습니다.
변경 전 origin/core에서도 재현했으며, 요청 진입 이벤트를 기다린 뒤 취소하도록 테스트만 수정했습니다.

## 남은 환경 검증

- BE에서 건너뛴 8개: PostgreSQL 마이그레이션·로컬 컴파일러가 필요한 검사. CORE gRPC 통합 9개는 실행했습니다.
- 로컬 Docker 엔진이 실행되지 않아 새 이미지 빌드·컨테이너 기동은 확인하지 못했습니다.
  기존 CI/CodeBuild에 Docker 빌드·read-only 컨테이너 smoke 검사가 있습니다.
- 새 기능 브랜치는 푸시하지 않아 이번 변경의 GitHub Actions는 아직 실행하지 않았습니다.
- 운영 TUTOR는 여전히 Sample 전용 버전입니다. 새 기능을 배포했다고 주장하지 않습니다.
- 실제 브라우저의 클릭·시각 검증과 배포된 FE→BE→TUTOR 전체 흐름은 반영 후 확인해야 합니다.
- ECS의 기존 0.25 vCPU/0.5 GiB 설정에서 분석 부하·메모리 여유·응답 시간은 배포 환경에서 검증해야 합니다.

성능·가용성을 검증한 기록은 아닙니다. 입력 제한과 실패 격리가 실제 운영 용량 측정을 대신하지 않습니다.
