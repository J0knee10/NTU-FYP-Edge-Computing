# Imbalance test, night of 19 Nov 2026 (A-B-A design)

Fan `pc01` on mount `flat4` (fan flat across two boxes, see `docs/setup/bench_setup.md`), logger 0.3.2.
The analysis is fixed in advance: `host/analysis/abtest.py` (primary measure below).

## Question

Does a small added mass on one blade (static imbalance) change the fan's vibration enough to detect, and
does the change grow with the unbalance U = m·r and with speed (ω²), as the physics predicts? It must
grow more than the healthy changes caused by drift and by handling the fan.

## Design

Each **block** is one recording with the `ab_block` profile, about 12 min:
- 3 min at 40 %;
- 2 min each at 50, 60, 70 and 80 %;
- 1 min at 50 % again.

There is no 100 %, so a mass is never run at full speed. Allow about 5 min of handling between blocks.

| # | Block | What you do before it | `--fault` / `--severity` |
|---|---|---|---|
| 1 | A0 | nothing (fan running) | `normal` / `none` |
| 2 | A1 sham | power off, press and hold blade 1 for 10 s as if adding a mass, add nothing, power on | `normal` / `sham` |
| 3 | H control | 0.2 g on the **hub centre** (on the label): same mass and handling, no imbalance | `other` / `hub0.2g` |
| 4 | A2 | remove the hub mass | `normal` / `none` |
| 5 | B | 0.1 g on **blade 1**, 25 mm from the axis | `imbalance` / `0.1g@25mm` |
| 6 | A3 | remove it | `normal` / `none` |
| 7 | B | 0.2 g on blade 1, 25 mm | `imbalance` / `0.2g@25mm` |
| 8 | A4 | remove | `normal` / `none` |
| 9 | B | 0.1 g on **blade 4**, 25 mm (about 180° from blade 1) | `imbalance` / `0.1g@25mm_b4` |
| 10 | A5 | remove | `normal` / `none` |
| 11 | B | 0.05 g on blade 1, 25 mm | `imbalance` / `0.05g@25mm` |
| 12 | A6 | remove | `normal` / `none` |

That is about 3.4 h. If time is short, stop after block 8 (the core result is blocks 1–8).

Optional extras if time allows:
- 0.05 g at **50 mm** on blade 1. This has the same U as 0.1 g at 25 mm, so it tests whether the effect follows m·r.
- A repeat of 0.1 g on blade 1, to check the result reproduces.

**Overnight afterwards:** remove every mass, then run a healthy `flat4` campaign until the morning
(`fanlog.campaign ... --fault normal`). Healthy `flat4` data is still scarce.

## Why these blocks

- **A between every B:** each mass is compared with the healthy blocks right before and after it, so slow drift cancels.
- **Sham (A1) and hub mass (H):** they measure what handling and extra weight alone do. Only an off-centre mass should change 1× much.
- **Blade 1 and blade 4:** the fan already has some imbalance of its own. A mass adds to it or partly cancels it, depending on where it sits, so one position alone can mislead.
- **Masses not in increasing order:** so a slow trend can't fake a dose-response.

## Making and placing the masses

- **Weighing:** weigh a larger piece of Blu-Tack (e.g. 2.0 g), roll it into an even rod, and cut it by length (2 g in 20 equal pieces = 0.1 g each). Weigh pieces together where the scale allows, and weigh each mass again after it comes off. Note any loss.
- **No precise scale?** A kitchen scale (1 g steps) can't weigh 0.1 g directly.
  - Use staples as known masses: weigh a whole strip (for example 100 staples) and divide. Standard staples are typically around 30 mg each, but weigh yours.
  - Then 3–4 staples ≈ 0.1 g, and 7 ≈ 0.2 g.
  - Tape them flat on the blade face. Use the **same size of tape strip in every block, including the sham** (tape only), so the tape's own mass cancels out.
- **Numbering:** number the blades from the hub label. Blade 1 is the one the label's text points to; count in the direction of rotation.
- **Placement:**
  - 25 mm from the axis is just outside the hub, at the blade root. Press the piece firmly onto the blade face and cover it with a small strip of tape.
  - Take a photo of each placement with a ruler in view.
- **Safety:**
  - Unplug the 12 V supply before touching the blades.
  - Keep your face out of the blade plane when powering on.
  - Each block starts at 40 %.

## Log to keep (one line per block)

| Block | Time power off | Time power on | Mass (g) before / after | Blade, radius | Notes (touches, anything odd) |
|---|---|---|---|---|---|
| | | | | | |

