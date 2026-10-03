"""Segment feature vector from cached perception outputs (shared by OOF training and the tool).

Blocks (all deterministic functions of one segment; nothing fitted here):
  emb      : R(2+1)D full-clip embedding (512)
  emb_dir  : emb_full - emb_rev (512) — antisymmetric under time reversal, i.e. encodes direction
  emb_half : emb_h2 - emb_h1 (512) — change from first to second half
  pose     : box-normalised keypoint statistics: start / end / delta means, plus box-shape trend
"""
import warnings

import numpy as np

SHOULDERS, HIPS, KNEES, WRISTS, ANKLES = (5, 6), (11, 12), (13, 14), (9, 10), (15, 16)
NOSE = 0


def _norm_kps(kps, boxes):
    """kps (T,17,3) frame px, boxes (T,4) -> (T,17,2) coordinates relative to the box:
    x in units of box height from the box centre, y in [0,1] top->bottom. Missing (conf<0.3) -> nan."""
    h = np.maximum(boxes[:, 3] - boxes[:, 1], 1.0)[:, None]
    cx = ((boxes[:, 0] + boxes[:, 2]) / 2)[:, None]
    x = (kps[..., 0] - cx) / h
    y = (kps[..., 1] - boxes[:, 1:2]) / h
    xy = np.stack([x, y], -1)
    xy[kps[..., 2] < 0.3] = np.nan
    return xy


def _nanmean(a, axis):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # all-nan slices -> 0 below
        m = np.nanmean(a, axis=axis)
    return np.nan_to_num(m, nan=0.0)


def pose_block(kps, boxes):
    T = kps.shape[0]
    q = max(T // 4, 1)
    xy = _norm_kps(kps, boxes)                  # (T,17,2)
    start, end = _nanmean(xy[:q], 0), _nanmean(xy[-q:], 0)   # (17,2)
    delta = end - start
    # torso / limb summary curves (T,)
    def joint_y(idx):
        return _nanmean(xy[:, list(idx), 1], 1)
    hip_y, sh_y, knee_y, wr_y = joint_y(HIPS), joint_y(SHOULDERS), joint_y(KNEES), joint_y(WRISTS)
    wr_x = _nanmean(np.abs(xy[:, list(WRISTS), 0]), 1)
    torso = hip_y - sh_y                        # torso vertical extent (shrinks when seated/bent)
    w = boxes[:, 2] - boxes[:, 0]
    hgt = np.maximum(boxes[:, 3] - boxes[:, 1], 1.0)
    aspect = w / hgt
    scale = hgt / hgt[0]
    bottom = (boxes[:, 3] - boxes[0, 3]) / hgt[0]
    top = (boxes[:, 1] - boxes[0, 1]) / hgt[0]
    curves = np.stack([hip_y, sh_y, knee_y, wr_y, wr_x, torso, aspect, scale, bottom, top], 0)  # (10,T)
    # resample each curve to 4 bins + slope
    bins = np.stack([c.reshape(4, -1).mean(1) if T % 4 == 0 else np.interp(np.linspace(0, T - 1, 4), np.arange(T), c)
                     for c in curves])        # (10,4)
    slope = np.array([np.polyfit(np.arange(T), c, 1)[0] * T for c in curves])
    vis = (kps[..., 2] > 0.3).mean(0)           # per-joint visibility (17,)
    return np.concatenate([start.ravel(), end.ravel(), delta.ravel(), bins.ravel(), slope, vis]).astype(np.float32)


POSE_DIM = 17 * 2 * 3 + 10 * 4 + 10 + 17


def segment_vector(d):
    """d: dict with emb_full, emb_h1, emb_h2, emb_rev (512,), kps (T,17,3), boxes (T,4)."""
    return np.concatenate([
        d["emb_full"], d["emb_full"] - d["emb_rev"], d["emb_h2"] - d["emb_h1"],
        pose_block(d["kps"], d["boxes"]),
    ]).astype(np.float32)


BLOCKS = {"emb": slice(0, 512), "emb_dir": slice(512, 1024), "emb_half": slice(1024, 1536),
          "pose": slice(1536, 1536 + POSE_DIM)}


def clip_blocks(emb, sims):
    """emb (N,F,512), sims (N,F,P) -> dict of CLIP state blocks (start = first 2 frames, end = last 2)."""
    st, en = emb[:, :2].mean(1), emb[:, -2:].mean(1)
    ss, se = sims[:, :2].mean(1), sims[:, -2:].mean(1)
    return {"clip_mean": emb.mean(1), "clip_delta": en - st,
            "sims": np.concatenate([ss, se, se - ss], 1) * 10.0}


# Candidate feature sets; the choice among them is made inside the inner CV (contract §5).
FEATURE_SETS = {
    "state+pose": ["clip_mean", "clip_delta", "sims", "pose"],
    "state+pose+motion": ["clip_mean", "clip_delta", "sims", "pose", "emb", "emb_dir", "emb_half"],
}


REVERSIBLE = {"clip_mean", "clip_delta", "sims", "pose"}


def reversed_blocks(z_seg, z_clip):
    """Blocks of the time-reversed segment (exact for state/pose blocks; used for augmentation)."""
    emb, sims = z_clip["emb"][:, ::-1], z_clip["sims"][:, ::-1]
    out = clip_blocks(emb, sims)
    n = len(z_seg["segment_id"])
    out["pose"] = np.stack([pose_block(z_seg["kps"][i][::-1], z_seg["boxes"][i][::-1]) for i in range(n)])
    return out


def all_blocks(z_seg, z_clip):
    X = matrix_from_cache(z_seg)
    out = {k: X[:, s] for k, s in BLOCKS.items()}
    out.update(clip_blocks(z_clip["emb"], z_clip["sims"]))
    return out


def single_blocks(d, clip_emb, clip_sims):
    """Same blocks for one segment/window (tool path)."""
    v = segment_vector(d)
    out = {k: v[s][None] for k, s in BLOCKS.items()}
    out.update(clip_blocks(clip_emb[None], clip_sims[None]))
    return out


def stack(blocks, names):
    return np.concatenate([blocks[n] for n in names], 1).astype(np.float32)


def matrix_from_cache(z):
    """z: loaded segments.npz -> (N,D) feature matrix in manifest order."""
    n = len(z["segment_id"])
    X = np.zeros((n, 1536 + POSE_DIM), np.float32)
    for i in range(n):
        if not z["has_track"][i]:
            continue
        X[i] = segment_vector({k: z[k][i] for k in ("emb_full", "emb_h1", "emb_h2", "emb_rev", "kps", "boxes")})
    return X
