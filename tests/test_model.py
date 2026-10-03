import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.model import head as H  # noqa: E402
from src.model import metrics as M  # noqa: E402
from src.model.features import POSE_DIM, pose_block  # noqa: E402


def test_metrics_perfect_and_uniform():
    y = np.array([0, 1, 2, 3])
    P = np.eye(8)[y]
    s = M.summary(P, y, abstain=np.zeros(4, bool))
    assert s["accuracy"] == 1 and s["ece"] == 0 and s["aurc"] == 0 and s["coverage"] == 1
    U = np.full((4, 8), 1 / 8)
    u = M.summary(U, y)
    assert abs(u["nll"] - np.log(8)) < 1e-9 and abs(u["ece"] - (1 - 1 / 8 - 0.75 + 0.75)) < 1  # finite


def test_aurc_orders_by_confidence():
    conf = np.array([0.9, 0.8, 0.7, 0.6])
    good = np.array([True, True, False, False])
    bad = good[::-1].copy()
    assert M.aurc(conf, good) < M.aurc(conf, bad)


def test_pair_swap_rate():
    y = np.array([0, 0, 1, 1])
    P = np.eye(8)[[1, 0, 0, 1]]
    pe = M.summary(P, y)["confusable_pair_error"]["posture"]
    assert pe["n"] == 4 and pe["pair_swap_rate"] == 0.5


def test_threshold_meets_target_risk():
    rng = np.random.default_rng(0)
    n = 400
    y = rng.integers(0, 8, n)
    conf = rng.uniform(0.2, 1, n)
    correct = rng.uniform(0, 1, n) < conf  # higher conf -> more likely correct
    pred = np.where(correct, y, (y + 1) % 8)
    P = np.full((n, 8), 0.0)
    P[np.arange(n), pred] = conf
    P[np.arange(n), (pred + 2) % 8] = 1 - conf
    tau = H.pick_threshold(P, y, 0.2)
    acc = P.max(1) >= tau
    assert acc.any() and (P[acc].argmax(1) != y[acc]).mean() <= 0.2 + 1e-9


def test_threshold_abstains_all_when_unreachable():
    y = np.zeros(10, int)
    P = np.eye(8)[np.ones(10, int)] * 0.9 + 0.1 / 8
    assert H.pick_threshold(P, y, 0.2) == 1.0


def test_temperature_recovers_overconfidence():
    rng = np.random.default_rng(1)
    n = 2000
    y = rng.integers(0, 8, n)
    true_logits = rng.normal(0, 1, (n, 8))
    true_logits[np.arange(n), y] += 1.5
    p = H.softmax(true_logits)
    yy = np.array([rng.choice(8, p=row) for row in p])
    t = H.fit_temperature(true_logits * 3, yy)
    assert 2.3 < t < 3.7


def test_oof_never_uses_test_fold(monkeypatch):
    """Every fit inside fit_predict_fold(k) must see zero fold-k rows."""
    rng = np.random.default_rng(2)
    n = 200
    folds = np.repeat(np.arange(5), 40)
    y = np.tile(np.arange(8), 25)
    X = rng.normal(0, 1, (n, 6)) + y[:, None] * 0.5
    X[:, -1] = folds  # tag column identifies fold
    seen = []
    orig = H.make_head

    class Spy:
        def __init__(self, C):
            self.m = orig(C)

        def fit(self, Xf, yf):
            seen.append(set(np.unique(Xf[:, -1]).astype(int)))
            self.m.fit(Xf, yf)
            return self

        def __getitem__(self, i):
            return self.m[i]

        def decision_function(self, Xf):
            return self.m.decision_function(Xf)

    monkeypatch.setattr(H, "make_head", Spy)
    for k in range(5):
        seen.clear()
        fr, _ = H.fit_predict_fold(X, y, folds, k, 0.2)
        assert seen and all(k not in s for s in seen)
        assert set(folds[fr.test_idx]) == {k}
        assert np.allclose(fr.probs.sum(1), 1)


def test_abstain_reason():
    p = np.array([0.45, 0.40, 0.05, 0.05, 0.05, 0, 0, 0])
    assert H.abstain_decision(p, 0.6) == (True, "confusable_pair_margin", 1)
    p2 = np.array([0.45, 0.05, 0.40, 0.05, 0.05, 0, 0, 0])
    assert H.abstain_decision(p2, 0.6)[1] == "low_confidence"
    assert H.abstain_decision(p2, 0.4)[0] is False


def test_pose_block_shape_and_missing():
    T = 16
    kps = np.zeros((T, 17, 3), np.float32)
    boxes = np.tile(np.array([100, 100, 200, 400], np.float32), (T, 1))
    v = pose_block(kps, boxes)
    assert v.shape == (POSE_DIM,) and np.isfinite(v).all()


def test_tool_features_match_training_features():
    """single_blocks (tool/open-world path) must equal all_blocks (OOF training path) for the same segment."""
    import pytest
    from src.model.features import FEATURE_SETS, all_blocks, single_blocks, stack
    if not os.path.exists("artifacts/features/clip.npz"):
        pytest.skip("feature cache not built")
    z = np.load("artifacts/features/segments.npz")
    zc = np.load("artifacts/features/clip.npz")
    B = all_blocks(z, zc)
    for i in (0, 50, 166):
        d = {k: z[k][i] for k in ("emb_full", "emb_h1", "emb_h2", "emb_rev", "kps", "boxes")}
        sb = single_blocks(d, zc["emb"][i], zc["sims"][i])
        for names in FEATURE_SETS.values():
            assert np.allclose(stack(sb, names)[0], stack(B, names)[i], atol=1e-5)
