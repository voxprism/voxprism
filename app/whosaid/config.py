"""환경 변수 기반 설정. 서버에서는 /etc/whosaid.env 를 systemd가 읽어 넣어 줍니다."""
from __future__ import annotations

import os
from pathlib import Path


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


DATA_DIR = Path(_env("WHOSAID_DATA_DIR", "/srv/whosaid/data"))
JOBS_DIR = DATA_DIR / "jobs"
MODEL_DIR = Path(_env("WHOSAID_MODEL_DIR", "/srv/whosaid/models"))

# 네이버 클라우드 CLOVA Speech (장문 인식)
CLOVA_SPEECH_INVOKE_URL = _env("CLOVA_SPEECH_INVOKE_URL")
CLOVA_SPEECH_SECRET = _env("CLOVA_SPEECH_SECRET")
# 이벤트 탐지(웃음·음악 등): auto = 시도해 보고 도메인이 지원하지 않으면 끄고 다시 요청
CLOVA_SED = _env("WHOSAID_CLOVA_SED", "auto")

# Hugging Face (pyannote 화자 분리 모델은 약관 동의 + 토큰 필요)
HF_TOKEN = _env("HF_TOKEN")
DIARIZATION_MODEL = _env("WHOSAID_DIAR_MODEL", "pyannote/speaker-diarization-community-1")
EMBEDDING_MODEL = _env("WHOSAID_EMB_MODEL", "pyannote/wespeaker-voxceleb-resnet34-LM")
SEPARATION_MODEL = _env("WHOSAID_SEP_MODEL", "speechbrain/sepformer-whamr16k")
WHISPER_MODEL = _env("WHOSAID_WHISPER_MODEL", "deepdml/faster-whisper-large-v3-turbo-ct2")

# 선택: CLOVA Studio (HyperCLOVA X)
CLOVASTUDIO_API_KEY = _env("CLOVASTUDIO_API_KEY")

# 웹 로그인 (비밀번호가 없으면 로그인 없이 열림 — 개발용)
WEB_PASSWORD = _env("WHOSAID_WEB_PASSWORD")
SECRET_KEY = _env("WHOSAID_SECRET") or (WEB_PASSWORD or "dev") + "-whosaid-session"
SESSION_DAYS = int(_env("WHOSAID_SESSION_DAYS", "7"))

MAX_DURATION_SEC = float(_env("WHOSAID_MAX_DURATION_SEC", "1200"))  # 20분
MAX_UPLOAD_MB = int(_env("WHOSAID_MAX_UPLOAD_MB", "1024"))
CPU_THREADS = int(_env("WHOSAID_THREADS", str(os.cpu_count() or 4)))
SAMPLE_RATE = 16000

ALLOWED_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".mp3", ".m4a", ".wav", ".aac", ".flac", ".ogg"}


def clova_available() -> bool:
    return bool(CLOVA_SPEECH_INVOKE_URL and CLOVA_SPEECH_SECRET)


# 화면 속 화자 찾기 모델(SPEC-009): MODEL_DIR/vision/ 에 YuNet·SFace·YOLO11n-seg ONNX
VISION_DIR = MODEL_DIR / "vision"


def pyannote_available() -> bool:
    return bool(HF_TOKEN)
