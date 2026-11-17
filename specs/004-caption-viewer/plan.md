---
spec: SPEC-004
status: 구현됨
updated: 2026-11-18
---

# SPEC-004 설계

## 1. 접근

결과(`result.json`)는 바꾸지 않고, 사용자 편집은 `speakers.json`에 따로 둡니다. 화면·파일을 만들 때마다 `captions.resolve_speakers`로 둘을 합칩니다. 자막 오버레이는 비디오 위 절대 위치 상자 두 개(`#cap-bottom`, `#cap-top`)에 `requestAnimationFrame`으로 현재 시각의 이벤트를 그립니다(바뀔 때만 DOM 갱신). 디자인 규칙은 [04 디자인 3절](../../docs/04-디자인.md#3-자막-디자인).

## 2. 바뀌는 곳

| 영역 | 파일·함수 |
| --- | --- |
| 미리보기·번인 | `pipeline/media.py` `make_preview`, `burn_in`; `pipeline/run.py` `render` |
| 편집 API | `web/main.py` `edit_speakers`, `request_render`, `download`, `get_job` |
| 병합·파일 | `pipeline/captions.py` `resolve_speakers`, `to_srt`, `to_vtt`, `to_ass`; `subtitles.py` |
| 화면 | `web/static/job.html`, `job.js`, `app.css`(`.cap`, `.capbox`, `.line .flag`) |
| 미디어 전송 | `deploy/nginx-whosaid.conf` `/media/` (SPEC-005와 공유) |

## 3. 데이터·API

- `speakers.json`: `{"S3": {"name": null, "merge_into": "S1"}}`.
- `POST /api/jobs/{id}/speakers`, `POST /api/jobs/{id}/render`, `GET /api/jobs/{id}/download/{kind}` ([상세설계 10절](../../docs/02-상세설계.md#10-api)).
- 렌더 상태: `render.request`(대기) → `render.json`(running·done·error) → `burned.mp4`.

## 4. 대안

| 대안 | 결정 | 이유 |
| --- | --- | --- |
| 브라우저 기본 `<track>` 자막 | 안 함 | 화자 색·동시 두 줄·이름표를 마음대로 그릴 수 없음 |
| 편집 내용을 result.json에 덮어쓰기 | 안 함 | 원래 결과를 잃음, 웹·워커가 같은 파일을 씀 |
| 업로드 즉시 MP4까지 만들기 | 안 함 | 대부분 필요 없음, 처리 시간 증가 → 요청 시에만 |

## 5. 테스트

- `test_writers_and_merge`(SRT·VTT·ASS 생성과 병합), `test_upload_status_edit_download`(편집 API·다운로드).
- 화면은 수동 확인 + [접근성 점검표](../../docs/04-디자인.md#5-접근성-점검표).
