"""Frozen perception models (CPU): YOLO11n person detector, YOLO11n-pose, R(2+1)D-18 (Kinetics-400).

All weights are pretrained on non-CAP data and used frozen (contract §5). Paths/hashes are
recorded by `weights_manifest()` for predictions.json and docs/weights.md.
"""
import hashlib
import os
from functools import lru_cache

import cv2
import numpy as np
import torch

WEIGHTS_DIR = os.environ.get("CAP_WEIGHTS_DIR", "weights")
DET_W = os.path.join(WEIGHTS_DIR, "yolo11n.pt")
POSE_W = os.path.join(WEIGHTS_DIR, "yolo11n-pose.pt")
torch.set_num_threads(int(os.environ.get("CAP_THREADS", "4")))

# Kinetics normalisation used by torchvision video models
_K_MEAN = np.array([0.43216, 0.394666, 0.37645], np.float32)
_K_STD = np.array([0.22803, 0.22145, 0.216989], np.float32)
CLIP_LEN = 16
CLIP_SIZE = 112


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@lru_cache(maxsize=None)
def detector():
    from ultralytics import YOLO
    return YOLO(DET_W)


@lru_cache(maxsize=None)
def pose_model():
    from ultralytics import YOLO
    return YOLO(POSE_W)


@lru_cache(maxsize=None)
def video_backbone():
    from torchvision.models.video import r2plus1d_18, R2Plus1D_18_Weights
    m = r2plus1d_18(weights=R2Plus1D_18_Weights.KINETICS400_V1)
    m.fc = torch.nn.Identity()
    return m.eval()


def backbone_weight_path():
    from torchvision.models.video import R2Plus1D_18_Weights
    url = R2Plus1D_18_Weights.KINETICS400_V1.url
    return os.path.join(torch.hub.get_dir(), "checkpoints", os.path.basename(url)), url


def weights_manifest():
    bpath, burl = backbone_weight_path()
    return [
        {"name": "yolo11n.pt", "source": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt",
         "sha256": _sha256(DET_W), "role": "person_detector", "license": "AGPL-3.0 (Ultralytics), COCO-trained"},
        {"name": "yolo11n-pose.pt", "source": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n-pose.pt",
         "sha256": _sha256(POSE_W), "role": "pose", "license": "AGPL-3.0 (Ultralytics), COCO-keypoints-trained"},
        {"name": os.path.basename(bpath), "source": burl, "sha256": _sha256(bpath), "role": "video_backbone",
         "license": "BSD-3-Clause (torchvision code/weights), Kinetics-400-trained"},
    ] + _clip_entry()


def _clip_entry():
    from . import clip_state
    p, url = clip_state.weight_path()
    if not os.path.exists(p):
        return []
    return [{"name": "CLIP ViT-B-32 (openai)", "source": url, "sha256": _sha256(p), "role": "other",
             "license": "MIT (OpenAI CLIP), WebImageText-400M-trained; frame/state image encoder"}]


def iou(a, b):
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / u if u > 0 else 0.0


def detect_persons(frame_bgr, conf=0.25, imgsz=640):
    """Returns (N,5) xyxy+score of COCO 'person' detections in frame pixels."""
    r = detector().predict(frame_bgr, imgsz=imgsz, conf=conf, classes=[0], verbose=False)[0]
    if r.boxes is None or len(r.boxes) == 0:
        return np.zeros((0, 5), np.float32)
    return np.concatenate([r.boxes.xyxy.cpu().numpy(), r.boxes.conf.cpu().numpy()[:, None]], 1)


def pose_in_crops(crops, crop_origins, target_boxes, imgsz=320):
    """Run pose on a batch of crops; for each crop pick the person whose box best matches the
    target (GT) box. Returns (B,17,3) keypoints in frame pixels (x, y, conf); zeros if none."""
    out = np.zeros((len(crops), 17, 3), np.float32)
    if not crops:
        return out
    res = pose_model().predict(crops, imgsz=imgsz, conf=0.1, verbose=False)
    for i, r in enumerate(res):
        if r.keypoints is None or r.boxes is None or len(r.boxes) == 0:
            continue
        ox, oy = crop_origins[i]
        boxes = r.boxes.xyxy.cpu().numpy() + np.array([ox, oy, ox, oy])
        j = int(np.argmax([iou(b, target_boxes[i]) for b in boxes]))
        if iou(boxes[j], target_boxes[i]) < 0.1:
            continue
        k = r.keypoints.data[j].cpu().numpy()  # (17,3)
        k[:, 0] += ox
        k[:, 1] += oy
        out[i] = k
    return out


def clip_tensor(frames_bgr, box):
    """Crop each frame to `box` (fixed for the clip), resize to 112, normalise. -> (3,T,112,112)."""
    x1, y1, x2, y2 = [int(round(v)) for v in box]
    arr = []
    for f in frames_bgr:
        c = f[y1:max(y2, y1 + 2), x1:max(x2, x1 + 2)]
        c = cv2.resize(c, (CLIP_SIZE, CLIP_SIZE), interpolation=cv2.INTER_AREA)
        arr.append(c[:, :, ::-1].astype(np.float32) / 255.0)
    a = (np.stack(arr) - _K_MEAN) / _K_STD  # (T,H,W,3)
    return torch.from_numpy(a.transpose(3, 0, 1, 2).copy())


@torch.no_grad()
def embed_clips(clips):
    """clips: list of (3,T,H,W) tensors -> (N,512) numpy."""
    if not clips:
        return np.zeros((0, 512), np.float32)
    return video_backbone()(torch.stack(clips)).numpy().astype(np.float32)
