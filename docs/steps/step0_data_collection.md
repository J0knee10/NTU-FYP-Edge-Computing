# Step 0: Data Collection

**Goal:** labelled recordings of every PC fan you have, both normal and with faults, at different speeds.
Every later step (features, model, RL simulator, FL simulation) is built on these recordings.
This step also runs a quick check that the board can train the model at all.

## How it works

```
                    USB cable (power + data)
  ┌──────────┐   vibration   ┌────────────────────┐  binary frames   ┌────────────────────┐
  │  PC fan  │ ────────────► │ Feather nRF52840   │ ───────────────► │ Laptop: recorder   │
  │  (12 V)  │ ◄──── PWM ─── │ Sense: logger      │ ◄── commands ─── │ (Python)           │
  │          │ ──── tach ──► │                    │  "PWM 500" etc.  │                    │
  └──────────┘               └────────────────────┘                  └─────────┬──────────┘
                                                                               ▼
                                                    data/raw/<session>/ : meta, events, stream, session.npz
```

- **The board measures.** Vibration and rotation (accelerometer + gyro, 833 times a second), magnetic
  field (~274 Hz), sound (optional, 16 kHz), temperature, humidity, pressure, light and fan speed, all
  sent to the laptop. It also sets the fan speed when told to.
- **The laptop is in charge.** The recorder runs a speed script ("50 % for 5 min, then 70 %..."), saves
  everything the board sends, and labels the session with what you tell it (which fan, which fault).

## Code used in this step

| Path | What it does |
|---|---|
| `firmware/smoke_train/` | One-off benchmark: trains a 48-16-8-16-48 autoencoder on the board and reports RAM and time per training step |
| `firmware/logger/` | Data logger firmware (sensors, fan control, USB streaming). Settings are in `config.h` |
| `firmware/i2c_scan/` | Bring-up check: lists the sensors on the I2C bus and identifies the IMU revision |
| `host/fanlog/record.py` | Records one labelled session from the logger |
| `host/fanlog/campaign.py` | Unattended (overnight) recording: mount check, then sweep / 70 % / drift / 30-min steady cycles until a set time |
| `host/analysis/` | Exploration of own sessions: per-window order features, stability, drift, report figures (see `results/own/overnight/REPORT.md`) |
| `host/fanlog/session.py` | Converts a session's raw stream into `session.npz` and checks for lost data |
| `host/fanlog/datasets.py` | Downloads and loads public datasets (UCI cooler-fan accelerometer set, Fraunhofer unbalance set) |
| `host/profiles/*.json` | Fan speed scripts the recorder plays during a session |

---

## Part A: One-time setup

**Python** (in a terminal at the repo root):

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pytest host
.venv\Scripts\python -m fanlog.datasets uci-accelerometer
```

**Arduino IDE 2:**

1. File → Preferences → Additional boards manager URLs: add
   `https://adafruit.github.io/arduino-board-index/package_adafruit_index.json`.
2. Boards Manager → install **Adafruit nRF52**.
3. Tools → Board → **Adafruit Feather nRF52840 Sense**.
4. Opening a `.ino` file also opens the `.h` files in the same folder as tabs. They are part of the sketch.

**Use a data USB cable.** A charge-only cable lights the board up but no COM port appears. The board
shows up as "USB Serial Device" with Adafruit's vendor ID `239A`.

If an upload fails, double-tap the board's reset button to enter the bootloader (the red LED pulses and
a `FTHRSNSBOOT` drive appears), then upload again.

**Check the board revision once:** upload `firmware/i2c_scan` and open the Serial Monitor. The logger
supports the original Feather Sense (IMU line says `LSM6DS33`, WHO_AM_I `0x69`). Newer boards have an
LSM6DS3TR-C (`0x6A`), which needs a different driver.

> **Only one program can use the serial port at a time.** Close the IDE's Serial Monitor before running
> the Python recorder, or the recorder cannot connect.

<details>
<summary>Command-line alternative (arduino-cli)</summary>

