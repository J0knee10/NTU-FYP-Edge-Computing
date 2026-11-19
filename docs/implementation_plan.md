# Implementation Plan

Agreed 7 Oct 2026. Refines the revised proposal (`FYP_predictive_maintenance_proposal.docx`); where they differ, this file wins.

## Decisions

| Topic | Decision | Reason |
|---|---|---|
| Test machine | 12 V PC fans instead of 230 V standing fans | Safe; PWM speed control lets the board script benign drift; tach wire gives ground-truth RPM; easy to get identical units; same BLDC motor type as EC fans in HVAC and server cooling. Proposal sections 7.2, 8.1 and 11 need updating. |
| Board | Adafruit **Feather nRF52840 Sense**, original revision (LSM6DS33 IMU, PDM mic, SHT30 temperature/humidity) | Hardware on hand; no further purchases. Corrected 18 Nov: earlier versions of this plan said Arduino Nano 33 BLE Sense Rev1. Same nRF52840 MCU, so the RAM/flash budget is unchanged; sensors, pins and Arduino core differ. |
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
| 0. Data | **19 Nov: logger 0.3.2 with all onboard sensors; fan `pc01` wired. Healthy data: 7.4 h overnight on `tapeCorner` plus a daytime campaign on `flat4`. First fault (Blu-Tack imbalance, A-B-A) on the night of 19 Nov. Smoke test passed 18 Nov (0.58 ms per training step).** Logging firmware (IMU at ~833 Hz, mic, temperature, fan PWM duty and tach RPM); Python recorder on the laptop; scripted speed profiles; labelled fault sessions. Record **several fans / mounting setups**, since each becomes a simulated FL client. Download UCI "Accelerometer" cooler-fan dataset. Smoke test: run one dummy dense-layer forward + backward + SGD step on the board to measure RAM and time. | Labelled raw recordings + session metadata; early on-device training numbers. Guide: [`steps/step0_data_collection.md`](steps/step0_data_collection.md) | Oct 2026 |
| 1. Feature spec | **Code done 8 Oct (provisional spec).** Fix window length, FFT size, band edges, scalar statistics and normalisation, using only operations easy to reproduce in C (CMSIS-DSP). Keep band energies as one ordered low→high block so both MLP and frequency-axis CNN candidates can use them. Write and unit-test the code on UCI first (rate taken from the recording, never hard-coded), but choose window length and band edges on our 833 Hz recordings: UCI's 25 Hz Nyquist limit makes its bands meaningless for our sensor. | `feature_spec` + Python implementation | Oct 2026 |
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
| Own recordings (`data/raw/`, step 0) | Several fans and mounts; accelerometer ~833 Hz, mic, temperature, PWM duty, tach RPM; benign drift, graded faults | All reported results: final features, model selection and pre-training, RL episodes (RQ1), FL clients (RQ3), C++ golden vectors | — |
| Fraunhofer unbalance (`data/external/fraunhofer-unbalance/`, Mey et al. 2020) | Shaft driven by an EC DC motor; 3 PCB vibration sensors at 4096 Hz (resampled to 833 Hz), measured RPM; no unbalance plus 4 graded levels (45.9–152.1 mm·g); speed steps every 20 s, 630–2330 rpm (D, ~107 min per level) and 1060–1900 rpm (E, ~28 min, rig reassembled) | Developing steps 1–4 before our recordings exist: feature code, model comparison, RL episodes (D = train, E = test), FL client simulation | Reported results (not a fan; one machine) |
| UCI "Accelerometer" (`data/external/uci-accelerometer/`, Sampaio et al. 2019) | One Akasa AK-FN059 12 cm fan (1900 rpm max) with magnets on its blades; MMA8452Q at ±8 g, 12-bit, read by an Arduino UNO at **50 Hz**; a second magnet on two neighbouring, perpendicular or opposite blades × 17 speeds (20–100 %); one 1-minute clip (3,000 samples) each | Unit tests of the loaders; a sanity check that the pipeline runs on real fan data | Anything rate-dependent (Nyquist 25 Hz); RL or FL (51 one-minute clips, one fan, no healthy run) |

Every source loads into the same `Recording` format (`host/fanlog/recording.py`: `fraunhofer_recordings()`, `uci_recordings()`, `session_recordings()`, or `load(source)`). Steps 1–4 take `Recording` objects (through `features.sets`) and every command has `--source fraunhofer|uci|own`, so switching to our recordings changes one argument. The sample rate always comes from `Recording.rate_hz`.

