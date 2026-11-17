---
spec: SPEC-007
status: 구현됨
updated: 2026-11-18
---

# SPEC-007 설계

## 1. 평가셋 생성 (`app/tools/make_test_set.py`)

- 입력: Zeroth-Korean test parquet(`speaker_id`, `audio`, `text`; CC BY 4.0).
- 화자 N명(기본 3)을 고르고 턴 12개를 이어 붙임. 턴의 약 45%는 앞사람이 끝나기 0.8~2.2초 전에 끼어듦.
- 긴 발화 3곳(`--interjections`)에 다른 화자의 짧은 말을 통째로 겹침(맞장구).
- 같은 화자의 말은 서로 겹치지 않게(`free()` 검사), 겹침 정답(`overlapped_by`)에서 같은 화자는 제외.
- 출력: `<이름>.wav`, `<이름>.mp4`(말하는 화자 칸을 색으로 강조), `<이름>.truth.json`(발화별 화자·시각·글자·겹침 상대).

## 2. 지표 계산 (`app/tools/evaluate.py`)

- 글자 비교는 공백·문장부호를 뺀 글자열의 편집 거리.
- cpCER: 화자별 정답·결과 텍스트를 이어 붙이고, 화자 짝 순열 중 오류가 가장 작은 것을 고름.
- 발화 재현율: 정답 발화가 짝지어진 결과 화자 텍스트 안에 있는 정도(부분 문자열 편집 거리 기반).
- `--baseline-asr`: `asr.json`의 단어를 한 화자로 보고 같은 지표 계산(일반 자막 기준선).

## 3. 묶음·진단

- `eval_runs.py runs.json [--out]`: `{조건, 결과 파일}` 목록 → 조건별 평균 표. 결과가 없으면 `testset/jobs_archive`에서 찾음.
- `inspect_job.py`: 정답 발화와 결과 이벤트를 시간순으로 나란히 출력.

## 4. 운영

- 평가 자료는 서버 `/srv/whosaid/testset/`에 있고(저장소에는 결과 JSON만), 실행은 서버 venv에서 합니다. 명령은 [06 인수인계](../../docs/06-인수인계.md#5-평가-다시-돌리기).
