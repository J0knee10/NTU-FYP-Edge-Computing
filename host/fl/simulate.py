"""Step 4: federated learning across a simulated fleet (RQ3, proposal S4 and S5).

    python -m fl.simulate --source fraunhofer
    python -m fl.simulate --source own

Every client is one device: its own autoencoder copy, gated window by window by the frozen policy
from step 3, learning only on ADAPT windows with the on-device SGD rule. After each round of
--round-len windows the server computes weighted FedAvg (weight = approved training windows) and
each client blends the global model into its own (personalisation, --beta).

S4 cold start: established clients run --rounds rounds; then a new client starts either from the
   pre-trained model alone (isolated) or from the global model (FL). Leave-one-out over clients.
S5 fleet transfer: a gradual fault develops on client A during the later rounds; afterwards the same
   fault hits client B. Compared across gating policies: does A's fault leak into the global model
   (contamination) and stop B from detecting it?

Requires step 3 output (results/step3/<source>/pretrained.npz and q_table.npy).
Writes results/step4/<source>/results.json.

Clients for public data (development only): the Fraunhofer rig has one machine, so clients are
made from its two mounts (D and E recordings), different speed ranges and a per-client sensor gain.
With our own data every fan@mount is one client.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass

import numpy as np

from features import DEFAULT_SPEC, Normaliser
from features.extract import Windows
from features.sets import SOURCES, load_source
from models.autoencoder import MLPAutoencoder
from models.autoencoder import load as load_model
from models.compare import ON_DEVICE_LR, RESULTS
from models.metrics import auroc
from rl.agents import AlwaysAdapt, QAgent, RuleGate, StaticModel
from rl.env import GateEnv, run_episode
from rl.episodes import EpisodeBuilder

from .fedavg import blend, dequantise_int8, fedavg, quantise_int8, update_bytes


@dataclass
class ClientSpec:
    name: str
    fan: str
    rpm_lo: float = -np.inf
    rpm_hi: float = np.inf
    gain: float = 1.0


def apply_gain(X: np.ndarray, gain: float, spec=DEFAULT_SPEC) -> np.ndarray:
    """Exact effect on the features of scaling the raw signal by `gain` (a different sensor
    sensitivity or mounting stiffness): log band power +2 log10 g, log RMS +log10 g."""
    X = X.copy()
    X[:, :spec.n_bands] += 2 * np.log10(gain)
    X[:, spec.n_bands:spec.n_bands + 3] += np.log10(gain)
    return X


def client_specs(source: str, windows: Windows) -> list[ClientSpec]:
    if source == "fraunhofer":
        return [
            ClientSpec("D_slow", "fraunhofer_D", 630, 1200, 1.0),
            ClientSpec("D_mid", "fraunhofer_D", 1200, 1750, 0.8),
            ClientSpec("D_fast", "fraunhofer_D", 1750, 2330, 1.25),
            ClientSpec("E_all", "fraunhofer_E", 1060, 1900, 1.1),
        ]
    fans = sorted(set(windows.fan))
    if len(fans) < 3:
        raise SystemExit(f"{source}: FL needs at least 3 fans/mounts, found {fans}")
    return [ClientSpec(f, f) for f in fans]


class Client:
    def __init__(self, spec: ClientSpec, windows: Windows, norm: Normaliser, model: MLPAutoencoder,
                 threshold: float, policy, seed: int):
        m = (windows.fan == spec.fan) & (np.isnan(windows.rpm) | ((windows.rpm >= spec.rpm_lo) & (windows.rpm <= spec.rpm_hi)))
        w = windows.subset(m)
        w.X = apply_gain(w.X, spec.gain)
        self.spec = spec
        self.w = w
        self.builder = EpisodeBuilder(w, norm, seed=seed)
        self.model = model.copy()
        self.env = GateEnv(model, threshold, ON_DEVICE_LR)
        self.policy = policy
        self.rng = np.random.default_rng(seed)
        self.alerted = False
        self.severities = sorted({int(s) for s in w.severity[w.fault]})

    def stream(self, n: int, severity: int = 0) -> list[np.ndarray]:
        lo, hi = self.builder.speed_range(self.spec.fan)
        parts, total = [], 0
        while total < n:
            rpm = self.rng.uniform(lo, hi) if np.isfinite(lo) else np.nan
            seg = self.builder.segment(self.spec.fan, severity, rpm, int(min(self.rng.integers(100, 300), n - total)))
            parts.append(seg)
            total += len(seg)
        return parts

    def run(self, parts: list[np.ndarray], label: str):
        """Run windows through the gated device; the client keeps the resulting model."""
        ep = self.builder.from_segments(parts, label, self.spec.fan)
        stats = run_episode(self.env, ep, self.policy, model=self.model)
        self.model = self.env.model
        if stats.detected_at is not None:
            self.alerted = True   # operator confirms; device stops contributing until repaired
        return stats

    def holdout_auroc(self, model: MLPAutoencoder, min_severity: int = 1) -> float | None:
        s = model.score(self.builder.Xn)
        normal, fault = s[~self.w.fault], s[self.w.fault & (self.w.severity >= min_severity)]
        return round(auroc(normal, fault), 4) if len(normal) and len(fault) else None


def fl_rounds(clients: list[Client], global_flat: np.ndarray, rounds: int, round_len: int, beta: float,
              fault_plan: dict | None = None, track: Client | None = None) -> tuple[np.ndarray, list]:
    """fault_plan: {client_name: (first_round, severities...)} for clients that develop a fault."""
    log = []
    for r in range(rounds):
        flats, counts = [], []
        for c in clients:
            c.model.set_flat(global_flat if r == 0 else blend(c.model.get_flat(), global_flat, beta))
            sev = 0
            if fault_plan and c.spec.name in fault_plan:
                first, sevs = fault_plan[c.spec.name]
                if r >= first:
                    sev = sevs[min(r - first, len(sevs) - 1)]
            if c.alerted:
                counts.append(0)
                flats.append(c.model.get_flat())
                continue
            stats = c.run(c.stream(round_len, sev), f"round{r}")
            q, scale = quantise_int8(c.model.get_flat())   # what goes over BLE
            flats.append(dequantise_int8(q, scale))
            counts.append(stats.adapts)
        new = fedavg(flats, counts)
        if new is not None:
            global_flat = new
        entry = {"round": r, "approved_windows": counts, "alerted": [c.spec.name for c in clients if c.alerted]}
        if track is not None:
            g = track.model.copy()
            g.set_flat(global_flat)
            entry["global_auroc_on_tracked"] = track.holdout_auroc(g, 2)
        log.append(entry)
    return global_flat, log


def cold_start_windows(ratios: list[float], window: int = 50, level: float = 0.05) -> int | None:
    above = np.asarray(ratios) >= 1.0
    if len(above) < window:
        return None
    rolling = np.convolve(above, np.ones(window) / window, mode="valid")
    ok = np.flatnonzero(rolling < level)
    return int(ok[0] + window) if len(ok) else None


def policies_from_step3(source: str) -> dict:
    q = QAgent()
    q.Q = np.load(RESULTS / "step3" / source / "q_table.npy")
    q.explore = False
    return {"q_learning": q, "always_adapt": AlwaysAdapt(), "rule_gate": RuleGate(), "static": StaticModel()}


def run(source: str, rounds: int, round_len: int, beta: float, new_len: int, seed: int) -> dict:
    t0 = time.time()
    step3 = RESULTS / "step3" / source
    if not (step3 / "pretrained.npz").exists():
        raise SystemExit(f"run step 3 first: python -m rl.train --source {source}")
    pretrained, d = load_model(step3 / "pretrained.npz")
    norm, threshold = Normaliser.from_dict(d), float(d["threshold"])
    windows = Windows.concat(list(load_source(source, DEFAULT_SPEC).values()))
    specs = client_specs(source, windows)
    policies = policies_from_step3(source)
    make = lambda spec, pol, k: Client(spec, windows, norm, pretrained, threshold, pol, seed + k)  # noqa: E731
    results = {"source": source, "rounds": rounds, "round_len": round_len, "beta": beta,
               "clients": [vars(s) for s in specs],
               "bytes_per_client_per_round": 2 * update_bytes(pretrained.n_params),
               "bytes_per_client_per_round_float32": 2 * update_bytes(pretrained.n_params, int8=False)}

    # ---- S4 cold start (leave-one-out, gated by the step 3 Q-table) ------------------------------
    s4 = []
    for k, new_spec in enumerate(specs):
        others = [make(s, policies["q_learning"], i) for i, s in enumerate(specs) if s is not new_spec]
        global_flat, _ = fl_rounds(others, pretrained.get_flat(), rounds, round_len, beta)
        row = {"new_client": new_spec.name}
        for init in ("isolated", "fl"):
            c = make(new_spec, policies["q_learning"], 100 + k)
            if init == "fl":
                c.model.set_flat(global_flat)
            stats = c.run(c.stream(new_len, 0), "cold_start")
            row[init] = {
                "false_alarms": stats.false_alarms,
                "frac_above_threshold_first_100": round(float(np.mean(np.asarray(stats.ratios[:100]) >= 1)), 3),
                "cold_start_windows": cold_start_windows(stats.ratios),
                "auroc_after": c.holdout_auroc(c.model),
            }
        s4.append(row)
        print("S4", json.dumps(row))
    results["S4_cold_start"] = s4

    # ---- S5 fleet transfer: fault on A, does it leak to B? ---------------------------------------
    s5 = {}
    a, b = specs[0], specs[1]
    for name in ("q_learning", "always_adapt", "rule_gate"):
        clients = [make(s, policies[name], i) for i, s in enumerate(specs)]
        ca, cb = clients[0], clients[1]
        plan = {a.name: (rounds // 2, ca.severities)}
        _, log = fl_rounds(clients, pretrained.get_flat(), rounds, round_len, beta, plan, track=cb)
        cb.alerted = False
        stats = cb.run(cb.stream(new_len // 2, max(cb.severities)), "fault_on_B")
        s5[name] = {
            "A_detected": ca.alerted,
            "global_auroc_on_B_by_round": [e["global_auroc_on_tracked"] for e in log],
            "B_detected": stats.detected_at is not None,
            "B_delay_windows": stats.delay,
            "B_false_alarms_before": stats.false_alarms,
        }
        print("S5", name, json.dumps(s5[name]))
    results["S5_fleet_transfer"] = {"A": a.name, "B": b.name, "fault_from_round": rounds // 2, "policies": s5}
    results["seconds"] = round(time.time() - t0, 1)

    out = RESULTS / "step4" / source
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(results, indent=2, default=float))
    print(f"wrote {out / 'results.json'}")
    return results


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", choices=SOURCES, default="fraunhofer")
    ap.add_argument("--rounds", type=int, default=8)
    ap.add_argument("--round-len", type=int, default=400, help="windows per client per round")
    ap.add_argument("--beta", type=float, default=0.5, help="share of the global model in the blend")
    ap.add_argument("--new-len", type=int, default=600, help="windows the new client runs in S4")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    run(a.source, a.rounds, a.round_len, a.beta, a.new_len, a.seed)


if __name__ == "__main__":
    main()
