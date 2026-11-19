# Session Handoff

Last updated: Thu 19 Nov 2026. For Jonathan, or a new Claude session picking this up.
The plan is [`docs/implementation_plan.md`](docs/implementation_plan.md) (it wins over the proposal docx).
The to-do list lives in `Work/personal-assistant-bot/todos.md`.

## Where things stand

| Step | Status | Date |
|---|---|---|
| 0. Data | Logger 0.3.1 on the board (all sensors, fan wired). 7.4 h healthy overnight campaign recorded (`pc01` on `tapeCorner`). Fault (Blu-Tack imbalance) night next. | Code 7 Oct; board 18 Nov; healthy data 19 Nov |
| 1. Features | Provisional 48 features coded. Real feature engineering not started. | 8 Oct |
| 2. Anomaly model | Done on Fraunhofer (MLP autoencoder 48-16-8-16-48, provisional) | 8 Oct |
| 3. RL simulator | Done on Fraunhofer (Q-table + baselines) | 8 Oct |
| 4. FL simulation | Done on Fraunhofer | 8 Oct |
| 5. C++ port | Not started | Planned mid Dec – 10 Jan |
| 6. Real link | Not started (Should tier) | Planned late Jan – Feb |

## Next steps, in order

1. **Imbalance night (Blu-Tack), same mount, A-B-A.** Plan and safety notes in
   [`results/own/overnight/REPORT.md`](results/own/overnight/REPORT.md) section 9. Don't touch the
   fan or board before it. Normal sessions for the minimum set are done (overnight, 19 Nov).
2. **Step 1 on own data**: order-normalised features first. The overnight data already shows why:
   fixed-Hz features give 93 % false alarms at unseen speeds, order amplitudes 0.26 %
   (`host/analysis/night_summary.py`, section 7). Use the 0.3.1 tach as the speed reference.
   Then port the order features into `host/features/`.
3. **Step 1 follow-up**: compare with `features.report`, `models.compare`, then a short `rl.train`, all `--source own`.
   Compare with `features.report`, `models.compare`, then a short `rl.train`, all `--source own`.
4. **Re-run steps 2–4 with `--source own`.** Step 4 needs at least 3 fan@mount clients
   (`fl/simulate.py` stops otherwise), so with one fan only steps 1–3 run.

**Bench tips** (from reading the code):
- `--source own` loads every session in `data/raw/`. Bring-up sessions would count as normal
  training data, and `--fan none` would count as an extra fan. Until the recorder is changed
  (pending, see "Discussed with Jonathan"), record bring-up with `--out data/bringup`.
- Always pass `--mount` (the current mount is `tapeCorner`: board taped to the fan-frame corner). The
  default is `default`, which becomes a separate client.
- Run the recorder from the repo root (profile paths and `--out data/bringup` are relative).

## Schedule check

- **Plan:** step 0 in October; steps 2–4 by mid/late Nov. **Now:** steps 1–4 code is done early,
  but only on Fraunhofer. Own data is about a month behind.
- **Suggested re-plan (for Jonathan to confirm, not decided):**
  - By ~end Nov: bench set up, smoke test, bring-up, minimum set on one fan.
  - Exams (light): re-run steps 1–3 on own data; try order-normalised bands.
  - By mid Dec: freeze a feature spec, so the C++ port does not chase a moving target.
  - Mid Dec – 10 Jan: C++ port as planned (31 Dec checkpoint below). Record other fans in Jan
    or after the interim.
- **Must be true by Mon 25 Jan (Must tier, one fan):** own recordings; fixed feature spec;
  features + model + SGD + Q-table running on the board and matching the NumPy twin;
  steps 2–3 results on own data; smoke-test numbers. FL on own data is not needed yet.

## Discussed with Jonathan (18 Nov)

1. **What step 5, the "C++ port", means.** The board code today (`logger`, `smoke_train`) is C++
   but only data tooling. The detector (features, autoencoder and its training step, RL agent) is
   Python only, on purpose (faster to experiment). Step 5 rewrites it in C++ (`firmware/detector/`,
   planned); the Python version is the reference it must match (golden vectors).
2. **Exams (≈ late Nov – mid Dec): light work only** (tidy results, read for the port). If the
   minimum data set isn't recorded before exams, exams can take it, but not past mid Dec: the port
   needs the data. Winter break (mid Dec – ~10 Jan) is full-time FYP. Dates approximate: check NTU's calendar.
3. **Suggested checkpoint, Thu 31 Dec** (suggestion, not in the plan): steps 0–3 done on own data;
   C++ parts written, matching the Python version on the PC, and running on the board.
   1–10 Jan: full loop on the board with a real fan, plus RAM, time and energy profiling. 11–25 Jan: Interim Report.
