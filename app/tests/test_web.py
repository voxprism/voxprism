"""웹 API 테스트 (워커 없이 결과 파일을 직접 만들어 검증)."""
import importlib
import json
import os


def make_client(tmp_path, password=None):
    os.environ["WHOSAID_DATA_DIR"] = str(tmp_path / "data")
    os.environ["WHOSAID_MODEL_DIR"] = str(tmp_path / "models")
    if password:
        os.environ["WHOSAID_WEB_PASSWORD"] = password
    else:
        os.environ.pop("WHOSAID_WEB_PASSWORD", None)
    from whosaid import config, store, subtitles
    importlib.reload(config)
    importlib.reload(store)
    importlib.reload(subtitles)
    from whosaid.web import main
    importlib.reload(main)
    from fastapi.testclient import TestClient
    return TestClient(main.app), store


def test_upload_status_edit_download(tmp_path):
    client, store = make_client(tmp_path)
    assert client.get("/api/health").json()["ok"]
    r = client.post("/api/jobs", files={"file": ("clip.mp4", b"\x00" * 2048, "video/mp4")},
                    data={"title": "테스트", "num_speakers": "3", "recover_overlap": "true", "sound_events": "false"})
    assert r.status_code == 200, r.text
    jid = r.json()["id"]
    j = client.get(f"/api/jobs/{jid}").json()
    assert j["status"]["state"] == "queued" and j["options"]["num_speakers"] == 3
    assert client.post("/api/jobs", files={"file": ("x.exe", b"1", "application/octet-stream")}).status_code == 400

    # 워커가 끝낸 것처럼 결과를 만든다
    d = store.job_dir(jid)
    result = {"speakers": [{"id": "S1", "name": "화자 1", "color": "#FFD84D"},
                           {"id": "S2", "name": "화자 2", "color": "#5FD3FF"}],
              "events": [{"id": 0, "speaker": "S1", "start": 0, "end": 1, "text": "안녕", "overlap": True},
                         {"id": 1, "speaker": "S2", "start": 0.5, "end": 1.2, "text": "응", "overlap": True,
                          "recovered": True}],
              "stats": {}, "video": {"width": 640, "height": 360}}
    (d / "result.json").write_text(json.dumps(result, ensure_ascii=False))
    store.set_status(jid, state="done", progress=100)
    j = client.get(f"/api/jobs/{jid}").json()
    assert j["result"]["display"]["S1"]["name"] == "화자 1"

    r = client.post(f"/api/jobs/{jid}/speakers", json={"speakers": [{"id": "S1", "name": "재석"},
                                                                       {"id": "S2", "name": "", "merge_into": "S1"}]})
    assert r.status_code == 200
    assert r.json()["result"]["display"]["S2"]["name"] == "재석"
    srt = client.get(f"/api/jobs/{jid}/download/srt")
    assert srt.status_code == 200 and "[재석] 응" in srt.content.decode("utf-8-sig")
    assert client.get(f"/api/jobs/{jid}/download/mp4").status_code == 404
    assert client.post(f"/api/jobs/{jid}/render").json()["render"]["state"] == "queued"
    assert store.next_render_request() == jid
    assert client.get("/api/jobs/../../etc/passwd").status_code == 404
    assert client.get(f"/media/{jid}/result.json").status_code == 404
    assert client.delete(f"/api/jobs/{jid}").json()["ok"]


def test_login_required(tmp_path):
    client, _ = make_client(tmp_path, password="s3cret-pw")
    assert client.get("/api/health").status_code == 200            # 공개
    assert client.get("/api/jobs").status_code == 401               # API는 401
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/login")
    assert client.get("/api/auth-check").status_code == 401
    r = client.post("/login", data={"password": "wrong", "next": "/"}, follow_redirects=False)
    assert "error=1" in r.headers["location"]
    r = client.post("/login", data={"password": "s3cret-pw", "next": "//evil.com"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"   # 외부로 튕기지 않음
    assert client.get("/api/jobs").status_code == 200               # 쿠키로 통과
    assert client.get("/api/auth-check").status_code == 204
    client.cookies.clear()
    assert client.get("/api/jobs", auth=("x", "s3cret-pw")).status_code == 200   # curl -u 방식
    assert client.get("/api/jobs", auth=("x", "nope")).status_code == 401
