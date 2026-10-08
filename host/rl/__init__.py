"""Step 3: RL gate simulator. An agent chooses ADAPT / FREEZE / ALERT for every window while the
anomaly model learns online (only on ADAPT), using the same SGD rule as the device.

    python -m rl.train --source fraunhofer
"""

from .agents import AlwaysAdapt, QAgent, RuleGate, StaticModel
from .env import ADAPT, ALERT, FREEZE, GateEnv, RewardConfig
from .episodes import Episode, EpisodeBuilder
from .state import N_STATES, StateEncoder

__all__ = ["ADAPT", "ALERT", "AlwaysAdapt", "Episode", "EpisodeBuilder", "FREEZE", "GateEnv", "N_STATES",
           "QAgent", "RewardConfig", "RuleGate", "StateEncoder", "StaticModel"]