4. **RL agent role confirmed** (as agreed 23 Sep): per window ADAPT / FREEZE / ALERT. Its job is to
   tell a harmless change (speed, re-mount, wear-in) from a developing fault, so the model never
   learns a fault as normal. State today (`host/rl/state.py`): score level, trend, persistence, speed-change flag.
   - Temperature and humidity (SHT30; the logger already records both) are a candidate extra
     context input (plan's feature idea #10). Test once own data exists. Supervisor question, not decided.
5. **Pending, Jonathan to answer:** Claude offered to change the recorder so bring-up sessions save
   outside `data/raw/` by default (so they can't mix into training). Until then, use
   `--out data/bringup` and always pass `--mount plateA`.

## Open questions for Jonathan

- Fan inventory: `pc01` is known (see `docs/setup/bench_setup.md`). Any other fans for more FL clients?
- Supervisor: order-normalised vs audio features first? How much feature work does the report need?
  Temperature/humidity as RL context (idea #10)?
- Recorder: save bring-up sessions outside `data/raw/` by default? (Claude offered, 18 Nov.)
- Proposal sections 7.2, 8.1, 11 still need updating for PC fans (plan, Open items).
- Clean-up: `circuit_design_guide.md` is at the repo root and in `docs/`. The two differ only in
  the "Location" line (line 4). It is a general circuit-design note (EIT, ADS1298, STM32), not
  fan-specific. Keep `docs/` only, or move it to the EIT project?

## Health check (18 Nov)

- Git: `main`, up to date with `origin/main`. Last commit `30033fb` (30 Oct). Today's doc edits
  (this file, `README.md`, `docs/implementation_plan.md`, `docs/steps/step0_data_collection.md`)
  are not committed yet.
- Python tests: `pytest host -q` → **30 passed** (6 s).

## Board correction and bring-up (18 Nov, evening)

- **The board is an Adafruit Feather nRF52840 Sense (original revision), not a Nano 33 BLE Sense.**
  Same nRF52840. I2C scan: LSM6DS33 IMU (WHO_AM_I 0x69), LIS3MDL, APDS9960, SHT30, BMP280.
  Docs, firmware and `host/` updated. The proposal docx may still name the Nano.
- Toolchain: the `arduino-cli` 1.1.1 bundled with Arduino IDE 2, core `adafruit:nrf52` 1.7.0, FQBN
  `adafruit:nrf52:feather52840sense`, board on COM6. The first USB cable was charge-only.
  - `firmware/smoke_train`: 61 KB flash (7 %), 17 KB RAM. On the board: 231 us forward, 582 us train step, loss falls.
  - `firmware/logger` 0.2.0: 79 KB flash (9 %), 27 KB RAM (11 %). Bench test without a fan: IMU
    ~839 Hz with 0 overruns over 16 s, 0.985 g at rest; recovers from a forced 4 s host stall with one
    counted overrun; audio 16 kHz with 0 drops; SHT30 reads; 0 CRC errors. PWM/tach not yet tested.
  - `firmware/i2c_scan`: new bring-up sketch.
- Accelerometer rate is now **833 Hz** (`BOARD_RATE_HZ`). **`results/step2-4/fraunhofer` were made at
  952 Hz and are stale**; re-run steps 2–4 before quoting them.
- `.venv` is Python 3.11 and out of date with `requirements.txt` (no editable `host` install; pytest
  and pyserial were added 18 Nov). Re-run `pip install -r requirements.txt` when convenient.

## Fan wired, logger 0.3.x and overnight campaign (18–19 Nov)

- Fan `pc01` = Thermalright TL-H12-X28-R7 (120 mm, 7 blades, rated 2400 rpm), wired PWM pin 5, tach pin 6,
  grounds shared. It stands **free on its edge on the floor**; the board is taped flat on the top edge of
  the frame near a corner (`tapeCorner`). Photo, board-axis mapping and handling rules:
  [`docs/setup/bench_setup.md`](docs/setup/bench_setup.md).
- Logger 0.3.0 added the gyro, magnetometer, pressure and light, and fixed an nRF52 I2C (TWIM) race
  that corrupted 1.8 % of accelerometer samples. The recorder now reads on a thread with a 1 MB buffer.
- Logger 0.3.1 (19 Nov) fixes the tach: `micros()` on this core ticks every 976 µs, so the glitch
  filter failed and the speed read 1–1.6 % high under PWM. Tach edges are now timed on a 1 MHz timer (TIMER4).
  STATUS grows to 52 bytes (`tach_edge_us`, `tach_rejected`); the host still reads older sessions.
- Overnight campaign 00:07–07:49: 22 sessions, 7.4 h, every sensor, no data loss. Placement is fine
  for the fault test (caveats: slow 1× drift, 0.5× rocking at 90–100 %). Full findings:
  [`results/own/overnight/REPORT.md`](results/own/overnight/REPORT.md).
- Python tests: `pytest host -q` → **34 passed**.

## Rules

- `data/` is not in git. **Back it up after each recording day** (OneDrive or external drive).
- Reported results use `--source own` only.
- Fraunhofer and UCI are for development only, never for reported results.

## How to resume

Open Claude Code in this folder and say:
"Read SESSION_HANDOFF.md, then let's continue with step 0".
