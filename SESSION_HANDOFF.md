# Session Handoff

Last updated: Thu 19 Nov 2026. For Jonathan, or a new Claude session picking this up.
The plan is [`docs/implementation_plan.md`](docs/implementation_plan.md) (it wins over the proposal docx).
The to-do list lives in `Work/personal-assistant-bot/todos.md`.

## Where things stand

| Step | Status | Date |
|---|---|---|
| 0. Data | Logger 0.3.2 on the board (all sensors, tach edge timing). Healthy data: 7.4 h on `tapeCorner` (overnight 18–19 Nov) and 31 sessions (~10 h) on `flat4` (19 Nov). Blu-Tack A-B-A night next. | Code 7 Oct; board 18 Nov; healthy data 19 Nov |
| 1. Features | Provisional 48 features coded. Draft spec from own data (11 per-axis order features from 5 s tach-locked windows) in `docs/steps/step1_features.md`, to confirm after the fault night. | 8 Oct; draft 19 Nov |
| 2. Anomaly model | Done on Fraunhofer (MLP autoencoder 48-16-8-16-48, provisional) | 8 Oct |
| 3. RL simulator | Done on Fraunhofer (Q-table + baselines) | 8 Oct |
| 4. FL simulation | Done on Fraunhofer | 8 Oct |
| 5. C++ port | Not started | Planned mid Dec – 10 Jan |
| 6. Real link | Not started (Should tier) | Planned late Jan – Feb |

## Next steps, in order

1. **Imbalance night (Blu-Tack), `flat4`, A-B-A.** Protocol, commands and the analysis fixed in advance:
   [`docs/experiments/2026-11-19_imbalance_ABA.md`](docs/experiments/2026-11-19_imbalance_ABA.md)
   (`host/analysis/abtest.py`, then `fault_eval.py`). Then a healthy `flat4` campaign overnight.
2. **Step 1 on own data:** confirm or revise the draft spec in `docs/steps/step1_features.md` on the
   real fault blocks (5 s tach-locked per-axis orders; the stricter `feature_eval.py` is the reference
   method, not the early overnight-report numbers). Then port it into `host/features/`.
3. **Step 1 follow-up**: `features.report`, `models.compare`, then a short `rl.train`, all `--source own`.
4. **Re-run steps 2–4 with `--source own`.** Step 4 needs at least 3 fan@mount clients
   (`fl/simulate.py` stops otherwise), so with one fan only steps 1–3 run.

**Bench tips** (from reading the code):
- `--source own` loads every session in `data/raw/`. Bring-up sessions would count as normal
  training data, and `--fan none` would count as an extra fan. Until the recorder is changed
  (pending, see "Discussed with Jonathan"), record bring-up with `--out data/bringup`.
- Always pass `--mount`. The current mount is **`flat4`** (fan lying flat on four corner screws, from
  19 Nov). `tapeCorner` is the standing setup used 18–19 Nov. Photos and details are in
  `docs/setup/bench_setup.md`. The default is `default`, which becomes a separate client.
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
- Python tests: `pytest host -q` → **35 passed**.

## 19 Nov (day): flat4 mount, reviews, logger 0.3.2

- **Mount moved to `flat4`.** The fan lies flat across two boxes; the mount check passed (`docs/setup/bench_setup.md`). A healthy campaign ran on it from 10:06 to 19:12 (`data/raw/campaign_20261119-100654.log`, restarted once at 10:06 to add the 5 % sweep; analysis in `results/own/flat4_healthy`). All 31 flat4 sessions of the day passed `session_check.py`.
- **19:13 onwards: healthy `ab_block` recordings** back to back (notes "pre-night healthy ab_block null run", log `data/raw/prenight_*.log`), until the A-B-A starts. They measure the block-to-block noise of the real profile without handling. They are not part of the A-B-A analysis.
- **Two independent reviews** (subagents) checked the code and the analysis. They found:
  - **Tach lock bug (0.3.1).** The glitch filter could lock at 1/2 or 1/3 of the real speed after one lost edge or a fast spin-up. Fixed in **logger 0.3.2**: simulated, and checked on the fan (tach vs audio within 0.15 %, smooth 30↔100 % steps).
  - **Wrong rpm in the steps 1–4 loader.** `session_recording` mapped rpm using STATUS rows from before START. Fixed, with a test.
  - **Analysis fixes:**
    - tach-only speed for 0.3.1+ data (the audio-refined speed was circular for audio features);
    - order amplitudes in true RMS;
    - per-axis features.
  - **Overnight report claims were too strong.** Order features were ranked on false alarms only; the unseen-speed test was thin; thresholds were set on random neighbouring windows. `host/analysis/feature_eval.py` redoes this properly: speed-conditioned normalisation, session-held-out thresholds, leave-one-duty-out, synthetic faults.
