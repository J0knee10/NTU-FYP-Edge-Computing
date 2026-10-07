# Implementation Plan

Agreed 7 Oct 2026. Refines the revised proposal (`FYP_predictive_maintenance_proposal.docx`); where they differ, this file wins.

## Decisions

| Topic | Decision | Reason |
|---|---|---|
| Test machine | 12 V PC fans instead of 230 V standing fans | Safe; PWM speed control lets the board script benign drift; tach wire gives ground-truth RPM; easy to get identical units; same BLDC motor type as EC fans in HVAC and server cooling. Proposal sections 7.2, 8.1 and 11 need updating. |
| Board | Arduino Nano 33 BLE Sense **Rev1** (LSM9DS1, MP34DT05 mic, HTS221) | Hardware on hand; no further purchases. |
| Gateway | Laptop (Raspberry Pi later, optional) | Hardware on hand. |
| Fleet | One physical board; extra FL clients simulated from recordings of different fans | Only one board available. Must tier needs one fan only. |
| Toolchain | PyTorch pre-training → NumPy reference twin → hand-written static C++ forward/backward/SGD | TFLite Micro cannot train; Tiny Training Engine is PyTorch-only research code aimed at much larger CNNs. A ~2k-parameter model needs only ~150–200 lines of C++. |
| Order | Prove feasibility of the whole pipeline (model, RL gate, FL) in Python simulation first, then port to C++ | Software iterates much faster than hardware. The RL agent is trained in a simulator that must reproduce the exact on-device update rule; RQ1 and the simulated part of RQ3 can be answered in Python. A small on-board smoke test in step 0 de-risks the hardware early. |
| Anomaly model | **Open.** MLP autoencoder on features is the default candidate | Decided by experiment in step 2 (see below). |

## Hard deadlines

From the School's schedule (`Dates Aug 2026.pdf`). These cannot move.

| Date | Deadline | Notes |
|---|---|---|
| 10 Aug 2026 (Mon, Sem 1 Wk 1) | FYP starts | Done |
| 31 Aug 2026 (Mon, Sem 1 Wk 4) | Project plan / strategy to supervisor | Done |
| **25 Jan 2027** (Mon, Sem 2 Wk 3) | **Interim Report** to supervisor | Must tier should be working |
| **22 Mar 2027** (Mon, Sem 2 Wk 10) | **Final Report** softcopy to supervisor **and examiner** | **This is the version that is graded.** Amendments are not assessed, so all results must be in this version. |
| **16 Apr 2027** (Fri, Sem 2 Wk 13) | **Amended Final Report** to supervisor and examiner | Final submission; no changes after this. Also upload to DR-NTU. Get amendments from supervisor/examiner 1–2 weeks after 22 Mar. |
| **7, 10–12 May 2027** (Sem 2 exam period) | **Oral presentation** | 20 min talk + 10 min Q&A, with live demo. Re-upload to DR-NTU if the report changed. |

