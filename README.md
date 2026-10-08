# Predictive Maintenance at the Edge

NTU Final Year Project, AY2026/2027 — Jonathan Low Seng Kian

A plug-and-play fan fault detector that learns a fan's normal vibration and sound on the
microcontroller itself. A reinforcement learning agent decides, window by window, whether the
on-device anomaly model may keep learning (ADAPT), must stop learning (FREEZE), or should raise a
fault (ALERT). Federated learning shares model weights, never raw data, across a fleet of devices.

Full proposal: [`docs/FYP_predictive_maintenance_proposal.docx`](docs/FYP_predictive_maintenance_proposal.docx)
Implementation plan and decisions since the proposal: [`docs/implementation_plan.md`](docs/implementation_plan.md)

## Hardware

- Arduino Nano 33 BLE Sense **Rev1** — nRF52840 (Cortex-M4F @ 64 MHz, 256 KB SRAM, 1 MB flash),
  LSM9DS1 IMU (accelerometer up to ~952 Hz), MP34DT05 PDM microphone, HTS221 temperature/humidity
- Laptop (Raspberry Pi later, optional) as BLE gateway, MQTT broker and FL aggregator
- 12 V PC fans as the test machines (PWM speed control, tach for ground-truth RPM); faults injected mechanically

## Setup

Python 3.13, from the repo root:

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pytest host
```

Arduino: Arduino IDE 2 with the **Arduino Mbed OS Nano Boards** package; board **Arduino Nano 33 BLE**.

## Repository layout

| Path | Contents |
|---|---|
| `docs/` | Revised proposal, implementation plan, literature sources, school FYP schedule |
| `docs/steps/` | One how-to guide per step: what to do, what should happen, how to check it worked |
| `firmware/` | Arduino sketches that run on the Nano 33 BLE Sense Rev1 |
| `host/` | Python code that runs on the laptop (one package per component, shared tests) |
| `data/` | Recordings, downloaded datasets and caches (not in git; back up `data/raw/` separately) |
| `results/` | Outputs of steps 2–4 per data source, e.g. `results/step3/fraunhofer/` |
| `archive/` | Superseded proposals, notes and the first CWRU prototype (see `archive/README.md`) |

Code is organised by **component**, not by step, because later steps reuse earlier code (the feature
extractor from step 1 is used by every step after it). Each step has a guide in `docs/steps/` that
points to the code it uses.

Steps 1–4 run on any data source with `--source fraunhofer|uci|own`. Until our own recordings
exist they are developed on the public Fraunhofer unbalance dataset (see the plan's Datasets section);
reported results will use `--source own`.

| Step | Guide | Code |
|---|---|---|
| 0. Data collection | [`docs/steps/step0_data_collection.md`](docs/steps/step0_data_collection.md) | `firmware/logger/`, `firmware/smoke_train/`, `host/fanlog/` |
| 1. Feature spec | [`docs/steps/step1_features.md`](docs/steps/step1_features.md) | `host/features/` |
| 2. Anomaly model | [`docs/steps/step2_anomaly_model.md`](docs/steps/step2_anomaly_model.md) | `host/models/` |
| 3. RL simulator | [`docs/steps/step3_rl_simulator.md`](docs/steps/step3_rl_simulator.md) | `host/rl/` |
| 4. FL simulation | [`docs/steps/step4_fl_simulation.md`](docs/steps/step4_fl_simulation.md) | `host/fl/` |
| 5. C++ port | — | `firmware/detector/` (planned) |
| 6. Real link | — | `host/gateway/` (planned) |

## Hard deadlines

From [`docs/Dates Aug 2026.pdf`](docs/Dates%20Aug%202026.pdf).

| Date | Deadline |
|---|---|
| 10 Aug 2026 | FYP starts (done) |
| 31 Aug 2026 | Project plan / strategy to supervisor (done) |
| 25 Jan 2027 | Interim Report (Must tier: single-fan device with on-device learning and RL gate) |
| 22 Mar 2027 | Final Report to supervisor and examiner — **the graded version** |
| 16 Apr 2027 | Amended Final Report (final submission; upload to DR-NTU) |
| 7, 10–12 May 2027 | Oral presentation and demo (20 min + 10 min Q&A) |
