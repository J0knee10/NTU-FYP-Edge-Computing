"""Gating policies: the learned agents (tabular Q-learning, contextual bandit) and the proposal's
baselines (section 8.4). All share act(state, env); baselines read the decoded state from env.encoder.
"""

from __future__ import annotations

import numpy as np

from .env import ACTIONS, ADAPT, ALERT, FREEZE, N_ACTIONS
from .state import N_STATES

# Fixed alert rule used by every baseline: score at least ALERT_LEVEL bins above threshold
# (level 2 = score >= 2x threshold) for at least ALERT_PERSIST bins (2 = 3+ windows in a row).
ALERT_LEVEL = 2
ALERT_PERSIST = 2


def _rule_alert(env) -> bool:
    level, _, persist, _ = env.encoder.last
    return level >= ALERT_LEVEL and persist >= ALERT_PERSIST


class StaticModel:
    """Pre-trained model with a fixed threshold; never adapts."""

    name = "static"

    def act(self, s, env):
        return ALERT if _rule_alert(env) else FREEZE


class AlwaysAdapt:
    """Naive continual learning: trains on every window that does not trigger the alert rule."""

    name = "always_adapt"

    def act(self, s, env):
        return ALERT if _rule_alert(env) else ADAPT


class RuleGate:
    """Adapt only while the score is below the threshold (typical manual use of on-device tools)."""

    name = "rule_gate"

    def act(self, s, env):
        if _rule_alert(env):
            return ALERT
        return ADAPT if env.encoder.last[0] == 0 else FREEZE


class QAgent:
    """Tabular Q-learning with epsilon-greedy exploration. gamma = 0 gives the contextual bandit."""

    def __init__(self, alpha: float = 0.1, gamma: float = 0.95, epsilon: float = 0.1, seed: int = 0,
                 name: str = "q_learning"):
        self.Q = np.zeros((N_STATES, N_ACTIONS))
        self.alpha, self.gamma, self.epsilon = alpha, gamma, epsilon
        self.rng = np.random.default_rng(seed)
        self.name = name
        self.explore = True

    def act(self, s, env=None):
        if self.explore and self.rng.random() < self.epsilon:
            return int(self.rng.integers(N_ACTIONS))
        q = self.Q[s]
        return int(self.rng.choice(np.flatnonzero(q == q.max())))

    def update(self, s, a, reward, s2, done):
        target = reward if done else reward + self.gamma * self.Q[s2].max()
        self.Q[s, a] += self.alpha * (target - self.Q[s, a])

    def greedy(self) -> "QAgent":
        g = QAgent(self.alpha, self.gamma, 0.0, name=self.name)
        g.Q = self.Q.copy()
        g.explore = False
        return g

    def policy_table(self) -> list[str]:
        return [ACTIONS[int(np.argmax(q))] if q.any() else "UNVISITED" for q in self.Q]


def contextual_bandit(**kw) -> QAgent:
    return QAgent(gamma=0.0, name="contextual_bandit", **kw)


BASELINES = (StaticModel, AlwaysAdapt, RuleGate)
