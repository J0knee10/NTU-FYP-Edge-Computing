# Step 2: Anomaly Model

**Goal:** choose the model that turns a feature vector into an anomaly score, pre-train it, and have
a NumPy copy of its on-device training step (the "twin") that the C++ code in step 5 must match.

The code is written and runs on Fraunhofer. What's left is rerunning it on our own recordings.

## How it works

- Every candidate is fitted on **normal windows only**. No fault labels are needed, which is what
  makes the device plug-and-play.
- The anomaly score is how badly the model reconstructs (or how far from normal it puts) a window.
- **AUROC** measures how well the score separates normal from faulty windows: 0.5 is guessing, 1.0
  is perfect. It is reported per fault severity, for the same mount and after re-mounting.
- **Adaptation** measures whether on-device SGD fixes false alarms after a benign speed change.
- **Device cost** is the RAM and multiply-accumulates (MACs) per window on the board.

| Candidate | What it is |
|---|---|
| `mlp_ae` | MLP autoencoder 48-16-8-16-48, ReLU, linear output (the default) |
| `pca8` | Reconstruction error from the top 8 principal components |
| `mahalanobis` | Distance from the normal data, accounting for feature correlations |
| `kmeans16` | Distance to the nearest of 16 cluster centres |

The 1D-CNN candidate from the plan is not implemented yet.

## Code used in this step

| Path | What it does |
|---|---|
| `host/models/autoencoder.py` | `MLPAutoencoder`. `sgd_step()` is the twin of the firmware's `trainStep()`; `train()` is offline pre-training (mini-batches, Adam) |
| `host/models/baselines.py` | PCA, Mahalanobis and k-means models |
| `host/models/metrics.py` | AUROC and the alert threshold (99th percentile of normal scores) |
| `host/models/compare.py` | Runs the comparison and saves the pre-trained model |

## Part A: Run the comparison

```
.venv\Scripts\python -m models.compare --source fraunhofer
```

Takes about a minute. **What should happen:** one line per candidate, then the adaptation result, then
`wrote results\step2\fraunhofer\compare.json and ...\pretrained.npz`.

Results on Fraunhofer (8 Oct):

| Model | AUROC same mount | AUROC after re-mount | Severity 1 after re-mount |
|---|---|---|---|
| `mlp_ae` | **0.960** | **0.934** | 0.773 |
| `mahalanobis` | 0.946 | 0.932 | 0.770 |
| `pca8` | 0.936 | 0.892 | 0.703 |
| `kmeans16` | 0.904 | 0.924 | 0.747 |

- The autoencoder needs 1,880 parameters, about 8.4 KB of RAM and 5,376 MACs per training step.
- **Adaptation:** pre-trained on the slowest 30 % of speeds, then shown faster normal speeds.
  - A frozen model flags 91–100 % of those normal windows.
  - Adapting on every window brings that down to about 25 % within 2,000 windows.
- This is the drift problem the RL gate exists for. Adapting is necessary, but adapting during a fault
  would teach the model the fault.

## Part B: On our own data (after steps 0 and 1)

```
.venv\Scripts\python -m models.compare --source own
```

`--source own` splits each fan's normal sessions 80/20 in time (pre-training / threshold). The test
set is the held-out normal windows plus every fault session. Choose the model on AUROC, adaptation and
device cost, then record the decision in `docs/implementation_plan.md`.

## How to tell it worked

```
.venv\Scripts\python -m pytest host
```

`test_models.py::test_sgd_step_matches_firmware_rule` runs a line-by-line Python copy of the firmware
`trainStep()` and checks that `sgd_step()` gives the same weights. Step 5 uses the same idea with golden
vectors on the board.

## Done when

- [ ] Comparison run on our own recordings
- [ ] Model chosen and recorded in the plan (default: MLP autoencoder)
- [ ] `results\step2\own\pretrained.npz` saved
- [ ] Tests pass

**Next:** step 3 trains the RL gate with this model learning inside the simulator.
