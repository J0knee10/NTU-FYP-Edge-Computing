# Healthy campaign on `flat4`, 19 Nov 2026 (daytime)

Fan `pc01` lying flat across two boxes (`flat4`, see `docs/setup/bench_setup.md`), logger 0.3.2.
The campaign ran from 10:06 (`data/raw/campaign_20261119-100654.log`); every session passed `session_check.py` (no data loss, tach rejects 1.1–1.5 %, speed within 2 % of the first mount check).
Sessions from the morning mount checks (09:04, 09:14) and the first, restarted campaign (09:38) are included: same mount, same firmware.

This note covers the feature evaluation at about 14:30 (18 sessions). For the method see `host/analysis/feature_eval.py`. The tapeCorner results it is compared with are in `results/own/overnight/REPORT.md`, section 7.

## Main finding: on this quiet mount the in-plane 1× is small, and short windows can't see it at low speed

| Duty | In-plane 1× | Background between orders | Window-to-window spread of log10(1×), 0.62 s window |
|---|---|---|---|
| 30–60 % | 0.3–1 mg | ~0.5 mg | 0.15–0.18 (noise-like) |
| 70–100 % | 1.3–14 mg | 0.5–1 mg | 0.02–0.07 |

On `tapeCorner` the in-plane 1× was 2–4 mg at every speed (the standing fan rocked). Flat on the boxes, the fan's own imbalance barely moves the frame in its plane. Most of its 1× is axial (board y, 1.7 mg at 50 %, 9 mg at 70 %): the corner of the frame rocks.

**Consequence for the synthetic-fault test.** Multiplying the in-plane 1× by 1.25–2 is caught much less often than on `tapeCorner`.

| Grid | Detector (O set, 8-window median) | False alarms | Detected at ×1.25 / ×1.5 / ×2 |
|---|---|---|---|
| 10 % | max\|z\| | 1.1 % | 1 / 1 / 2 % |
| 10 % | AE | 0.7 % | 1 / 1 / 29 % |
| 10 % | Mahalanobis | 1.5 % | 1 / 2 / 45 % |
| 5 % | AE | 5.8 % | 11 / 47 / 77 % |

On `tapeCorner` the same test caught ×2 99.5 % of the time.

Two reasons:
- At 40–60 % a 0.62 s window measures background, not 1×.
- The max|z| threshold is set by the features with the tightest spreads (12× and the 150–400 Hz band). They drift a little between sessions and reach z ≈ 10 on healthy data, which hides the 1× change.

The synthetic test also overstates the problem at low speed. Multiplying a background-dominated reading by 2 doubles the background too, which is not what an added mass does. A mass adds a coherent 1× force that grows with ω². After tonight, calibrate the synthetic fault as an *added* 1× component from the real Blu-Tack blocks.

## Window length decides it

`host/analysis/window_length.py`: narrowband (±2 bins) 1× at the tach speed vs background at 0.75× and 1.25×, on the five `speed_sweep` sessions (`window_length.json`).

| Duty | 1× / background, 0.62 s | 1× / background, 5 s | Per-window z for ×1.5, 0.62 s → 5 s |
|---|---|---|---|
| 30 % | 1.0 | 1.0 | 1.7 → 1.3 |
| 40 % | 1.0 | 1.2 | 1.6 → 2.0 |
| 50 % | 1.1 | 1.9 | 1.8 → 2.9 |
| 60 % | 1.4 (erratic) | 3.1 | 0.5 → 3.6 |
| 70 % | 2.4 | 6.2 | 3.0 → 6.1 |
| 80 % | 1.8 | 7.8 | 3.1 → 5.5 |
| 90 % | 2.8 | 12.4 | 5.7 → 8.9 |

- **From 50 % up, a 5 s window finds a stable 1× line.** The line stays put while the background falls as 1/√T.
- **At 30–40 % there is no 1× line above the background even at 10 s.** The fan's own imbalance force (∝ ω²) is too small there. Imbalance is best judged at higher speeds; the device or agent should know that sensitivity depends on speed.
- **60 % with a 0.62 s window is erratic.** Content near 25 Hz that is not the 1× moves between sessions as the speed shifts by about 1 %. It is likely aliased high motor orders, since an alias moves k times faster than the speed. Check again after the anti-alias firmware change (0.4.0).

**For the step 1 feature spec:**
- Take the order amplitudes (at least 1×) from a long tach-locked window (about 4096 samples, 5 s) rather than from the 512-sample windows. On the board this is a single-bin DFT per order (O(n), no FFT needed).
- Put a floor on each feature's spread, so very stable features can't dominate max|z|.

## Unseen speeds

Smooth healthy curves did not make unseen speeds easy:
- **10 % grid** (leave out 40–80 % in turn, O set, 8-window median):
  - false alarms are near zero at 50 and 70 %;
  - 19–63 % at 60 % (the erratic step above);
  - 0–82 % at 40 %, depending on the detector.
  - 80 % is extrapolated from 70 % on this grid, so it always fails. It is reported but not meaningful.
- **5 % grid** (leave out 35–95 %, each interpolated between its neighbours 10 % apart): false alarms range from 0 to 60–90 %, depending on duty and detector.

Learning a new speed stays an RL-agent role (ADAPT at a new speed) rather than something interpolation solves.

## Files

- `feature_eval_grid10.json`: `--duties 300:800:100 --lodo 400:800` (comparable with `tapeCorner`).
- `feature_eval_grid5.json`: `--duties 300:1000:50 --lodo 350:950`.
- `window_length.json`: the window-length table.
- `summary.json`, `figs/`: `night_summary.py`, run by `autoproc.py` after each steady session.
- A-B-A dry run on these sessions: `docs/experiments/2026-11-19_imbalance_ABA.md`.
