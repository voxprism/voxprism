# 보안 정책

## 알리는 방법

비밀 값 노출이나 취약점을 찾았다면 **공개 이슈를 만들지 말고** [비공개 보안 알림](https://github.com/voxprism/voxprism/security/advisories/new)으로 알려 주세요.

## 비밀 값 다루기

| 무엇 | 어디에 | 저장소 |
| --- | --- | --- |
| NCP API 키, CLOVA Speech 키, Hugging Face 토큰 | `secrets/keys.env` (권한 600) | 올리지 않음 (`.gitignore`) |
| 웹 비밀번호·세션 서명 키 | `secrets/web_login.txt` | 올리지 않음 |
| 서버 SSH 키 | `secrets/whosaid_ed25519` | 올리지 않음 |
| 자원 번호·서버 IP·관리자(집) IP | `infra/state.env` | 올리지 않음 |
| 서버 쪽 키 | `/etc/whosaid.env` (root:whosaid 640) | — |

막는 장치: `.gitignore` → `pre-commit` 훅(실제 키 값·집 IP가 들어갔는지 대조, 값은 출력하지 않음) → CI `secret-scan`(패턴) → GitHub 비밀 스캔·푸시 보호.

## 키가 새어 나갔다면

1. 바로 콘솔에서 해당 키를 **사용 중지·삭제**하고 새로 발급합니다(NCP 마이페이지 › 인증키 관리, CLOVA Speech 도메인 › Secret Key 재발급, Hugging Face Settings › Tokens).
2. `secrets/keys.env`를 새 값으로 바꾸고 `./infra/deploy.sh code`로 서버에 반영합니다.
3. 저장소 기록에 남았다면 기록에서 지우는 것만으로는 부족합니다. 키를 바꾸는 것이 먼저입니다.

## 알려진 제약

- 시연 서버는 HTTPS 없이 HTTP(80)로 열려 있습니다. 비밀번호는 시연 전용으로만 씁니다.
- SSH(22)는 관리자 공인 IP 하나에만 열려 있습니다.
- NCP API 키는 계정 전체 권한입니다. 프로젝트가 끝나면 삭제합니다.
