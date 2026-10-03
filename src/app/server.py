"""CAP Activity Review Tool — FastAPI backend (local only).

Run:  .venv/bin/python -m src.app.server        (binds 127.0.0.1:8000)

Auth: set CAP_AUTH_USER and CAP_AUTH_PASS to require HTTP Basic auth on every route (used when the
tool is exposed through a tunnel). If either is unset the app runs without auth (local-only default).

Security (security-baseline lite): loopback bind; no client-supplied filesystem paths (videos and
jobs are looked up by id in server-side tables); strict id regexes; upload size/duration/extension
limits; CSP + nosniff headers; review payloads validated against enums.
Data rules (contract §2): only collector_id[:8] is exposed; no personal fields are read.
"""
import csv
import base64
import binascii
import datetime as dt
import json
import os
import queue
import re
import secrets
import shutil
import sys
import threading
import uuid
from typing import Literal, Optional

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

from src.model.head import CLASSES  # noqa: E402
from src.perception.annotations import DATA_ROOT, load_all  # noqa: E402

MANIFEST = "manifests/val_segments.csv"
PREDICTIONS = os.environ.get("CAP_PREDICTIONS", "predictions.json")
REPORT = "artifacts/report/report.json"
GALLERY = "artifacts/gallery"
UPLOADS = "artifacts/uploads"
REVIEWS = "artifacts/reviews.jsonl"
WEB = os.path.join(ROOT, "web")
MAX_UPLOAD_BYTES = 200 * 1024 * 1024
MAX_UPLOAD_SECONDS = 90
ALLOWED_EXT = {".mp4", ".mov", ".m4v", ".webm", ".avi"}
ID_RE = re.compile(r"^[A-Za-z0-9\-]{8,80}$")
SEG_RE = re.compile(r"^[A-Za-z0-9\-_]{1,120}$")
ATTRIBUTION = "Consented Activities of People (CAP), Visym Labs, CC BY 4.0"

app = FastAPI(title="CAP Activity Review Tool", docs_url=None, redoc_url=None, openapi_url=None)

# ---------------------------------------------------------------- HTTP Basic auth (optional)
# Enabled only when BOTH CAP_AUTH_USER and CAP_AUTH_PASS are set in the environment. Credentials are
# never hardcoded or logged. When unset (the default local-only mode, contract Q10), the app runs
# without auth exactly as before. Used to gate access when the tool is exposed via a tunnel (v0.2).
AUTH_USER = os.environ.get("CAP_AUTH_USER") or ""
AUTH_PASS = os.environ.get("CAP_AUTH_PASS") or ""
AUTH_ENABLED = bool(AUTH_USER and AUTH_PASS)
AUTH_REALM = "CAP Activity Review Tool"


def _check_basic_auth(header: Optional[str]) -> bool:
    if not header or not header.startswith("Basic "):
        return False
    try:
        raw = base64.b64decode(header[6:].strip(), validate=True).decode("utf-8")
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return False
    user, _, pw = raw.partition(":")
    # constant-time compares; evaluate both so timing does not reveal which field was wrong
    ok_user = secrets.compare_digest(user, AUTH_USER)
    ok_pass = secrets.compare_digest(pw, AUTH_PASS)
    return ok_user and ok_pass


@app.middleware("http")
async def basic_auth(request: Request, call_next):
    if AUTH_ENABLED and not _check_basic_auth(request.headers.get("authorization")):
        return Response(status_code=401, content="Authentication required",
                        headers={"WWW-Authenticate": f'Basic realm="{AUTH_REALM}", charset="UTF-8"'})
    return await call_next(request)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["Content-Security-Policy"] = ("default-src 'self'; img-src 'self' data:; media-src 'self' blob:; "
                                               "style-src 'self' 'unsafe-inline'; frame-ancestors 'self'")
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Cache-Control"] = resp.headers.get("Cache-Control", "no-store")
    return resp


# ---------------------------------------------------------------- data tables (loaded once)
class State:
    def __init__(self):
        self.rows = list(csv.DictReader(open(MANIFEST)))
        self.gts = load_all()
        self.preds = {}
        self.run = {}
        if os.path.exists(PREDICTIONS):
            p = json.load(open(PREDICTIONS))
            self.preds = {x["segment_id"]: x for x in p["predictions"]}
            self.run = {k: p["run"][k] for k in ("run_id", "stage", "abstention", "notes")}
        self.videos = {}
        for vid, g in self.gts.items():
            self.videos[vid] = g


S = State()


def _video_or_404(video_id):
    if not ID_RE.match(video_id) or video_id not in S.videos:
        raise HTTPException(404, "unknown video")
    return S.videos[video_id]


