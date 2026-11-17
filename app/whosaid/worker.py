"""백그라운드 워커: 대기 중인 작업을 하나씩 처리합니다. (systemd: whosaid-worker.service)"""
from __future__ import annotations

import logging
import signal
import sys
import time

from . import config, store

log = logging.getLogger("whosaid.worker")
_stop = False


def _handle_stop(signum, frame):  # noqa: ARG001
    global _stop
    _stop = True


def warmup() -> None:
    """첫 작업이 오래 걸리지 않도록 모델을 미리 내려받고 메모리에 올립니다."""
    from .pipeline import diarize, separate
    if config.pyannote_available():
        try:
            diarize.get_pipeline()
            diarize.get_embedder()
        except Exception:  # noqa: BLE001
            log.exception("pyannote 미리 로드 실패 (작업 시 다시 시도)")
    try:
        separate.get_separator()
    except Exception:  # noqa: BLE001
        log.exception("분리 모델 미리 로드 실패 (작업 시 다시 시도)")
    if not config.clova_available():
        try:
            from .pipeline import asr_whisper
            asr_whisper.get_model()
        except Exception:  # noqa: BLE001
            log.exception("Whisper 미리 로드 실패")


def main() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)
    store.ensure_dirs()
    fixed = store.recover_interrupted()
    if fixed:
        log.info("중단된 작업 복구: %s", fixed)
    log.info("CLOVA Speech: %s / pyannote: %s / 스레드: %d",
             config.clova_available(), config.pyannote_available(), config.CPU_THREADS)
    warmup()
    from .pipeline import run
    log.info("워커 대기 시작")
    while not _stop:
        job = store.next_queued()
        if job:
            log.info("작업 시작 %s", job)
            run.process(job)
            continue
        rjob = store.next_render_request()
        if rjob:
            log.info("렌더 시작 %s", rjob)
            run.render(rjob)
            continue
        time.sleep(1.0)
    log.info("워커 종료")


if __name__ == "__main__":
    main()
