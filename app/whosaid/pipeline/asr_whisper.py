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


def _load_16k(path: Path):
    """16kHz 모노 float32 배열. faster-whisper에 파일 경로를 주면 PyAV로 다시 디코딩하는데,
    PyAV 19에서 faster-whisper 1.2.1이 쓰는 인자(metadata_errors)가 없어져 실패하므로 직접 읽어 넘긴다."""
    import numpy as np
    import soundfile as sf
    wav, sr = sf.read(str(path), dtype="float32", always_2d=True)
    wav = wav.mean(axis=1)
    if sr != 16000:
        n = int(round(len(wav) * 16000 / sr))
        wav = np.interp(np.linspace(0, len(wav) - 1, n), np.arange(len(wav)), wav).astype(np.float32)
    return wav


def recognize_words(path: Path, vad: bool = True) -> list[dict]:
    model = get_model()
    segments, _info = model.transcribe(
        _load_16k(path), language="ko", beam_size=5, word_timestamps=True,
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
