"""Classifier head, temperature scaling and abstention with strict nested out-of-fold fitting.

For outer fold k (contract §5):
  train = segments of the other 4 folds
  1. inner leave-one-fold-out over those 4 folds -> inner-OOF logits for every training segment
     for each C in the grid; pick C by inner-OOF log-loss
  2. fit temperature on the inner-OOF logits (chosen C)
  3. pick abstention threshold on the calibrated inner-OOF probs: smallest confidence threshold
     whose selective risk <= target (max coverage)
  4. refit the head on all 4 training folds, apply (head, T, tau) to fold k
Fold k is never seen by any step that produces its predictions.
"""
from dataclasses import dataclass
from typing import List

import numpy as np
from scipy.optimize import minimize_scalar
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

CLASSES = ["sit_down", "stand_up", "pick_up_object", "put_down_object",
           "open", "close", "put_on_wearable", "take_off_wearable"]
K = len(CLASSES)
PARTNER = np.array([1, 0, 3, 2, 5, 4, 7, 6])
C_GRID = (0.001, 0.003, 0.01, 0.03)


def make_head(C):
    return make_pipeline(StandardScaler(),
                         LogisticRegression(C=C, max_iter=3000, class_weight="balanced"))


def full_logits(model, X):
    """Decision function laid out over all K classes (classes absent from training get -inf-ish)."""
    lr = model[-1]
    raw = model.decision_function(X)
    out = np.full((X.shape[0], K), -30.0)
    out[:, lr.classes_] = raw
    return out


def softmax(z):
    z = z - z.max(1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(1, keepdims=True)


def nll(p, y):
    return float(-np.mean(np.log(np.clip(p[np.arange(len(y)), y], 1e-12, 1))))


def fit_temperature(logits, y):
    r = minimize_scalar(lambda t: nll(softmax(logits / t), y), bounds=(0.05, 20.0), method="bounded")
    return float(r.x)


def pick_threshold(probs, y, target_risk):
    """Max-coverage confidence threshold with selective risk <= target on (probs, y).
    Accept iff conf >= tau. If no non-empty set reaches the target, tau = 1.0 (abstain on all)."""
    conf = probs.max(1)
    correct = probs.argmax(1) == y
    order = np.argsort(-conf, kind="stable")
    c_sorted, ok_sorted = conf[order], correct[order]
    risk = np.cumsum(~ok_sorted) / np.arange(1, len(y) + 1)
    best = None
    for i in range(len(y)):
        # only cut between distinct confidence values
        if i + 1 < len(y) and c_sorted[i + 1] == c_sorted[i]:
            continue
        if risk[i] <= target_risk:
            best = i
    return float(c_sorted[best]) if best is not None else 1.0


AUG_WEIGHTS = (0.0, 0.5)


def fit_head(C, X, y, Xrev=None, w_aug=0.0):
    """Fit; optionally add time-reversed copies labelled with the partner class (weight w_aug)."""
    if Xrev is None or w_aug <= 0:
        return make_head(C).fit(X, y)
    Xa = np.concatenate([X, Xrev])
    ya = np.concatenate([y, PARTNER[y]])
    sw = np.concatenate([np.ones(len(y)), np.full(len(y), w_aug)])
    return make_head(C).fit(Xa, ya, logisticregression__sample_weight=sw)


def inner_oof(X, y, folds, C, Xrev=None, w_aug=0.0):
    out = np.zeros((len(y), K))
    for f in np.unique(folds):
        tr, te = folds != f, folds == f
        m = fit_head(C, X[tr], y[tr], None if Xrev is None else Xrev[tr], w_aug)
        out[te] = full_logits(m, X[te])
    return out


@dataclass
class FoldResult:
    fold: int
    C: float
    temperature: float
    threshold: float
    logits: np.ndarray       # uncalibrated logits for test segments
    probs: np.ndarray        # calibrated
    test_idx: np.ndarray
    feature_set: str = ""


def _as_sets(X):
    """Normalise to {name: (X, Xrev_or_None)}."""
    if not isinstance(X, dict):
        X = {"x": X}
    return {n: (v if isinstance(v, tuple) else (v, None)) for n, v in X.items()}


def _sub(pair, idx):
    X, Xr = pair
    return X[idx], (None if Xr is None else Xr[idx])


def select_config(sets, y, folds):
    """Inner leave-one-fold-out over (feature set x C x reversal-aug weight) by NLL.
    Returns (set_name, C, w_aug, inner logits)."""
    best = None
    for name, (Xs, Xr) in sets.items():
        for w in (AUG_WEIGHTS if Xr is not None else (0.0,)):
            for C in C_GRID:
                lg = inner_oof(Xs, y, folds, C, Xr, w)
                s = nll(softmax(lg), y)
                if best is None or s < best[0]:
                    best = (s, name, C, w, lg)
    return best[1:]


def fit_predict_fold(X, y, folds, k, target_risk):
    """X: (N,D) array, or {set_name: X | (X, X_time_reversed)}; every selection/fit uses only folds != k."""
    sets = _as_sets(X)
    tr = np.where(folds != k)[0]
    te = np.where(folds == k)[0]
    ytr, ftr = y[tr], folds[tr]
    name, C, w, inner = select_config({n: _sub(p, tr) for n, p in sets.items()}, ytr, ftr)
    T = fit_temperature(inner, ytr)
    tau = pick_threshold(softmax(inner / T), ytr, target_risk)
    Xtr, Xrtr = _sub(sets[name], tr)
    head = fit_head(C, Xtr, ytr, Xrtr, w)
    lg = full_logits(head, sets[name][0][te])
    fr = FoldResult(k, C, T, tau, lg, softmax(lg / T), te, name)
    fr.aug_weight = w
    return fr, head


def run_oof(X, y, folds, target_risk=0.20) -> List[FoldResult]:
    return [fit_predict_fold(X, y, folds, k, target_risk)[0] for k in range(5)]


def fit_deploy(X, y, folds, target_risk=0.20):
    """Model for the review tool (not scored): set, C, T, tau from 5-fold OOF on all val; head on all val."""
    sets = _as_sets(X)
    name, C, w, inner = select_config(sets, y, folds)
    T = fit_temperature(inner, y)
    tau = pick_threshold(softmax(inner / T), y, target_risk)
    Xs, Xr = sets[name]
    return fit_head(C, Xs, y, Xr, w), name, C, w, T, tau


def abstain_decision(probs_row, tau):
    """-> (abstain, reason or None, second_class_idx)."""
    o = np.argsort(-probs_row)
    top, second = int(o[0]), int(o[1])
    if probs_row[top] >= tau:
        return False, None, second
    reason = "confusable_pair_margin" if PARTNER[top] == second else "low_confidence"
    return True, reason, second
