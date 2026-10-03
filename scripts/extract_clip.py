#!/usr/bin/env python3
"""U2b: CLIP state features for every manifest segment -> artifacts/features/clip.npz
(arrays in manifest order: emb (N,8,512), sims (N,8,P))."""
import csv
import json
import os
import sys
import time
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.perception import clip_state as CS  # noqa: E402
from src.perception.annotations import expand_box, load_all, sample_frames, video_abspath  # noqa: E402
from src.perception.features import read_frames  # noqa: E402


def segment_crops(frames, tr, s, e, W, H):
    fidx = sample_frames(s, e, CS.N_FRAMES)
    boxes = tr.box_at(fidx)
    crops = []
    for f, b in zip(fidx, boxes):
        cb = expand_box(b, W, H, pad=CS.CTX_PAD, square=True).astype(int)
        crops.append(frames[int(f)][cb[1]:cb[3] + 1, cb[0]:cb[2] + 1])
    return crops


def main():
    rows = list(csv.DictReader(open("manifests/val_segments.csv")))
    gts = load_all()
    by_video = defaultdict(list)
    for i, r in enumerate(rows):
        by_video[r["video_id"]].append(i)
    n, P = len(rows), len(CS.PROMPTS)
    emb = np.zeros((n, CS.N_FRAMES, 512), np.float32)
    sims = np.zeros((n, CS.N_FRAMES, P), np.float32)
    t0 = time.time()
    for k, (vid, idxs) in enumerate(sorted(by_video.items())):
        g = gts[vid]
        want = [int(f) for i in idxs for f in sample_frames(int(rows[i]["start_frame"]), int(rows[i]["end_frame"]), CS.N_FRAMES)]
        frames = read_frames(video_abspath(g), want)
        for i in idxs:
            r = rows[i]
            tr = g.tracks.get(r["track_id"])
            if tr is None:
                continue
            crops = segment_crops(frames, tr, int(r["start_frame"]), int(r["end_frame"]), g.width, g.height)
            emb[i], sims[i] = CS.embed_crops(crops)
        print(f"[{k + 1}/{len(by_video)}] {vid[:12]} {time.time() - t0:.0f}s", flush=True)
    np.savez_compressed("artifacts/features/clip.npz", segment_id=np.array([r["segment_id"] for r in rows]),
                        emb=emb, sims=sims, prompts=np.array(CS.PROMPTS))
    meta_p = "artifacts/features/meta.json"
    meta = json.load(open(meta_p))
    meta["clip"] = {"model": f"{CS.MODEL}/{CS.PRETRAINED}", "n_frames": CS.N_FRAMES, "ctx_pad": CS.CTX_PAD,
                    "elapsed_s": round(time.time() - t0, 1)}
    json.dump(meta, open(meta_p, "w"), indent=2)


if __name__ == "__main__":
    main()
