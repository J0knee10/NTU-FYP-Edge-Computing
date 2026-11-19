# Fault blocks, A-B-A design: imbalance, blocked intake, blade rub

Fan `pc01` on mount `flat4` (fan flat across two boxes, see `docs/setup/bench_setup.md`), logger 0.3.2.
The analysis is fixed in advance: `host/analysis/abtest.py` (measures and decision rules below).

Planned 19 Nov 2026 as an imbalance-only test (the original plan, kept at the end). Revised the same evening,
before any fault data, to three fault types. The fault blocks were postponed, so the revised plan runs in two
parts on later dates.

## Question

Does a detector trained only on healthy data react to three different physical faults it has never seen, and
which measurements change for each?
- **Static imbalance** (a small mass on one blade): does the 1× grow with the unbalance U = m·r and with speed
  (ω²), as the physics predicts?
- **Blocked intake** (a dusty filter, a fan against a wall): does the speed at a fixed PWM change, and the
  blade-pass tone and noise?
- **Something touching the blades** (a cable rubbing a PC fan): do clicks show up in the audio and the
  high-frequency vibration?

Each change must be larger than the healthy changes caused by drift and by handling the fan.

## Design

Each **block** is one recording with the `ab_block` profile, about 12 min:
- 3 min at 40 %;
- 2 min each at 50, 60, 70 and 80 %;
- 1 min at 50 % again.

There is no 100 %, so a fault is never run at full speed. Allow 2–5 min of handling between blocks. You don't
have to watch the fan while a block runs. Stay nearby, don't touch the desk or the boxes, and come back when
Claude posts "block done, next: …".

**A0 is a fresh healthy block.** The board runs the overnight campaign between sessions, so each part starts by
stopping it and recording one healthy block with nobody touching the fan. You can prepare the masses or the
cardboard during A0, away from the desk.

### Part 1: imbalance (about 1.5 h)

| # | Block | What you do before it | `--fault` / `--severity` |
|---|---|---|---|
| 1 | A0 | nothing | `normal` / `none` |
| 2 | Sham | unplug, hold blade 1 for 10 s, put on an **empty** tape strip, plug in | `normal` / `sham` |
| 3 | B | 0.2 g on **blade 1**, 25 mm from the axis, under a fresh strip | `imbalance` / `0.2g@25mm` |
| 4 | A | remove the mass, fresh empty strip | `normal` / `none` |
| 5 | B | 0.1 g on blade 1, 25 mm, under a fresh strip | `imbalance` / `0.1g@25mm` |
| 6 | A | remove the mass, fresh empty strip | `normal` / `none` |

From the sham on, blade 1 always carries one tape strip of the same size: empty in the A blocks, over the mass in
the B blocks. So the tape's own mass is in every block that is compared.

### Part 2: blocked intake and blade rub (about 1.75 h)

| # | Block | What you do before it | `--fault` / `--severity` |
|---|---|---|---|
| 7 | A0 | nothing | `normal` / `none` |
| 8 | B | intake about **50 %** covered | `obstruction` / `intake50` |
| 9 | A | remove the cover | `normal` / `none` |
| 10 | B | intake about **90 %** covered | `obstruction` / `intake90` |
| 11 | A | remove the cover | `normal` / `none` |
| 12 | B | paper strip just ticking the blade tips | `rub` / `paper_tip` |
| 13 | A | remove the strip | `normal` / `none` |

If time runs short, stop after block 9 or 11. Every B needs the A after it.

## Why these blocks

- **An A between every B:** each fault is compared with the healthy blocks right before and after it, so slow
  drift cancels.
- **Sham:** it measures what handling and the tape alone do. In part 2, every A after a removal includes the
  same kind of handling as the B before it.
- **Masses not in increasing order:** so a slow trend can't fake a dose-response.
- **Two blockage levels:** a change that grows from 50 % to 90 % is hard to explain as drift.
- **What was dropped from the original plan:** the hub-mass control, the blade-4 position and the 0.05 g mass,
  to make room for two more fault types. A device that reacts to three faults is worth more than a finer
  imbalance curve. The full imbalance study can be repeated on another night.

## Making and placing the masses (part 1)