Fraunhofer notes: the CSVs are read straight from the zip and cached as arrays at the board rate (833 Hz since 18 Nov; the file name includes the rate) in `data/external/fraunhofer-unbalance/cache/`. The first 50,000 samples of each file are dropped, as the authors do. `Measured_RPM` updates once per second and has a few bad 1 s readings per file (up to ~4,000 rpm); a 3 s median filter removes them. Vibration units are not stated. Licence CC BY 4.0; cite doi:10.24406/fordatis/65 and the paper (arXiv:2005.12742, IEEE ETFA 2020). Python's CA bundle lacks the HARICA root that the Fordatis server chains to, so the zip is fetched with curl (TLS still verified); `fanlog.datasets` then uses the existing file.

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

## Feature engineering (to do, step 1)

**Status:** not started. The current 48 features (`host/features/spec.py`) are a provisional
baseline, not an engineered set:
- The feature *types* (band energies, RMS, kurtosis, crest factor, spectral centroid) are standard in
  vibration condition monitoring.
- The count of 48 only matches the proposal's 48-16-8-16-48 network.
- The layout (40 equal 11 Hz bands from 2 to 450 Hz, 512-sample windows) is a judgment call.

The examiner will ask "why these features?", so the final set must be justified by experiment and
references. Do this on our own recordings once step 0 has data. It needs the supervisor's input too.

**What we know so far** (`python -m features.report --source fraunhofer`, 8 Oct):
- Most features correlate 0.8–0.9 with speed, so speed moves them more than faults do.
- No single feature separates faults well (AUROC 0.20–0.68).
- The 1× rotation region (10–40 Hz), where imbalance shows, gets only ~3 coarse bands.

**What our own data shows so far** (19 Nov; `results/own/overnight/REPORT.md` section 7, `host/analysis/feature_eval.py`):
- **Fixed-Hz bands fail at speeds not seen in training** (100 % false alarms with a duty left out). Order (per-rotation) amplitudes don't shift with speed.
- **Order features must be per axis.** Summed over axes, a doubled in-plane 1× (where an imbalance acts) is invisible behind the fore-aft rocking of the mount.
- **Normalise each feature against its healthy value at the current speed** (a curve vs log rpm) and average about 5 s before scoring. A max-|z| detector on 11 per-axis order features then detects a doubled in-plane 1× 99.5 % of the time at 1.3 % false alarms, which matches the autoencoder with fewer false alarms.
- **Amplitude vs speed is uneven** (mount resonances), so 10 % duty steps are too coarse to interpolate a new speed. The campaign now adds 5 % sweeps. Learning a new speed is a natural ADAPT decision for the RL agent.
- Still to do: repeat on `flat4` and on the real imbalance data, then freeze the spec.

**Candidate experiments** (most promising first):

| # | Idea | Why | Cost on the board |
|---|---|---|---|
| 1 | **Order-normalised bands**: bands at multiples of the rotation frequency from the tach (1×, 2×, 3×, blade-pass ± sidebands) instead of fixed Hz | Removes most of the speed dependence, so a speed change no longer looks like a fault. Directly reduces the benign-drift problem the RL gate has to handle | Low: tach is already measured; the band table is recomputed when speed changes |
| 2 | **Finer or log-spaced low bands** | More resolution at 1× and 2×, where imbalance and looseness show | None |
| 3 | **Window length** 256 / 512 / 1024 | Frequency resolution vs decisions per minute vs RAM | RAM = 3 × window × 4 bytes |
| 4 | **Per-axis spectra** instead of summing x+y+z | Some faults are directional (imbalance is radial). Costs orientation independence | 3× the band features, or fewer bands per axis |
| 5 | **Feature selection / ablation**: drop groups (bands, RMS, kurtosis, ...) one at a time and re-run step 2 | Shows which features matter, and justifies the final set in the report | Fewer features = smaller model |
| 6 | **Feature count vs model size**: e.g. 24 or 32 inputs with a matching autoencoder | 48 was set by the proposal, not by data; fewer inputs may generalise as well and train faster on the board | Smaller model, less RAM |
| 7 | **Audio features** from the PDM mic (band energies of 16 kHz audio) | Blade damage and obstruction may be clearer in sound than in vibration; MIMII DUE (E10) could help develop them | PDM + FFT on the MCU; more RAM |
| 8 | **Envelope / spectral-kurtosis features** | Standard for early bearing faults | Higher; check CMSIS-DSP feasibility |
| 9 | **Normalisation**: fixed after pre-training (current) vs running statistics updated only on ADAPT windows (closer to proposal 7.3) | A running normaliser outside the agent's control could absorb a fault; a gated one keeps the RL design consistent | Negligible |
| 10 | **Context features** for the RL state rather than the model: temperature (SHT30), PWM duty | Helps the agent tell drift from faults | Negligible |

**How to compare:** for each variant run `features.report` (separability, speed correlation), then
`models.compare` (AUROC same mount / after re-mount, adaptation), then a short `rl.train`. Keep
whichever helps detection and drift robustness without breaking the board's RAM and time budget.
Every variant must use only CMSIS-DSP-friendly operations.

