"""잡음 거르기 (SPEC-009, FR-CAP-08).

자막을 어지럽히는 세 가지를 뺀다.
  1. 신뢰도가 아주 낮은 인식 단어(박수·웃음·배경음이 글자로 잡힌 것)
  2. 앞뒤로 말이 없는 짧은 외톨이 단어 중 신뢰도가 낮은 것
  3. Whisper가 소리 없는 구간에 흔히 지어내는 문장(방송 끝인사 등)
그리고 화자 분리에서 아주 잠깐만 잡힌 '가짜 화자'(합계 1초 미만, 단어 2개 이하)를 없애 그 구간 단어가
주변 화자에게 배정되게 한다.
"""
from __future__ import annotations

MIN_CONF = 0.25          # 이보다 낮으면 무조건 뺌
ISOLATED_CONF = 0.6      # 외톨이 단어는 이보다 낮으면 뺌
ISOLATED_GAP = 1.5       # 앞뒤 이 시간 안에 다른 단어가 없으면 외톨이
ISOLATED_MAX_DUR = 0.5   # 외톨이로 볼 최대 길이(초)
NOISE_SPK_TALK = 1.0     # 이보다 짧게 말한 화자는 잡음 후보(초)
NOISE_SPK_WORDS = 2      # 그리고 단어가 이 이하일 때

WHISPER_JUNK = (
    "시청해 주셔서 감사합니다", "시청해주셔서 감사합니다", "구독과 좋아요", "구독 좋아요", "자막 제공",
    "자막 by", "한국어 자막", "MBC 뉴스", "KBS 뉴스", "SBS 뉴스", "다음 영상에서 만나요", "끝까지 시청",
)


def _norm(s: str) -> str:
    return "".join(s.split())


def filter_words(words: list[dict], engine: str = "clova") -> tuple[list[dict], int]:
    """돌려줌: (남길 단어, 뺀 개수). conf 가 없는 단어는 신뢰도 규칙을 적용하지 않는다."""
    ws = sorted(words, key=lambda w: (w["start"], w["end"]))
    drop = [False] * len(ws)
    for i, w in enumerate(ws):
        c = w.get("conf")
        if c is not None and c < MIN_CONF:
            drop[i] = True
            continue
        prev_end = ws[i - 1]["end"] if i > 0 else -1e9
        next_start = ws[i + 1]["start"] if i + 1 < len(ws) else 1e9
        isolated = w["start"] - prev_end > ISOLATED_GAP and next_start - w["end"] > ISOLATED_GAP
        if isolated and w["end"] - w["start"] <= ISOLATED_MAX_DUR and c is not None and c < ISOLATED_CONF:
            drop[i] = True
    if engine == "whisper":
        _drop_junk(ws, drop)
    kept = [w for w, d in zip(ws, drop) if not d]
    return kept, sum(drop)


def _drop_junk(ws: list[dict], drop: list[bool], gap: float = 0.8) -> None:
    """이어진 단어 묶음(0.8초 이내) 단위로 맞춰 보고, 묶음 전체가 지어낸 문장이면 뺀다."""
    i = 0
    while i < len(ws):
        j = i
        while j + 1 < len(ws) and ws[j + 1]["start"] - ws[j]["end"] <= gap:
            j += 1
        text = _norm(" ".join(w["text"] for w in ws[i:j + 1]))
        if text and any(_norm(p) in text and len(text) <= len(_norm(p)) + 6 for p in WHISPER_JUNK):
            for k in range(i, j + 1):
                drop[k] = True
        i = j + 1


def noise_speakers(turns: list[dict], words: list[dict]) -> set[str]:
    """아주 잠깐만 잡힌 화자. turns 의 화자 이름 기준. words 는 assign 전이라 시간으로 센다."""
    talk: dict[str, float] = {}
    for t in turns:
        talk[t["speaker"]] = talk.get(t["speaker"], 0.0) + (t["end"] - t["start"])
    out = set()
    for s, sec in talk.items():
        if sec >= NOISE_SPK_TALK or len(talk) <= 1:
            continue
        mine = [t for t in turns if t["speaker"] == s]
        n = sum(1 for w in words if any(t["start"] <= (w["start"] + w["end"]) / 2 < t["end"] for t in mine))
        if n <= NOISE_SPK_WORDS:
            out.add(s)
    return out
