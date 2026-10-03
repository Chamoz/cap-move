# Requirements — CAP Activity Review Tool

Status: DRAFT for approval · Depth: Standard · Request type: greenfield prototype · Complexity: moderate (ML + UI, 1.5-day deadline)

## 1. Intent analysis
Activity recognisers mix up look-alike motions and still report high confidence. In patient or elderly
monitoring, those wrong records go unnoticed. This prototype shows a reviewer what the model saw, how
sure it really is, and when it gives the decision back to a human. Success is measured by calibration
and selective risk, not accuracy alone.

## 2. Facts that constrain the design (verified)
| Fact | Evidence | Consequence |
|---|---|---|
| 167 in-scope segments, 41 videos, 28 collectors; 8–39 segments per class (sit_down 13, stand_up 9) | `build_manifest.py` output | Too little data to train a deep model from scratch → frozen pretrained features + small head; wide confidence intervals; report them |
| 1 annotated person track per video, boxes every ~6 frames, linear interpolation | vipy JSON | GT track available for scored path; open-world tracker only needed for uploads |
| Portrait handheld phones; 33 device types; 10/15/30 fps; 3 resolutions | JSON attributes | "Viewpoint" breakdown uses proxies (device family, fps, resolution, person-box scale); no camera-pose labels exist |
| No GPU, 4 vCPU, 15 GB RAM | `nproc`, `free`, no `nvidia-smi` | CPU-only models (nano/small); pre-compute features for val set offline |
| `ref.csv` ≠ JSON by ±1 frame on most rows | diff script | JSON is ground truth (contract §1) |
| No system ffmpeg | `which` | Decode via OpenCV wheel (bundles FFmpeg); browser playback of original MP4 (H.264) |

## 3. Functional requirements
| ID | Requirement | Acceptance criterion |
|---|---|---|
| FR-1 | Upload a video (mp4/mov ≤ 200 MB, ≤ 2 min) | File is accepted, validated by type, size and decodability; rejection gives a clear message |
| FR-2 | Detect and track people; draw bbox + track id per frame | Overlay is synchronised with playback (±1 frame at native fps); ids stable across frames |
| FR-3 | Activity timeline per track | Segments rendered as coloured bars on a time axis; click seeks the video |
| FR-4 | Calibrated confidence per segment | Shown as a % with its top-2 classes; calibrated with out-of-fold temperature scaling |
| FR-5 | Abstention / "needs human review" | Segments below the threshold or with a small confusable-pair margin are flagged; reviewer can Confirm / Correct (choose a class) / Reject; decision saved locally with timestamp |
| FR-6 | Failure gallery | Grid of OOF errors and abstentions, filterable by confusable pair, class, collector_id (8-char prefix), device family, fps, box scale; each card shows true vs predicted, confidence, and a clip/keyframe strip |
| FR-7 | Scored predictions | `predictions.json` covering all 167 manifest segments, OOF per contract §5, passes `scripts/validate_predictions.py` |
| FR-8 | Evaluation report | `scripts/score.py` produces metrics from contract §6 plus a reliability diagram and a risk–coverage curve, viewable in the tool |
| FR-9 | Val-video mode | Choosing a val video from a list shows GT next to predictions, with OOF predictions for scored segments |
| FR-10 | Weights list | `docs/weights.md`: name, source URL, sha256, license, role |
| FR-11 | Effort log | `docs/effort-log.md` by AI-DLC phase: prompts/turns, wall-clock, human interventions, review defects |

## 4. Non-functional requirements
| ID | Requirement |
|---|---|
| NFR-1 Privacy | Contract §2: no identification or re-ID across videos, no subject_ids/ip/device_identifier in any output; media never leaves the host; all models run locally |
| NFR-2 Security (lite) | Server binds 127.0.0.1 with **no authentication** (single-user local demo); upload size/type limits; random server-side filenames (no path traversal); uploads stored under `artifacts/uploads/` and deletable |
| NFR-3 Performance | Val set features pre-computed once (target < 60 min on CPU). Upload processing ≤ ~1× video duration × 3 for a 30 s clip on CPU, with a progress indicator |
| NFR-4 Reproducibility | Fixed seeds; pinned dependencies (`uv` lock); `make predictions` regenerates `predictions.json` deterministically from cached features |
| NFR-5 Accessibility | Keyboard-operable controls, text labels in addition to colour on the timeline, contrast ≥ 4.5:1, ARIA labels on review buttons |
| NFR-6 Licensing | CAP attribution displayed; weight licenses recorded; AGPL components (if chosen) noted as prototype-only |

## 5. Approach (proposed, Stage A)
1. **Perception**: person detector + tracker (YOLO11n + ByteTrack, CPU) for uploads; for scored segments use the GT track box. Pose keypoints per frame (YOLO11n-pose, COCO-17).
2. **Segment features** (per segment, from the GT box crop): (a) pose-trajectory features that carry the *direction of time* (hip/shoulder height change, wrist-to-hip distance change, start-vs-end deltas). These target the reversed-motion pairs. (b) frozen clip embedding (X3D-S or similar Kinetics-400 backbone, CPU) over 16 frames.
3. **Head**: multinomial logistic regression (or small MLP), trained per outer fold on 4 folds.
4. **Calibration**: temperature scaling fitted with inner group-CV inside the training folds only. **Abstention**: threshold on calibrated confidence, plus a confusable-pair margin rule (top-2 are a pair and p1 − p2 < m), both chosen on the training folds to meet a target selective risk.
5. **Open-world uploads**: sliding windows (≈2 s, stride 0.5 s) along each track → per-window probs → merge consecutive windows with the same label; windows below the threshold are shown as "uncertain / needs review". This path is not scored (contract §5); a visible banner says so.

## 6. Out of scope
Training on any data besides the val file (Stage A); identity, face or re-ID features; cloud hosting;
multi-user auth; real-time streaming; classes beyond the 8.

## 7. Risks
| Risk | Mitigation |
|---|---|
| Tiny classes (stand_up n=9) → unstable folds | Report per-class n and bootstrap CIs; abstention protects precision |
| Open-world timeline quality on uploads is unvalidated | Label it as experimental; demo primarily in val-video mode |
| CPU latency for upload processing | Nano models, frame stride 2–3, cache results per upload hash |
| Deadline (≈1.5 days) | Unit order prioritises a working end-to-end slice by end of Day 1 (see units-of-work.md) |
