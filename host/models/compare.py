"""Step 2: compare anomaly-model candidates and pre-train the default one.

    python -m models.compare --source fraunhofer
    python -m models.compare --source own

For each candidate: AUROC per fault severity (same mount, and after re-mounting where the source
has it), adaptation speed after a benign speed change (autoencoder only: the others cannot learn
on the device), and on-device cost. Writes results/step2/<source>/compare.json and the pre-trained
autoencoder (weights + normaliser + threshold) to results/step2/<source>/pretrained.npz, which
steps 3 and 4 load.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from fanlog.recording import REPO_ROOT
from features import DEFAULT_SPEC, Normaliser
from features.extract import Windows
from features.sets import SOURCES, Splits, standard_splits

from . import autoencoder as ae_io
from .autoencoder import MLPAutoencoder
from .baselines import KMeansModel, MahalanobisModel, PCAModel
from .metrics import auroc, threshold_at

RESULTS = REPO_ROOT / "results"
ON_DEVICE_LR = 1e-3


def candidates(seed: int = 0) -> dict:
    return {
        "mlp_ae": MLPAutoencoder(seed=seed),
        "pca8": PCAModel(8),
        "mahalanobis": MahalanobisModel(),
        "kmeans16": KMeansModel(16, seed=seed),
    }


def fit(name: str, model, X: np.ndarray, epochs: int):
    if name == "mlp_ae":
        model.train(X, epochs=epochs)
    else:
        model.fit(X)
    return model


def auroc_by_severity(model, norm: Normaliser, test: Windows) -> dict:
    s = model.score(norm(test.X))
    normal = s[~test.fault]
    out = {}
    for sev in sorted(np.unique(test.severity[test.fault])):
        out[f"severity_{int(sev)}"] = round(auroc(normal, s[test.fault & (test.severity == sev)]), 4)
    out["all_faults"] = round(auroc(normal, s[test.fault]), 4)
    return out


def adaptation_speed(splits: Splits, epochs: int, lr: float = ON_DEVICE_LR, seed: int = 0) -> dict | None:
    """Benign drift test: pre-train on the slowest 30 % of normal speeds, then stream normal windows
    from the faster speeds in time order. Compare the fraction of windows scoring above the alert
    threshold when the device never adapts vs adapts on every window (one sgd_step each)."""
    tr = splits.train
    if np.isnan(tr.rpm).all():
        return None
    cut = np.nanquantile(tr.rpm, 0.3)
    low, high = tr.subset(tr.rpm <= cut), tr.subset(tr.rpm > cut)
    norm = Normaliser.fit(low.X)
    base = MLPAutoencoder(seed=seed)
    base.train(norm(low.X), epochs=epochs)
    thr = threshold_at(base.score(norm(low.X)), 0.99)
    stream = norm(high.X[np.lexsort((high.start, high.rec))][:2000])
    frozen = base.score(stream) > thr
    model, adapting = base.copy(), []
    for x in stream:
        adapting.append(model.score(x)[0] > thr)
        model.sgd_step(x, lr)
    adapting = np.array(adapting)
    quarters = lambda a: [round(float(q.mean()), 3) for q in np.array_split(a, 4)]  # noqa: E731
    return {
        "lr": lr,
        "stream_windows": len(stream),
        "frac_above_threshold_frozen_by_quarter": quarters(frozen),
        "frac_above_threshold_adapting_by_quarter": quarters(adapting),
    }


def run(source: str, epochs: int = 30, seed: int = 0) -> dict:
    t0 = time.time()
    splits = standard_splits(source, DEFAULT_SPEC)
    norm = Normaliser.fit(splits.train.X)
    Xtr = norm(splits.train.X)
    result = {"source": source, "spec": DEFAULT_SPEC.to_dict(), "n_train": len(Xtr), "candidates": {}}
    trained = {}
    for name, model in candidates(seed).items():
        fit(name, model, Xtr, epochs)
        trained[name] = model
        entry = {"auroc_same_mount": auroc_by_severity(model, norm, splits.test_same)}
        if splits.test_shifted is not None:
            entry["auroc_after_remount"] = auroc_by_severity(model, norm, splits.test_shifted)
        if name == "mlp_ae":
            entry["device_cost"] = model.device_cost()
        result["candidates"][name] = entry
        print(f"{name:12s} {json.dumps(entry)}")

    adapt = adaptation_speed(splits, epochs, seed=seed)
    result["candidates"]["mlp_ae"]["adaptation"] = adapt
    print(f"mlp_ae adaptation {json.dumps(adapt)}")

    model = trained["mlp_ae"]
    thr = threshold_at(model.score(norm(splits.val.X)), 0.99)
    out = RESULTS / "step2" / source
    ae_io.save(out / "pretrained.npz", model, **norm.to_dict(), threshold=np.float32(thr))
    result["threshold_p99_val"] = thr
    result["seconds"] = round(time.time() - t0, 1)
    (out / "compare.json").write_text(json.dumps(result, indent=2, default=float))
    print(f"wrote {out / 'compare.json'} and {out / 'pretrained.npz'}")
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", choices=SOURCES, default="fraunhofer")
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    run(args.source, args.epochs, args.seed)


if __name__ == "__main__":
    main()
