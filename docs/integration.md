# 해설 gRPC 연결

기준: TUTOR `develop` 99801bc, BE `core` 4f09fc8, FE `develop` edd0770 (2026-11-12 조회).
기존 ECS 자동배포·OIDC·Cloud Map·포트 50051·gRPC health·Sample RPC는 유지합니다.
이 브랜치를 병합하면 기존 develop 자동배포가 실행되므로 리뷰 전에는 병합하지 않습니다.

## 요청 경로

```text
FE → BE REST → TUTOR gRPC (해설·매핑)
            → CORE gRPC (CPU 실행)
```

| BE 동작 | TUTOR RPC | 응답 |
| --- | --- | --- |
| `/api/v1/tutor/sample` | Sample | 기존 연결 확인 응답 |
| `/api/v1/tutor/explain` | Explain | 최대 128개 C/ASM/문맥 해설 |
| RV32IM 컴파일 성공 | Compile | 줄별 구문 해설·소스 hash |
| 시뮬레이션 성공/오류/제한 결과 | Analyze | PC 매핑·완료 횟수·이벤트·실제 값 변화 |

세 가지 새 RPC의 응답은 request_id, schema_version 1.0, tutor_version, result_json입니다.
result_json은 기존 FE tutor schema 1.0을 유지하면서 상세 필드를 추가합니다.
기존 Sample 메시지와 필드 번호는 변경하지 않았습니다.

Analyze에는 내부 CORE result JSON, 선택적 C 소스·사용자 파일명, ELF bytes를 전달합니다.
검증된 ELF의 DWARF 파일·줄·열과 함수 심볼로 대응을 보완하며, 결과 fingerprint와 ELF가 다르면 거절합니다.
전체 정적 명령어를 유지하고 실행되지 않은 분기와 반복 PC의 완료 횟수를 구별합니다.
소스 위치가 없다는 사실만으로 CRT라고 단정하지 않습니다.
CORE의 U형 명령어 표시가 이미 이동된 즉치값인 경우 기계어를 기준으로 연산 의미를 설명합니다.

## 범위·실패 처리

- 수신 최대 16 MiB, 응답 최대 32 MiB, ELF 최대 256 KiB, history 최대 2,000클록.
- C 소스 최대 65,536자. Explain은 항목당 최대 4,096자.
- 잘못된 입력: INVALID_ARGUMENT. 메시지 초과: RESOURCE_EXHAUSTED.
- BE는 요청 ID·schema·응답 모양을 검증하고 기존 TUTOR_GRPC_TIMEOUT_SECONDS를 사용합니다.
- TUTOR 미설정·장애·이전 Sample 전용 버전에서는 빌드·실행의 tutor가 null이며 CORE result는 유지합니다.
- 해설 전용 REST 요청은 실패를 422/429/503/504/502로 전달합니다. 제출 소스나 내부 오류 상세는 노출하지 않습니다.
- AI 실행 문맥은 허용된 필드만 TUTOR에 보내고, 파일 정보·부분 이력의 완료 카운터는 저장하지 않습니다.
  해설 불가 시에도 실행 문맥은 저장하고 tutor.available=false로 구별합니다.

정적 해설은 완전한 C 파서·변수 저장 위치 분석이 아닙니다. 문법 의미와 실제 관찰 값을 구분합니다.
내부 서비스로 유지하며 FE가 gRPC나 ELF를 직접 다루지 않습니다. DB와 외부 LLM은 사용하지 않습니다.

## 함께 준비한 로컬 브랜치

- TUTOR: `feat/contextual-tutor-grpc`, 최신 develop 기준.
- BE: `feat/tutor-grpc-analysis`, 최신 core 기준. 기존 TUTOR_GRPC_TARGET 설정 사용. HTTP 서버 추가 불필요.
- FE: `feat/tutor-grpc-ui`, 최신 develop 기준. PR #18 API 전환을 재사용하고 새 헤더·단일 사이클 UI는 유지.

이전 로컬 HTTP 브랜치 `feat/contextual-tutor`, `feat/tutor-service-client`, `feat/tutor-service-ui`를 그대로 병합하지 않습니다.
기존 열린 FE PR #18은 변경하거나 닫지 않았습니다. FE 담당자가 중복분을 정리해야 합니다.

## 검토·적용 순서

1. TUTOR 기능 브랜치를 develop 대상 PR로 리뷰한 뒤 병합·자동배포합니다.
2. BE 기능 브랜치를 팀 통합 브랜치 core 대상으로 리뷰·반영합니다. 새 생성 계약만 복사하며 TUTOR 구현은 설치하지 않습니다.
3. FE 담당자와 중복 PR을 정리하고 develop 대상 표시 변경을 반영합니다.
4. 실제 개발 FE에서 C 줄 선택·두 엔진 재생·분기·메모리 변화·TUTOR 장애 처리를 확인합니다.

현재는 PR 생성·기능 브랜치 푸시·병합·AWS 변경을 수행하지 않았습니다.
로컬 검증 범위와 미검증 항목은 [verification.md](verification.md)를 확인하세요.