**References needed** (none in `literature_sources.md` yet): a vibration condition-monitoring
textbook for the standard features, the ISO 10816/20816 vibration-severity standard (RMS), a paper on
kurtosis / spectral kurtosis for fault detection, and one on order tracking for variable-speed
machines. Find and verify them before citing.

**Discuss with the supervisor:** whether to prioritise order-normalised features (1) over audio (7),
and how much feature engineering the report should contain, given that the project's main
contribution is the RL gate and FL rather than the features.

## Anomaly-model candidates (step 2)

| Candidate | Notes |
|---|---|
| MLP autoencoder on feature vector | Default. Tiny training memory; simple hand-written backprop. |
| 1D-CNN autoencoder over band energies (frequency axis) | Frequency bins are ordered, so convolution is meaningful; more activation memory. Not implemented yet. |
| 1D-CNN on raw waveform | Likely too heavy to train on-device; offline reference only. |
| PCA reconstruction / Mahalanobis / k-means distance | Non-neural baselines an examiner will ask about. |

LSTM/GRU are excluded: backprop through time is too costly on the MCU, and temporal context is already in the RL state (score trend, persistence).

Selection criteria: AUROC on PC-fan faults; adaptation speed with on-device SGD after benign drift; estimated on-device training RAM and time per window.

## Board hardware notes (Feather nRF52840 Sense)

- Arduino core `adafruit:nrf52` (FQBN `adafruit:nrf52:feather52840sense`), not Mbed. USB serial comes from TinyUSB: sketches that use `Serial` must `#include <Adafruit_TinyUSB.h>`.
- **IMU:** LSM6DS33 accelerometer and gyro at 833 Hz, with the 400 Hz analog anti-alias filter. The measured rate is ~827 Hz in board time (the board's RC time base is 0.23 % fast). The gyro has been on since logger 0.3.0.
- **The anti-alias filter is not enough (found 19 Nov).**
  - The motor's 24×, 36× and 48× orders (700–1450 Hz at 70–100 %) fold back into 0–416 Hz as lines that wander with speed. At some speeds they land on whole orders 3–9.
  - **Options, after the imbalance test and before re-recording the main dataset:**
    - **(a) 200 Hz analog filter:** a config change, a few dB more attenuation, but it also cuts 200–400 Hz.
    - **(b) 1.66 kHz ODR plus a half-band FIR on the board, decimating to 833 Hz.** The host format stays the same. Content from 1.25–1.66 kHz still aliases, attenuated by the analog filter.
      - I2C budget: 20 kB/s of FIFO data in bursts is about 45 % of the bus at 400 kHz, plus about 25 % for magnetometer polling every 1 ms. Poll the magnetometer every 2 ms.
      - The FIFO then holds only about 0.4 s (6 words per sample).
    - Check either option with a mount check comparing alias-line levels.
- The IMU FIFO holds ~0.8 s at 833 Hz with the gyro on. Measured 18 Nov: when it overflows, the 12-bit level counter wraps to 0 and only the OVER_RUN/FULL flags show it; the logger resets the FIFO and counts one overrun.
- **Tach:** `micros()` follows the 1024 Hz FreeRTOS tick on this core. Logger ≥ 0.3.1 times tach edges on TIMER4 at 1 MHz, and 0.3.2 adds a glitch filter that can't lock onto a fraction of the speed. Use 0.3.2 or later.
- Cap fan speed so blade-pass frequency (RPM / 60 × blade count) stays below ~400 Hz, e.g. 7 blades at 3,000 RPM = 350 Hz.
- PWM control: 25 kHz on pin 5 (fan's PWM input is open-drain, 3.3 V logic is fine). Tach: pin 6, interrupt with pull-up to 3.3 V, never 12 V. Pin 3 is not connected on this board and pin 2 is an NFC pad. Share ground between the 12 V supply and the board.
- Use a data USB cable: a charge-only one powers the board but no COM port appears.
- Mount the fan to a fixed plate the same way every session and fix the board rigidly to the fan frame. Keep imbalance masses small (~0.1–0.5 g) and the finger guard on. Current setups and photos are in [`setup/bench_setup.md`](setup/bench_setup.md).

## Open items

- Parts in hand (18 Nov). Still to confirm: PC fan inventory (how many, same model, 3-pin or 4-pin?).
- 12 V supply on hand? (still to confirm, 18 Nov)
- Step 0 is about a month behind the October target. A suggested re-plan and a suggested 31 Dec checkpoint (not yet agreed) are in [`../SESSION_HANDOFF.md`](../SESSION_HANDOFF.md).
- Update proposal sections 7.2, 8.1 and 11 for PC fans and inform the supervisor.
- Feature engineering: see [Feature engineering (to do, step 1)](#feature-engineering-to-do-step-1); discuss priorities with the supervisor.
