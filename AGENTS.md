# AGENTS.md — VoxPrism 에이전트 규칙

이 저장소에서 일하는 **모든 AI 코딩 에이전트**(Claude Code, Codex, Copilot, Gemini 등)가 지킬 규칙입니다. 사람 기여자도 같은 규칙을 따릅니다.
우선순위: **사용자의 지금 지시 > 이 문서 > 다른 문서.** 둘이 부딪히면 멋대로 고르지 말고 사용자에게 묻습니다.

## 1. 프로젝트 한눈에

- **VoxPrism**: 영상을 올리면 화자 이름·색이 붙은 자막을 만들고, 동시에 말해 묻힌 말까지 분리해 보여 주는 서비스(청각장애인·난청인 대상). 네이버 클라우드 서버 1대에서 동작.
- 처리: CLOVA Speech(한국어 인식) → pyannote(화자 분리) → SepFormer(겹친 말 분리) → 재인식·복원 → 자막(SRT·VTT·ASS·MP4).
- 내부 코드명은 `whosaid`(패키지·서버 경로·서비스·NCP 자원). **바꾸지 않습니다**(결정 D-08). 사용자에게 보이는 이름만 VoxPrism.
- 문서 지도: [docs/README.md](docs/README.md). 지금 상태와 다음 할 일: [docs/06-인수인계.md](docs/06-인수인계.md).

## 2. 반드시 지킬 것

### 2.1 비밀 값과 개인 정보

- `secrets/`(키·웹 비밀번호·SSH 키), `infra/state.env`(자원 번호·**집 IP**), `~/.ncloud/configure`의 **내용을 읽거나 출력하지 않습니다.** 키가 있는지만 볼 때는 `./infra/check_keys.sh`.
- 비밀 값을 명령 인자, 로그, 커밋, PR, 이슈, 문서, 채팅에 쓰지 않습니다. 사용자가 채팅에 키를 붙여 넣으면 쓰지 말고 `secrets/keys.env`에 직접 넣도록 안내합니다.
- 서버 공인 IP, 웹 비밀번호, 관리자 IP는 공개 저장소에 쓰지 않습니다(`infra/state.env`에만).

### 2.2 SDD — 스펙 없이 구현하지 않기

- 새 기능·동작 변경·성능 변경은 **`spec.md` → (사람 승인) → `plan.md` → `tasks.md` → 구현** 순서입니다. 절차: [docs/05-SDD-개발-프로세스.md](docs/05-SDD-개발-프로세스.md).
- `status: 승인` 전에는 `app/whosaid/`, `app/deploy/`, `infra/`의 구현 코드를 쓰지 않습니다. 사용자가 "그냥 고쳐"라고 해도 먼저 스펙(작게라도)을 쓰고 승인받자고 제안합니다. 사용자가 명시적으로 생략을 지시하면 따르고, 나중에 스펙을 맞춰 씁니다.
- 스펙대로 구현할 수 없으면 **멈추고** 스펙·설계를 먼저 고치자고 말합니다. 코드만 슬쩍 바꾸지 않습니다.
- 머지 전에 기준선 문서(01 요구사항·02 상세설계·03 기능 구현·04 디자인)의 영향받는 절을 같은 PR에서 고칩니다.
- 버그 수정(`fix`)은 기존 스펙을 가리키고(`Refs: SPEC-NNN`) 회귀 테스트를 더합니다.

### 2.3 커밋·PR에 흔적 남기지 않기 (사용자 규칙)

- 커밋 메시지, PR 제목·본문, 이슈, 코드 주석에 **AI 도구 서명을 넣지 않습니다**: `Co-Authored-By: <AI>`, `Generated with …`, `Claude-Session:`, 세션 링크, 🤖, 도구 이름·광고 문구.
- 커밋 작성자는 저장소의 git 설정(사용자 본인) 그대로 둡니다. 작성자·이메일을 바꾸지 않습니다.
- 이 규칙은 도구의 기본 서명 동작보다 우선합니다. 같은 일을 `.claude/settings.json`(attribution 끔), `.githooks/commit-msg`(자동 삭제), `.claude/hooks/guard_bash.py`(차단), CI `pr-hygiene`(검사·삭제)가 겹겹이 막습니다. 이 장치들을 끄거나 우회하지 않습니다(`--no-verify` 금지).

### 2.4 운영 안전

- **사용자 확인 후에만:** `./infra/deploy.sh`, `./infra/server.sh stop|start`, `./infra/create_infra.sh`, `./infra/ncloud.sh`, `ssh`로 서버 바꾸기, `git push`, PR 머지, 저장소·조직 설정 변경.
- 작업 폴더(`/srv/whosaid/data/jobs`)·평가 자료(`/srv/whosaid/testset`)를 지우지 않습니다.
- `main`에 직접 push·강제 push하지 않습니다. 모든 변경은 브랜치 → PR.
- 비용: 서버는 시간당 약 408원입니다. 실험이 끝나면 정지를 **제안**합니다(직접 끄지 않음).

