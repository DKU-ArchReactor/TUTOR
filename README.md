# ArchReactor TUTOR

독립 ECS Fargate gRPC 서비스. 현재는 **연결 확인용 Sample RPC**이며 AI 모델 호출이나 실제 코드 해설은 없습니다.

## 요청 경로

브라우저 -> BE REST `POST /api/v1/tutor/sample` -> `archreactor.tutor.v1.Tutor/Sample`.

요청: `{"message":"Hello TUTOR"}`. 공백만 있는 입력 금지, 최대 256자/1024 UTF-8 bytes.
응답: `request_id`, `schema_version`, `tutor_version`, `message`, `reply`, `sample: true`.
샘플은 인증 없이 호출 가능하며 코드 실행, DB 접근, 모델 호출을 하지 않습니다.
실제 튜터 기능은 별도 RPC와 인증·소유권·사용량 정책을 설계하여 추가합니다.

## 로컬 실행

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
python scripts/check-contract.py
pytest -q
python -m service.server
# 다른 터미널
python scripts/smoke.py 127.0.0.1:50051
```

BE 설정: `TUTOR_GRPC_TARGET=127.0.0.1:50051`, `TUTOR_GRPC_TIMEOUT_SECONDS=5`.

```sh
curl -fsS "${BE_BASE_URL}/api/v1/tutor/sample" -H 'Content-Type: application/json' --data @examples/sample-request.json
```

## 계약 갱신

```sh
python -m grpc_tools.protoc -Iproto --python_out=. --grpc_python_out=. --descriptor_set_out=proto/contract.pb proto/tutor_contract/v1/tutor.proto
python scripts/check-contract.py
```

기존 필드 번호/의미를 재사용하거나 변경하지 않습니다. 파괴적 변경은 v2 RPC를 병행 제공합니다. BE에는 생성된 계약만 복사하며 TUTOR 구현을 가져오지 않습니다.

## 배포

계정·리전·프로파일 및 운영 자원 이름은 배포 설정에서 명시합니다. STS 계정이 설정한 계정과 다르면 작업을 중단합니다. 실제 운영 값은 커밋하지 않습니다.

- `infrastructure/build.json`: 전용 ECR, CodeBuild, 로그, 최소 권한 역할.
- `infrastructure/service.json`: Fargate 0.25 vCPU/0.5 GiB 1태스크, 별도 SG와 실행 역할.
- 기존 Cloud Map namespace ID/이름을 전달하며 `tutor.<NamespaceName>:50051`로 연결.
- 50051은 BE SG만 허용. 공인 IPv4는 이미지/로그의 외부 HTTPS 통신용. ALB/NAT 추가 없음.
- 내부 h2c gRPC이며 TLS/mTLS는 미구성. 단일 AZ/태스크이므로 고가용성 구성은 아님.
- 비root/read-only 컨테이너, gRPC health, 5초 graceful shutdown.
- 샘플 런타임은 AWS API 권한·비밀값 없음.

최초 구축: build 스택 생성 -> CodeBuild 이미지 빌드 -> ECR digest를 service 스택 Image에 지정. VpcId, SubnetId, BackendSecurityGroup, NamespaceId는 기존 환경에서 조회해 전달. CloudFormation change set을 검사한 후 실행합니다.

최초 구축 후 독립 배포/롤백:

```sh
pip install -r requirements-deploy.txt
mkdir -p dist
cp examples/deployment-config.example.json dist/deployment-config.local.json
# dist/deployment-config.local.json의 REPLACE_ME를 승인된 운영 값으로 설정
python scripts/deploy.py --config dist/deployment-config.local.json
python scripts/deploy.py --config dist/deployment-config.local.json --rollback sha256:<previous-digest>
```

STS 계정 확인, 소스 패키징, CodeBuild 테스트/컨테이너 스모크, digest 배포, ECS health 검증을 수행합니다. BE/CORE는 재배포하지 않습니다.


### GitHub Actions 자동 배포

배포 트리거는 **`develop` push/PR 머지**입니다. 테스트 통과 후 전용 CodeBuild에서
테스트·컨테이너 스모크·ECR push를 수행하고, 기존 서비스 스택의 Image만 digest로 변경합니다.
ECS health와 실제 image digest를 확인한 뒤 BE REST 응답의 `tutor_version`이 이번 빌드와 같은지 검증합니다.
배포는 순차 실행하며 진행 중인 배포를 취소하지 않습니다. PR과 다른 브랜치는 테스트만 실행합니다.

관리자가 최초 1회 `infrastructure/github-oidc.json`을 별도 CloudFormation 스택으로 배포합니다.
기존 GitHub OIDC provider와 TUTOR의 bucket, build project, ECR, service stack,
cluster/service/task family, execution role ARN을 매개변수로 전달합니다.
역할은 이 저장소의 조직·저장소 고유 ID가 포함된 immutable OIDC subject, `develop`, STS audience만 신뢰합니다.
이 저장소의 subject 형식은 `repo:DKU-ArchReactor@265494649/TUTOR@1451272949:ref:refs/heads/develop`입니다.
이름만 포함한 과거 형식으로 되돌리면 인증이 실패합니다. [GitHub OIDC 문서](https://docs.github.com/en/actions/reference/security/oidc#immutable-subject-claims)를 참고하세요. BE/CORE 배포 권한은 없습니다.

Repository Settings → Secrets and variables → Actions에 다음을 설정합니다.
실제 운영 값은 소스에 커밋하지 않습니다. 장기 AWS 키는 사용하지 않습니다.

| 이름 | 저장 위치 | 값 |
|---|---|---|
| `AWS_ROLE_ARN` | Secrets | OIDC 스택의 RoleArn 출력 |
| `AWS_REGION` | Variables | `ap-northeast-2` |
| `TUTOR_DEPLOYMENT_CONFIG` | Secrets | 예제 deployment-config JSON에서 `profile`을 제외한 실제 값 |
| `BE_BASE_URL` | Variables | BE 공개 HTTPS 기본 주소 |

운영 설정은 비밀번호가 아니지만 공개 로그 노출을 막기 위해 Secrets에 저장합니다. CI는 각 운영 식별자도 로그에서 마스킹합니다. 업로드하는 기록은 버전과 현재/이전 digest뿐이며,
계정·내부 이름이 담긴 설정과 원본 배포 기록은 artifact로 게시하지 않습니다.
로컬 실행은 계속 명시적인 AWS profile을 요구합니다.

`workflow_dispatch`도 정의되어 있습니다. GitHub의 수동 실행 버튼은 워크플로 파일이
기본 브랜치에도 있어야 나타납니다. 현재 기본 브랜치가 `main`이면 해당 파일을 `main`에도
반영한 후 **실행 대상 `develop`**을 선택하세요. 그 전에는 `develop` push 자동 배포와
기존 실행의 Re-run jobs를 사용할 수 있습니다. 기본 브랜치는 이 변경에서 바꾸지 않습니다.

수동 실행의 `rollback_digest`에 성공한 배포 기록의 이전 digest를 입력하면 재빌드 없이 복구합니다.
기본 브랜치 반영 전에도 로컬 `--rollback` 명령은 사용할 수 있습니다.
배포 실패 시 ECS circuit breaker/CloudFormation rollback 상태를 확인하세요.
배포 후 REST 검증만 실패한 경우에는 자동으로 되돌리지 않으므로 성공한 이전 digest로 복구합니다.

CloudFormation은 이미지 갱신 때도 기존 VPC/Subnet/SecurityGroup 형식의 매개변수를 검증하므로, 배포 역할에는 배포 리전에 한정한 세 가지 EC2 Describe 조회 권한이 포함됩니다. 네트워크 변경 권한은 부여하지 않습니다.
