---
id: SPEC-006
title: 네이버 클라우드 인프라와 배포
status: 구현됨
owner: "@Movinggun-bit"
requirements: [FR-OPS-01, FR-OPS-02, FR-OPS-03, FR-OPS-04, FR-OPS-05, FR-OPS-06, NFR-SEC-01, NFR-SEC-02, NFR-COST-01, NFR-SOV-01]
updated: 2026-11-18
---

# SPEC-006 네이버 클라우드 인프라와 배포

## 1. 배경과 문제

수업 과제의 조건은 네이버 클라우드에서 서비스를 돌리는 것입니다. 콘솔에서 손으로 만들면 다시 만들 수 없고, 키를 화면·채팅에 노출하기 쉽습니다. 서버를 켜 두면 한 달 약 29만 원이 나갑니다.

## 2. 목표 / 하지 않는 것

- 목표: ncloud CLI 스크립트로 자원을 다시 만들 수 있게, 키는 파일로만 오가게, 명령 한 줄로 배포·정지·시작.
- 하지 않는 것: 오토스케일링, 로드밸런서, 컨테이너 오케스트레이션, Terraform.

## 3. 사용자 시나리오

1. 운영자가 `secrets/keys.env`에 키를 넣고 `./infra/check_keys.sh`로 '입력됨'만 확인한다.
2. `./infra/create_infra.sh <내 공인 IP>` → 약 3분 뒤 서버 RUN, `infra/state.env`에 자원 번호 기록.
3. `./infra/deploy.sh setup` → 약 10~15분 설치. 이후 코드 수정은 `./infra/deploy.sh code`.
4. 시연이 끝나면 `./infra/server.sh stop`.

## 4. 요구사항

| ID | 요구사항 |
| --- | --- |
| FR-OPS-01 | 스크립트로 ACG·Init Script·서버·공인 IP 생성, 이미 있으면 건너뜀 |
| FR-OPS-02 | 빈 서버 설치(setup) |
| FR-OPS-03 | 코드 배포(code) |
| FR-OPS-04 | 상태·정지·시작·SSH |
| FR-OPS-05 | 비밀 값 무출력 전달 |
| FR-OPS-06 | 키 존재 여부 점검 |
| NFR-SEC-01·02 | 비밀 값 관리, SSH 관리자 IP만 |
| NFR-COST-01 | 약 408원/시간, 미사용 시 정지 |
| NFR-SOV-01 | 국내 클라우드(KR 리전) |

## 5. 수용 시나리오

```gherkin
시나리오: 다시 실행해도 안전
  조건 ACG와 Init Script가 이미 state.env에 있다
  만일 create_infra.sh를 다시 실행하면
  그러면 이미 있는 자원은 건너뛰고 없는 것만 만든다

시나리오: 키를 화면에 내지 않음
  만일 deploy.sh code를 실행하면
  그러면 출력에는 단계 이름과 웹 주소만 있고 키 값은 없다
```

## 6. 영향과 위험

- NCP API 키는 계정 전체 권한 → 프로젝트가 끝나면 콘솔에서 사용 중지·삭제.
- SSH 규칙은 만들 때의 공인 IP 하나 → 장소가 바뀌면 ACG 규칙 수정 필요.
- IPv6가 꺼진 서버에서 nginx 설치 후처리가 실패하는 문제 → setup 스크립트가 우회.

## 개정 이력

| 날짜 | 내용 |
| --- | --- |
| 2026-11-18 | MVP 구현 기준으로 작성(백필) |