- **Weighing:** weigh a larger piece of Blu-Tack (e.g. 2.0 g), roll it into an even rod, and cut it by length (2 g in 20 equal pieces = 0.1 g each). Weigh pieces together where the scale allows, and weigh each mass again after it comes off. Note any loss.
- **No precise scale?** A kitchen scale (1 g steps) can't weigh 0.1 g directly.
  - Use staples as known masses: weigh a whole strip (for example 100 staples) and divide. Standard staples are typically around 30 mg each, but weigh yours.
  - Then 3–4 staples ≈ 0.1 g, and 7 ≈ 0.2 g.
  - Tape them flat on the blade face under the strip.
- **Numbering:** number the blades from the hub label. Blade 1 is the one the label's text points to; count in the direction of rotation.
- **Placement:**
  - 25 mm from the axis is just outside the hub, at the blade root. Press the piece firmly onto the blade face and cover it with the tape strip.
  - Take a photo of each placement with a ruler in view.

## Blocking the intake and the rub (part 2)

The fan lies flat with the struts up, so it blows **up** and draws air from the gap between the boxes. The
intake is the underside.

- **The rule for both:** nothing may touch the fan frame or change how it sits on the boxes, or the mount
  itself changes and the result can't be blamed on the fault.
- **Intake cover:**
  - Use flat cardboard **below** the fan in the gap, held up from the floor (a stack of books or a box). Leave
    about 5–10 mm between the cardboard and the intake face.
  - Cover about half of the intake face, then about nine-tenths. Note the gap and the covered fraction, and take
    a photo from the side.
  - If the underside can't be reached without touching the fan, cover the outlet (top) instead in the same way:
    held from the side, not resting on the frame. Note which side you used.
- **Rub:**
  - Unplug first. Tape a strip of plain paper (about 1 cm wide) firmly to the top face of the frame. Bend it
    down between two struts so its end reaches 2–3 mm into the path of the blade tips.
  - Soft paper only, never anything rigid. Fix it so it can't be pulled in.
  - Keep your face out of the blade plane when powering on. If it sounds harsh, unplug. The block is then
    aborted, which `abtest.py` reports.
  - It is the least repeatable fault. That is fine for a demonstration.

## Safety

- Unplug the 12 V supply before touching the blades.
- Keep your face out of the blade plane when powering on.
- Each block starts at 40 %.

## Log to keep (one line per block)

| Block | Time power off | Time power on | What changed (mass g before / after, blade, radius; cover %, gap; strip) | Notes (touches, anything odd) |
|---|---|---|---|---|
| | | | | |

## Commands (Claude runs these; you handle the fan)

First stop the overnight campaign so the board is free: create `data/raw/STOP` and wait for the current
session to end (up to about 30 min), or stop that session. Then delete `STOP`.

```
python -m fanlog.record --port COM6 --fan pc01 --mount flat4 --fault normal --severity none --audio --profile host/profiles/ab_block.json --notes "A0"
python -m fanlog.record --port COM6 --fan pc01 --mount flat4 --fault imbalance --severity 0.2g@25mm --audio --profile host/profiles/ab_block.json --notes "B 0.2g blade1"
python -m fanlog.record --port COM6 --fan pc01 --mount flat4 --fault obstruction --severity intake50 --audio --profile host/profiles/ab_block.json --notes "B intake 50 %"
python -m fanlog.record --port COM6 --fan pc01 --mount flat4 --fault rub --severity paper_tip --audio --profile host/profiles/ab_block.json --notes "B paper strip"
```

## Analysis (fixed in advance)

Each part is analysed on its own, with its blocks in recorded order:

```
python host/analysis/abtest.py --inplane xz --null-from results/own/prenight_20261119/abtest_prenight.json --out results/own/abtest_<date>/abtest.json --fig results/own/abtest_<date>/abtest.png data/raw/<block 1> ... data/raw/<block 6>
```

- **Effect:** each B block divided by the geometric mean of the nearest A before and after, compared with the
  spread of consecutive A-to-A ratios. It is reported as a ratio and as z.
  - The sham block (fault `normal`) counts as an A, so its handling is part of the null.
- **Combined effect per block:** one ratio over the 50, 60, 70 and 80 % steps, the mean of the step log ratios
  weighted by 1 / sd² of each step's A-to-A spread.
  - Its z uses the spread of the same weighted mean over the consecutive A pairs, so a drift common to all
    steps is included.
- **Which spread is used (`--null-from`, fixed 20 Nov before any fault data).** Each part has only 3–4 A blocks,
  so its own A-to-A spread rests on 2–3 pairs. Every spread used for z is the largest of:
  - the part's own A-to-A spread;
  - the spread over the 25 healthy pre-night blocks (19 Nov, 19:13–00:35, 24 pairs, no handling);
  - a floor: 0.02 log10 (about 5 %) for amplitudes, 0.001 log10 (0.24 %) for speed.

  This can only lower z. The pre-night blocks had no handling, which is why the part's own spread, sham
  included, still counts.