# ---------------------------------------------------------------- range file serving
def ranged_file(path, request: Request, media_type):
    size = os.path.getsize(path)
    rng = request.headers.get("range")
    headers = {"Accept-Ranges": "bytes", "Cache-Control": "private, max-age=3600"}
    if not rng:
        return FileResponse(path, media_type=media_type, headers=headers)
    m = re.match(r"bytes=(\d*)-(\d*)$", rng.strip())
    if not m:
        raise HTTPException(416, "bad range")
    a, b = m.groups()
    if a == "" and b == "":
        raise HTTPException(416, "bad range")
    if a == "":
        start, end = max(0, size - int(b)), size - 1
    else:
        start, end = int(a), (int(b) if b else size - 1)
    end = min(end, size - 1)
    if start > end:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})

    def it():
        with open(path, "rb") as fh:
            fh.seek(start)
            left = end - start + 1
            while left > 0:
                chunk = fh.read(min(1 << 16, left))
                if not chunk:
                    break
                left -= len(chunk)
                yield chunk

    headers.update({"Content-Range": f"bytes {start}-{end}/{size}", "Content-Length": str(end - start + 1)})
    return StreamingResponse(it(), status_code=206, media_type=media_type, headers=headers)


# ---------------------------------------------------------------- pages
@app.get("/")
def index():
    return FileResponse(os.path.join(WEB, "index.html"))


@app.get("/gallery")
def gallery_page():
    return FileResponse(os.path.join(WEB, "gallery.html"))


@app.get("/report")
def report_page():
    return FileResponse(os.path.join(WEB, "report.html"))


@app.get("/static/{name}")
def static(name: str):
    if not re.match(r"^[a-z0-9_\-]+\.(js|css)$", name):
        raise HTTPException(404)
    p = os.path.join(WEB, name)
    if not os.path.exists(p):
        raise HTTPException(404)
    return FileResponse(p, media_type="text/javascript" if name.endswith(".js") else "text/css")


