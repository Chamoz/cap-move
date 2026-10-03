"""Load CAP vipy JSON ground truth (tracks + activities) in native video pixel coordinates.

Contract §2: only whitelisted fields are read. `subject_ids`, `ipAddress`, `device_identifier`
are never touched (attributes are accessed by explicit key, never copied wholesale).

vipy boxes are stored in the frame produced by the JSON's `ffmpeg` filter (`scale=W':H'`,
512x910 for this dataset); they are rescaled here to native resolution.
"""
import json
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

DATA_ROOT = "data/cap_detection_handheld_val"
_SAFE_ATTRS = ("video_id", "collector_id", "collection_name", "frame_width", "frame_height", "device_type")


@dataclass
class Track:
    track_id: str
    keyframes: np.ndarray  # (K,) int, sorted
    keyboxes: np.ndarray   # (K, 4) float xyxy, native pixels

    def box_at(self, frames) -> np.ndarray:
        """Linear interpolation (vipy 'linear'); frames outside the track span are clamped
        to the nearest keyframe. Returns (N, 4)."""
        f = np.asarray(frames, dtype=float)
        return np.stack([np.interp(f, self.keyframes, self.keyboxes[:, j]) for j in range(4)], axis=1)

    def covers(self, frames) -> np.ndarray:
        f = np.asarray(frames)
        return (f >= self.keyframes[0]) & (f <= self.keyframes[-1])


@dataclass
class Activity:
    activity_id: str
    raw_label: str
    track_id: str
    start_frame: int
    end_frame: int


@dataclass
class VideoGT:
    video_id: str
    video_path: str  # relative to DATA_ROOT
    collector_id: str
    collection_name: str
    width: int
    height: int
    fps: float
    device_type: str
    tracks: Dict[str, Track] = field(default_factory=dict)
    activities: List[Activity] = field(default_factory=list)


def _scale_factor(ffmpeg_cmd: str, width: int, height: int) -> float:
    m = re.search(r"scale=(\d+):(\d+)", ffmpeg_cmd or "")
    if not m:
        return 1.0
    sw, sh = int(m.group(1)), int(m.group(2))
    sx, sy = width / sw, height / sh
    if abs(sx - sy) / sx > 0.01:
        raise ValueError(f"anisotropic scale {sx:.3f} vs {sy:.3f}")
    return sx


def load_video_gt(json_path: str, data_root: str = DATA_ROOT) -> VideoGT:
    scene = json.load(open(json_path))[0]
    v = next(iter(scene.values()))
    a = v["attributes"]
    safe = {k: a[k] for k in _SAFE_ATTRS}
    rel = os.path.normpath(os.path.join("annotations", v["filename"]))
    s = _scale_factor(v.get("ffmpeg"), int(safe["frame_width"]), int(safe["frame_height"]))
    gt = VideoGT(
        video_id=safe["video_id"], video_path=rel, collector_id=safe["collector_id"],
        collection_name=safe["collection_name"], width=int(safe["frame_width"]),
        height=int(safe["frame_height"]), fps=float(v["framerate"]), device_type=safe["device_type"],
    )
    for t in v["tracks"].values():
        kf = np.asarray(t["keyframes"], dtype=int)
        kb = np.asarray([[b["xmin"], b["ymin"], b["xmax"], b["ymax"]] for b in t["keyboxes"]], float) * s
        order = np.argsort(kf, kind="stable")
        gt.tracks[t["id"]] = Track(t["id"], kf[order], kb[order])
    for act in v["activities"].values():
        gt.activities.append(Activity(act["id"], act["label"], act["actorid"],
                                      int(act["startframe"]), int(act["endframe"])))
    return gt


def load_all(data_root: str = DATA_ROOT) -> Dict[str, VideoGT]:
    out = {}
    ann = os.path.join(data_root, "annotations")
    for fn in sorted(os.listdir(ann)):
        if fn.endswith(".json"):
            g = load_video_gt(os.path.join(ann, fn), data_root)
            out[g.video_id] = g
    return out


def video_abspath(gt: VideoGT, data_root: str = DATA_ROOT) -> str:
    return os.path.join(data_root, gt.video_path)


def expand_box(box, frame_w: int, frame_h: int, pad: float = 0.15, square: bool = False) -> np.ndarray:
    x1, y1, x2, y2 = box
    w, h = x2 - x1, y2 - y1
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    w, h = w * (1 + 2 * pad), h * (1 + 2 * pad)
    if square:
        w = h = max(w, h)
    b = np.array([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2])
    b[[0, 2]] = b[[0, 2]].clip(0, frame_w - 1)
    b[[1, 3]] = b[[1, 3]].clip(0, frame_h - 1)
    return b


def sample_frames(start: int, end: int, n: int) -> np.ndarray:
    """n frame indices uniformly spanning [start, end] inclusive (repeats allowed if short)."""
    return np.round(np.linspace(start, end, n)).astype(int)