`arduino-cli` is the command-line tool the IDE uses internally. It does the same job without the GUI.
IDE 2 ships a copy at `C:\Program Files\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe`;
pass `--config-file %USERPROFILE%\.arduinoIDE\arduino-cli.yaml` so it shares the IDE's settings.

```
arduino-cli config add board_manager.additional_urls https://adafruit.github.io/arduino-board-index/package_adafruit_index.json
arduino-cli core update-index
arduino-cli core install adafruit:nrf52
arduino-cli board list
arduino-cli compile --fqbn adafruit:nrf52:feather52840sense firmware/logger
arduino-cli upload  --fqbn adafruit:nrf52:feather52840sense -p COMx firmware/logger
arduino-cli monitor -p COMx
```
</details>

## Part B: Prepare the hardware

### Mounting

Mounting changes the vibration signal as much as some faults do, so keep it repeatable:

- Screw the fan to a rigid plate (wood or acrylic) with all four screws, and place the plate on the
  same surface each time.
- Fix the board rigidly to the **fan frame**, not the plate, in the same position and orientation every
  session. Thin double-sided tape plus a cable tie works; foam tape damps vibration and should be avoided.
- Give each distinct setup a mount id (e.g. `plateA`) and photograph it. Moving to a different table or
  plate means a new mount id. That change counts as benign drift, which the RL agent must learn to
  tolerate.

### Wiring

