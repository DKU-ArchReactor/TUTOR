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

STS 계정 확인, 소스 패키징, CodeBuild 테스트/컨테이너 스모크, digest 배포, ECS health 검증을 수행합니다. BE/CORE는 재배포하지 않습니다. GitHub Actions는 테스트용이며 자동 배포는 미연결입니다.
