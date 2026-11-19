"""웹 API + 정적 페이지 (FastAPI). 무거운 처리는 워커가 하므로 여기서는 파일·상태만 다룹니다."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import re
import shutil
import time
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .. import __version__, config, store, subtitles

STATIC = Path(__file__).parent / "static"
app = FastAPI(title="VoxPrism", version=__version__)
app.mount("/static", StaticFiles(directory=STATIC), name="static")

# ───────────────────────── 로그인 (쿠키 세션) ─────────────────────────
SESSION_COOKIE = "whosaid_session"
PUBLIC_PREFIXES = ("/login", "/static/", "/api/health", "/api/auth-check", "/favicon")


def _sign(exp: int) -> str:
    mac = hmac.new(config.SECRET_KEY.encode(), str(exp).encode(), hashlib.sha256).hexdigest()[:40]
    return f"{exp}.{mac}"


def _session_ok(token: str | None) -> bool:
    try:
        exp = int((token or "").split(".", 1)[0])
    except ValueError:
        return False
    return exp > time.time() and hmac.compare_digest(_sign(exp), token or "")


def _basic_ok(request: Request) -> bool:
    """스크립트·curl용: Authorization: Basic (아이디 아무거나:비밀번호)"""
    h = request.headers.get("authorization", "")
    if not h.lower().startswith("basic "):
        return False
    try:
        _, pw = base64.b64decode(h[6:]).decode().split(":", 1)
    except Exception:  # noqa: BLE001
        return False
    return hmac.compare_digest(pw, config.WEB_PASSWORD or "")


def authed(request: Request) -> bool:
    if not config.WEB_PASSWORD:
        return True
    return _session_ok(request.cookies.get(SESSION_COOKIE)) or _basic_ok(request)


@app.middleware("http")
async def require_login(request: Request, call_next):
    path = request.url.path
    if not (path.startswith(PUBLIC_PREFIXES) or authed(request)):
        if path.startswith(("/api/", "/media/")):
            return JSONResponse({"detail": "로그인이 필요합니다"}, status_code=401)
        return RedirectResponse(f"/login?next={quote(path)}", status_code=303)
    response = await call_next(request)
    if path.startswith("/static/") or path in ("/", "/login") or path.startswith("/jobs/"):
        # 배포 후 바뀐 화면이 바로 보이도록 매번 변경 여부를 확인(바뀌지 않았으면 304로 가볍게)
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/api/auth-check", include_in_schema=False)
def auth_check(request: Request):
    """nginx auth_request용: 로그인했으면 204, 아니면 401."""
    return Response(status_code=204 if authed(request) else 401)


def _safe_next(nxt: str | None) -> str:
    return nxt if nxt and nxt.startswith("/") and not nxt.startswith("//") else "/"


@app.get("/login", include_in_schema=False)
def login_page():
    return FileResponse(STATIC / "login.html")


@app.post("/login", include_in_schema=False)
async def login(password: str = Form(""), next: str = Form("/")):  # noqa: A002
    if not config.WEB_PASSWORD or hmac.compare_digest(password, config.WEB_PASSWORD):
        exp = int(time.time()) + config.SESSION_DAYS * 86400
        resp = RedirectResponse(_safe_next(next), status_code=303)
        resp.set_cookie(SESSION_COOKIE, _sign(exp), max_age=config.SESSION_DAYS * 86400,
                        httponly=True, samesite="lax", path="/")
        return resp
    await asyncio.sleep(1.0)  # 무차별 대입 속도 늦추기
    return RedirectResponse(f"/login?error=1&next={quote(_safe_next(next))}", status_code=303)


@app.post("/logout", include_in_schema=False)
def logout():
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(SESSION_COOKIE, path="/")
    return resp


def _job_or_404(job_id: str) -> Path:
    if not store.exists(job_id):
        raise HTTPException(404, "작업을 찾을 수 없습니다")
    return store.job_dir(job_id)


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/jobs/{job_id}", include_in_schema=False)
def job_page(job_id: str):
    _job_or_404(job_id)
    return FileResponse(STATIC / "job.html")


@app.get("/api/health")
def health():
    return {"ok": True, "version": __version__, "clova_speech": config.clova_available(),
            "pyannote": config.pyannote_available(), "max_minutes": int(config.MAX_DURATION_SEC // 60),
            "max_upload_mb": config.MAX_UPLOAD_MB}


@app.post("/api/jobs")
async def create_job(
    file: UploadFile = File(...),
    title: str = Form(""),
    num_speakers: int = Form(0),
    engine: str = Form("auto"),
    recover_overlap: bool = Form(True),
    sound_events: bool = Form(True),
):
    store.ensure_dirs()
    name = file.filename or "upload"
    ext = Path(name).suffix.lower()
    if ext not in config.ALLOWED_EXTS:
        raise HTTPException(400, f"지원하지 않는 형식입니다: {ext or '확장자 없음'}")
    if engine not in ("auto", "clova", "whisper"):
        engine = "auto"
    job_id = store.new_job_id()
    tmp_dir = config.JOBS_DIR / f".upload-{job_id}"
    tmp_dir.mkdir(parents=True)
    dst = tmp_dir / f"input{ext}"
    limit = config.MAX_UPLOAD_MB * 1024 * 1024
    size = 0
    try:
        with dst.open("wb") as f:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > limit:
                    raise HTTPException(413, f"파일이 너무 큽니다 (최대 {config.MAX_UPLOAD_MB}MB)")
                f.write(chunk)
        if size == 0:
            raise HTTPException(400, "빈 파일입니다")
        clean_title = re.sub(r"[\r\n\t]", " ", title).strip()[:80] or Path(name).stem[:80]
        store.create_job(job_id, dst.name, name, {
            "title": clean_title,
            "num_speakers": max(0, min(int(num_speakers or 0), 12)) or None,
            "engine": engine,
            "recover_overlap": bool(recover_overlap),
            "sound_events": bool(sound_events),
            "size": size,
        })
        shutil.move(str(dst), str(store.job_dir(job_id) / dst.name))
    except Exception:
        if store.exists(job_id):
            store.delete_job(job_id)
        raise
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    return {"id": job_id}


@app.get("/api/jobs")
def list_jobs():
    return {"jobs": store.list_jobs()}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    d = _job_or_404(job_id)
    opts = store.get_options(job_id)
    status = store.get_status(job_id)
    out = {"id": job_id, "title": opts.get("title"), "options": {k: opts.get(k) for k in
           ("num_speakers", "engine", "recover_overlap", "sound_events", "original_filename")},
           "status": status, "render": store.read_json(d / "render.json", None)}
    if (d / "render.request").exists() and not out["render"]:
        out["render"] = {"state": "queued"}
    if status.get("state") == "done":
        result, spk = subtitles.effective(job_id)
        edits = store.read_json(d / "speakers.json", {}) or {}
        for s in result.get("speakers", []):
            s["display"] = spk.get(s["id"])
            s["merge_into"] = (edits.get(s["id"]) or {}).get("merge_into")
        result["display"] = spk
        out["result"] = result
    return out


class SpeakerEdit(BaseModel):
    id: str
    name: str | None = None
    merge_into: str | None = None


class SpeakerEdits(BaseModel):
    speakers: list[SpeakerEdit]


@app.post("/api/jobs/{job_id}/speakers")
def edit_speakers(job_id: str, body: SpeakerEdits):
    d = _job_or_404(job_id)
    result = store.read_json(d / "result.json", None)
    if not result:
        raise HTTPException(409, "아직 처리가 끝나지 않았습니다")
    valid = {s["id"] for s in result.get("speakers", [])}
    edits = store.read_json(d / "speakers.json", {}) or {}
    for s in body.speakers:
        if s.id not in valid:
            continue
        name = (s.name or "").strip()[:30]
        merge = s.merge_into if s.merge_into in valid and s.merge_into != s.id else None
        edits[s.id] = {"name": name or None, "merge_into": merge}
    store.write_json(d / "speakers.json", edits)
    subtitles.write_all(job_id)
    (d / "render.json").unlink(missing_ok=True)   # 이름이 바뀌었으니 예전 번인 영상은 무효
    (d / "burned.mp4").unlink(missing_ok=True)
    return get_job(job_id)


@app.post("/api/jobs/{job_id}/render")
def request_render(job_id: str):
    d = _job_or_404(job_id)
    if store.get_status(job_id).get("state") != "done":
        raise HTTPException(409, "아직 처리가 끝나지 않았습니다")
    (d / "render.json").unlink(missing_ok=True)
    (d / "render.request").write_text(str(time.time()))
    return {"render": {"state": "queued"}}


DOWNLOADS = {
    "srt": ("subs/whosaid.srt", "application/x-subrip"),
    "vtt": ("subs/whosaid.vtt", "text/vtt"),
    "ass": ("subs/whosaid.ass", "text/plain"),
    "json": ("result.json", "application/json"),
    "mp4": ("burned.mp4", "video/mp4"),
}


@app.get("/api/jobs/{job_id}/download/{kind}")
def download(job_id: str, kind: str):
    d = _job_or_404(job_id)
    if kind not in DOWNLOADS:
        raise HTTPException(404)
    rel, mime = DOWNLOADS[kind]
    path = d / rel
    if not path.exists():
        raise HTTPException(404, "파일이 아직 없습니다")
    title = re.sub(r"[^\w\-가-힣 ]", "", store.get_options(job_id).get("title") or job_id).strip() or job_id
    suffix = "_자막영상.mp4" if kind == "mp4" else f".{kind}"
    return FileResponse(path, media_type=mime, filename=f"{title}{suffix}")


@app.delete("/api/jobs/{job_id}")
def delete(job_id: str):
    _job_or_404(job_id)
    if store.get_status(job_id).get("state") == "running":
        raise HTTPException(409, "처리 중인 작업은 지울 수 없습니다")
    store.delete_job(job_id)
    return {"ok": True}


MEDIA_RE = re.compile(r"^(preview\.mp4|burned\.mp4|thumbs/S\d+_\d\.jpg|faces/P\d+\.jpg|visual\.json)$")


@app.get("/media/{job_id}/{rel:path}", include_in_schema=False)
def media(job_id: str, rel: str):
    """개발용. 운영에서는 nginx가 같은 경로를 직접(Range 지원) 내려줍니다."""
    d = _job_or_404(job_id)
    if not MEDIA_RE.match(rel):
        raise HTTPException(404)
    path = d / rel
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path)


@app.exception_handler(ValueError)
def _value_error(_, exc: ValueError):
    return JSONResponse({"detail": str(exc)}, status_code=400)