# ---------------------------------------------------------------- val-video mode
@app.get("/api/info")
def info():
    return {"attribution": ATTRIBUTION, "classes": CLASSES, "run": S.run,
            "has_predictions": bool(S.preds), "max_upload_seconds": MAX_UPLOAD_SECONDS,
            "max_upload_mb": MAX_UPLOAD_BYTES // (1024 * 1024)}


@app.get("/api/val/videos")
def val_videos():
    segs_by_vid = {}
    for r in S.rows:
        segs_by_vid.setdefault(r["video_id"], []).append(r)
    out = []
    for vid, g in sorted(S.videos.items(), key=lambda kv: (kv[1].collection_name, kv[0])):
        segs = segs_by_vid.get(vid, [])
        n_ab = sum(1 for r in segs if S.preds.get(r["segment_id"], {}).get("abstain"))
        n_wrong = sum(1 for r in segs if r["segment_id"] in S.preds
                      and S.preds[r["segment_id"]]["pred_class"] != r["class"])
        out.append({"video_id": vid, "collection_name": g.collection_name, "collector": g.collector_id[:8],
                    "fold": int(segs[0]["fold"]) if segs else None, "n_segments": len(segs),
                    "n_flagged": n_ab, "n_wrong": n_wrong, "fps": g.fps})
    return out


@app.get("/api/val/videos/{video_id}")
def val_video(video_id: str):
    g = _video_or_404(video_id)
    import cv2
    cap = cv2.VideoCapture(os.path.join(DATA_ROOT, g.video_path))
    n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or g.fps
    cap.release()
    tracks = [{"track_id": t.track_id[:8], "full_id": t.track_id, "keyframes": t.keyframes.tolist(),
               "boxes": t.keyboxes.round(1).tolist()} for t in g.tracks.values()]
    segs = []
    for r in S.rows:
        if r["video_id"] != video_id:
            continue
        p = S.preds.get(r["segment_id"])
        segs.append({"segment_id": r["segment_id"], "track_id": r["track_id"][:8], "gt_class": r["class"],
                     "raw_label": r["raw_label"], "confusable_pair": r["confusable_pair"],
                     "start_frame": int(r["start_frame"]), "end_frame": int(r["end_frame"]), "fold": int(r["fold"]),
                     "pred": None if p is None else {k: p.get(k) for k in
                                                     ("pred_class", "probs", "confidence", "abstain",
                                                      "abstain_reason", "second_class")}})
    segs.sort(key=lambda s: s["start_frame"])
    return {"video_id": video_id, "collection_name": g.collection_name, "collector": g.collector_id[:8],
            "width": g.width, "height": g.height, "fps": fps, "n_frames": n_frames, "tracks": tracks,
            "segments": segs, "media_url": f"media/val/{video_id}", "reviews": reviews_for("val", video_id)}


@app.get("/media/val/{video_id}")
def val_media(video_id: str, request: Request):
    g = _video_or_404(video_id)
    return ranged_file(os.path.join(DATA_ROOT, g.video_path), request, "video/mp4")


# ---------------------------------------------------------------- reviews
class Review(BaseModel):
    source: Literal["val", "upload"]
    ref: str = Field(..., max_length=80)
    segment_id: str = Field(..., max_length=120)
    action: Literal["confirm", "correct", "reject"]
    corrected_class: Optional[Literal[tuple(CLASSES)]] = None  # type: ignore
    note: Optional[str] = Field(None, max_length=500)


_rev_lock = threading.Lock()


def reviews_for(source, ref):
    if not os.path.exists(REVIEWS):
        return {}
    out = {}
    for line in open(REVIEWS):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("source") == source and r.get("ref") == ref:
            out[r["segment_id"]] = r  # last write wins
    return out


@app.post("/api/reviews")
def post_review(rv: Review):
    if not SEG_RE.match(rv.segment_id) or not ID_RE.match(rv.ref):
        raise HTTPException(400, "bad id")
    if rv.source == "val":
        _video_or_404(rv.ref)
        if not any(r["segment_id"] == rv.segment_id and r["video_id"] == rv.ref for r in S.rows):
            raise HTTPException(404, "unknown segment")
    else:
        _job_or_404(rv.ref)
    if rv.action == "correct" and rv.corrected_class is None:
        raise HTTPException(400, "corrected_class required for action=correct")
    rec = rv.model_dump()
    rec["utc"] = dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    os.makedirs(os.path.dirname(REVIEWS), exist_ok=True)
    with _rev_lock, open(REVIEWS, "a") as fh:
        fh.write(json.dumps(rec) + "\n")
    return rec


@app.get("/api/reviews/export")
def export_reviews():
    if not os.path.exists(REVIEWS):
        return JSONResponse([])
    return JSONResponse([json.loads(x) for x in open(REVIEWS) if x.strip()])


# ---------------------------------------------------------------- upload (open-world, experimental)
JOBS = {}
_q = queue.Queue()
_deploy = {}


def _job_or_404(job_id):
    if not ID_RE.match(job_id) or job_id not in JOBS:
        raise HTTPException(404, "unknown job")
    return JOBS[job_id]


def _worker():
    from src.pipeline import openworld
    while True:
        job_id = _q.get()
        job = JOBS[job_id]
        try:
            if "m" not in _deploy:
                _deploy["m"] = openworld.load_deploy()

            def prog(p, msg):
                job.update(progress=round(p, 3), message=msg)
            job["status"] = "running"
            openworld.run(job["input"], job["dir"], _deploy["m"], MAX_UPLOAD_SECONDS, prog)
            job["status"] = "done"
        except Exception as e:  # report to the UI, keep the worker alive
            job.update(status="error", message=str(e)[:300])
        finally:
            try:
                os.remove(job["input"])  # keep only the downscaled proxy + numeric results
            except OSError:
                pass


threading.Thread(target=_worker, daemon=True).start()


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, f"unsupported file type; allowed: {sorted(ALLOWED_EXT)}")
    job_id = uuid.uuid4().hex
    d = os.path.join(UPLOADS, job_id)
    os.makedirs(d, exist_ok=True)
    dst = os.path.join(d, "input" + ext)
    n = 0
    with open(dst, "wb") as fh:
        while True:
            chunk = await file.read(1 << 20)
            if not chunk:
                break
            n += len(chunk)
            if n > MAX_UPLOAD_BYTES:
                fh.close()
                shutil.rmtree(d, ignore_errors=True)
                raise HTTPException(413, "file too large")
            fh.write(chunk)
    JOBS[job_id] = {"job_id": job_id, "status": "queued", "progress": 0.0, "message": "queued",
                    "dir": d, "input": dst, "created_utc": dt.datetime.utcnow().isoformat() + "Z"}
    _q.put(job_id)
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def job(job_id: str):
    j = _job_or_404(job_id)
    out = {k: j[k] for k in ("job_id", "status", "progress", "message")}
    if j["status"] == "done":
        out["result"] = json.load(open(os.path.join(j["dir"], "result.json")))
        out["media_url"] = f"media/upload/{job_id}"
        out["reviews"] = reviews_for("upload", job_id)
    return out


@app.get("/media/upload/{job_id}")
def upload_media(job_id: str, request: Request):
    j = _job_or_404(job_id)
    p = os.path.join(j["dir"], "proxy.webm")
    if not os.path.exists(p):
        raise HTTPException(404, "not ready")
    return ranged_file(p, request, "video/webm")


# ---------------------------------------------------------------- report & gallery
@app.get("/api/report")
def report():
    if not os.path.exists(REPORT):
        raise HTTPException(404, "run scripts/score.py first")
    return JSONResponse(json.load(open(REPORT)))


@app.get("/api/gallery")
def gallery():
    p = os.path.join(GALLERY, "index.json")
    if not os.path.exists(p):
        raise HTTPException(404, "run scripts/build_gallery.py first")
    return JSONResponse(json.load(open(p)))


@app.get("/thumbs/{segment_id}.jpg")
def thumb(segment_id: str):
    if not SEG_RE.match(segment_id) or segment_id not in S.preds:
        raise HTTPException(404)
    p = os.path.join(GALLERY, "thumbs", f"{segment_id}.jpg")
    if not os.path.exists(p):
        raise HTTPException(404)
    return FileResponse(p, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


def main():
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("CAP_PORT", "8000")), log_level="info")


if __name__ == "__main__":
    main()
