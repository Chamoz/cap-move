"""Open-world path for uploaded video (EXPERIMENTAL, UNSCORED — contract §5):
detect + track (YOLO11n + ByteTrack) -> sliding windows per track -> same features and deploy
head as Stage A -> calibrated probs -> abstention -> merge windows into segments.

The head was trained only on the 8 classes with oracle boundaries, so windows with no activity
are still forced into a class. A pose-motion gate labels near-static windows "no_activity",
and abstention catches low-confidence windows; the UI labels this path as experimental.
"""
import json
import os
import pickle
import time

import cv2
import numpy as np

from src.model import head as H
from src.model.features import single_blocks, stack
from src.perception import clip_state as CS
from src.perception import models
from src.perception.annotations import expand_box, sample_frames
from src.perception.features import T

PROC_FPS = 10.0
MAX_SIDE = 1280
WIN_S, STRIDE_S = 2.4, 1.2
MIN_TRACK_S = 1.5
MOTION_GATE = 0.02  # mean per-frame keypoint displacement (box heights)
PROXY_W = 480


def load_deploy(path="artifacts/model/deploy.pkl"):
    return pickle.load(open(path, "rb"))


MOTION_BLOCKS = {"emb", "emb_dir", "emb_half"}


def decode(path, max_seconds):
    """Decode at <= PROC_FPS, downscale to MAX_SIDE. Also writes nothing. Returns frames, times, meta."""
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise ValueError("cannot decode video")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    if not (1.0 <= fps <= 240.0):
        fps = 30.0
    step = max(1, int(round(fps / PROC_FPS)))
    frames, times, i = [], [], 0
    while True:
        ok = cap.grab()
        if not ok:
            break
        if i % step == 0:
            ok, f = cap.retrieve()
            if not ok:
                break
            h, w = f.shape[:2]
            s = min(1.0, MAX_SIDE / max(h, w))
            if s < 1.0:
                f = cv2.resize(f, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
            frames.append(f)
            times.append(i / fps)
            if times[-1] > max_seconds:
                raise ValueError(f"video longer than {max_seconds}s")
        i += 1
    cap.release()
    if len(frames) < 5:
        raise ValueError("video too short or undecodable")
    return frames, np.array(times), {"native_fps": fps, "proc_fps": fps / step,
                                     "width": frames[0].shape[1], "height": frames[0].shape[0]}


def track_people(frames):
    """ByteTrack via ultralytics; returns {track_id: {frame_idx: [x1,y1,x2,y2,score]}}."""
    from ultralytics import YOLO
    m = YOLO(models.DET_W)  # fresh instance so tracker state is per job
    tracks = {}
    for fi, f in enumerate(frames):
        r = m.track(f, persist=True, tracker="bytetrack.yaml", classes=[0], conf=0.25, verbose=False)[0]
        if r.boxes is None or r.boxes.id is None:
            continue
        for b, tid, sc in zip(r.boxes.xyxy.cpu().numpy(), r.boxes.id.cpu().numpy().astype(int),
                              r.boxes.conf.cpu().numpy()):
            tracks.setdefault(int(tid), {})[fi] = [*map(float, b), float(sc)]
    return tracks


def _interp_track(tdict, n):
    fi = np.array(sorted(tdict))
    bx = np.array([tdict[i][:4] for i in fi])
    span = np.arange(fi[0], fi[-1] + 1)
    full = np.stack([np.interp(span, fi, bx[:, j]) for j in range(4)], 1)
    return span, full


def write_proxy(frames, times, out_path, fps):
    h, w = frames[0].shape[:2]
    s = PROXY_W / w
    size = (PROXY_W, int(round(h * s / 2) * 2))
    wr = cv2.VideoWriter(out_path, cv2.VideoWriter_fourcc(*"VP80"), fps, size)
    if not wr.isOpened():
        raise RuntimeError("VP8 writer unavailable")
    for f in frames:
        wr.write(cv2.resize(f, size, interpolation=cv2.INTER_AREA))
    wr.release()
    return s, size


def run(path, out_dir, deploy, max_seconds=90, progress=lambda p, msg: None):
    t0 = time.time()
    progress(0.02, "decoding")
    frames, times, meta = decode(path, max_seconds)
    W, Hh = meta["width"], meta["height"]
    progress(0.10, "writing playback proxy")
    scale, psize = write_proxy(frames, times, os.path.join(out_dir, "proxy.webm"), meta["proc_fps"])
    progress(0.15, "detecting and tracking people")
    raw_tracks = track_people(frames)
    pf = meta["proc_fps"]
    win, stride = int(round(WIN_S * pf)), max(1, int(round(STRIDE_S * pf)))
    blocks, tau, temp, model = deploy["blocks"], deploy["threshold"], deploy["temperature"], deploy["model"]

    kept = {tid: d for tid, d in raw_tracks.items() if (max(d) - min(d) + 1) / pf >= MIN_TRACK_S}
    out_tracks, windows = [], []
    jobs = []
    for tid, d in sorted(kept.items()):
        span, boxes = _interp_track(d, len(frames))
        out_tracks.append({"track_id": f"t{tid}", "frames": span.tolist(),
                           "boxes": (boxes * scale).round(1).tolist(),
                           "detected": [int(i in d) for i in span]})
        starts = list(range(0, max(1, len(span) - win + 1), stride))
        for s in starts:
            e = min(s + win - 1, len(span) - 1)
            jobs.append((tid, span, boxes, s, e))

    for j, (tid, span, boxes, s, e) in enumerate(jobs):
        progress(0.2 + 0.75 * j / max(1, len(jobs)), f"classifying window {j + 1}/{len(jobs)}")
        a, b = int(span[s]), int(span[e])
        full = sample_frames(a, b, T)
        mid = (a + b) // 2
        plan = {"full": full, "h1": sample_frames(a, max(mid, a), T), "h2": sample_frames(min(mid, b), b, T)}
        bx = boxes[full - span[0]]
        crops, origins = [], []
        for f, bb in zip(full, bx):
            cb = expand_box(bb, W, Hh, pad=0.15).astype(int)
            crops.append(frames[f][cb[1]:cb[3] + 1, cb[0]:cb[2] + 1])
            origins.append((cb[0], cb[1]))
        kps = models.pose_in_crops(crops, origins, bx)
        seg_boxes = boxes[a - span[0]:b - span[0] + 1]
        ub = expand_box([seg_boxes[:, 0].min(), seg_boxes[:, 1].min(), seg_boxes[:, 2].max(), seg_boxes[:, 3].max()],
                        W, Hh, pad=0.10, square=True)
        if MOTION_BLOCKS & set(blocks):
            clips = {k: models.clip_tensor([frames[int(f)] for f in plan[k]], ub) for k in ("full", "h1", "h2")}
            clips["rev"] = clips["full"].flip(1)
            emb = models.embed_clips([clips[k] for k in ("full", "h1", "h2", "rev")])
        else:  # deploy head does not use the R(2+1)D blocks; skip the expensive pass
            emb = np.zeros((4, 512), np.float32)
        d = {"emb_full": emb[0], "emb_h1": emb[1], "emb_h2": emb[2], "emb_rev": emb[3], "kps": kps, "boxes": bx}
        cf = sample_frames(a, b, CS.N_FRAMES)
        ccrops = []
        for f, bb in zip(cf, boxes[cf - span[0]]):
            cb = expand_box(bb, W, Hh, pad=CS.CTX_PAD, square=True).astype(int)
            ccrops.append(frames[f][cb[1]:cb[3] + 1, cb[0]:cb[2] + 1])
        c_emb, c_sims = CS.embed_crops(ccrops)
        hgt = np.maximum(bx[:, 3] - bx[:, 1], 1)[:, None]
        vis = (kps[1:, :, 2] > 0.3) & (kps[:-1, :, 2] > 0.3)
        disp = np.linalg.norm(np.diff(kps[..., :2], axis=0), axis=-1) / hgt[1:]
        motion = float(disp[vis].mean()) if vis.any() else 0.0
        logits = H.full_logits(model, stack(single_blocks(d, c_emb, c_sims), blocks))
        p = H.softmax(logits / temp)[0]
        ab, reason, second = H.abstain_decision(p, tau)
        windows.append({"track_id": f"t{tid}", "start_frame": a, "end_frame": b, "motion": round(motion, 4),
                        "probs": p.round(5).tolist(), "pred_class": H.CLASSES[int(p.argmax())],
                        "confidence": float(p.max()), "abstain": bool(ab), "abstain_reason": reason,
                        "second_class": H.CLASSES[second], "static": motion < MOTION_GATE})

    segments = merge_windows(windows, tau)
    res = {"experimental": True, "scored": False, "meta": {**meta, "n_frames": len(frames),
           "proxy_scale": scale, "proxy_size": list(psize), "elapsed_s": round(time.time() - t0, 1),
           "window_s": WIN_S, "stride_s": STRIDE_S, "motion_gate": MOTION_GATE, "threshold": tau,
           "temperature": temp}, "times": np.round(times, 3).tolist(), "tracks": out_tracks,
           "windows": windows, "segments": segments}
    json.dump(res, open(os.path.join(out_dir, "result.json"), "w"))
    progress(1.0, "done")
    return res


def merge_windows(windows, tau):
    """Per track, merge consecutive non-static windows with the same top class into one segment.
    Segment probs = mean of window probs; abstain if mean confidence < tau."""
    segs = []
    by_track = {}
    for w in windows:
        by_track.setdefault(w["track_id"], []).append(w)
    for tid, ws in by_track.items():
        ws.sort(key=lambda w: w["start_frame"])
        cur = None
        for w in ws:
            if w["static"]:
                cur = None
                continue
            if cur and cur["pred_class"] == w["pred_class"] and w["start_frame"] <= cur["end_frame"] + 1:
                cur["end_frame"] = w["end_frame"]
                cur["_p"].append(w["probs"])
            else:
                cur = {"track_id": tid, "start_frame": w["start_frame"], "end_frame": w["end_frame"],
                       "pred_class": w["pred_class"], "_p": [w["probs"]]}
                segs.append(cur)
    for i, s in enumerate(segs):
        p = np.mean(s.pop("_p"), 0)
        ab, reason, second = H.abstain_decision(p, tau)
        s.update({"segment_id": f"u{i:03d}", "probs": p.round(5).tolist(), "confidence": float(p.max()),
                  "pred_class": H.CLASSES[int(p.argmax())], "abstain": bool(ab), "abstain_reason": reason,
                  "second_class": H.CLASSES[second]})
    return segs
