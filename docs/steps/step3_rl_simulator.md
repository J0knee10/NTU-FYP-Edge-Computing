# Step 3: RL Gate Simulator

**Goal:** train the agent that decides, window by window, whether the anomaly model may learn
(ADAPT), must not learn (FREEZE), or should raise a fault (ALERT). Then show whether it beats the
baselines. This answers **RQ1**.

The code is written and runs on Fraunhofer. What's left is running it on our own recordings and
tuning the rewards.

## How it works

```
        pre-trained model (step 2)
                 │ copy
 episode ──► learning period ──► for each window:  score ─► state ─► agent ─► action
 (spliced     (~300 normal                          │                        │
  recordings)  windows, always                      └──── model ◄── ADAPT: one sgd_step
               adapt, then set                                    FREEZE: nothing
               own threshold)                                     ALERT: end (fault) or false alarm
```

- **Episodes** (proposal Table 8) are built by splicing recorded windows:

  | Scenario | What happens | Correct behaviour |
  |---|---|---|
  | S1 | Speed change(s) only | ADAPT, no alert |
  | S2 | Fault severity 1 → 2 → 3 → 4 at one speed | FREEZE as the score rises, then ALERT |
  | S3 | Sudden severe fault | ALERT quickly |
  | S1+S3 | Speed change, then a fault at the new speed | ADAPT, then ALERT |

- **State** (proposal Table 4): 5 score levels × 3 trends × 4 persistence bins × 2 context
  (speed changed recently) = **120 states**. With 3 actions the Q-table has 360 values (1.4 KB as
  float32).
- **Learning period** (proposal 7.4): each episode starts with ~300 normal windows where the device
  always adapts, then sets its own threshold. Without it, a model pre-trained on another mount sees
  everything as abnormal, and every policy raises constant false alarms.
- **Pre-training** for this step uses only the slowest 50 % of speeds, so faster speeds are drift
  the agent has to deal with.
- **Train/test:**
  - Fraunhofer: the agent trains on episodes from the D recordings and is tested on E (the rig was
    taken apart and reassembled, and the speed range differs). E is split in time: the first half is
    used for online refinement, the second half for testing.
  - Own data: a 70/30 time split per recording.
- **Rewards** are in `RewardConfig` in `host/rl/env.py`. A first attempt with equal +10/−10/−10 for
  detection, false alarm and miss taught the agent never to alert (one false alarm cost as much as a
  whole missed fault), so a miss is now −50.
- **Online refinement** (proposal 7.5): the deployed agent keeps updating its Q-table, but only from
  operator feedback on its alerts (confirm = +20, dismiss = −5), because that is all a real device
  learns.

## Code used in this step

| Path | What it does |
|---|---|
| `host/rl/state.py` | Score history + speed → state index (the same arithmetic the C code will do) |
| `host/rl/episodes.py` | `EpisodeBuilder`: S1, S2, S3, S1+S3 episodes from any source's windows |
| `host/rl/env.py` | `GateEnv` (learning period, actions, rewards), `RewardConfig`, metrics |
| `host/rl/agents.py` | Q-learning, contextual bandit (Q-learning with γ = 0), and the baselines: static, always-adapt, rule gate |
| `host/rl/train.py` | Pre-train → train agents → evaluate → online refinement → save |

## Part A: Run it

```
.venv\Scripts\python -m rl.train --source fraunhofer
```

Takes about 5 minutes (2,000 training episodes per agent, 200 test episodes). Use `--episodes 300
--test-episodes 60` for a quick check. **What should happen:** a table with one row per policy and
scenario, then `wrote results\step3\fraunhofer`.

Columns:
- `detect`: share of fault episodes with an alert after onset
- `delay`: windows from fault onset to the alert (one window = 0.54 s)
- `FA/1k`: false alarms per 1,000 normal windows
- `contam`: share of fault windows (before the alert) that the model trained on
- `adapt`: share of windows with ADAPT
- `return`: mean episode reward

Results on Fraunhofer (8 Oct, seed 0, 200 test episodes on the reassembled E rig; development only):

| Policy | Detect | Delay (windows) | False alarms / 1k | Contamination | Return |
|---|---|---|---|---|---|
| Static | 0.97 | 46 | 91 | 0.00 | −161 |
| Always-adapt | 0.82 | 45 | 36 | 1.00 | −178 |
| Rule gate | 0.89 | 44 | 64 | 0.63 | −174 |
| Contextual bandit | 0.71 | 19 | 641 | 0.09 | −1193 |
| **Q-learning** | **0.91** | **23** | **9.9** | 0.46 | **−37** |
| Q-learning + online refinement | 0.61 | 34 | 1.2 | 0.52 | −103 |

What this says so far:
- Q-learning gives the best trade-off by a wide margin. It has about a tenth of static's false alarms
  and half the delay, and keeps 91 % detection. That is the RQ1 claim in development form.
- Its contamination is still high: it trains on 46 % of fault windows before alerting. The next tuning
  target is the reward for ADAPT on fault windows, or a state that better separates drift from faults.
- The contextual bandit fails. Without looking ahead it cannot see that adapting now prevents false
  alarms later. That is a useful argument for full RL over a bandit.
- Online refinement with alert feedback only makes the agent too quiet (detection falls to 0.61). A
  device that only hears "false alarm" never learns about faults it missed. The proposal's "delayed
  confirmation" signal, or a periodic missed-fault check, is needed. This is worth discussing in the
  report.
- Single seed: rerun with several seeds before drawing conclusions.

## Part B: On our own data (after steps 0–2)

```
.venv\Scripts\python -m rl.train --source own --episodes 3000
```

Then tune: the reward values, the state bin edges (`LEVEL_EDGES`, `PERSIST_EDGES` and so on in
`state.py`) and the learning-period length. Record each change and its effect, because the report
needs to justify the final design. Report several seeds (`--seed 0`, `1`, `2`) rather than one run.

## Outputs

`results\step3\<source>\`:
- `results.json`: all metrics and settings
- `pretrained.npz`: model, normaliser and threshold, used by step 4
- `q_table.npy`, `bandit_table.npy`, `q_table_refined.npy`
- `policy.json`: the greedy action for every (level, trend, persistence, context) state, readable
  for the report. This table is what goes onto the board in step 5.

## How to tell it worked

```
.venv\Scripts\python -m pytest host
```

`test_rl_fl.py` checks that the state space has 120 states, that an alert on a fault ends the episode,
that ADAPT on a fault counts as contamination, and that Q-learning learns to detect faults in a toy
problem.

## Done when

- [ ] Run on our own recordings, with at least 3 seeds
- [ ] Rewards and state bins tuned; choices recorded in the plan
- [ ] RQ1 table: Q-learning vs bandit vs the three baselines, per scenario
- [ ] Tests pass

**Next:** step 4 puts the trained agent on every client of a simulated fleet.
