import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.perception.annotations import Track, _scale_factor, expand_box, load_video_gt  # noqa: E402

ANN = "data/cap_detection_handheld_val/annotations"


def test_interpolation_and_clamp():
    t = Track("t", np.array([0, 10]), np.array([[0, 0, 10, 10], [10, 10, 20, 20]], float))
    b = t.box_at([5, -3, 99])
    assert np.allclose(b[0], [5, 5, 15, 15]) and np.allclose(b[1], [0, 0, 10, 10]) and np.allclose(b[2], [10, 10, 20, 20])
    assert list(t.covers([0, 5, 11])) == [True, True, False]


def test_scale_factor():
    assert abs(_scale_factor('-filter_complex "[s0]scale=512:910[s1]"', 1080, 1920) - 1080 / 512) < 1e-9
    assert _scale_factor("", 1080, 1920) == 1.0


def test_expand_box_clips():
    b = expand_box([0, 0, 100, 100], 120, 120, pad=0.5)
    assert b[0] == 0 and b[1] == 0 and b[2] <= 119 and b[3] <= 119


def test_loader_never_exposes_personal_fields():
    fn = sorted(os.listdir(ANN))[0]
    gt = load_video_gt(os.path.join(ANN, fn))
    blob = json.dumps(gt.__dict__, default=lambda o: getattr(o, "__dict__", str(o)))
    for bad in ("subject_ids", "ipAddress", "device_identifier"):
        assert bad not in blob
    # boxes are rescaled into native pixel space
    tr = next(iter(gt.tracks.values()))
    assert tr.keyboxes[:, 2].max() <= gt.width + 1 and tr.keyboxes[:, 3].max() <= gt.height + 1
    assert tr.keyboxes[:, 3].max() > 0.4 * gt.height
