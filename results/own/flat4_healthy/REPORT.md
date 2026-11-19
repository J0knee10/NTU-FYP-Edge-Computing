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
The table below is from the first evaluation at 14:30 (one threshold session, before the review fixes); the corrected comparison is in the set L section.

| Grid | Detector (O set, 8-window median) | False alarms | Detected at ×1.25 / ×1.5 / ×2 |
|---|---|---|---|
| 10 % | max\|z\| | 1.1 % | 1 / 1 / 2 % |
| 10 % | AE | 0.7 % | 1 / 1 / 29 % |
| 10 % | Mahalanobis | 1.5 % | 1 / 2 / 45 % |
| 5 % | AE | 5.8 % | 11 / 47 / 77 % |

On `tapeCorner` the same first test caught ×2 99.5 % of the time.

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

## Long-window features tested (set L), corrected after a methods review

- **Sidecars.** `host/analysis/long_windows.py` adds, for every short-window row, per-axis orders from a 4096-sample (5 s) tach-locked window centred on it. They go in `windows_long/`, which is not in git; rerun the script to make them.
- **The L set** in `feature_eval.py` is set O with these orders in place of the 0.62 s ones. The 12× and 150–400 Hz columns stay short-window in both. Every set is scored on the same rows: those whose whole 5 s window lies in one settled step.
- **Rotation.** One held-out threshold session made the numbers swing. `--rotate` repeats the test with each of the 8 sweep-type training sessions as the threshold session and reports mean [min–max].

**Methods review (19 Nov, 15:30).** An independent review found that the first version of this section overstated L's lead, and one claim was wrong. Fixed in `feature_eval.py`, and every number below was rerun:
1. **Sets were compared at different false-alarm rates.** Comparisons now use detection at **matched 2 % false alarms** (an oracle threshold on the healthy test windows, for comparison only).
2. **The spread assumed independent windows** (a 1.25/√avg factor). Overlapping 5 s windows aren't independent, so L's z-scores were inflated. The spread is now measured on the running-medianed features themselves.
3. **The running median started fresh at each scored row's step,** so O's first rows used fewer windows. The median now runs over every settled row, repeated visits to a duty are kept apart, and only rows with a full median are scored.
4. `settled_long` was half a row short at the end of each step (negligible). Fixed and rebuilt.
5. **Withdrawn:** "L is much less sensitive to which session sets the threshold". With session-based thresholds, both sets' false alarms vary a lot between threshold sessions (below).

**Matched 2 % false alarms** (`feature_eval_grid10L_rot.json`; 18 sessions, mean over 8 rotations):

| Set | Median | Detector | ×1.25 | ×1.5 | ×2 | ×1.5 at 70 / 80 % | ×1.5 at 40 / 50 / 60 % |
|---|---|---|---|---|---|---|---|
| O | 8 (5 s) | max\|z\| | 2 | 2 | 17 | 0 / 1 | 6 / 0 / 8 |
| O | 8 (5 s) | Mahalanobis | 3 | 23 | 68 | 37 / 29 | 20 / 0 / 2 |
| O | 16 (10 s) | Mahalanobis | 3 | 41 | 79 | 68 / 56 | 21 / 0 / 0 |
| **L** | **8 (9.4 s)** | **Mahalanobis** | 6 | **54** | 65 | **92 / 90** | 15 / 0 / 4 |
| L | 8 (9.4 s) | max\|z\| | 6 | 53 | 64 | 91 / 90 | 13 / 0 / 3 |
| L | 8 (9.4 s) | AE | 7 | 46 | 65 | 79 / 69 | 12 / 0 / 4 |
| L, streaming | 3 non-overlapping (15 s) | max\|z\| | 8 | 62 | 82 | 100 / 100 | 9 / 1 / 31 |
| O, streaming | 3 (subsampled rows) | max\|z\| | 3 | 6 | 40 | 1 / 17 | 8 / 0 / 19 |

- **At 70–80 %, at equal data span (about 10 s) and equal false alarms, L leads O by 25–35 points** (92 / 90 % against 68 / 56 %). The narrow tach-locked band helps; it is not just more data. The lead is smaller than first reported.
- **The streaming variant** (non-overlapping 5 s windows, median of 3; no sample buffer on the board) is at least as good: 100 % at 70–80 %.
- **At 40–60 % neither set catches a ×1.5 change** in the fan's own 1×, which is near the background there. A real added mass adds its own 1× force, so tonight's blocks will show whether it rises above the background at these speeds.
- **A ×2 change is caught only about 65–80 % of the time overall,** because the 40–60 % rows are part of the test.
- **Thresholds from one held-out session give unstable false alarms**, for O and L alike:

  | Run | False alarms, mean [min–max] |
  |---|---|
  | L, 8-window median | 3.1–3.4 % [1.0–8.9] |
  | O, 8-window median | 2.8–3.8 % [0.3–11.6] |
  | L, streaming | 3.9–5.2 % [0.3–19] |

  The 99th percentile of one session is a noisy threshold, worst for streaming, which has few windows. **A device needs a longer calibration** (several healthy sessions or speeds pooled), or a threshold that adapts. The RL agent's persistence and ADAPT logic is the natural place.
- **Oall (vector orders) stays blind** (≤ 7 % at ×2 in the earlier runs), as on `tapeCorner`. Features must be per axis.
- **A spread floor of 0.03 log10** (`feature_eval_grid10L_rot_f03.json`, made before the review fixes) hurt detection. Don't use a uniform floor.
- **False alarms per window are not per hour.** 2 % of 0.62 s windows is about 116 flags an hour; 2 % of 5 s windows is about 14 an hour. A single flag can't trigger ALERT. Persistence over several windows, which is in the RL state, has to do that work.

