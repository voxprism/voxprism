"""작업(Job) 저장소. 작업 하나 = 디렉터리 하나.

파일별 소유자를 나눠서 웹 프로세스와 워커 프로세스가 같은 파일을 동시에 덮어쓰지 않게 합니다.
  options.json   웹이 생성 시 1회 기록
  status.json    워커가 갱신 (진행률·단계·오류)
  result.json    워커가 생성 (화자·자막 이벤트)
  speakers.json  웹이 갱신 (사용자가 바꾼 화자 이름·병합)
  render.request 웹이 생성, 워커가 처리 후 삭제 (자막 입힌 MP4 요청)
"""
from __future__ import annotations

import json
import os
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from . import config

JOB_ID_RE = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{6}$")


def ensure_dirs() -> None:
    config.JOBS_DIR.mkdir(parents=True, exist_ok=True)
    config.MODEL_DIR.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, data: Any) -> None:
    path = Path(path)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def new_job_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]


def job_dir(job_id: str) -> Path:
    if not JOB_ID_RE.match(job_id or ""):
        raise ValueError("잘못된 작업 ID")
    return config.JOBS_DIR / job_id


def exists(job_id: str) -> bool:
    try:
        return job_dir(job_id).is_dir()
    except ValueError:
        return False


def create_job(job_id: str, input_name: str, original_filename: str, options: dict) -> None:
    d = job_dir(job_id)
    d.mkdir(parents=True, exist_ok=False)
    write_json(d / "options.json", {
        **options,
        "input": input_name,
        "original_filename": original_filename,
        "created_at": time.time(),
    })
    set_status(job_id, state="queued", stage="queued", progress=0, message="대기 중")


def set_status(job_id: str, **fields: Any) -> dict:
    d = job_dir(job_id)
    status = read_json(d / "status.json", {}) or {}
    status.update(fields)
    status["updated_at"] = time.time()
    write_json(d / "status.json", status)
    return status


def get_status(job_id: str) -> dict:
    return read_json(job_dir(job_id) / "status.json", {}) or {}


def get_options(job_id: str) -> dict:
    return read_json(job_dir(job_id) / "options.json", {}) or {}


def list_jobs(limit: int = 50) -> list[dict]:
    if not config.JOBS_DIR.exists():
        return []
    items = []
    for d in sorted(config.JOBS_DIR.iterdir(), reverse=True):
        if not d.is_dir() or not JOB_ID_RE.match(d.name):
            continue
        opts = read_json(d / "options.json", {}) or {}
        st = read_json(d / "status.json", {}) or {}
        res_meta = read_json(d / "summary.json", {}) or {}
        items.append({
            "id": d.name,
            "title": opts.get("title") or opts.get("original_filename") or d.name,
            "created_at": opts.get("created_at"),
            "state": st.get("state"),
            "progress": st.get("progress", 0),
            "message": st.get("message"),
            **res_meta,
        })
        if len(items) >= limit:
            break
    return items


def next_queued() -> str | None:
    if not config.JOBS_DIR.exists():
        return None
    for d in sorted(config.JOBS_DIR.iterdir()):
        if d.is_dir() and JOB_ID_RE.match(d.name):
            st = read_json(d / "status.json", {}) or {}
            if st.get("state") == "queued":
                return d.name
    return None


def next_render_request() -> str | None:
    if not config.JOBS_DIR.exists():
        return None
    for req in sorted(config.JOBS_DIR.glob("*/render.request")):
        return req.parent.name
    return None


def recover_interrupted() -> list[str]:
    """워커가 재시작될 때 'running'으로 멈춘 작업을 한 번 다시 대기열에 넣습니다."""
    fixed = []
    if not config.JOBS_DIR.exists():
        return fixed
    for d in config.JOBS_DIR.iterdir():
        st = read_json(d / "status.json", {}) or {}
        if st.get("state") == "running":
            retries = int(st.get("retries", 0))
            if retries < 1:
                set_status(d.name, state="queued", stage="queued", progress=0,
                           message="서버 재시작으로 다시 대기 중", retries=retries + 1)
            else:
                set_status(d.name, state="error", message="처리 중 서버가 중단되었습니다. 다시 업로드해 주세요.")
            fixed.append(d.name)
    return fixed


def delete_job(job_id: str) -> None:
    shutil.rmtree(job_dir(job_id), ignore_errors=True)
