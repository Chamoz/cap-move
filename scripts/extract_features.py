#!/usr/bin/env python3
"""U2: extract cached perception features for every manifest segment.

Output: artifacts/features/segments.npz (numeric arrays only, keyed by manifest order) and
artifacts/features/meta.json (weights, timings). Idempotent per video via artifacts/features/per_video/.
"""
import argparse
import csv
import json
import os
import sys
import time
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.perception import models  # noqa: E402
from src.perception.annotations import load_all  # noqa: E402
from src.perception.features import T, extract_video  # noqa: E402

KEYS = ["frames", "boxes", "covered", "kps", "union_box", "emb_full", "emb_h1", "emb_h2", "emb_rev"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="manifests/val_segments.csv")
    ap.add_argument("--out", default="artifacts/features")
    ap.add_argument("--limit-videos", type=int, default=0)
    args = ap.parse_args()

    rows = list(csv.DictReader(open(args.manifest)))
    by_video = defaultdict(list)
    for r in rows:
        by_video[r["video_id"]].append(r)
    gts = load_all()
    pv_dir = os.path.join(args.out, "per_video")
    os.makedirs(pv_dir, exist_ok=True)

    t0 = time.time()
    vids = sorted(by_video)[: args.limit_videos or None]
    for i, vid in enumerate(vids):
        fp = os.path.join(pv_dir, f"{vid}.npz")
        if os.path.exists(fp):
            continue
        ts = time.time()
        res = extract_video(gts[vid], by_video[vid])
        flat = {}
        for sid, d in res.items():
            flat[f"{sid}|has_track"] = np.array(d["has_track"])
            for k in KEYS:
                if k in d:
                    flat[f"{sid}|{k}"] = d[k]
        np.savez_compressed(fp + ".tmp.npz", **flat)
        os.replace(fp + ".tmp.npz", fp)
        print(f"[{i + 1}/{len(vids)}] {vid[:12]} segs={len(res)} {time.time() - ts:.1f}s", flush=True)

    if args.limit_videos:
        return
    # assemble in manifest order
    n = len(rows)
    out = {"segment_id": np.array([r["segment_id"] for r in rows]),
           "has_track": np.zeros(n, bool),
           "frames": np.zeros((n, T), np.int32), "boxes": np.zeros((n, T, 4), np.float32),
           "covered": np.zeros((n, T), bool), "kps": np.zeros((n, T, 17, 3), np.float32),
           "union_box": np.zeros((n, 4), np.float32)}
    for k in ("emb_full", "emb_h1", "emb_h2", "emb_rev"):
        out[k] = np.zeros((n, 512), np.float32)
    cache = {}
    for i, r in enumerate(rows):
        vid = r["video_id"]
        if vid not in cache:
            cache = {vid: np.load(os.path.join(pv_dir, f"{vid}.npz"))}
        z = cache[vid]
        sid = r["segment_id"]
        out["has_track"][i] = bool(z[f"{sid}|has_track"])
        if out["has_track"][i]:
            for k in KEYS:
                out[k][i] = z[f"{sid}|{k}"]
    np.savez_compressed(os.path.join(args.out, "segments.npz"), **out)
    kp_rate = float((out["kps"][..., 2].max(-1) > 0).mean())
    meta = {"n_segments": n, "n_with_track": int(out["has_track"].sum()), "T": T,
            "pose_detected_frame_rate": round(kp_rate, 4), "weights": models.weights_manifest(),
            "elapsed_s_this_run": round(time.time() - t0, 1)}
    json.dump(meta, open(os.path.join(args.out, "meta.json"), "w"), indent=2)
    print(json.dumps({k: v for k, v in meta.items() if k != "weights"}))


if __name__ == "__main__":
    main()
