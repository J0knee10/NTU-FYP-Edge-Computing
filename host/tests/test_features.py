import numpy as np

from features import DEFAULT_SPEC, FeatureSpec, Normaliser
from features.extract import extract, window_features
from fanlog.recording import Recording

RATE = 952.0


def _sine(freq, n=DEFAULT_SPEC.window, amp=1.0, axis=0):
    t = np.arange(n) / RATE
    x = np.zeros((n, 3))
    x[:, axis] = amp * np.sin(2 * np.pi * freq * t)
    return x


def test_shape_and_names():
    f = window_features(_sine(50)[None], RATE)
    assert f.shape == (1, DEFAULT_SPEC.n_features) == (1, 48)
    assert f.dtype == np.float32


def test_sine_lands_in_its_band():
    for freq in (20.0, 100.0, 300.0):
        f = window_features(_sine(freq)[None], RATE)[0]
        band = int(np.argmax(f[:DEFAULT_SPEC.n_bands]))
        edges = DEFAULT_SPEC.band_edges(RATE)
        assert edges[band] - 2 <= freq <= edges[band + 1] + 2


def test_band_bins_cover_only_the_band_range():
    bins = DEFAULT_SPEC.band_bins(RATE)
    freqs = np.arange(len(bins)) * RATE / DEFAULT_SPEC.window
    assert (bins[freqs < DEFAULT_SPEC.f_lo_hz] == -1).all()
    assert (bins[freqs >= 450] == -1).all()
    assert set(bins[bins >= 0]) == set(range(DEFAULT_SPEC.n_bands))


def test_band_edges_capped_below_nyquist_at_low_rates():
    assert DEFAULT_SPEC.band_edges(50.0)[-1] == 0.95 * 25


def test_scaling_shifts_log_features_and_leaves_shape_features():
    x = _sine(60, amp=1.0) + 0.1 * np.random.default_rng(0).normal(size=(DEFAULT_SPEC.window, 3))
    a = window_features(x[None], RATE)[0]
    b = window_features(2 * x[None], RATE)[0]
    n = DEFAULT_SPEC.n_bands
    np.testing.assert_allclose(b[:n] - a[:n], 2 * np.log10(2), atol=1e-4)
    np.testing.assert_allclose(b[n:n + 3] - a[n:n + 3], np.log10(2), atol=1e-4)
    np.testing.assert_allclose(b[n + 3:], a[n + 3:], rtol=1e-4)


def test_extract_windows_and_rpm():
    spec = FeatureSpec(window=128, hop=64, n_bands=8)
    n = 1000
    rec = Recording("test", "r", RATE, np.random.default_rng(1).normal(size=(n, 3)).astype(np.float32), "g",
                    "fan1", "normal", 0, rpm=np.linspace(1000, 2000, n).astype(np.float32))
    w = extract(rec, spec, cache=False)
    assert len(w) == (n - 128) // 64 + 1
    assert w.X.shape == (len(w), 16)
    assert np.all(np.diff(w.rpm) > 0) and not w.fault.any()


def test_normaliser_roundtrip():
    X = np.random.default_rng(2).normal(3, 2, size=(500, 4))
    norm = Normaliser.fit(X)
    Z = norm(X)
    np.testing.assert_allclose(Z.mean(axis=0), 0, atol=1e-5)
    np.testing.assert_allclose(Z.std(axis=0), 1, atol=1e-4)
    np.testing.assert_array_equal(Normaliser.from_dict(norm.to_dict())(X), Z)