## Commands (Claude runs these; you handle the fan)

```
python -m fanlog.record --port COM6 --fan pc01 --mount flat4 --fault normal --severity none --audio --profile host/profiles/ab_block.json --notes "A0"
python -m fanlog.record --port COM6 --fan pc01 --mount flat4 --fault imbalance --severity 0.1g@25mm --audio --profile host/profiles/ab_block.json --notes "B 0.1g blade1"
```

## Analysis (fixed in advance)

```
python host/analysis/abtest.py --inplane xz --fig results/own/abtest/2026-11-19.png data/raw/<block 1> ... data/raw/<block 12>
```

- **Primary measure:** in-plane accelerometer 1× RMS, sqrt(x² + z²) in mg. On `flat4` the rotor plane is board x/z. It is measured at 50, 60, 70 and 80 %, from a per-axis Welch spectrum of each step at the tach speed.
- **Effect:** each B block divided by the geometric mean of the nearest A before and after, compared with the spread of consecutive A-to-A ratios. It is reported as a ratio and as z.
  - The sham block (A1, fault `normal`) counts as an A, so its handling is part of the null.
  - The hub-mass block (H, fault `other`) is analysed like a B, as a **no-effect control**. It should show no effect. It is not in the null.
- **Combined effect per block:** one ratio over the 50, 60, 70 and 80 % steps, the mean of the step log ratios weighted by 1 / sd² of each step's A-to-A spread.
  - Its z uses the spread of the same weighted mean over the consecutive A pairs, so a drift common to all steps is included.
  - Every spread is floored at 0.02 log10 (about 5 %), so a step whose few A-to-A ratios happen to agree closely can't give z in the hundreds.
- **Decision rule (fixed before the data):** an effect counts as detected if the combined z ≥ 3. The sham and the hub control must stay below that.
  - With 6 A-to-A pairs, the spread has 5 degrees of freedom, so z = 3 corresponds to about p = 0.015 one-sided (t distribution).
  - z is conservative. If block noise is independent, a B between two A blocks has 3/4 of the variance of an A-to-A ratio, so the true z is about 1.15× larger.
- **Input checks:** `abtest.py` warns if a block is not `ab_block`, was aborted, has a step shorter than 60 s or a missing step, or if the sessions are not in time order. Pass the sessions in recorded order.
- **Dose-response:** the combined ratio vs U (g·mm), and the added 1× in mg (B − A) vs ω², one line per block. Below the ~40 Hz bounce of the mount, the added 1× should grow roughly in proportion to U·ω². B − A is only a rough stand-in for the added vector: the measure has no phase, so the added and existing imbalance can partly cancel.
- **Secondary:**
  - the same tables for axial accel 1× (board y), accel 1× over all axes, and gyro 1× over all axes (`abtest.py` prints them);
  - per-window detection (`host/analysis/fault_eval.py`): detectors trained on the healthy `flat4` campaign, with the threshold rotated over its sweep-type sessions. It reports the % of windows flagged per block and duty, for feature sets O (0.62 s orders) and L (5 s tach-locked orders), with max|z|, Mahalanobis and the autoencoder. Commands (after the last block; give the block session folders in order):
    ```
    $env:ANALYSIS_OUT="results/own/flat4_healthy"; python host/analysis/long_windows.py
    $env:ANALYSIS_OUT="results/own/abtest_20261119"; python host/analysis/windows.py <blocks>
    python host/analysis/long_windows.py <blocks>
    python host/analysis/fault_eval.py --train results/own/flat4_healthy
    ```
    Tested on fake blocks: the injected block was flagged in 27–73 % of windows at 50–80 % with L (much less with O); healthy and relabelled blocks were flagged in 0–6 %.
  - **Per-window threshold (changed 19 Nov, 19:35, before any fault data).** The main per-window result is the "max|z| LOSO" row, set L. It is fitted on all 31 healthy `flat4` sessions; the threshold is the 99.5th percentile of the pooled leave-one-session-out scores (`feature_eval.py --loso`).
    - On the later `flat4` sessions this gave 1.3 % false alarms and caught every synthetic ×1.5 at 70–80 %.
    - On pre-night healthy `ab_block` block 1 it flagged 0 % of windows at every duty. The rotated Mahalanobis and AE thresholds flagged 19–41 % at 50 % on the same block.
    - The rotated rows stay in the output for comparison only.
  - accel 2× and 0.5×.

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
