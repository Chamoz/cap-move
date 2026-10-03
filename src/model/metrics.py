"""Contract §6 metrics. Pure numpy; used by scripts/score.py and the review tool's report page."""
import numpy as np

PAIRS = {"posture": (0, 1), "pick_vs_put": (2, 3), "open_vs_close": (4, 5), "don_vs_doff": (6, 7)}


def ece(conf, correct, n_bins=10):
    edges = np.linspace(0, 1, n_bins + 1)
    idx = np.clip(np.digitize(conf, edges[1:-1], right=True), 0, n_bins - 1)
    e = 0.0
    for b in range(n_bins):
        m = idx == b
        if m.any():
            e += m.mean() * abs(correct[m].mean() - conf[m].mean())
    return float(e)


def reliability(conf, correct, n_bins=10):
    edges = np.linspace(0, 1, n_bins + 1)
    idx = np.clip(np.digitize(conf, edges[1:-1], right=True), 0, n_bins - 1)
    out = []
    for b in range(n_bins):
        m = idx == b
        out.append({"lo": float(edges[b]), "hi": float(edges[b + 1]), "n": int(m.sum()),
                    "acc": float(correct[m].mean()) if m.any() else None,
                    "conf": float(conf[m].mean()) if m.any() else None})
    return out


def risk_coverage(conf, correct):
    order = np.argsort(-conf, kind="stable")
    err = np.cumsum(~correct[order])
    n = np.arange(1, len(conf) + 1)
    return n / len(conf), err / n


def aurc(conf, correct):
    _, risk = risk_coverage(conf, correct)
    return float(risk.mean())


def macro_f1(y, yhat, k):
    f = []
    for c in range(k):
        tp = np.sum((yhat == c) & (y == c))
        fp = np.sum((yhat == c) & (y != c))
        fn = np.sum((yhat != c) & (y == c))
        d = 2 * tp + fp + fn
        f.append(2 * tp / d if d else 0.0)
    return float(np.mean(f))


def summary(probs, y, abstain=None):
    probs = np.asarray(probs, float)
    y = np.asarray(y)
    k = probs.shape[1]
    yhat = probs.argmax(1)
    conf = probs.max(1)
    correct = yhat == y
    onehot = np.eye(k)[y]
    out = {"n": int(len(y)), "accuracy": float(correct.mean()), "macro_f1": macro_f1(y, yhat, k),
           "ece": ece(conf, correct), "nll": float(-np.mean(np.log(np.clip(probs[np.arange(len(y)), y], 1e-12, 1)))),
           "brier": float(np.mean(np.sum((probs - onehot) ** 2, 1))), "aurc": aurc(conf, correct)}
    if abstain is not None:
        acc = ~np.asarray(abstain, bool)
        out["coverage"] = float(acc.mean())
        out["selective_accuracy"] = float(correct[acc].mean()) if acc.any() else None
        out["selective_risk"] = (1 - out["selective_accuracy"]) if acc.any() else None
    pe = {}
    for name, (a, b) in PAIRS.items():
        m = (y == a) | (y == b)
        partner = np.where(y == a, b, a)
        pe[name] = {"n": int(m.sum()), "pair_swap_rate": float((yhat[m] == partner[m]).mean()) if m.any() else None,
                    "error_rate": float((~correct[m]).mean()) if m.any() else None}
    out["confusable_pair_error"] = pe
    return out


def confusion(y, yhat, k):
    m = np.zeros((k, k), int)
    for a, b in zip(y, yhat):
        m[a, b] += 1
    return m
