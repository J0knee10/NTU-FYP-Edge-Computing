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
- **Effect:** each B block divided by the geometric mean of the nearest A before and after, compared with the spread of A-to-A ratios (sham and hub control included). It is reported as a ratio and as z.
- **Dose-response:** the ratio vs U (g·mm) and vs ω². Below the ~40 Hz bounce of the mount, the added 1× should grow roughly in proportion to U·ω².
- **Secondary:**
  - the autoencoder on order features, trained on healthy `flat4` data with its threshold set on a held-out session; detection rate per mass and duty;
  - gyro 1×, accel 2× and 0.5×.
