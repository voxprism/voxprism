---
spec: SPEC-006
status: 구현됨
updated: 2026-11-18
---

# SPEC-006 설계

## 1. 접근

모든 운영 명령은 개발 PC의 `infra/` 스크립트로 실행합니다. 스크립트는 `secrets/`(키·SSH 키)와 `infra/state.env`(자원 번호)를 읽고, 둘 다 저장소에 올리지 않습니다. 배포 구성도는 [상세설계 3절](../../docs/02-상세설계.md#3-배포-구성-ncp).

| 자원 | 이름 | 설정 |
| --- | --- | --- |
| VPC / Subnet | ai-vpc / ai-public-subnet | 172.16.0.0/16, 172.16.3.0/24 (KR-2, Public), 1차시 자원 재사용 |
| ACG | whosaid-acg | in: TCP 22 관리자 IP/32, TCP 80 0.0.0.0/0, ICMP / out: TCP·UDP 1-65535, ICMP |
| Init Script | whosaid-init | 배포 공개키를 `/root/.ssh/authorized_keys`에 추가 |
| 서버 | whosaid-001 | KVM, Ubuntu 22.04, c8-g3(vCPU 8, 16GB), SSD 100GB(CB1), 시간 요금제 |
| 공인 IP | 자동 할당 | `state.env`의 `PUBLIC_IP` |

## 2. 바뀌는 곳

| 파일 | 역할 |
| --- | --- |
| `infra/ncloud.sh` | CLI 래퍼(내장 JRE) |
| `infra/create_infra.sh` | 자원 생성, `save`/`js` 도우미로 state.env 기록 |
| `infra/deploy.sh` | setup / code |
| `infra/server.sh` | status / stop / start / ssh |
| `infra/check_keys.sh` | 키 점검 |
| `infra/ncp_api.py` | HMAC v2 서명 호출(요금 조회) |
| `infra/state.env.example`, `infra/keys.env.example` | 저장소에 올리는 빈 틀 |
| `app/deploy/setup_server.sh` | 서버 설치 |
| `app/deploy/*.service`, `nginx-whosaid.conf` | systemd·nginx |

## 3. 비밀 값 흐름

```text
secrets/keys.env (PC, 600) ──grep 필요한 키만──▶ ssh stdin ──▶ /etc/whosaid.env (서버, root:whosaid 640) ──▶ systemd EnvironmentFile
secrets/keys.env ──(값 출력 없이)──▶ ~/.ncloud/configure (PC, 600) ──▶ ncloud CLI
```

## 4. 대안

| 대안 | 결정 | 이유 |
| --- | --- | --- |
| 콘솔에서 수동 생성 | 안 함 | 재현 불가, 기록 없음 |
| Terraform(ncloud provider) | 보류 | 과제 범위 대비 학습 비용. 자원이 늘면 검토 |
| Docker 배포 | 안 함 | 모델·torch 이미지가 커서 단일 서버에선 이득 적음 |

## 5. 확인

- `./infra/deploy.sh code` 출력의 `systemctl is-active` 3줄이 모두 `active`.
- `curl -s http://<PUBLIC_IP>/api/health` → `{"ok": true, …}`.
