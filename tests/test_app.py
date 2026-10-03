"""API contract tests for the review tool (FastAPI TestClient; no network)."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from src.app import server  # noqa: E402

C = TestClient(server.app)
VID = next(iter(sorted(server.S.videos)))


def test_info_and_pages():
    assert C.get("/api/info").json()["attribution"].startswith("Consented Activities")
    for p in ("/", "/gallery", "/report", "/static/app.js", "/static/style.css"):
        r = C.get(p)
        assert r.status_code == 200, p
        assert "default-src 'self'" in r.headers["content-security-policy"]


def test_val_video_payload_has_no_personal_fields():
    r = C.get(f"/api/val/videos/{VID}")
    assert r.status_code == 200
    txt = r.text
    for bad in ("subject_ids", "ipAddress", "device_identifier"):
        assert bad not in txt
    d = r.json()
    assert len(d["collector"]) == 8 and d["tracks"] and "media_url" in d


def test_media_range():
    r = C.get(f"/media/val/{VID}", headers={"Range": "bytes=10-19"})
    assert r.status_code == 206 and len(r.content) == 10 and r.headers["content-range"].startswith("bytes 10-19/")


@pytest.mark.parametrize("path", ["/media/val/..%2F..%2Fetc%2Fpasswd", "/static/..%2Fserver.py",
                                  "/api/val/videos/not-a-video-id", "/api/jobs/deadbeefdeadbeef", "/thumbs/x.jpg"])
def test_lookup_by_id_only(path):
    assert C.get(path).status_code == 404


def test_review_validation(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "REVIEWS", str(tmp_path / "r.jsonl"))
    seg = next(r["segment_id"] for r in server.S.rows if r["video_id"] == VID)
    ok = C.post("/api/reviews", json={"source": "val", "ref": VID, "segment_id": seg, "action": "confirm"})
    assert ok.status_code == 200
    assert C.post("/api/reviews", json={"source": "val", "ref": VID, "segment_id": seg, "action": "correct"}).status_code == 400
    assert C.post("/api/reviews", json={"source": "val", "ref": VID, "segment_id": seg, "action": "correct",
                                        "corrected_class": "dance"}).status_code == 422
    assert C.post("/api/reviews", json={"source": "val", "ref": VID, "segment_id": "x", "action": "confirm"}).status_code == 404
    lines = open(tmp_path / "r.jsonl").read().splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["action"] == "confirm"


def test_upload_rejects_bad_type():
    assert C.post("/api/upload", files={"file": ("a.txt", b"hello", "text/plain")}).status_code == 400


def test_basic_auth_helper():
    import base64 as b64

    def hdr(u, p):
        return "Basic " + b64.b64encode(f"{u}:{p}".encode()).decode()

    orig = (server.AUTH_USER, server.AUTH_PASS)
    server.AUTH_USER, server.AUTH_PASS = "gr11", "secret-pw"
    try:
        assert server._check_basic_auth(hdr("gr11", "secret-pw")) is True
        assert server._check_basic_auth(hdr("gr11", "wrong")) is False
        assert server._check_basic_auth(hdr("other", "secret-pw")) is False
        assert server._check_basic_auth(None) is False
        assert server._check_basic_auth("Bearer x") is False
        assert server._check_basic_auth("Basic not-base64!!") is False
    finally:
        server.AUTH_USER, server.AUTH_PASS = orig


def test_basic_auth_gate(monkeypatch):
    import base64 as b64
    monkeypatch.setattr(server, "AUTH_ENABLED", True)
    monkeypatch.setattr(server, "AUTH_USER", "gr11")
    monkeypatch.setattr(server, "AUTH_PASS", "secret-pw")
    client = TestClient(server.app)
    # no credentials -> 401 with a WWW-Authenticate challenge
    r = client.get("/api/info")
    assert r.status_code == 401 and r.headers.get("www-authenticate", "").startswith("Basic")
    # wrong credentials -> 401
    assert client.get("/api/info", auth=("gr11", "nope")).status_code == 401
    # correct credentials -> 200, and security headers still present
    ok = client.get("/api/info", auth=("gr11", "secret-pw"))
    assert ok.status_code == 200
    assert "default-src 'self'" in ok.headers["content-security-policy"]


def test_no_auth_when_disabled(monkeypatch):
    # default local mode: auth disabled -> endpoints open as before
    monkeypatch.setattr(server, "AUTH_ENABLED", False)
    client = TestClient(server.app)
    assert client.get("/api/info").status_code == 200