Standard 4-pin PC fan pinout (wire colours vary, so check the fan's label or datasheet):

| Fan pin | Function | Connect to |
|---|---|---|
| 1 | GND | 12 V supply GND **and** board GND |
| 2 | +12 V | 12 V supply + only |
| 3 | Tach (open collector, 2 pulses per revolution) | Feather pin **6** |
| 4 | PWM (25 kHz control input) | Feather pin **5** (see check below) |

The board is powered over USB from the laptop. **Never connect 12 V to any board pin**: the nRF52840
is 3.3 V only. Don't use pins 2 or 3 for the fan: on the Feather Sense, 3 is not connected to anything
and 2 is shared with the NFC antenna pad. Pins are set in `firmware/logger/config.h`.

Do these two checks with a multimeter **before** connecting pins 5 and 6. Power the fan from 12 V with
pins 3 and 4 not connected to anything:

1. **Tach (pin 3) to GND.** Expect about 0 V or a floating reading. The firmware pulls it up to 3.3 V.
   If you read more than 3.3 V, the fan has its own pull-up: do not connect it directly. Use a resistor
   divider (e.g. 10 kΩ / 20 kΩ) instead.
2. **PWM (pin 4) to GND.** The fan pulls this pin up internally, to 3.3 V or 5 V depending on the model.
   - **3.3 V or less:** connect directly to pin 5.
   - **About 5 V:** drive it through a small N-MOSFET (e.g. 2N7000) or NPN transistor: pin 5 → 1 kΩ →
     gate/base, drain/collector → fan pin 4, source/emitter → GND. Then set `FAN_PWM_INVERT 1` in
     `firmware/logger/config.h`, because the transistor inverts the signal.

The fan runs at full speed until the recorder sends its first PWM command.

**3-pin fan (no PWM wire):** set `PIN_FAN_PWM -1` in `config.h`. Change speed by adjusting the supply
voltage instead, and write the voltage in `--notes`.

## Part C: Smoke test (about 5 minutes, no fan needed)

This checks one thing before months go into it: can this board train the model fast enough?

1. Open `firmware/smoke_train/smoke_train.ino` and upload it.
2. Open the Serial Monitor. You should see something like:
   ```
   --- smoke_train: 48-16-8-16-48 MLP autoencoder, float32, SGD ---
   parameters:            1880
   model RAM (W,b,x,y):   8224 bytes
   gradient scratch RAM:  352 bytes
   forward per window:    231.4 us
   train step per window: 582.0 us
   loss before / after:   0.874847 / 0.091550
   result: OK (loss decreased)
   ```
   (Measured on our board, 18 Nov 2026.)
3. **It worked if** the last line says `OK`. Training on one window should take well under a few
   milliseconds, since a window is 1 second of data. Save the numbers: they go into the interim report.

## Part D: Flash the logger

1. If your PWM check in Part B needed a transistor, first set `FAN_PWM_INVERT 1` in the `config.h` tab.
2. Open `firmware/logger/logger.ino` and upload it.
3. **Close the Serial Monitor.** The logger sends binary data, so the monitor would only show gibberish,
   and it would block the recorder.

**What should happen:** when the board boots, it silently sets up the sensors, checks the IMU buffer,
and measures its real sample rate for 1 second. It then waits for commands. The red LED stays off
until recording starts and blinks while recording.

## Part E: Record a session

In a terminal at the repo root:

```
.venv\Scripts\python -m fanlog.record --fan pc01 --mount plateA --fault normal --profile host/profiles/speed_sweep.json
.venv\Scripts\python -m fanlog.record --fan pc01 --mount plateA --fault imbalance --severity 0.2g --profile host/profiles/speed_sweep.json
.venv\Scripts\python -m fanlog.record --fan pc01 --mount plateA --fault normal --pwm 500 --duration 60
```

Use `--list-ports` if the board isn't found automatically, then pass `--port COMx`. Add `--audio` to
also record the microphone. Always pass `--mount`: the default (`default`) would become a separate
FL client.

**What happens, in order:**

1. The recorder finds the board's USB port and asks it for its configuration (sensor rates, pins).
2. It creates a folder like `data/raw/20261008-143000_pc01_normal_none/` and saves your labels.
3. It sends `START`. The board's LED starts blinking and data flows.
4. It plays the speed script step by step, telling the board to change the fan's PWM. A live line
   updates every second:
   ```
   step 3/9: duty40 pwm=400 for 120 s
     pwm= 40.0%  rpm=  1180  imu= 838.0 Hz  overruns=0  audio_drop=0  temp=27.3C  crc_err=0  lost=0
   ```
5. At the end (or on Ctrl+C) it sends `STOP`, converts the recording, and prints a summary. If any data
   was lost, it adds `WARNING` lines.

**It worked if:**
- `rpm` changes when the PWM step changes, and is steady within a step.
- `imu` stays around 825–835 Hz (nominal 833 Hz; the IMU's own clock and the board's RC time base both
  differ from nominal by under 1 %).
- `rpm` matches the fan's sound. Logger 0.3.2 times tach edges on a 1 MHz crystal timer and filters PWM
  glitches without locking onto a fraction of the speed. 0.3.0 counted 1–1.6 % extra pulses under PWM;
  0.3.1 could lock at 1/2 or 1/3 of the speed after a lost edge. Use 0.3.2 or later.
- `overruns`, `audio_drop`, `crc_err` and `lost` stay at 0, and the summary has no `WARNING` lines.

### What ends up in the session folder

| File | Contents |
|---|---|
| `meta.json` | Your labels (fan, mount, fault, severity, notes), the speed script, the board's configuration, the git commit |
| `events.jsonl` | Timestamped log of every command and speed change. These become the segment labels later. |
| `stream.bin` | The exact bytes the board sent. The master copy, so the data can always be re-converted. |
| `session.npz` | The data as numpy arrays (vibration, audio, rpm, temperature). This is what step 1 loads. |
| `summary.json` | Quality report: samples, gaps, measured sample rate, errors |

To re-convert a session (e.g. after a converter fix): `.venv\Scripts\python -m fanlog.session data/raw/<session>`.

## Part F: Bring-up order

Do these the first time, in this order. Each one checks one thing. Add `--mount plateA --out data/bringup`
to each command, so these test sessions stay out of `data/raw/` (`--source own` trains on everything
there, and `--fan none` would count as an extra fan).

| # | Session | Command | Checks |
|---|---|---|---|
| 1 | Fan unplugged, 30 s | `--fan none --fault normal --notes "fan off, noise floor" --duration 30` | Board and USB link; sensor noise floor |
| 2 | Fan at 50 %, 60 s | `--fan pc01 --fault normal --pwm 500 --duration 60` | Tach: rpm appears and is stable |
| 3 | Same, with audio | add `--audio` | The USB link can carry microphone data too. If `audio_drop` stays above 0, record without audio for now. |

If `meta.json` shows `"imu_fifo": "0"` under `board_info`, the IMU buffer self-test failed and the
logger fell back to polling. Sort that out before recording real data. `"imu_burst": "0"` is less
serious: the buffer works but is read one value at a time, which is slower.

## Part G: Data collection

Fault labels: `normal`, `imbalance`, `blade_damage`, `loose_mount`, `bearing_wear`, `obstruction`,
`other`. Put the amount in `--severity` (e.g. `0.2g`, `25pct`, `2screws`) and anything unusual in `--notes`.

Each fan becomes one simulated client for federated learning, so record **every fan you have**, not
just one. Start with the minimum set on one fan (`pc01` on `plateA`; see
[`../../SESSION_HANDOFF.md`](../../SESSION_HANDOFF.md)): it is enough for steps 1–3. Other fans and
faults come after.

| Session | Profile | Repeats per fan | Purpose |
|---|---|---|---|
| Normal, sweep | `speed_sweep` | 2 (different days if possible) | Baseline across all speeds; pre-training data |
| Normal, steady | `constant_10min` | 2 | Longer stretches of clean normal data |
| Normal, benign drift | `benign_drift` | 2, plus 1 on a different mount | Scenario S1: changes the agent must ADAPT to, not alert on |
| Imbalance | `speed_sweep` | 3 severities (e.g. 0.1, 0.2, 0.5 g of tape or Blu-Tack on one blade) | Main fault; graded severities let the simulator build gradual faults (S2) |
| Loose mount | `speed_sweep` | 2 levels (e.g. 1 screw loosened, 2 screws loosened) | Looseness signature |
| Obstruction | `constant_10min` | 25 % and 50 % of the inlet covered with card | Airflow / acoustic change |
| Blade damage | `speed_sweep` | 1, **only on a spare fan you can sacrifice** | Permanent damage |
| Bearing wear | `speed_sweep` | Only if you have an old, noisy fan | Real wear is hard to fake reversibly |

**Unattended runs.** `python -m fanlog.campaign --port COM6 --fan pc01 --mount tapeCorner --fault normal --until 07:30`
runs a mount check, then repeats sweep / 70 % / benign drift / 30-min steady cycles until the given time,
then a final mount check. It keeps Windows awake, retries a failed session, and stops early if a file
named `STOP` appears in the output folder. `python host/analysis/autoproc.py <campaign log>` builds the
analysis tables as sessions finish. For a fault night use A-B-A: a healthy reference right before,
the fault sessions, then a healthy session after removing the fault.

A truly gradual fault can't be recorded mechanically. The RL simulator in step 3 builds gradual-fault
episodes by splicing sessions of increasing severity.

`data/` is not tracked by git. **Back it up** (OneDrive, external drive) after each recording day.

### Safety

- Unplug the 12 V supply before attaching masses or touching the blades.
- Keep imbalance masses small (0.1–0.5 g) and well stuck down, and keep a finger guard on the fan.
- After changing anything, run at low duty (`--pwm 300`) first.

## Done when

- [ ] Smoke test result recorded (`OK`, RAM and time per step)
- [ ] Bring-up sessions 1–3 pass with no warnings
- [ ] Every fan has the normal sessions from the table and at least the imbalance severities
- [ ] `data/` backed up

**Next:** step 1 designs the feature extraction (window length, frequency bands, statistics).
Provisional feature code already exists (8 Oct, developed on Fraunhofer); the real window length and
band edges are chosen on these recordings (`--source own`, i.e. `fanlog.recording.session_recordings()`).
See "Datasets" in [`../implementation_plan.md`](../implementation_plan.md) for what UCI and Fraunhofer
are and aren't used for.
