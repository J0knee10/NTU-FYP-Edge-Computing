import numpy as np

from features import DEFAULT_SPEC, Normaliser
from features.extract import Windows, window_features
from fl.fedavg import blend, dequantise_int8, fedavg, quantise_int8
from fl.simulate import apply_gain
from models import MLPAutoencoder
from rl import ADAPT, ALERT, FREEZE, N_STATES, AlwaysAdapt, EpisodeBuilder, GateEnv, QAgent, StaticModel
from rl.env import run_episode, summarise
from rl.state import decode, state_index


def _toy_windows(n=600, seed=0):
    """One fan; normal = low-variance noise at two speeds, faults = shifted, by severity."""
    rng = np.random.default_rng(seed)
    X, rpm, sev, rec = [], [], [], []
    for s in range(4):
        X.append(rng.normal(s * 2.0, 0.3, size=(n, 8)))
        rpm.append(np.where(np.arange(n) < n // 2, 1000.0, 1600.0))
        sev.append(np.full(n, s))
        rec.append(np.full(n, f"sev{s}", dtype=object))
    X, rpm, sev, rec = (np.concatenate(a) for a in (X, rpm, sev, rec))
    return Windows(X.astype(np.float32), rpm.astype(np.float32), sev > 0, sev, rec,
                   np.full(len(X), "fan1", dtype=object), np.tile(np.arange(n), 4) * 512, 952.0)


def _toy_env():
    w = _toy_windows()
    norm = Normaliser.fit(w.X[~w.fault])
    model = MLPAutoencoder((8, 4, 8), seed=0)
    model.train(norm(w.X[~w.fault]), epochs=20, lr=3e-3)
    thr = float(np.quantile(model.score(norm(w.X[~w.fault])), 0.99))
    return w, norm, GateEnv(model, thr, lr=1e-3)


def test_state_space_is_120_and_bijective():
    assert N_STATES == 120
    seen = {state_index(*decode(i)) for i in range(N_STATES)}
    assert seen == set(range(N_STATES))


def test_alert_on_fault_ends_episode_and_adapt_counts_contamination():
    w, norm, env = _toy_env()
    ep = EpisodeBuilder(w, norm, seed=0, learn_len=50).build("S3")
    env.reset(ep)
    onset = ep.onset
    assert ep.learn > 0 and env.t == ep.learn   # learning period already done
    for t in range(ep.learn, onset):
        _, _, done = env.step(FREEZE)
        assert not done
    env.step(ADAPT)
    assert env.stats.adapts_on_fault == 1
    _, reward, done = env.step(ALERT)
    assert done and env.stats.detected_at == onset + 1 and reward == env.r.detect


def test_static_detects_obvious_faults_and_q_learning_learns_to():
    w, norm, env = _toy_env()
    lens = dict(normal_len=(30, 60), drift_len=(30, 60), step_len=(10, 20), fault_len=(20, 40), learn_len=50)
    builder = EpisodeBuilder(w, norm, seed=1, **lens)
    test = EpisodeBuilder(w, norm, seed=2, **lens).batch(40)
    static = summarise([run_episode(env, ep, StaticModel()) for ep in test])
    assert static["detection_rate"] == 1.0
    agent = QAgent(seed=0)
    for i in range(400):
        agent.epsilon = 0.3 * (1 - i / 400)
        run_episode(env, builder.build(), agent, learn=True)
    learned = summarise([run_episode(env, ep, agent.greedy()) for ep in test])
    assert learned["detection_rate"] >= 0.9
    always = summarise([run_episode(env, ep, AlwaysAdapt()) for ep in test])
    assert always["adapt_fraction"] > learned["adapt_fraction"]


def test_fedavg_weights_by_approved_windows():
    a, b = np.zeros(3, np.float32), np.ones(3, np.float32)
    np.testing.assert_allclose(fedavg([a, b], [1, 3]), 0.75)
    assert fedavg([a, b], [0, 0]) is None
    np.testing.assert_allclose(blend(a, b, 0.25), 0.25)


def test_int8_quantisation_error_is_bounded():
    flat = np.random.default_rng(0).normal(size=2000).astype(np.float32)
    q, scale = quantise_int8(flat)
    assert q.dtype == np.int8
    assert np.abs(dequantise_int8(q, scale) - flat).max() <= scale / 2 + 1e-7


def test_apply_gain_equals_recomputing_features_on_scaled_signal():
    x = np.random.default_rng(3).normal(size=(DEFAULT_SPEC.window, 3))
    f = window_features(x[None], 952.0)
    np.testing.assert_allclose(apply_gain(f, 1.7), window_features(1.7 * x[None], 952.0), atol=1e-4)
