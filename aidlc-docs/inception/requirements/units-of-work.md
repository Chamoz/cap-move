# Units of Work

| Unit | Scope | Key outputs | Depends on | Est. |
|---|---|---|---|---|
| U1 Contract & data | Manifest generator, schema, validator, scorer | `manifests/val_segments.csv`, `configs/predictions.schema.json`, `scripts/validate_predictions.py` ✅ drafted; `scripts/score.py` | — | 1 h (mostly done) |
| U2 Perception | OpenCV decode, detector+ByteTrack, pose, GT-track crops, feature cache (`artifacts/features/*.npz`) | `src/perception/`, cached val features | U1 | 3 h |
| U3 Classify · calibrate · abstain | Features → head per outer fold; inner-CV temperature + thresholds; OOF predictions; score report | `src/model/`, `predictions.json` (Stage A), `artifacts/report/` | U2 | 3 h |
| U4 Review tool | FastAPI + vanilla HTML/JS: upload, video+canvas overlay, timeline, confidence, review flags with Confirm/Correct/Reject, val-video mode | `src/app/`, `web/` | U2 (overlays), U3 (model) | 4 h |
| U5 Failure gallery & report view | Gallery page with filters; reliability diagram and risk–coverage curve | `web/gallery`, thumbnails in `artifacts/gallery/` | U3, U4 | 2 h |
| U6 Docs & demo | `docs/weights.md`, `docs/effort-log.md`, README (run steps, attribution), demo script | docs | all | 1 h |
| U7 Stage B (optional) | Cost/time estimate → **user approval** → one-pass extraction of 8 classes from one trainval archive into a dedicated bucket, excluding the 32 val collectors; retrain head; separate run | `predictions_stageB.json` | U3 + approval | ≥ 6 h, gated |

## Dependency graph
```
U1 ──> U2 ──> U3 ──> U5
        │      │      ^
        └────> U4 ────┘
U6 continuous · U7 only after U3/U4/U5 demo-ready and user approval
```

## Schedule to demo (2026-10-04)
- Day 1 (today, after approval): U2 → U3 → first valid Stage A `predictions.json`; U4 skeleton with val-video mode.
- Day 2 morning: U4 upload path + review actions, U5, U6, end-to-end rehearsal. Stage B is only considered if all of Stage A is demo-ready.

## Definition of done (Stage A)
- `scripts/validate_predictions.py predictions.json` → VALID, 167 segments.
- `score.py` report includes AURC, ECE, Macro-F1, coverage/selective accuracy, per-pair confusion, and baselines.
- Tool demo: upload → overlays + timeline + confidence + review flags; gallery filterable by pair, collector, viewpoint proxy.
- Contract §2 check: grep shows no subject_ids/ipAddress/device_identifier in `artifacts/`, `predictions.json`, or `web/`.
