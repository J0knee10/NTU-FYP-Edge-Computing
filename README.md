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

## Repository layout

| Path | Contents |
|---|---|
| `docs/` | Revised proposal, literature sources, school FYP schedule |
| `archive/` | Superseded proposals, notes and the first CWRU prototype (see `archive/README.md`) |

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
