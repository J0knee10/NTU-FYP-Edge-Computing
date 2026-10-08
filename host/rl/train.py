"""Step 3: train the gating agent in simulation and compare it with the baselines (RQ1).

    python -m rl.train --source fraunhofer
    python -m rl.train --source own --episodes 3000

1. Pre-train the autoencoder on normal windows from only part of the speed range ("factory"
   conditions), so the other speeds act as benign drift the device has to adapt to.
2. Train tabular Q-learning and a contextual bandit on training episodes (S1, S2, S3, S1+S3).
3. Evaluate the greedy agents and the baselines (static, always-adapt, rule gate) on held-out
   episodes. Fraunhofer: train on the D recordings, test on E (reassembled rig, new speed range).
4. Online refinement: continue Q-learning on deployment episodes with operator-feedback reward
   only (proposal 7.5), then re-evaluate. Deployment episodes come from the first half (in time)
   of the test recordings and evaluation episodes from the second half.

Writes results/step3/<source>/: results.json, pretrained.npz (model + normaliser + threshold used
by the simulator and by step 4), q_table.npy, bandit_table.npy, q_table_refined.npy, policy.json.
"""

from __future__ import annotations

import argparse
import json
import time

import numpy as np

from features import DEFAULT_SPEC, Normaliser
from features.extract import Windows
from features.sets import SOURCES, load_source, time_split
from models.autoencoder import MLPAutoencoder
from models.autoencoder import save as save_model
from models.compare import ON_DEVICE_LR, RESULTS
from models.metrics import threshold_at

from .agents import BASELINES, QAgent, contextual_bandit
from .env import ACTIONS, GateEnv, RewardConfig, run_episode, summarise
from .episodes import SCENARIOS, EpisodeBuilder
from .state import N_STATES, decode


def pretrain_for_rl(train: Windows, speed_frac: float, epochs: int, seed: int):
    """Autoencoder + normaliser + threshold from normal windows at the lowest speed_frac of speeds."""
    normal = train.subset(~train.fault)
    if np.isfinite(normal.rpm).any() and speed_frac < 1.0:
        normal = normal.subset(normal.rpm <= np.nanquantile(normal.rpm, speed_frac))
    first, rest = time_split(normal)
    norm = Normaliser.fit(normal.X[first])
    model = MLPAutoencoder(seed=seed)
    model.train(norm(normal.X[first]), epochs=epochs, seed=seed)
    threshold = threshold_at(model.score(norm(normal.X[rest])), 0.99)
    return model, norm, threshold


def split_groups(source: str, groups: dict) -> tuple[Windows, Windows]:
    if source == "fraunhofer":
        return groups["D"], groups["E"]
    w = groups["all"]
    first, rest = time_split(w, 0.7)
    return w.subset(first), w.subset(rest)


def train_agent(agent: QAgent, env: GateEnv, builder: EpisodeBuilder, n: int,
                eps_start: float = 0.3, eps_end: float = 0.02) -> list[float]:
    returns = []
    for i in range(n):
        agent.epsilon = eps_start + (eps_end - eps_start) * i / max(n - 1, 1)
        stats = run_episode(env, builder.build(SCENARIOS[i % len(SCENARIOS)]), agent, learn=True)
        returns.append(stats.ret)
    return returns


def evaluate(policies: dict, env: GateEnv, episodes: list) -> dict:
    out = {}
    for name, policy in policies.items():
        stats = [run_episode(env, ep, policy) for ep in episodes]
        out[name] = {"all": summarise(stats)}
        for sc in SCENARIOS:
            out[name][sc] = summarise([s for s in stats if s.scenario == sc])
    return out


def print_table(results: dict) -> None:
    cols = [("detection_rate", "detect"), ("mean_delay_windows", "delay"),
            ("false_alarms_per_1000_normal_windows", "FA/1k"), ("contamination_rate", "contam"),
            ("adapt_fraction", "adapt"), ("mean_return", "return")]
    print(f"{'policy':20s} {'scenario':7s} " + " ".join(f"{c[1]:>7s}" for c in cols))
    for name, res in results.items():
        for sc in ("all",) + SCENARIOS:
            row = res[sc]
            vals = " ".join(f"{'-' if row.get(k) is None else row.get(k):>7}" for k, _ in cols)
            print(f"{name:20s} {sc:7s} {vals}")


