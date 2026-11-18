# Session Handoff

Last updated: Wed 18 Nov 2026. For Jonathan, or a new Claude session picking this up.
The plan is [`docs/implementation_plan.md`](docs/implementation_plan.md) (it wins over the proposal docx).
The to-do list lives in `Work/personal-assistant-bot/todos.md`.

## Where things stand

| Step | Status | Date |
|---|---|---|
| 0. Data | Tooling written and compiles; **never run on hardware**; no recordings yet. Parts in hand. | Code 7 Oct; parts 18 Nov |
| 1. Features | Provisional 48 features coded. Real feature engineering not started. | 8 Oct |
| 2. Anomaly model | Done on Fraunhofer (MLP autoencoder 48-16-8-16-48, provisional) | 8 Oct |
| 3. RL simulator | Done on Fraunhofer (Q-table + baselines) | 8 Oct |
| 4. FL simulation | Done on Fraunhofer | 8 Oct |
| 5. C++ port | Not started | Planned mid Dec – 10 Jan |
| 6. Real link | Not started (Should tier) | Planned late Jan – Feb |

## Next steps, in order

1. **Step 0, Parts B → G** of [`docs/steps/step0_data_collection.md`](docs/steps/step0_data_collection.md). Part A is already done on this laptop.
   - B: mount fan and board, wire PWM/tach, do the two multimeter checks.
   - C: smoke test (5 min, no fan). Save the RAM and time numbers for the interim report.
   - D–F: flash the logger, then bring-up sessions 1–3 (saved to `data/bringup`, see bench tips).
2. **Minimum data set, one fan (`pc01` on `plateA`), before exams.** About 2.7 h of recording:
   normal sweep ×2, steady ×2, benign drift ×2, imbalance at 3 severities (0.1 / 0.2 / 0.5 g, sweep).
   Other fans and faults come later.
3. **Step 1 on own data**: order-normalised bands first (plan, "Feature engineering", idea 1).
   Compare with `features.report`, `models.compare`, then a short `rl.train`, all `--source own`.
4. **Re-run steps 2–4 with `--source own`.** Step 4 needs at least 3 fan@mount clients
   (`fl/simulate.py` stops otherwise), so with one fan only steps 1–3 run.

**Bench tips** (from reading the code):
- `--source own` loads every session in `data/raw/`. Bring-up sessions would count as normal
  training data, and `--fan none` would count as an extra fan. Until the recorder is changed
  (pending, see "Discussed with Jonathan"), record bring-up with `--out data/bringup`.
- Always pass `--mount plateA`. The default is `default`, which becomes a separate client.
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
   - Temperature and humidity (HTS221; the logger already records both) are a candidate extra
     context input (plan's feature idea #10). Test once own data exists. Supervisor question, not decided.
5. **Pending, Jonathan to answer:** Claude offered to change the recorder so bring-up sessions save
   outside `data/raw/` by default (so they can't mix into training). Until then, use
   `--out data/bringup` and always pass `--mount plateA`.

## Open questions for Jonathan

- Fan inventory: how many, which model, 3-pin or 4-pin? (3-pin means no PWM: see Part B.)
- Is a 12 V supply on hand?
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
- `arduino-cli` 1.5.1, core `arduino:mbed_nano` 4.6.0, board `nano33ble`. Compile only, not flashed:
  - `firmware/smoke_train`: OK, 88 KB flash (8 %), 53 KB RAM (20 %).
  - `firmware/logger`: OK, 113 KB flash (11 %), 64 KB RAM (24 %).

## Rules

- `data/` is not in git. **Back it up after each recording day** (OneDrive or external drive).
- Reported results use `--source own` only.
- Fraunhofer and UCI are for development only, never for reported results.

## How to resume

Open Claude Code in this folder and say:
"Read SESSION_HANDOFF.md, then let's continue with step 0".
