"""겹친 말 음원 분리 (SpeechBrain SepFormer, WHAMR! 16 kHz — 잡음·잔향 섞인 2인 혼합음으로 학습)."""
from __future__ import annotations

import logging
import threading

import numpy as np

from .. import config

log = logging.getLogger(__name__)
_sep = None
_lock = threading.Lock()


def get_separator():
    global _sep
    with _lock:
        if _sep is None:
            import torch
            torch.set_num_threads(config.CPU_THREADS)
            from speechbrain.inference.separation import SepformerSeparation
            log.info("음원 분리 모델 로드: %s", config.SEPARATION_MODEL)
            _sep = SepformerSeparation.from_hparams(
                source=config.SEPARATION_MODEL,
                savedir=str(config.MODEL_DIR / config.SEPARATION_MODEL.replace("/", "__")),
                run_opts={"device": "cpu"},
            )
        return _sep


def separate(wav: np.ndarray, sr: int) -> np.ndarray:
    """(T,) 혼합음 → (2, T) 분리음. 두 출력의 상대 크기는 그대로 둡니다(에너지 판단용)."""
    import torch
    sep = get_separator()
    x = torch.from_numpy(np.ascontiguousarray(wav, dtype=np.float32)).unsqueeze(0)
    with torch.no_grad():
        est = sep.separate_batch(x)  # [1, T', n_src]
    src = est[0].detach().cpu().numpy().T.astype(np.float32)  # (n_src, T')
    n = len(wav)
    if src.shape[1] < n:
        src = np.pad(src, ((0, 0), (0, n - src.shape[1])))
    return src[:2, :n]


def normalize(x: np.ndarray, peak: float = 0.9) -> np.ndarray:
    m = float(np.max(np.abs(x)) + 1e-8)
    return (x * (peak / m)).astype(np.float32)


def rms_db(x: np.ndarray) -> float:
    if x.size == 0:
        return -120.0
    return float(20 * np.log10(np.sqrt(np.mean(np.square(x, dtype=np.float64))) + 1e-9))
