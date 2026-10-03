"""Per-segment perception features on GT segments / GT person tracks (Stage A, oracle boundaries).

For each manifest segment:
  * T=16 frames sampled uniformly over [start_frame, end_frame]
  * GT person box per sampled frame (interpolated track, native px)
  * YOLO11n-pose keypoints inside the padded GT crop  -> (T,17,3)
  * R(2+1)D-18 embeddings of a fixed crop (union of track boxes over the segment, square, padded):
      full segment, first half, second half, and the time-reversed full clip  -> 4 x 512
    (the reversed clip is only used as training augmentation for the directional pairs)

Nothing is fitted here, so there is no fold leakage. No raw pixels are written; only numeric features.
"""
from typing import Dict, List

import cv2
import numpy as np

from . import models
from .annotations import VideoGT, expand_box, sample_frames, video_abspath

T = 16


def read_frames(path: str, wanted: List[int]) -> Dict[int, np.ndarray]:
    """Sequential decode, keeping only wanted frame indices (OpenCV; no ffmpeg on host).
    Indices beyond the end are clamped to the last decoded frame."""
    want = sorted(set(int(w) for w in wanted))
    cap = cv2.VideoCapture(path)
    out, idx, last = {}, 0, None
    wi = 0
    while wi < len(want):
        ok = cap.grab()
        if not ok:
            break
        if idx == want[wi]:
            ok, f = cap.retrieve()
            if ok:
                out[idx] = f
                last = f
            while wi < len(want) and want[wi] <= idx:
                wi += 1
        idx += 1
    cap.release()
    if last is not None:
        lastidx = max(out)
        for w in want:
            if w not in out:
                out[w] = out[lastidx] if w > lastidx else out[min(k for k in out if k >= w)]
    return out


def segment_plan(gt: VideoGT, seg):
    s, e = int(seg["start_frame"]), int(seg["end_frame"])
    mid = (s + e) // 2
    return {
        "full": sample_frames(s, e, T),
        "h1": sample_frames(s, max(mid, s), T),
        "h2": sample_frames(min(mid, e), e, T),
    }


def extract_video(gt: VideoGT, segs: List[dict]) -> Dict[str, dict]:
    plans = {sg["segment_id"]: segment_plan(gt, sg) for sg in segs}
    wanted = sorted({int(f) for p in plans.values() for arr in p.values() for f in arr})
    frames = read_frames(video_abspath(gt), wanted)
    if not frames:
        raise RuntimeError(f"no frames decoded for video {gt.video_id}")
    H, W = next(iter(frames.values())).shape[:2]
    if (W, H) != (gt.width, gt.height):
        raise RuntimeError(f"frame size {W}x{H} != annotation {gt.width}x{gt.height}")

    results = {}
    for sg in segs:
        sid = sg["segment_id"]
        tr = gt.tracks.get(sg["track_id"])
        p = plans[sid]
        if tr is None:
            results[sid] = {"has_track": False}
            continue
        fidx = p["full"]
        boxes = tr.box_at(fidx)                      # (T,4)
        covered = tr.covers(fidx)
        # --- pose on padded per-frame GT crops
        crops, origins = [], []
        for f, b in zip(fidx, boxes):
            cb = expand_box(b, W, H, pad=0.15)
            x1, y1, x2, y2 = cb.astype(int)
            crops.append(frames[int(f)][y1:y2 + 1, x1:x2 + 1])
            origins.append((x1, y1))
        kps = models.pose_in_crops(crops, origins, boxes)  # (T,17,3) frame px

        # --- clip embeddings on a fixed square crop covering the whole segment
        allb = tr.box_at(np.arange(int(sg["start_frame"]), int(sg["end_frame"]) + 1))
        ub = np.array([allb[:, 0].min(), allb[:, 1].min(), allb[:, 2].max(), allb[:, 3].max()])
        ub = expand_box(ub, W, H, pad=0.10, square=True)
        clip = {k: models.clip_tensor([frames[int(f)] for f in p[k]], ub) for k in ("full", "h1", "h2")}
        clip["rev"] = clip["full"].flip(1)
        names = ["full", "h1", "h2", "rev"]
        emb = models.embed_clips([clip[k] for k in names])
        results[sid] = {
            "has_track": True,
            "frames": fidx.astype(np.int32),
            "boxes": boxes.astype(np.float32),
            "covered": covered,
            "kps": kps,
            "union_box": ub.astype(np.float32),
            **{f"emb_{k}": emb[i] for i, k in enumerate(names)},
        }
    return results