- **Primary measure and decision rule per fault (fixed before the data).** An effect counts as detected if the
  combined z of its primary measure passes the threshold:

  | Fault | Primary measure | Rule | Healthy combined spread (pre-night) | Detectable change at z = 3 |
  |---|---|---|---|---|
  | Imbalance | in-plane accel 1× RMS, sqrt(x² + z²) | z ≥ 3 (one-sided, a mass adds 1×) | 0.020 (floor) | about ×1.15 |
  | Blocked intake | speed at the step's PWM (`rpm`) | \|z\| ≥ 3 (direction not known) | 0.0010 | about 0.7 % |
  | Blade rub | audio 2–7.9 kHz band, median of 1 s chunks (`aud_hi`) | \|z\| ≥ 3 | 0.020 (floor) | about ×1.15 |

  - The sham must stay below the threshold.
  - z is conservative: if block noise is independent, a B between two A blocks has 3/4 of the variance of an
    A-to-A ratio, so the true z is about 1.15× larger.
  - **`aud_hi` uses the median of 1 s chunks** so that a brief room sound doesn't count but a steady rub does.
    On the pre-night blocks this cut the A-to-A spread at 70 / 80 % from 0.10 / 0.044 log10 (plain band RMS) to
    0.010 / 0.006. At 40–60 % the fan is quieter than the room in this band (spread 0.12–0.15), so the
    weighting leaves those steps out in effect.
  - **False-alarm check on healthy data:** with every fifth pre-night block relabelled as B, no measure reached
    |z| = 3 (largest 2.4, `aud7x`).
  - **Injection check** (6 pre-night blocks, two turned into fake B blocks, `--null-from` as above):
    - tach speed ×1.01: `rpm` ×1.010, z +4.2 (detected). This fake moves only the tach reading, not the
      spectrum, so the blade-pass bands then sit off the real tone and drop by a third. A real speed change
      moves the tone with it.
    - a click train at blade pass added to the audio, its 2–7.9 kHz RMS 0.5× / 1× the block's own at 80 %:
      `aud_hi` ×1.22, z +4.4 / ×1.70, z +11.5 (both detected).
- **Other measures** (all printed, descriptive only):
  - axial accel 1× (board y), accel 1× over all axes, gyro 1× over all axes;
  - `acc7x_vec`: accel blade-pass tone (7 blades) over all axes;
  - `acc_hf`: accel 150–400 Hz band over all axes;
  - `aud_rms`: audio level; `aud7x`: audio blade-pass tone.
  - Every fault is reported against every measure. A table of which measures moved for which fault is the
    diagnosis result.
- **Dose-response (imbalance):** the combined ratio vs U (g·mm), and the added 1× in mg (B − A) vs ω², one line
  per block. Below the ~40 Hz bounce of the mount, the added 1× should grow roughly in proportion to U·ω².
  B − A is only a rough stand-in for the added vector: the measure has no phase, so the added and existing
  imbalance can partly cancel.
- **Input checks:** `abtest.py` warns if a block is not `ab_block`, was aborted, has a step shorter than 60 s
  or a missing step, or if the sessions are not in time order.
- **Per-window detection** (`host/analysis/fault_eval.py`, secondary):
  - Detectors are trained on every healthy `flat4` campaign session recorded before the part.
  - The main row is "max|z| LOSO", set L: its threshold is the 99.5th percentile of the pooled
    leave-one-session-out scores (`feature_eval.py --loso`). It was fixed 19 Nov, 19:35, before any fault data.
  - It reports the % of windows flagged per block and duty.
  - **Expected sensitivity for imbalance is modest.** The model's training spread includes an afternoon drift of
    the healthy in-plane 1× (board z ×0.7 at 70–80 % from about 16:00 on 19 Nov). On the 31 sessions of 19 Nov,
    its own leave-one-session-out estimate caught a synthetic ×1.5 in about 34 / 68 % of windows at 70 / 80 %,
    and ×2 in 100 %. So the A-B-A block comparison stays primary.
  - **Blockage is a known gap:** speed is used to normalise the features, not as a feature, so these detectors
    see a blockage only through its side effects. A speed-residual feature is planned for step 1.
  - Commands (after the last block of a part; give the block folders in order):
    ```
    $env:ANALYSIS_OUT="results/own/flat4_healthy"; python host/analysis/long_windows.py
    $env:ANALYSIS_OUT="results/own/abtest_<date>"; python host/analysis/windows.py <blocks>
    python host/analysis/long_windows.py <blocks>
    python host/analysis/fault_eval.py --train results/own/flat4_healthy
    ```
  - On pre-night healthy `ab_block` block 1 it flagged 0 % of windows at every duty. The rotated Mahalanobis and
    AE thresholds flagged 19–41 % at 50 % on the same block, so they stay in the output for comparison only.