def run(source: str, n_train: int, n_test: int, speed_frac: float, epochs: int, n_refine: int, seed: int) -> dict:
    t0 = time.time()
    groups = load_source(source, DEFAULT_SPEC)
    train_w, test_w = split_groups(source, groups)
    model, norm, threshold = pretrain_for_rl(train_w, speed_frac, epochs, seed)
    reward = RewardConfig()
    env = GateEnv(model, threshold, ON_DEVICE_LR, reward)
    print(f"pre-trained on {speed_frac:.0%} of speeds; threshold {threshold:.4f}")

    train_builder = EpisodeBuilder(train_w, norm, seed=seed)
    q = QAgent(seed=seed)
    bandit = contextual_bandit(seed=seed)
    q_returns = train_agent(q, env, train_builder, n_train)
    b_returns = train_agent(bandit, env, train_builder, n_train)
    print(f"trained on {n_train} episodes each ({time.time() - t0:.0f} s)")

    # Refinement ("deployment") uses the first half of the test recordings, evaluation the second.
    deploy_w, eval_w = (test_w.subset(m) for m in time_split(test_w, 0.5)) if n_refine else (None, test_w)
    test_episodes = EpisodeBuilder(eval_w, norm, seed=seed + 1).batch(n_test)
    policies = {p.name: p() for p in BASELINES}
    policies["contextual_bandit"] = bandit.greedy()
    policies["q_learning"] = q.greedy()
    results = evaluate(policies, env, test_episodes)

    refined = None
    if n_refine:
        refined = q.greedy()
        refined.explore, refined.epsilon, refined.alpha = True, 0.02, 0.02
        deploy_env = GateEnv(model, threshold, ON_DEVICE_LR, reward, feedback_only=True)
        train_agent(refined, deploy_env, EpisodeBuilder(deploy_w, norm, seed=seed + 2), n_refine, 0.05, 0.02)
        results.update(evaluate({"q_learning_refined": refined.greedy()}, env, test_episodes))
    print_table(results)

    out = RESULTS / "step3" / source
    out.mkdir(parents=True, exist_ok=True)
    save_model(out / "pretrained.npz", model, **norm.to_dict(), threshold=np.float32(threshold))
    np.save(out / "q_table.npy", q.Q)
    np.save(out / "bandit_table.npy", bandit.Q)
    if refined is not None:
        np.save(out / "q_table_refined.npy", refined.Q)
    policy = {str(decode(s)): a for s, a in enumerate(q.policy_table())}
    (out / "policy.json").write_text(json.dumps(
        {"state_order": "(level, trend, persistence, context)", "actions": ACTIONS, "policy": policy}, indent=1))
    summary = {
        "source": source, "n_train_episodes": n_train, "n_test_episodes": n_test, "speed_frac": speed_frac,
        "threshold": threshold, "reward": reward.to_dict(), "n_states": N_STATES,
        "states_visited": int((q.Q != 0).any(axis=1).sum()),
        "train_return_last_200": {"q_learning": float(np.mean(q_returns[-200:])),
                                  "contextual_bandit": float(np.mean(b_returns[-200:]))},
        "results": results, "seconds": round(time.time() - t0, 1),
    }
    (out / "results.json").write_text(json.dumps(summary, indent=2, default=float))
    print(f"wrote {out}")
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", choices=SOURCES, default="fraunhofer")
    ap.add_argument("--episodes", type=int, default=2000, help="training episodes per agent")
    ap.add_argument("--test-episodes", type=int, default=200)
    ap.add_argument("--refine-episodes", type=int, default=400)
    ap.add_argument("--speed-frac", type=float, default=0.5, help="fraction of speeds seen in pre-training")
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    run(a.source, a.episodes, a.test_episodes, a.speed_frac, a.epochs, a.refine_episodes, a.seed)


if __name__ == "__main__":
    main()
