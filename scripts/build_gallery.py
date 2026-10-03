#!/usr/bin/env python3
"""U5: failure-gallery index + local thumbnails from predictions.json (OOF) and the manifest.

Thumbnails (4-frame strips of the padded GT person crop, 120 px high) stay in artifacts/gallery/
(git-ignored, served only to localhost). Categories:
  silent_error   wrong and accepted (most dangerous: high confidence, not flagged)
  caught_error   wrong and abstained (flag worked)
  over_cautious  right but abstained (reviewer cost)
  correct        right and accepted
"""
import argparse
import csv
import json
import os
import sys
from collections import defaultdict

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.score import viewpoint_keys  # noqa: E402
from src.model.head import CLASSES, PARTNER  # noqa: E402
from src.perception.annotations import expand_box, load_all, sample_frames, video_abspath  # noqa: E402
from src.perception.features import read_frames  # noqa: E402

THUMB_H = 120


def category(wrong, abstain):
    if wrong:
        return "caught_error" if abstain else "silent_error"
    return "over_cautious" if abstain else "correct"


def strip(frames, tr, s, e, W, H):
    tiles = []
    for f in sample_frames(s, e, 4):
        b = tr.box_at([f])[0]
        cb = expand_box(b, W, H, pad=0.25).astype(int)
        crop = frames[int(f)][cb[1]:cb[3] + 1, cb[0]:cb[2] + 1].copy()
        bb = (b - [cb[0], cb[1], cb[0], cb[1]]).astype(int)
        cv2.rectangle(crop, (bb[0], bb[1]), (bb[2], bb[3]), (0, 200, 255), max(2, crop.shape[0] // 120))
        sc = THUMB_H / crop.shape[0]
        tiles.append(cv2.resize(crop, (max(1, int(crop.shape[1] * sc)), THUMB_H), interpolation=cv2.INTER_AREA))
    return np.concatenate(tiles, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--predictions", default="predictions.json")
    ap.add_argument("--out", default="artifacts/gallery")
    ap.add_argument("--no-thumbs", action="store_true")
    args = ap.parse_args()
    rows = list(csv.DictReader(open("manifests/val_segments.csv")))
    pred = {p["segment_id"]: p for p in json.load(open(args.predictions))["predictions"]}
    vp = viewpoint_keys(rows)
    items = []
    for r in rows:
        p = pred[r["segment_id"]]
        wrong = p["pred_class"] != r["class"]
        items.append({
            "segment_id": r["segment_id"], "video_id": r["video_id"], "collection_name": r["collection_name"],
            "collector": r["collector_id"][:8], "fold": int(r["fold"]), "gt_class": r["class"],
            "raw_label": r["raw_label"], "confusable_pair": r["confusable_pair"], "pred_class": p["pred_class"],
            "second_class": p.get("second_class"), "confidence": p["confidence"],
            "gt_prob": p["probs"][CLASSES.index(r["class"])], "abstain": p["abstain"],
            "abstain_reason": p.get("abstain_reason"), "wrong": wrong,
            "pair_swap": bool(wrong and CLASSES.index(p["pred_class"]) == PARTNER[CLASSES.index(r["class"])]),
            "category": category(wrong, p["abstain"]), "start_frame": int(r["start_frame"]),
            "end_frame": int(r["end_frame"]), "duration_s": round((int(r["end_frame"]) - int(r["start_frame"]) + 1) / float(r["fps"]), 2),
            **vp[r["segment_id"]]})
    os.makedirs(os.path.join(args.out, "thumbs"), exist_ok=True)
    if not args.no_thumbs:
        gts = load_all()
        by_vid = defaultdict(list)
        for r in rows:
            by_vid[r["video_id"]].append(r)
        for vid, rs in sorted(by_vid.items()):
            g = gts[vid]
            want = [int(f) for r in rs for f in sample_frames(int(r["start_frame"]), int(r["end_frame"]), 4)]
            frames = read_frames(video_abspath(g), want)
            for r in rs:
                tr = g.tracks.get(r["track_id"])
                if tr is None:
                    continue
                img = strip(frames, tr, int(r["start_frame"]), int(r["end_frame"]), g.width, g.height)
                cv2.imwrite(os.path.join(args.out, "thumbs", f"{r['segment_id']}.jpg"), img,
                            [cv2.IMWRITE_JPEG_QUALITY, 80])
    counts = defaultdict(int)
    for it in items:
        counts[it["category"]] += 1
    json.dump({"items": items, "counts": counts}, open(os.path.join(args.out, "index.json"), "w"))
    print(dict(counts))


if __name__ == "__main__":
    main()
