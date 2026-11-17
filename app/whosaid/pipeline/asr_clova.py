"""네이버 클라우드 CLOVA Speech 장문 인식 (로컬 파일 업로드, sync)."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import requests

from .. import config

log = logging.getLogger(__name__)


class ClovaSpeechError(RuntimeError):
    pass


def recognize(path: Path, *, diarization: bool = False, speaker_min: int | None = None,
              speaker_max: int | None = None, sed: bool = False, boostings: list[str] | None = None,
              timeout: int = 3600) -> dict:
    """CLOVA Speech `/recognizer/upload` 호출. 성공 시 원본 응답(JSON dict)을 돌려줍니다."""
    if not config.clova_available():
        raise ClovaSpeechError("CLOVA Speech 키가 설정되지 않았습니다")
    params: dict = {
        "language": "ko-KR",
        "completion": "sync",
        "wordAlignment": True,
        "fullText": True,
        "noiseFiltering": True,
        "diarization": {"enable": bool(diarization)},
    }
    if diarization:
        if speaker_min:
            params["diarization"]["speakerCountMin"] = int(speaker_min)
        if speaker_max:
            params["diarization"]["speakerCountMax"] = int(speaker_max)
    if sed:
        params["sed"] = {"enable": True}
    if boostings:
        params["boostings"] = [{"words": ",".join(boostings)}]

    url = config.CLOVA_SPEECH_INVOKE_URL.rstrip("/") + "/recognizer/upload"
    headers = {"X-CLOVASPEECH-API-KEY": config.CLOVA_SPEECH_SECRET, "Accept": "application/json"}
    with open(path, "rb") as f:
        files = {
            "media": (Path(path).name, f, "application/octet-stream"),
            "params": (None, json.dumps(params), "application/json"),
        }
        resp = requests.post(url, headers=headers, files=files, timeout=timeout)
    if resp.status_code != 200:
        raise ClovaSpeechError(f"HTTP {resp.status_code}: {resp.text[:400]}")
    data = resp.json()
    if data.get("result") not in ("COMPLETED", "SUCCEEDED"):
        raise ClovaSpeechError(f"{data.get('result')}: {data.get('message')}")
    return data


def _segment_speaker(seg: dict) -> str | None:
    spk = seg.get("speaker") or {}
    label = spk.get("label") or (seg.get("diarization") or {}).get("label")
    return str(label) if label not in (None, "") else None


def to_words(data: dict) -> list[dict]:
    """응답 segments → 단어 목록 [{start, end, text, src_spk, conf}] (초 단위).

    words 배열에는 문장부호가 빠져 있는 경우가 많아, 세그먼트 text를 공백으로 나눈 토큰 수가
    단어 수와 같으면 문장부호가 붙은 토큰을 표시용 텍스트로 사용합니다.
    """
    out: list[dict] = []
    for seg in data.get("segments") or []:
        spk = _segment_speaker(seg)
        conf = seg.get("confidence")
        words = seg.get("words") or []
        seg_text = (seg.get("textEdited") or seg.get("text") or "").strip()
        tokens = seg_text.split()
        use_tokens = len(tokens) == len(words) and len(words) > 0
        if words:
            for i, w in enumerate(words):
                s, e, txt = w[0], w[1], w[2]
                out.append({
                    "start": s / 1000.0, "end": max(e, s + 1) / 1000.0,
                    "text": tokens[i] if use_tokens else str(txt),
                    "src_spk": spk, "conf": conf,
                })
        elif seg_text:
            # 단어 정렬이 없으면 세그먼트 시간을 토큰 길이 비율로 나눔
            s, e = seg.get("start", 0) / 1000.0, seg.get("end", 0) / 1000.0
            total = sum(len(t) for t in tokens) or 1
            t = s
            for tok in tokens:
                d = (e - s) * len(tok) / total
                out.append({"start": t, "end": t + d, "text": tok, "src_spk": spk, "conf": conf})
                t += d
    out.sort(key=lambda w: w["start"])
    return out


SED_LABELS_KO = {
    "music": "음악", "laughter": "웃음", "laugh": "웃음", "applause": "박수", "clap": "박수",
    "cough": "기침", "cry": "울음", "crying": "울음", "scream": "비명", "shout": "외침",
    "noise": "소음", "bgm": "음악", "singing": "노래", "sing": "노래",
}


def to_sound_events(data: dict) -> list[dict]:
    out = []
    for ev in data.get("events") or []:
        label = (ev.get("labelEdited") or ev.get("label") or ev.get("type") or "").strip()
        if not label:
            continue
        start, end = ev.get("start"), ev.get("end")
        if start is None or end is None:
            continue
        out.append({
            "start": float(start) / 1000.0, "end": float(end) / 1000.0,
            "label": SED_LABELS_KO.get(label.lower(), label),
            "raw_label": label,
        })
    return out
