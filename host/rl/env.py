"""The gating environment: one episode, one device.

Learning period first (if the episode has one): the device adapts on every window with learn_lr,
then sets its alert threshold to the 99th percentile of its own scores on those windows.

Per window t after that: the current model scores x_t, the encoder turns the score into state s_t, the agent
picks an action, and the action is applied:
  ADAPT   one sgd_step on x_t (the device's training rule), so later scores change
  FREEZE  no update
  ALERT   notify the operator. On a fault the episode ends (fault confirmed); on a normal
          window it is a false alarm, the operator dismisses it and the device carries on.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np

from models.autoencoder import MLPAutoencoder

from .episodes import Episode
from .state import StateEncoder

ADAPT, FREEZE, ALERT = 0, 1, 2
ACTIONS = ("ADAPT", "FREEZE", "ALERT")
N_ACTIONS = 3


@dataclass
class RewardConfig:
    """Proposal Table 4 rewards. Values are starting points, to be tuned in step 3."""

    detect: float = 20.0          # ALERT during a fault
    false_alarm: float = -5.0     # ALERT on a normal window
    miss: float = -50.0           # episode ends with an undetected fault
    contaminate: float = -2.0     # ADAPT on a fault window (learning the fault as normal)
    delay: float = -0.2           # every fault window before the alert
    adapt_drift: float = 0.2      # ADAPT on a normal window that currently scores above threshold
    train_cost: float = -0.01     # energy cost of one training step

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EpisodeStats:
    scenario: str
    windows: int = 0
    normal_windows: int = 0
    fault_windows: int = 0
    onset: int | None = None
    detected_at: int | None = None
    false_alarms: int = 0
    adapts: int = 0
    adapts_on_fault: int = 0
    ret: float = 0.0
    actions: list = field(default_factory=list)
    ratios: list = field(default_factory=list)   # score / threshold per window

    @property
    def delay(self) -> int | None:
        return None if self.detected_at is None else self.detected_at - self.onset


class GateEnv:
    def __init__(self, model: MLPAutoencoder, threshold: float, lr: float = 1e-3,
                 reward: RewardConfig | None = None, feedback_only: bool = False, learn_lr: float = 5e-3):
        """feedback_only: reward comes only from operator feedback on alerts (what a deployed
        device can observe), for online refinement of the Q-table."""
        self.pretrained = model
        self.threshold = threshold
        self.lr = lr
        self.learn_lr = learn_lr
        self.r = reward or RewardConfig()
        self.feedback_only = feedback_only
        self.encoder = StateEncoder(threshold)

    def reset(self, episode: Episode, model: MLPAutoencoder | None = None) -> int:
        self.ep = episode
        self.model = (model or self.pretrained).copy()
        self.encoder = StateEncoder(self.threshold)
        if episode.learn:
            for x in episode.X[:episode.learn]:
                self.model.sgd_step(x, self.learn_lr)
            self.encoder = StateEncoder(float(np.quantile(self.model.score(episode.X[:episode.learn]), 0.99)))
        self.t = episode.learn
        self.stats = EpisodeStats(episode.scenario, onset=episode.onset)
        return self._observe()

    def _observe(self) -> int:
        score = float(self.model.score(self.ep.X[self.t])[0])
        return self.encoder.update(score, float(self.ep.rpm[self.t]))

    def step(self, action: int) -> tuple[int | None, float, bool]:
        t, ep, r, st = self.t, self.ep, self.r, self.stats
        fault = bool(ep.fault[t])
        above = self.encoder.last_ratio >= 1.0
        reward = 0.0
        done = False
        st.windows += 1
        st.actions.append(action)
        st.ratios.append(self.encoder.last_ratio)
        if fault:
            st.fault_windows += 1
        else:
            st.normal_windows += 1

        if action == ADAPT:
            self.model.sgd_step(ep.X[t], self.lr)
            st.adapts += 1
            reward += r.train_cost
            if fault:
                st.adapts_on_fault += 1
                reward += r.contaminate
            elif above:
                reward += r.adapt_drift
        elif action == ALERT:
            if fault:
                st.detected_at = t
                reward += r.detect
                done = True
            else:
                st.false_alarms += 1
                reward += r.false_alarm
        if fault and not done:
            reward += r.delay

        self.t += 1
        if not done and self.t >= len(ep):
            done = True
            if st.onset is not None and st.detected_at is None:
                reward += r.miss
        if self.feedback_only:
            reward = (r.detect if action == ALERT and fault else r.false_alarm if action == ALERT else 0.0)
        st.ret += reward
        return (None if done else self._observe()), reward, done


def run_episode(env: GateEnv, episode: Episode, policy, learn: bool = False,
                model: MLPAutoencoder | None = None) -> EpisodeStats:
    """Run one episode, starting from `model` (default: the pre-trained one). policy.act(state, env)
    -> action; with learn=True, policy.update() is called after every step."""
    s = env.reset(episode, model)
    done = False
    while not done:
        a = policy.act(s, env)
        s2, reward, done = env.step(a)
        if learn:
            policy.update(s, a, reward, s2, done)
        s = s2
    return env.stats


def summarise(stats: list[EpisodeStats]) -> dict:
    """Proposal Table 9 metrics over a set of episodes."""
    fault_eps = [s for s in stats if s.onset is not None]
    detected = [s for s in fault_eps if s.detected_at is not None]
    normal_windows = sum(s.normal_windows for s in stats)
    fault_windows_before = sum(
        (s.detected_at - s.onset if s.detected_at is not None else s.fault_windows) for s in fault_eps)
    out = {
        "episodes": len(stats),
        "false_alarms_per_1000_normal_windows": round(1000 * sum(s.false_alarms for s in stats) / max(normal_windows, 1), 2),
        "episodes_with_false_alarm": round(np.mean([s.false_alarms > 0 for s in stats]), 3),
        "adapt_fraction": round(sum(s.adapts for s in stats) / max(sum(s.windows for s in stats), 1), 3),
        "mean_return": round(float(np.mean([s.ret for s in stats])), 2),
    }
    if fault_eps:
        out.update({
            "detection_rate": round(len(detected) / len(fault_eps), 3),
            "mean_delay_windows": round(float(np.mean([s.delay for s in detected])), 1) if detected else None,
            "contamination_rate": round(sum(s.adapts_on_fault for s in fault_eps) / max(fault_windows_before, 1), 3),
        })
    return out