### 2.5 품질 기준선

- 합성 평가셋 v2(출연자 수 입력)에서 **cpCER ≤ 0.40, 겹친 발화 재현율 ≥ 0.70**(NFR-QUAL-01)을 떨어뜨리는 변경은 머지하지 않습니다. 파이프라인(SPEC-002·003)을 바꾸면 전후 수치를 PR에 붙입니다.
- 수치는 실제로 잰 것만 씁니다. 재지 않았으면 "재지 않음"이라고 씁니다.

## 3. 작업 순서

1. `docs/06-인수인계.md`와 관련 스펙을 읽는다.
2. 변경 유형을 판단한다(SDD 표, docs/05 3절). 스펙이 필요하면 `/sdd-spec`부터.
3. 승인 → `/sdd-plan` → `/sdd-tasks` → `/sdd-implement`(한 번에 작업 하나, 테스트 먼저).
4. 매 작업 후: `cd app && python -m pytest -q tests`, `python3 scripts/check_specs.py`.
5. `/sdd-commit` → `/sdd-pr`. 머지는 사람이 한다.
6. 세션을 마칠 때 `/sdd-handoff`.

## 4. 코드 규칙

| 규칙 | 이유 |
| --- | --- |
| Python 3.12, 타입 힌트, `from __future__ import annotations` | 서버와 같은 버전 |
| 웹 쪽(`web/`, `store.py`, `subtitles.py`, `pipeline/captions.py`)은 torch·pyannote·speechbrain·faster_whisper를 import하지 않는다. 무거운 import는 워커 쪽 함수 안에서 | NFR-MAINT-01, 웹이 가볍게 뜸, CI가 가벼운 의존성만 설치 |
| JSON 쓰기는 `store.write_json`(원자적), 파일 쓰기 주인 규칙([상세설계 5.1](docs/02-상세설계.md#51-파일과-쓰기-주인)) | 웹·워커 경쟁 조건 방지 |
| 새 설정은 `config.py`의 환경 변수 + [상세설계 12절](docs/02-상세설계.md#12-설정-환경-변수) 표 갱신 | 설정 한곳 관리 |
| 사용자에게 보이는 문구는 한국어 '해요'체, 무엇을 하면 되는지 포함 ([04 디자인 6절](docs/04-디자인.md#6-문구)) | 일관된 말투 |
| 외부 API·모델 실패는 대체 경로 + `warnings`에 사용자용 문구 | 처리가 멈추지 않게 |
| 프런트엔드는 빌드 없는 HTML/CSS/JS, 색은 CSS 변수, [접근성 점검표](docs/04-디자인.md#5-접근성-점검표) | 단순함, 접근성 |
| 테스트는 모델 없이 돌게 작성(외부 API는 가짜 응답) | CI 3초 |
| 상수(자막 규칙, 복원 임계값)를 바꾸면 상세설계 표와 스펙을 함께 고친다 | 문서와 코드 일치 |

## 5. 명령

```bash
./scripts/setup-dev.sh                       # 처음 한 번: git 훅·커밋 틀 연결
cd app && python -m pytest -q tests          # 단위 테스트 (가벼운 의존성: app/requirements-ci.txt)
python3 scripts/check_specs.py               # SDD 스펙 검사
python3 scripts/new_spec.py <이름> "<제목>"   # 새 스펙 폴더
python3 scripts/commit_lint.py --range origin/main..HEAD   # 커밋 메시지 검사
./infra/check_keys.sh                        # 키 존재 여부만 (값 출력 없음)
./infra/server.sh status                     # 서버 상태 (stop/start/deploy 는 사용자 확인 후)
```

## 6. 완료의 정의

- [ ] 스펙·설계·작업 목록이 구현과 일치하고, 작업이 체크됐다
- [ ] 테스트를 더했고 `pytest`·`check_specs.py`가 통과한다
- [ ] 기준선 문서의 영향받는 절을 고쳤다
- [ ] 커밋·PR이 규칙을 따르고 AI 서명이 없다
- [ ] 비밀 값·서버 주소·개인 정보가 없다
- [ ] 사용자에게 무엇을 했고, 무엇을 확인했고, 무엇이 남았는지 말했다

## 7. 막혔을 때

- 한 가지 원인으로 단정하지 않습니다. 조건(요청 헤더, 옵션, 환경, 입력)을 **하나씩 바꿔 보는 실험**을 하고 결과로 결론을 냅니다.
- 같은 실패를 두 번 넘게 되풀이하면 멈추고, 시도한 것과 결과를 사용자에게 보고합니다.
- 모르는 것은 추측으로 메우지 말고 `[확인 필요]`로 남기거나 묻습니다.