Other constraints (approximate; confirm against the NTU academic calendar):
- Sem 1 exams ≈ late Nov – mid Dec 2026 (shaded on the proposal's Gantt chart). Plan light FYP work only.
- Winter break ≈ mid Dec 2026 – 10 Jan 2027 (Sem 2 Wk 1 = 11 Jan). Full-time FYP, as the School advises.

## Steps

Steps 0–4 are software-first: they prove the full pipeline in simulation before any C++ is written. Hardware time goes into data collection, which the simulations depend on.

| Step | Work | Output | Target |
|---|---|---|---|
| 0. Data | Rev1 logging firmware (IMU at ~952 Hz, mic, temperature, fan PWM duty and tach RPM); Python recorder on the laptop; scripted speed profiles; labelled fault sessions. Record **several fans / mounting setups**, since each becomes a simulated FL client. Download UCI "Accelerometer" cooler-fan dataset. Smoke test: run one dummy dense-layer forward + backward + SGD step on the board to measure RAM and time. | Labelled raw recordings + session metadata; early on-device training numbers. Guide: [`steps/step0_data_collection.md`](steps/step0_data_collection.md) | Oct 2026 |
| 1. Feature spec | Fix window length, FFT size, band edges, scalar statistics and normalisation, using only operations easy to reproduce in C (CMSIS-DSP). Keep band energies as one ordered low→high block so both MLP and frequency-axis CNN candidates can use them. | `feature_spec` + Python implementation | Oct 2026 |
| 2. Anomaly model | Compare candidates on PC-fan data; pre-train the winner in PyTorch; write the NumPy reference twin of on-device SGD. | Chosen model, pre-trained weights, NumPy twin | Late Oct – mid Nov 2026 |
| 3. RL simulator | Episodes built from recordings (benign drift, gradual fault, sudden fault) with the model updating online; tabular Q-learning (and contextual bandit) vs static, always-adapt and rule-based baselines. | Q-table; RQ1 results | Nov 2026, before Sem 1 exams |
| 4. FL simulation | Reuses the step 3 simulator: weighted FedAvg (weights = approved training windows) over simulated clients; cold-start (S4) and fleet-transfer (S5) experiments. Timebox ~1 week; if it slips, finish in the first week after exams. | RQ3 results in simulation | Nov 2026, before Sem 1 exams |
| — | Sem 1 exams | Light work only (tidy results, read for C++ port) | ≈ late Nov – mid Dec 2026 |
| 5. C++ port | Feature extraction, model forward/backward/SGD, Q-table lookup; golden-vector tests against the NumPy twin on PC, then on the board; RAM / flash / latency / energy profiling. | Must tier working on one fan | Mid Dec 2026 – ~10 Jan 2027 |
| — | Interim Report writing | **Interim Report, 25 Jan 2027** | 11 – 25 Jan 2027 |
| 6. Real link | BLE to laptop, MQTT, FedAvg with the real board plus simulated clients; operator feedback dashboard. | Should tier | Late Jan – Feb 2027 |
| — | Results freeze, evaluation and Final Report writing | **Final Report, 22 Mar 2027 (graded)** | ~1 – 22 Mar 2027 |
| — | Amendments, DR-NTU upload | **Amended Final Report, 16 Apr 2027** | 23 Mar – 16 Apr 2027 |
| — | Demo hardening, slides, rehearsal | **Oral presentation, 7 / 10–12 May 2027** | 17 Apr – May 2027 |

## Anomaly-model candidates (step 2)

| Candidate | Notes |
|---|---|
| MLP autoencoder on feature vector | Default. Tiny training memory; simple hand-written backprop. |
| 1D-CNN autoencoder over band energies (frequency axis) | Frequency bins are ordered, so convolution is meaningful; more activation memory. |
| 1D-CNN on raw waveform | Likely too heavy to train on-device; offline reference only. |
| PCA reconstruction / Mahalanobis / k-means distance | Non-neural baselines an examiner will ask about. |

LSTM/GRU are excluded: backprop through time is too costly on the MCU, and temporal context is already in the RL state (score trend, persistence).

Selection criteria: AUROC on PC-fan faults; adaptation speed with on-device SGD after benign drift; estimated on-device training RAM and time per window.

## Rev1 hardware notes

- `Arduino_LSM9DS1` configures the accelerometer at 119 Hz by default; set the ODR register directly for ~952 Hz (Nyquist ~476 Hz).
- Cap fan speed so blade-pass frequency (RPM / 60 × blade count) stays below ~476 Hz, e.g. 7 blades at 3,000 RPM = 350 Hz.
- PWM control: 25 kHz on the fan's PWM pin (open-drain input, 3.3 V logic is fine). Tach: interrupt pin with pull-up to 3.3 V, never 12 V. Share ground between the 12 V supply and the board.
- Mount the fan to a fixed plate the same way every session and fix the board rigidly to the fan frame. Keep imbalance masses small (~0.1–0.5 g) and the finger guard on.

## Open items

- PC fan inventory: how many, same model, 3-pin or 4-pin?
- 12 V supply available?
- Update proposal sections 7.2, 8.1 and 11 for PC fans and inform the supervisor.
