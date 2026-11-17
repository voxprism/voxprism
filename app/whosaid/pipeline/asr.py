"""음성 인식 엔진 선택 계층: CLOVA Speech 우선, 실패하면 faster-whisper."""
from __future__ import annotations

import logging
from pathlib import Path

from .. import config
from . import asr_clova

log = logging.getLogger(__name__)
# 도메인이 이벤트 탐지를 지원하는지 한 번 알아내면 기억 (워커 프로세스 동안)
_sed_supported: bool | None = None


def resolve_engine(requested: str | None) -> str:
    requested = (requested or "auto").lower()
    if requested == "whisper":
        return "whisper"
    if requested == "clova":
        return "clova"
    return "clova" if config.clova_available() else "whisper"


def recognize(path: Path, *, engine: str, diarization: bool = False, speaker_min: int | None = None,
              speaker_max: int | None = None, want_sed: bool = False) -> dict:
    """반환: {engine, words, sound_events, raw, warnings}"""
    global _sed_supported
    warnings: list[str] = []
    if engine == "clova":
        try:
            raw = None
            sed_mode = config.CLOVA_SED
            use_sed = want_sed and sed_mode != "off" and _sed_supported is not False
            if want_sed and _sed_supported is False:
                warnings.append("CLOVA Speech 도메인의 이벤트 탐지가 꺼져 있어 소리 자막([웃음]·음악)은 빠졌습니다.")
            try:
                raw = asr_clova.recognize(path, diarization=diarization, speaker_min=speaker_min,
                                          speaker_max=speaker_max, sed=use_sed)
                if use_sed:
                    _sed_supported = True
            except asr_clova.ClovaSpeechError as e:
                if use_sed and sed_mode == "auto" and "event" in str(e).lower():
                    log.warning("이벤트 탐지 미지원 도메인, 탐지 없이 재시도: %s", e)
                    _sed_supported = False
                    warnings.append("CLOVA Speech 도메인의 이벤트 탐지가 꺼져 있어 소리 자막([웃음]·음악)은 빠졌습니다.")
                    raw = asr_clova.recognize(path, diarization=diarization, speaker_min=speaker_min,
                                              speaker_max=speaker_max, sed=False)
                else:
                    raise
            return {
                "engine": "clova",
                "words": asr_clova.to_words(raw),
                "sound_events": asr_clova.to_sound_events(raw),
                "raw": raw,
                "warnings": warnings,
            }
        except Exception as e:  # noqa: BLE001 - 어떤 오류든 대체 엔진으로 넘어감
            log.exception("CLOVA Speech 실패, Whisper로 대체")
            warnings.append(f"CLOVA Speech 호출 실패로 Whisper로 대체했습니다: {str(e)[:160]}")
    from . import asr_whisper
    words = asr_whisper.recognize_words(path)
    return {"engine": "whisper", "words": words, "sound_events": [], "raw": None, "warnings": warnings}


def recognize_batch(path: Path, engine: str) -> list[dict]:
    """겹침 구간 재인식용(화자 분리·이벤트 탐지 없이 단어만)."""
    if engine == "clova":
        try:
            raw = asr_clova.recognize(path, diarization=False, sed=False)
            return asr_clova.to_words(raw)
        except Exception:  # noqa: BLE001
            log.exception("겹침 구간 CLOVA 재인식 실패, Whisper로 대체")
    from . import asr_whisper
    return asr_whisper.recognize_words(path, vad=False)
