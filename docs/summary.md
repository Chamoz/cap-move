# CAP Activity Review Tool — Summary (2026-10-03)

## Status
- Contract v0.1 is **frozen** (approved 07:26Z). Stage A is **built and running**.
- 24 tests pass, and `predictions.json` is VALID (167 segments, out-of-fold).
- Not yet checked in a real browser: there is none on the host. Click through the pages once before the demo.
- Stage B has **not started**. It needs a cost estimate and your approval.

## Open the tool on your PC

The server listens on `127.0.0.1:8000` on the workshop machine, so you reach it through a tunnel.

**Option A — code-server proxy (easiest)**
1. Log in to the workshop code-server in your browser as usual.
2. Open **https://d2wxa2we707rwy.cloudfront.net/proxy/8000/**. Keep the trailing `/`, otherwise styles and scripts won't load.

**Option B — Ports panel in code-server / VS Code**
Open the Ports panel and forward 8000, then click the globe icon.

**Option C — SSH tunnel (if you have SSH access)**
```bash
ssh -L 8000:127.0.0.1:8000 <user>@<workshop-host>
# then open http://localhost:8000/ on your PC
```

The tool has no login, so don't expose port 8000 publicly. Options A and B stay behind the code-server login.

## Start / stop the server (on the workshop machine)
```bash
cd /Workshop/cap-position
.venv/bin/python -m src.app.server            # start (Ctrl+C to stop)
# or in background:
nohup .venv/bin/python -m src.app.server > artifacts/server.log 2>&1 & echo $! > artifacts/server.pid
kill $(cat artifacts/server.pid)              # stop
```

## Pages
| Page | What it shows |
|---|---|
| `./` Review | Val videos (GT vs model) or Upload (experimental). Shows the person box overlay, a timeline, calibrated probabilities and a ⚑ review flag, with Confirm / Correct / Reject. Keys: space, n/p, f, c, r |
| `gallery` | Failure gallery: silent errors, caught errors and over-cautious flags. Filter by pair, class, collector, device, fps and person scale |
| `report` | Metrics, reliability diagram, risk–coverage curve, pair errors and breakdowns |

## Results (out-of-fold, 167 segments)
| | Acc | Macro-F1 | ECE ↓ | AURC ↓ | Coverage | Sel. acc |
|---|---|---|---|---|---|---|
| Model | 0.437 | 0.433 | 0.096 | 0.467 | 0.102 | 0.471 |
| Uniform prior | 0.078 | 0.018 | 0.047 | 0.919 | — | — |

Error rate per pair: sit/stand 0.18, pick/put 0.52, open/close 0.59, don/doff 0.88.
**The 20% selective-risk target is not met.** The tool flags about 90% of segments, and 9 errors go through unflagged. The cause is too little training data (167 segments), so Stage B data is the fix.

## Method in one paragraph
All models are frozen and pretrained, and run on the ground-truth person track: YOLO11n-pose keypoints, CLIP ViT-B/32 before/after "state" features, and R(2+1)D-18 as a candidate feature set. A logistic-regression head is trained with nested 5-fold CV grouped by collector. Inside the inner CV it selects the feature set, C, the time-reversal augmentation weight, the temperature and the abstention threshold, so no fold ever sees its own data. CLIP and R(2+1)D were added on top of the Q7 choice; both are listed in `docs/weights.md`.

## Rebuild everything (≈20 min on 4 vCPU)
```bash
.venv/bin/python scripts/extract_features.py && .venv/bin/python scripts/extract_clip.py
.venv/bin/python scripts/train_oof.py && .venv/bin/python scripts/validate_predictions.py predictions.json
.venv/bin/python scripts/score.py predictions.json && .venv/bin/python scripts/build_gallery.py
.venv/bin/python -m pytest -q tests
```

## Key files
`README.md` (full details) · `docs/shared-contract.md` · `docs/weights.md` · `docs/effort-log.md` · `predictions.json` · `artifacts/report/report.md` · `aidlc-docs/audit.md`

## Next
1. Check the UI in a browser via Option A.
2. Decide on Stage B. If yes, I'll prepare the cost and time estimate first (the archive is 308.7 GB).
