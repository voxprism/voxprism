"""ffmpeg/ffprobe 도우미: 오디오 추출, 브라우저 재생용 미리보기, 썸네일, 자막 번인."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

from .. import config


class MediaError(RuntimeError):
    pass


def _run(cmd: list[str], timeout: int | None = None) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        tail = (proc.stderr or "")[-800:]
        raise MediaError(f"{cmd[0]} 실패: {tail}")
    return proc


def probe(path: Path) -> dict:
    out = _run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)])
    data = json.loads(out.stdout or "{}")
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"
                  and s.get("disposition", {}).get("attached_pic", 0) == 0), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    duration = float(data.get("format", {}).get("duration") or 0.0)
    info = {
        "duration": duration,
        "has_video": video is not None,
        "has_audio": audio is not None,
        "format": data.get("format", {}).get("format_name", ""),
    }
    if video:
        info.update({
            "width": int(video.get("width") or 0),
            "height": int(video.get("height") or 0),
            "vcodec": video.get("codec_name"),
            "pix_fmt": video.get("pix_fmt"),
        })
    if audio:
        info["acodec"] = audio.get("codec_name")
    return info


def extract_audio(src: Path, dst_wav: Path, sr: int = config.SAMPLE_RATE) -> None:
    _run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vn", "-ac", "1", "-ar", str(sr),
          "-c:a", "pcm_s16le", str(dst_wav)])


def load_wav(path: Path) -> tuple[np.ndarray, int]:
    wav, sr = sf.read(str(path), dtype="float32", always_2d=False)
    if wav.ndim > 1:
        wav = wav.mean(axis=1)
    return wav, sr


def write_wav(path: Path, wav: np.ndarray, sr: int = config.SAMPLE_RATE) -> None:
    sf.write(str(path), np.clip(wav, -1.0, 1.0), sr, subtype="PCM_16")


def make_preview(src: Path, dst_mp4: Path, info: dict) -> None:
    """브라우저에서 바로 재생되는 H.264/AAC MP4(최대 720p)를 만듭니다."""
    if not info.get("has_video"):
        # 오디오만 올린 경우: 검은 화면 영상으로 감싸서 플레이어를 동일하게 사용
        _run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=1280x720:r=10",
              "-i", str(src), "-shortest", "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage",
              "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(dst_mp4)])
        return
    h = info.get("height") or 0
    simple_copy = (
        info.get("vcodec") == "h264" and info.get("pix_fmt") in ("yuv420p", "yuvj420p")
        and h and h <= 720 and info.get("acodec") in ("aac", "mp3", None)
    )
    if simple_copy:
        try:
            _run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-map", "0:v:0", "-map", "0:a:0?",
                  "-c", "copy", "-movflags", "+faststart", str(dst_mp4)])
            return
        except MediaError:
            pass
    _run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-map", "0:v:0", "-map", "0:a:0?",
          "-vf", "scale=-2:'min(720,ih)'", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
          "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-ac", "2", "-movflags", "+faststart",
          str(dst_mp4)])


def grab_frame(src: Path, t: float, dst_jpg: Path, width: int = 480) -> bool:
    try:
        _run(["ffmpeg", "-y", "-v", "error", "-ss", f"{max(0.0, t):.2f}", "-i", str(src), "-frames:v", "1",
              "-vf", f"scale={width}:-2", "-q:v", "4", str(dst_jpg)], timeout=60)
        return dst_jpg.exists()
    except (MediaError, subprocess.TimeoutExpired):
        return False


def burn_in(src_mp4: Path, ass_path: Path, dst_mp4: Path) -> None:
    """ASS 자막을 영상에 입힙니다(libass). 한글 폰트는 fonts-noto-cjk 사용."""
    ass_arg = str(ass_path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    _run(["ffmpeg", "-y", "-v", "error", "-i", str(src_mp4), "-vf", f"ass='{ass_arg}'",
          "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p",
          "-c:a", "copy", "-movflags", "+faststart", str(dst_mp4)])
