import numpy as np

from models import KMeansModel, MahalanobisModel, MLPAutoencoder, PCAModel, auroc


def _firmware_train_step(W, b, x, lr):
    """Line-by-line port of trainStep() in firmware/smoke_train/smoke_train.ino (float32)."""
    W = [w.copy() for w in W]
    b = [v.copy() for v in b]
    acts = [x.astype(np.float32)]
    for i in range(len(W)):
        y = np.zeros(len(b[i]), np.float32)
        for o in range(len(b[i])):
            s = b[i][o]
            for k in range(len(acts[-1])):
                s += W[i][o, k] * acts[-1][k]
            y[o] = s if (i == len(W) - 1 or s > 0) else 0.0
        acts.append(y)
    d = len(x)
    dy = (2.0 * (acts[-1] - x) / d).astype(np.float32)
    for i in range(len(W) - 1, -1, -1):
        relu = i < len(W) - 1
        if relu:
            dy = np.where(acts[i + 1] <= 0, 0.0, dy).astype(np.float32)
        dx = np.zeros(W[i].shape[1], np.float32)
        for o in range(W[i].shape[0]):
            g = dy[o]
            for k in range(W[i].shape[1]):
                dx[k] += W[i][o, k] * g
                W[i][o, k] -= lr * g * acts[i][k]
            b[i][o] -= lr * g
        dy = dx
    return W, b


def test_sgd_step_matches_firmware_rule():
    rng = np.random.default_rng(0)
    model = MLPAutoencoder((12, 6, 4, 6, 12), seed=3)
    x = rng.normal(size=12).astype(np.float32)
    W_ref, b_ref = _firmware_train_step(model.W, model.b, x, 0.01)
    model.sgd_step(x, 0.01)
    for a, r in zip(model.W + model.b, W_ref + b_ref):
        np.testing.assert_allclose(a, r, rtol=1e-5, atol=1e-6)


def test_gradient_matches_finite_differences():
    rng = np.random.default_rng(1)
    model = MLPAutoencoder((6, 4, 6), seed=0)
    X = rng.normal(size=(5, 6)).astype(np.float32)
    _, gW, _ = model._grads(X)
    i, o, k = 0, 1, 2
    eps = 1e-2
    base = model.W[i][o, k]
    model.W[i][o, k] = base + eps
    up = model.score(X).mean()
    model.W[i][o, k] = base - eps
    down = model.score(X).mean()
    model.W[i][o, k] = base
    assert abs((up - down) / (2 * eps) - gW[i][o, k]) < 1e-3


def test_training_reduces_loss_and_scores_anomalies_higher():
    rng = np.random.default_rng(2)
    basis = rng.normal(size=(4, 48))
    normal = (rng.normal(size=(2000, 4)) @ basis + 0.05 * rng.normal(size=(2000, 48))).astype(np.float32)
    anomalous = rng.normal(size=(200, 48)).astype(np.float32) * normal.std()
    model = MLPAutoencoder(seed=0)
    history = model.train(normal, epochs=20, lr=3e-3)
    assert history[-1] < 0.5 * history[0]
    assert auroc(model.score(normal), model.score(anomalous)) > 0.95
    for m in (PCAModel(4), MahalanobisModel(), KMeansModel(8)):
        m.fit(normal)
        assert auroc(m.score(normal), m.score(anomalous)) > 0.95


def test_flat_weights_roundtrip_and_copy_is_independent():
    m = MLPAutoencoder(seed=0)
    flat = m.get_flat()
    assert len(flat) == m.n_params == 48 * 16 + 16 + 16 * 8 + 8 + 8 * 16 + 16 + 16 * 48 + 48
    c = m.copy()
    c.set_flat(flat * 0)
    np.testing.assert_array_equal(m.get_flat(), flat)
    assert not c.get_flat().any()


def test_auroc_known_values():
    assert auroc(np.array([0, 1, 2]), np.array([3, 4])) == 1.0
    assert auroc(np.array([3, 4]), np.array([0, 1])) == 0.0
    assert auroc(np.array([1, 1]), np.array([1, 1])) == 0.5