- **Stricter feature evaluation** (`feature_eval.py` on the overnight data; table in REPORT section 7):
  - Features must be **per axis**.
  - Average about **5 s** (8 windows) before scoring.
  - A simple **max |z|** on speed-normalised per-axis order features detects a doubled in-plane 1× 99.5 % of the time at 1.3 % false alarms. That matches the autoencoder, with fewer false alarms.
  - **Unseen speeds are not solved** at 10 % duty spacing: amplitude vs speed is uneven. The campaign now adds a 5 % sweep, and learning a new speed is a candidate RL role (ADAPT at a new speed).
  - Repeat this on `flat4` and on the real Blu-Tack data.
- **flat4 feature evaluation (14:30, 18 sessions)**, in [`results/own/flat4_healthy/REPORT.md`](results/own/flat4_healthy/REPORT.md):
  - The flat mount is quiet in the rotor plane. The in-plane 1× is 0.3–1 mg at 30–60 %, about the background level in a 0.62 s window, so a synthetic ×2 is mostly missed (2–45 %, vs 99.5 % on tapeCorner).
  - A **5 s tach-locked window** (`host/analysis/window_length.py`) finds a stable 1× line from 50 % up, with 2–8× the background. At 30–40 % there is no 1× above the background.
  - **Tested as feature set L** (`long_windows.py` sidecars + `feature_eval.py --rotate`), corrected after a methods review:
    - At matched 2 % false alarms and about 10 s of data, ×1.5 in-plane is caught 90–92 % of the time at 70–80 % (0.62 s windows: 56–68 %).
    - On `tapeCorner`: ×1.5 overall 85 % vs 29 %.
    - At 40–60 % on `flat4`, neither set catches ×1.5.
    - Thresholds from one held-out session give unstable false alarms (1–9 %), so calibration needs more data.
  - For step 1: take order amplitudes from 5 s tach-locked windows (a single-bin DFT on the board). A uniform spread floor of 0.03 hurts; if needed, floor per feature.
  - The 60 % step is erratic with short windows, likely aliasing; check again after 0.4.0.
- **Evening (31 sessions), in the flat4 report, section "Full day":**
  - **Calibration.** A pooled leave-one-session-out threshold (`feature_eval.py --loso`) is far more stable than one held-out session. Use max|z|: Mahalanobis and the AE follow drift more.
  - **Afternoon drift.** The healthy in-plane 1× drifted from about 16:00 (board z ×0.7 at 70–80 %), about the size of a ×1.5 fault. Per-window detection of ×1.5 is therefore marginal when the model's spread includes it. Slow drift is the agent's ADAPT job, and the A-B-A comparison stays primary.
  - **Speed gate.** Logger 0.3.1 data needs a speed gate (`--speed-gate 0.03`): bad tach readings put the 5 s narrowband features on the wrong bin.
  - **Review.** A methods review corrected the first, overstated version of these claims; the percentile and the gate were chosen on test data.
  - **Tonight's per-window result.** `fault_eval.py` now uses the pooled threshold for its main result (fixed before any fault data).
- **A-B-A dry run** on healthy flat4 sweeps (fake B blocks) works end to end. `abtest.py` now also prints a combined 50–80 % effect, a spread floor of 0.02, and axial, all-axis and gyro secondaries. Details are in the protocol doc.
- **Imbalance night plan:** `docs/experiments/2026-11-19_imbalance_ABA.md` (A-B-A with sham and hub-mass controls; `ab_block` profile; analysis `host/analysis/abtest.py`, fixed in advance).
- **Next firmware change (after tonight):** stop the IMU aliasing of the motor's 24×/36×/48× orders (IMU at 1.66 kHz plus on-board decimation, or the 200 Hz filter). Then re-record the main dataset.

## Rules

- `data/` is not in git. **Back it up after each recording day** (OneDrive or external drive).
- Reported results use `--source own` only.
- Fraunhofer and UCI are for development only, never for reported results.

## How to resume

Open Claude Code in this folder and say:
"Read SESSION_HANDOFF.md, then let's continue with step 0".
