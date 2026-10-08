# Implementation Plan

Agreed 7 Oct 2026. Refines the revised proposal (`FYP_predictive_maintenance_proposal.docx`); where they differ, this file wins.

## Decisions

| Topic | Decision | Reason |
|---|---|---|
| Test machine | 12 V PC fans instead of 230 V standing fans | Safe; PWM speed control lets the board script benign drift; tach wire gives ground-truth RPM; easy to get identical units; same BLDC motor type as EC fans in HVAC and server cooling. Proposal sections 7.2, 8.1 and 11 need updating. |
| Board | Arduino Nano 33 BLE Sense **Rev1** (LSM9DS1, MP34DT05 mic, HTS221) | Hardware on hand; no further purchases. |
| Gateway | Laptop (Raspberry Pi later, optional) | Hardware on hand. |
| Fleet | One physical board; extra FL clients simulated from recordings of different fans | Only one board available. Must tier needs one fan only. |
| Toolchain | NumPy pre-training and NumPy reference twin → hand-written static C++ forward/backward/SGD | TFLite Micro cannot train; Tiny Training Engine is PyTorch-only research code aimed at much larger CNNs. A ~2k-parameter model needs only ~150–200 lines of C++. Since 8 Oct the MLP autoencoder is pre-trained in NumPy (`host/models/autoencoder.py`), so pre-training and the twin share one implementation; PyTorch is only needed if a CNN candidate is pursued. |
| Order | Prove feasibility of the whole pipeline (model, RL gate, FL) in Python simulation first, then port to C++ | Software iterates much faster than hardware. The RL agent is trained in a simulator that must reproduce the exact on-device update rule; RQ1 and the simulated part of RQ3 can be answered in Python. A small on-board smoke test in step 0 de-risks the hardware early. |
| Datasets | Own PC-fan recordings for all reported results. Until they exist, steps 1–4 are developed on the Fraunhofer unbalance dataset; UCI is a minor fan reference | Fraunhofer has a healthy baseline, 4 graded unbalance levels, speed ramps in the fan RPM range and a reassembled evaluation rig, which covers drift, gradual-fault and re-mount testing. It is a shaft rig, not a fan, and has one machine, so it cannot give reported RL/FL results. UCI is a fan but sampled at 50 Hz with no healthy run. See [Datasets](#datasets). |
| RL agent | Trained offline in the step 3 simulator and deployed as a Q-table; online refinement from operator feedback as in proposal 7.5 | The anomaly model is pre-trained first (unsupervised, normal data only). The Q-learning agent is then trained by reward in episodes where the model keeps updating online with the on-device SGD rule whenever the agent chooses ADAPT. On the board the anomaly model learns only on ADAPT windows. Online refinement (proposal 7.5) updates the Q-table from operator feedback on alerts only, since that is the only reward a deployed device sees; it is simulated in step 3 and needs the step 6 dashboard on the real device. FedAvg shares anomaly-model weights only; averaging Q-tables is a proposal stretch goal. |
| Anomaly model | MLP autoencoder 48-16-8-16-48 (default; provisional) | Best of the implemented candidates on Fraunhofer (step 2). Confirm on our own recordings; the 1D-CNN candidate is not implemented yet. |

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
| 1. Feature spec | **Code done 8 Oct (provisional spec).** Fix window length, FFT size, band edges, scalar statistics and normalisation, using only operations easy to reproduce in C (CMSIS-DSP). Keep band energies as one ordered low→high block so both MLP and frequency-axis CNN candidates can use them. Write and unit-test the code on UCI first (rate taken from the recording, never hard-coded), but choose window length and band edges on our 952 Hz recordings: UCI's 25 Hz Nyquist limit makes its bands meaningless for our sensor. | `feature_spec` + Python implementation | Oct 2026 |
| 2. Anomaly model | **Code done 8 Oct.** Compare candidates on PC-fan data (developed on Fraunhofer); pre-train the winner; NumPy reference twin of on-device SGD, checked against a line-by-line port of the firmware training step. | Chosen model, pre-trained weights, NumPy twin | Late Oct – mid Nov 2026 |
| 3. RL simulator | **Code done 8 Oct.** Episodes built from recordings (benign drift, gradual fault, sudden fault) with the model updating online; tabular Q-learning (and contextual bandit) vs static, always-adapt and rule-based baselines. Developed on Fraunhofer episodes (train on D, test on the reassembled E rig); reported results use our recordings only. Includes the proposal's learning period and simulated online refinement. | Q-table; RQ1 results | Nov 2026, before Sem 1 exams |
| 4. FL simulation | **Code done 8 Oct.** Reuses the step 3 simulator: weighted FedAvg (weights = approved training windows) over simulated clients; cold-start (S4) and fleet-transfer (S5) experiments. Timebox ~1 week; if it slips, finish in the first week after exams. | RQ3 results in simulation | Nov 2026, before Sem 1 exams |
| — | Sem 1 exams | Light work only (tidy results, read for C++ port) | ≈ late Nov – mid Dec 2026 |
| 5. C++ port | Feature extraction, model forward/backward/SGD, Q-table lookup; golden-vector tests against the NumPy twin on PC, then on the board; RAM / flash / latency / energy profiling. | Must tier working on one fan | Mid Dec 2026 – ~10 Jan 2027 |
| — | Interim Report writing | **Interim Report, 25 Jan 2027** | 11 – 25 Jan 2027 |
| 6. Real link | BLE to laptop, MQTT, FedAvg with the real board plus simulated clients; operator feedback dashboard. | Should tier | Late Jan – Feb 2027 |
| — | Results freeze, evaluation and Final Report writing | **Final Report, 22 Mar 2027 (graded)** | ~1 – 22 Mar 2027 |
| — | Amendments, DR-NTU upload | **Amended Final Report, 16 Apr 2027** | 23 Mar – 16 Apr 2027 |
| — | Demo hardening, slides, rehearsal | **Oral presentation, 7 / 10–12 May 2027** | 17 Apr – May 2027 |

## Datasets

| Dataset | Contents | Used for | Not used for |
|---|---|---|---|
| Own recordings (`data/raw/`, step 0) | Several fans and mounts; accelerometer ~952 Hz, mic, temperature, PWM duty, tach RPM; benign drift, graded faults | All reported results: final features, model selection and pre-training, RL episodes (RQ1), FL clients (RQ3), C++ golden vectors | — |
| Fraunhofer unbalance (`data/external/fraunhofer-unbalance/`, Mey et al. 2020) | Shaft driven by an EC DC motor; 3 PCB vibration sensors at 4096 Hz (resampled to 952 Hz), measured RPM; no unbalance plus 4 graded levels (45.9–152.1 mm·g); speed steps every 20 s, 630–2330 rpm (D, ~107 min per level) and 1060–1900 rpm (E, ~28 min, rig reassembled) | Developing steps 1–4 before our recordings exist: feature code, model comparison, RL episodes (D = train, E = test), FL client simulation | Reported results (not a fan; one machine) |
| UCI "Accelerometer" (`data/external/uci-accelerometer/`, Sampaio et al. 2019) | One Akasa AK-FN059 12 cm fan (1900 rpm max) with magnets on its blades; MMA8452Q at ±8 g, 12-bit, read by an Arduino UNO at **50 Hz**; a second magnet on two neighbouring, perpendicular or opposite blades × 17 speeds (20–100 %); one 1-minute clip (3,000 samples) each | Unit tests of the loaders; a sanity check that the pipeline runs on real fan data | Anything rate-dependent (Nyquist 25 Hz); RL or FL (51 one-minute clips, one fan, no healthy run) |

Every source loads into the same `Recording` format (`host/fanlog/recording.py`: `fraunhofer_recordings()`, `uci_recordings()`, `session_recordings()`, or `load(source)`). Steps 1–4 take `Recording` objects (through `features.sets`) and every command has `--source fraunhofer|uci|own`, so switching to our recordings changes one argument. The sample rate always comes from `Recording.rate_hz`.

Fraunhofer notes: the CSVs are read straight from the zip and cached as 952 Hz arrays in `data/external/fraunhofer-unbalance/cache/`. The first 50,000 samples of each file are dropped, as the authors do. `Measured_RPM` updates once per second and has a few bad 1 s readings per file (up to ~4,000 rpm); a 3 s median filter removes them. Vibration units are not stated. Licence CC BY 4.0; cite doi:10.24406/fordatis/65 and the paper (arXiv:2005.12742, IEEE ETFA 2020). Python's CA bundle lacks the HARICA root that the Fordatis server chains to, so the zip is fetched with curl (TLS still verified); `fanlog.datasets` then uses the existing file.

UCI facts and caveats (UCI page and the paper, PMC6806350):
- **No healthy run.** The UCI page calls configuration 1 "normal", but it means a doubled weight on two *neighbouring* blades, which is the largest imbalance. Opposite weights largely cancel. Our data check agrees: at 80 % speed the RMS vibration is ~1.4 g (neighbouring), ~1.0 g (perpendicular) and ~0.1 g (opposite). The loader treats "opposite" as normal (severity 0) and the others as faults (1, 2).
- **The paper does not do fault detection.** It regresses a synthetic "failure time" from y/z amplitudes and assumed growth rates. There are no published AUROC numbers to compare with.
- Licence CC BY 4.0. Cite the dataset (doi:10.24432/C5Q61V) and the paper (doi:10.3390/s19194342).

Other public datasets found on 8 Oct (not downloaded; see `literature_sources.md` E8–E11): matutani/cooling-fan (real PC fans, spectra only, fan-specific benchmark for step 2), MIMII DUE fan sections (16 kHz audio with labelled benign shifts, if audio features are added), XJTU-SY (bearing run-to-failure, as a template for realistic gradual-fault shapes).

## Simulator design (steps 3–4)

- **Learning period.** Every episode starts with ~300 normal windows (~2.7 min) where the device always adapts (learning rate 5×10⁻³), then sets its own alert threshold to the 99th percentile of its scores on those windows (proposal 7.4, "stick-on-and-learn"). Without it, a model pre-trained on another mount scores most normal windows above threshold and every policy raises constant false alarms.
- **Pre-training for RL** uses normal windows from only the slowest 50 % of speeds, so faster speeds act as benign drift the agent must handle.
- **Rewards** (`rl/env.py`, `RewardConfig`): detect +20, false alarm −5 per alert, missed fault −50, ADAPT on a fault window −2, −0.2 per fault window before the alert, ADAPT on an above-threshold normal window +0.2, −0.01 per training step. With equal detect/false-alarm/miss magnitudes (first attempt) the agent learned never to alert.
- **FL clients on Fraunhofer** (development only): the D and E mounts, three speed ranges and a per-client sensor gain (applied exactly in feature space).

## Anomaly-model candidates (step 2)

| Candidate | Notes |
|---|---|
| MLP autoencoder on feature vector | Default. Tiny training memory; simple hand-written backprop. |
| 1D-CNN autoencoder over band energies (frequency axis) | Frequency bins are ordered, so convolution is meaningful; more activation memory. Not implemented yet. |
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
