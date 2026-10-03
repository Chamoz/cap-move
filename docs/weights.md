# Weights used (Stage A)

The same list is in `predictions.json` under `run.weights`. All pretrained weights are used frozen. None of them was trained on CAP: their training sets (COCO 2017, Kinetics-400, OpenAI WIT-400M, released 2017–2021) were collected before CAP's public release. Nothing pretrained was fine-tuned.

| Name | Role | Used for | License / training data | Source | sha256 |
|---|---|---|---|---|---|
| `yolo11n.pt` | person_detector | Upload path: person detection for ByteTrack (val path uses GT tracks) | AGPL-3.0 (Ultralytics) · COCO | https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt | `0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1` |
| `yolo11n-pose.pt` | pose | 17 COCO keypoints in the GT/track box crop → pose block | AGPL-3.0 (Ultralytics) · COCO keypoints | https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n-pose.pt | `869e83fcdffdc7371fa4e34cd8e51c838cc729571d1635e5141e3075e9319dc0` |
| CLIP ViT-B/32 (OpenAI) | other (state encoder) | Frame embeddings + 16 state-prompt similarities at segment start/end → state blocks | MIT · WIT-400M web image-text | https://openaipublic.azureedge.net/clip/models/40d365715913c9da98579312b702a82c18be219cc2a73407c4526f58eba950af/ViT-B-32.pt | `40d365715913c9da98579312b702a82c18be219cc2a73407c4526f58eba950af` |
| `r2plus1d_18-91a641e6.pth` | video_backbone | Candidate motion block; the inner CV did not select it in any fold of the current run | BSD-3-Clause (torchvision) · Kinetics-400 | https://download.pytorch.org/models/r2plus1d_18-91a641e6.pth | `91a641e6c2ab531d1aca5f4321b4d802ec5c3babc15df855cdb6e39c6a1107c8` |
| `oof_logreg_heads_x5` | classifier_head | 5 per-fold L2 logistic-regression heads, refit deterministically by `scripts/train_oof.py`. The hash is an identity hash over the feature caches, the code and the candidate sets. | project-internal | in-repo | see `predictions.json` |
| `artifacts/model/deploy.pkl` | classifier_head (tool only) | Head fit on all 167 val segments, used for upload inference and **not scored**. Its C, augmentation, T and τ come from 5-fold OOF. | project-internal | in-repo | — |

The ByteTracker config is `bytetrack.yaml`, the Ultralytics 8.3.40 default. It has no weights.

## Licence note
The Ultralytics weights are AGPL-3.0. That is acceptable for this internal prototype, as approved in Q7. Distributing the tool or offering it as a network service would trigger AGPL obligations. Swapping in torchvision Keypoint R-CNN (BSD) would avoid them, at roughly 5–10× the CPU cost.