## Full day (31 sessions) and a calibration that works (19 Nov, evening)

The campaign ended at 19:12 with 31 sessions, all passing `session_check.py`. Every number in this section uses the same split: the first 19 sessions (09:04–15:01) train and the last 12 (15:01–19:02) test, so the test is a later part of the day.

**Rotated thresholds, 31 sessions** (`feature_eval_grid10L_rot_all.json`, 8-window median). At matched 2 % false alarms, ×1.5 at 70 / 80 %:

| Set | max\|z\| | Mahalanobis |
|---|---|---|
| L | 100 / 100 % | 97 / 100 % |
| O | 27 / 86 % | 41 / 92 % |

L's lead holds and is clearest at 70 %; at 80 % O catches up with more training data. With one held-out threshold session, Mahalanobis and the autoencoder give 11–18 % false alarms on average with an 8-window median (up to 54 %): their false alarms grow through the afternoon (set L, per test session: about 1–6 % up to 16:06, then 6–27 % from 16:17 on, about 15 % or more in seven of those eight sessions), while max|z| stays below 10 % in every test session. They react to slow drift through the day; max|z| on per-feature z-scores is more robust.

**Leave-one-session-out (LOSO) calibration** (`feature_eval.py --loso`, `feature_eval_grid10L_loso.json`):
- **How it works.** No single threshold session. Each training session is scored by a model fitted on the other training sessions. The threshold is a high percentile of all those out-of-session scores pooled. A device could do the same with several healthy calibration sessions, and no oracle is involved.

| Set, detector | Threshold (percentile) | False alarms, all test (worst session) | ×1.5 overall | ×1.5 at 70 / 80 % |
|---|---|---|---|---|
| **L, max\|z\|** | **99.5** | **1.3 % (5.3 %)** | 51 % | **100 / 100 %** |
| L, max\|z\| | 99 | 2.4 % (6.9 %) | 53 % | 100 / 100 % |
| L, Mahalanobis | 99.5 | 2.1 % (8.5 %) | 54 % | 99 / 100 % |
| O, max\|z\| | 99 | 1.0 % (6.1 %) | 20 % | 9 / 76 % |
| O, Mahalanobis | 99 | 7.6 % (29.9 %) | 52 % | 86 / 99 % |
| L streaming (median of 3), max\|z\| | 99.5 | 1.1 % (4.7 %) | 48 % | 79 / 97 % |

- **This fixes the unstable false alarms of the single-session threshold** for L with max|z|: about 1 % overall and at most about 5 % in any test session, while every ×1.5 change at 70–80 % is still caught.
- **On `tapeCorner` the same method first failed.** The pooled 99.5th percentile sat far out (26 vs 6 on `flat4`): ×2 dropped from 99.9 % at the 99th percentile to 1.8 % at the 99.5th.
  - **The cause was speed glitches, not the method.** In some overnight sessions the speed read about 5 % high for a few seconds (for example 1365 vs 1300 rpm at 50 %), then returned. It is likely a logger 0.3.1 tach glitch.
  - A 5 s narrowband feature measures ±0.4 Hz around the tach speed, so a wrong speed puts it on the wrong bin, and z reached about 150.
  - **Speed gate** (`--speed-gate 0.03`): drop rows more than 3 % off their visit's median speed, plus the 4 rows either side.
- **Results with the gate:**
  - **`tapeCorner`** (`results/own/overnight/feature_eval_L_loso_gate.json`), L max|z| at the 99.5th percentile: 4.6 % false alarms (worst session 13.5 %), ×1.5 caught 99.5 %, ×1.25 29 %. The higher false alarms are overnight drift on that mount.
  - **`flat4`** (logger 0.3.2, `feature_eval_grid10L_loso_gate.json`): the gate changes nothing; this data has no such glitches.
- **For the device:**
  1. calibrate the threshold on pooled out-of-session scores from several healthy sessions;
  2. score with max|z| on the 5 s order features;
  3. skip any window whose tach speed jumps.

  The leftover false-alarm rate (1–5 % per window) still needs persistence (several windows in a row) before an ALERT, and slow drift needs the agent's ADAPT.

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
- `feature_eval_grid10L.json`: with the L set (single threshold session; before the review fixes).
- `feature_eval_grid10L_rot.json`: the same with the threshold session rotated.
- `feature_eval_grid10L_rot_f03.json`: rotated, with a 0.03 spread floor (before the review fixes).
- `feature_eval_grid10L_rot_avg16.json`, `feature_eval_grid10L_rot_sub8.json`: 16-window median; streaming.
- `feature_eval_grid10L_rot_all.json`: rotated, all 31 sessions.
- `feature_eval_grid10L_loso.json`, `_loso_sub8.json`, `_loso_gate.json`: leave-one-session-out calibration (8-window median; streaming; with the speed gate).
- To rebuild:
  - `ANALYSIS_OUT=results/own/flat4_healthy python host/analysis/long_windows.py`
  - then `feature_eval.py --rotate --max-sessions 18 --tag grid10L_rot`.
- `summary.json`, `figs/`: `night_summary.py`, run by `autoproc.py` after each steady session.
- A-B-A dry run on these sessions: `docs/experiments/2026-11-19_imbalance_ABA.md`.
