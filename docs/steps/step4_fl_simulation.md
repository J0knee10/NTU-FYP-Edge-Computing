# Step 4: Federated Learning Simulation

**Goal:** test whether sharing model weights across a fleet helps (**RQ3**). Two questions:
- **S4:** does a newly installed device settle faster when it starts from the fleet's model?
- **S5:** does the RL gate stop one device's fault from leaking into everyone's model?

The code is written and runs on Fraunhofer. The results are not meaningful yet, because Fraunhofer is
one machine. Real conclusions need several of our own fans.

## How it works

```
 round r:  each client ── blend(local, global, β) ──► runs 400 windows, gated by the frozen
           Q-table from step 3 (ADAPT = one sgd_step) ──► int8 weights + number of ADAPT windows
                                                                        │
 server:   global = Σ weights × (ADAPT count / total)  ◄────────────────┘   (weighted FedAvg)
```

- Each **client** is one device: its own model copy, the step 3 policy, and the windows of one fan
  and mount.
- On Fraunhofer, which is one rig, the clients are made from:
  - its two mounts (D and E),
  - three speed ranges,
  - a per-client sensor gain (0.8–1.25).

  This tests the code, not the idea.
- Weights go up and down as **int8** (one scale per vector). That is 1,884 bytes each way per client
  per round, against 7,520 bytes as float32.
- A client that raises a confirmed alert stops contributing until repaired.

## Code used in this step

| Path | What it does |
|---|---|
| `host/fl/fedavg.py` | Weighted FedAvg, personalisation blend, int8 quantisation, bytes per update |
| `host/fl/simulate.py` | Clients, FL rounds, the S4 and S5 experiments |

It reuses `host/rl/` (environment, episodes, policies) and the step 3 outputs
(`results\step3\<source>\pretrained.npz` and `q_table.npy`), so run step 3 first.

## Part A: Run it

```
.venv\Scripts\python -m fl.simulate --source fraunhofer
```

Takes about a minute. Options: `--rounds 8 --round-len 400 --beta 0.5 --new-len 600`.

**What should happen:** one `S4` line per client (leave-one-out), one `S5` line per policy, then
`wrote results\step4\fraunhofer\results.json`.

**S4 cold start.** Each client in turn is the "new" one. It runs 600 normal windows starting from:
- **isolated:** the pre-trained model only, or
- **FL:** the global model after 8 rounds among the other clients.

Metrics: false alarms, the share of windows above threshold in the first 100, the windows until that
share stays under 5 % (cold-start time), and AUROC afterwards.

**S5 fleet transfer.** A gradual fault develops on client A from round 4. Afterwards the worst fault
hits client B. This is repeated with every client using Q-learning, always-adapt, or the rule gate.
Metrics: the global model's AUROC on B's data after every round, and whether and how fast B detects.

Results on Fraunhofer (8 Oct), with honest caveats:
- **S4:** mixed.
  - FL halved false alarms for `D_mid` (23 → 11) and slightly helped `E_all` (7 → 5).
  - It made no difference for `D_slow` or `D_fast`.
  - The clients differ in speed range and gain much more than identical fans would, so one averaged
    model suits nobody well.
- **S5:** no difference between policies yet. Client A alerts on its fault quickly under every policy
  and then stops contributing, so nothing leaks.
  - To test leakage, the fault on A has to stay mild for several rounds (e.g. severity 1 for 4 rounds)
    so that always-adapt absorbs it before anything alerts.
  - That is the first change to make here.

## Part B: On our own data (after steps 0–3 on `--source own`)

```
.venv\Scripts\python -m fl.simulate --source own
```

Each fan@mount in the recordings becomes one client (at least 3 needed). Then:
1. Make S5's fault plan mild and slow (see above) and check that always-adapt contaminates the
   global model while the RL gate does not.
2. Try `--beta` 0.3 / 0.5 / 0.8 (how much of the global model each client takes).
3. Run 3+ seeds.

## How to tell it worked

```
.venv\Scripts\python -m pytest host
```

`test_rl_fl.py` checks the weighted FedAvg maths, the int8 error bound, and that the sensor-gain trick
gives exactly the features of a scaled signal.

## Done when

- [ ] Run on our own recordings with at least 3 clients and 3 seeds
- [ ] S5 redesigned so a fault can leak, and the gate shown (or not) to stop it
- [ ] RQ3 numbers: cold-start time with and without FL, detection with and without FL, bytes per round
- [ ] Tests pass

**Next:** step 5 ports features, model, SGD and the Q-table lookup to C++ on the board.
