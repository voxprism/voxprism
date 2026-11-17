---
spec: SPEC-006
updated: 2026-11-18
---

# SPEC-006 작업

- [x] T-01 ncloud CLI 설치와 래퍼, 키 점검 스크립트 (FR-OPS-06, NFR-SEC-01)
  - 파일: infra/ncloud.sh, infra/check_keys.sh
- [x] T-02 ACG·Init Script·서버·공인 IP 생성 스크립트 (FR-OPS-01, NFR-SEC-02)
  - 파일: infra/create_infra.sh
- [x] T-03 서버 설치 스크립트 (FR-OPS-02)
  - 파일: app/deploy/setup_server.sh, *.service, nginx-whosaid.conf
- [x] T-04 배포 스크립트와 비밀 값 전달 (FR-OPS-03, FR-OPS-05)
  - 파일: infra/deploy.sh
- [x] T-05 서버 제어 스크립트 (FR-OPS-04, NFR-COST-01)
  - 파일: infra/server.sh
- [x] T-06 요금 조회 (NFR-COST-01)
  - 파일: infra/ncp_api.py
- [x] T-07 저장소용 빈 틀과 비밀 파일 제외 (NFR-SEC-01)
  - 파일: infra/state.env.example, infra/keys.env.example, .gitignore
