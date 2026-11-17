"""결과(result.json) + 사용자 편집(speakers.json) → 자막 파일(SRT/VTT/ASS) 생성.

웹 프로세스에서도 쓰므로 무거운 라이브러리(torch 등)를 import하지 않습니다.
"""
from __future__ import annotations

from . import store
from .pipeline import captions


def effective(job_id: str) -> tuple[dict, dict[str, dict]]:
    d = store.job_dir(job_id)
    result = store.read_json(d / "result.json", {}) or {}
    edits = store.read_json(d / "speakers.json", {}) or {}
    spk = captions.resolve_speakers(result.get("speakers", []), edits)
    return result, spk


def write_all(job_id: str) -> dict:
    d = store.job_dir(job_id)
    result, spk = effective(job_id)
    events = result.get("events", [])
    sub_dir = d / "subs"
    sub_dir.mkdir(exist_ok=True)
    w, h = result.get("video", {}).get("width") or 1280, result.get("video", {}).get("height") or 720
    files = {
        "srt": captions.to_srt(events, spk),
        "vtt": captions.to_vtt(events, spk),
        "ass": captions.to_ass(events, spk, w, h),
    }
    for ext, text in files.items():
        (sub_dir / f"whosaid.{ext}").write_text(text, encoding="utf-8-sig" if ext == "srt" else "utf-8")
    return {"speakers": spk}