## Healthy data behind the null (19 Nov, 19:13 – 20 Nov, 00:35)

25 healthy `ab_block` blocks back to back, nobody touching the fan
(`results/own/prenight_20261119/abtest_prenight.json`). Spread of the log10 ratio between consecutive blocks:

| Measure | 40 % | 50 % | 60 % | 70 % | 80 % |
|---|---|---|---|---|---|
| In-plane accel 1× | 0.027 | 0.019 | 0.071 | 0.013 | 0.022 |
| Axial accel 1× | 0.017 | 0.013 | 0.010 | 0.010 | 0.016 |
| Speed | 0.0012 | 0.0013 | 0.0012 | 0.0013 | 0.0011 |
| Accel blade-pass | 0.060 | 0.071 | 0.090 | 0.054 | 0.035 |
| Accel 150–400 Hz | 0.030 | 0.016 | 0.036 | 0.043 | 0.011 |
| Audio level | 0.044 | 0.029 | 0.026 | 0.021 | 0.015 |
| Audio blade-pass | 0.044 | 0.045 | 0.037 | 0.030 | 0.036 |
| Audio 2–7.9 kHz (median of 1 s) | 0.151 | 0.140 | 0.117 | 0.010 | 0.006 |

## Dry run on healthy flat4 data (19 Nov, afternoon, before any fault data)

`abtest.py` was run on the five healthy `speed_sweep` sessions of the day, all as A blocks, and then on a copy with fake B blocks.

| Duty | 30 % | 40 % | 50 % | 60 % | 70 % | 80 % | 90 % | 100 % |
|---|---|---|---|---|---|---|---|---|
| In-plane 1× (mg) | 0.33 | 0.42 | 0.59 | 1.15–1.72 | 2.0 | 3.9 | 8.2 | 14.1 |
| A-to-A spread (sd log10) | 0.051 | 0.050 | 0.015 | 0.097 | 0.025 | 0.035 | 0.021 | 0.010 |

- A ×1.5 change would give z ≈ 12, 7 and 5 at 50, 70 and 80 %.
- **60 % is speed-sensitive on this mount.** The board-x 1× fell from 1.52 to 1.00 mg as the speed rose from 1505 to 1523 rpm (1.2 %), so there is a steep response feature near 25 Hz. Expect weak z at 60 %. The combined effect down-weights it automatically.
- **The fan's own 1× is mostly axial on `flat4`.** Board y is 1.7 mg at 50 % and 9 mg at 70 %: the corner of the frame rocks. Hence the axial and all-axis secondaries. An added blade mass adds a rocking moment as well as an in-plane force.
- **Speed creeps up over the day:** about +1 % at fixed duty between 09:00 and 14:00. Each B is compared with its neighbouring A blocks, so this cancels.
- **Fake B blocks:**
  - A healthy block relabelled as B gives combined ×0.97, z −0.6, and |z| ≤ 1.5 on every secondary.
  - A healthy block with an added tach-locked 1× sine (0.5 mg RMS per in-plane axis at 50 %, growing with ω²) gives ×1.56 at 50 %, ×1.21 at 70 % and combined ×1.38, z +7.0 (detected).
  - These z values use the final script, after the code review the same afternoon. That review fixed:
    - NaN handling;
    - steps taken from the first block only;
    - the combined z, which had treated steps as independent;
    - the figure;
    - added the input checks.
  - The fake blocks were made with `fake_b.py`, a scratch script, not in the repo.

## Original plan (19 Nov, superseded the same evening)

Imbalance only, 12 blocks, about 3.4 h: A0, sham, a 0.2 g **hub-centre** control (weight with no imbalance), then
0.1 g and 0.2 g on blade 1, 0.1 g on **blade 4** (about 180° away) and 0.05 g on blade 1, each followed by an A
block. Optional extras were 0.05 g at 50 mm (same U as 0.1 g at 25 mm) and a repeat of 0.1 g.
