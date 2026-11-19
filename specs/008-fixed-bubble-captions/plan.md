---
spec: SPEC-008
status: 구현됨
updated: 2026-11-19
---

# SPEC-008 설계

## 1. 접근

자막 영역을 **줄(lane) N개 + 화자 표시줄(rail)** 로 고정합니다. N은 그 영상에서 동시에 뜨는 대화 자막의 최대 개수입니다.
줄 배정은 재생 중에 계산하지 않고 불러올 때 한 번 정합니다(시작 순서대로 비어 있는 가장 아래 줄, 끝날 때까지 유지).
그래서 앞뒤로 이동해도 같은 자막은 늘 같은 줄에 뜹니다. 웹(`job.js`)과 MP4(`captions.py`)가 같은 규칙을 씁니다.

화자 표시줄에는 화자 칩을 고정 순서(S1, S2, …, 합친 화자는 한 칩)로 고르게 놓습니다. 말하는 동안 칩을 화자 색으로 채우고
빛나게 합니다. 말풍선 꼬리는 그 칩의 x 위치(말풍선 폭 안으로 제한)에 붙고, 꼬리 끝에서 칩까지 같은 색 선을 긋습니다.
선은 말풍선보다 아래 층에 그려서 아래 줄 말풍선을 가리지 않습니다.

## 2. 바뀌는 곳

| 영역 | 파일·함수 | 변경 |
| --- | --- | --- |
| 화면 | `web/static/job.html` | `#capstage`(svg 선 + `#cap-bottom` 줄들 + `#rail`), '말하는 사람 표시' 체크 |
| 화면 | `web/static/job.js` | `assignLanes`, `renderStage`, `layoutLinks`(꼬리 위치·선), `fitStage`(작은 화면에서 빈 줄 접기), 위치 '위' = `.flip` |
| 화면 | `web/static/app.css` | `.capstage .lanes .lane .cap::after .rail .chip(.on) .links`, `prefers-reduced-motion` |
| MP4 | `pipeline/captions.py` | `assign_lanes`, `_Measure`(libass 글자 크기 기준 폭), `_fit_lines`, `to_ass_burn` |
| MP4 | `subtitles.write_burn` → `subs/burn.ass`, `run.render`가 이 파일로 굽기 |

## 3. 데이터·API 변경

- `result.json`·API 변화 없음. 줄 배정은 `events`(id·start·end·speaker)로 계산합니다.
- 작업 폴더에 `subs/burn.ass`가 생깁니다(렌더할 때마다 새로 씀). 내려받는 `subs/whosaid.ass`는 그대로.
- 하위 호환: 이미 처리된 작업도 화면을 새로 열면 바로 새 모양. 예전에 만든 `burned.mp4`는 다시 만들어야 새 모양.

## 4. 대안

| 대안 | 장점 | 단점 | 결정 |
| --- | --- | --- | --- |
| 지금처럼 가운데에 쌓기 | 단순 | 줄이 생기고 사라질 때 다른 줄이 밀림 | 버림 |
| 화자마다 칩 위에 말풍선(화자별 열) | 꼬리가 짧고 곧음 | 자막 위치가 화자마다 달라짐(요청은 고정 위치), 열이 좁아 긴 말이 여러 줄 | 버림 |
| 영상 속 얼굴 위에 말풍선 | 가장 직관적 | 얼굴 검출 + 말하는 얼굴 판별 필요, 자막 위치가 움직임 | 별도 검토(spec 7절) |
| 줄 고정 + 표시줄 + 꼬리·선 | 위치 고정, 색·꼬리로 화자 구분 | 위 줄 선이 아래 말풍선 뒤로 지나감 | **채택** |
| MP4: 말풍선 상자를 libass BorderStyle 3로 | 폭을 잴 필요 없음 | 글자마다 상자라 테두리가 들쭉날쭉, 둥근 모서리 불가 | 버림 → 폭을 재서 둥근 도형으로 그림 |

## 5. 테스트·평가 계획

- 단위 테스트: `test_assign_lanes_fixed_position`, `test_fit_lines_by_measured_width`, `test_burn_ass_rail_bubbles_and_tails`.
- 평가(NFR-QUAL-01): 파이프라인(인식·화자·복원)은 바꾸지 않으므로 다시 돌리지 않음.
- 화면 확인: 예시 ③(4인, 동시 3명 구간 18.8초)에서 PC 폭·휴대폰 폭(400px)·위치 '위'·글자 '크게', MP4 가로(1280×720)·세로(720×1280) 프레임.

## 6. 배포·되돌리기

- 배포: `./infra/deploy.sh code`
- 되돌리기: 이 PR의 squash 커밋을 revert 후 다시 배포. 데이터 변경이 없어 되돌려도 안전.

## 7. 위험

- 동시 화자가 많은 영상(줄 4개 이상)은 자막 영역이 높아짐 → 작은 화면에서는 빈 줄을 접음.
- MP4 글자 폭은 폰트(Noto Sans CJK KR Bold)로 재고, 폰트가 없으면 어림값을 씀 → 꼬리 위치가 조금 어긋날 수 있음.
