"""faster-whisper(오픈소스) 대체 엔진. CLOVA Speech 키가 없거나 호출이 실패할 때 사용합니다."""
from __future__ import annotations

import logging
import threading
from pathlib import Path

from .. import config

log = logging.getLogger(__name__)
_model = None
_lock = threading.Lock()


def get_model():
    global _model
    with _lock:
        if _model is None:
            from faster_whisper import WhisperModel
            log.info("faster-whisper 모델 로드: %s", config.WHISPER_MODEL)
            _model = WhisperModel(config.WHISPER_MODEL, device="cpu", compute_type="int8",
                                  cpu_threads=config.CPU_THREADS,
                                  download_root=str(config.MODEL_DIR / "whisper"))
        return _model


def recognize_words(path: Path, vad: bool = True) -> list[dict]:
    model = get_model()
    segments, _info = model.transcribe(
        str(path), language="ko", beam_size=5, word_timestamps=True,
        vad_filter=vad, condition_on_previous_text=False,
    )
    words: list[dict] = []
    for seg in segments:
        for w in seg.words or []:
            txt = (w.word or "").strip()
            if not txt:
                continue
            words.append({"start": float(w.start), "end": float(w.end), "text": txt,
                          "src_spk": None, "conf": float(w.probability)})
    return words
