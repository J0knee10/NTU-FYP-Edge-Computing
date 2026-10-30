# Step 1: Feature Specification

**Goal:** decide exactly how a window of vibration becomes the feature vector the model sees. Window
length, FFT size, frequency bands and statistics are fixed here. The C++ port in step 5 has to
reproduce them, so only operations CMSIS-DSP can do are allowed.

The code is written and runs on the Fraunhofer dataset. What's left is **choosing the values on our
own recordings** once step 0 has data.

## How it works

```
 Recording (n × 3 samples, rate_hz)                       one row per window
 ───────────────────────────────────►  window 512 samples ──►  48 features
                                       (0.54 s at 952 Hz)
   per window, per axis: remove mean → Hann → real FFT → power
   power summed over x, y, z → 40 linear bands, 2–450 Hz → log10        (features 0–39)
   log10 RMS per axis (3), kurtosis per axis (3), crest factor (1),       (features 40–47)
   spectral centroid / 450 Hz (1)
```

The 40 band energies stay one ordered low→high block, so a frequency-axis CNN could use them later.

## Code used in this step

| Path | What it does |
|---|---|
| `host/features/spec.py` | `FeatureSpec`: window, hop, number of bands, band range. `band_bins()` gives the FFT-bin→band table the C code will use |
| `host/features/extract.py` | `extract(recording)` → `Windows` (feature matrix + per-window speed and labels). Public-dataset features are cached in `data/processed/features/` |
| `host/features/normalise.py` | Per-feature standardisation, fitted on pre-training data and fixed on the device |
| `host/features/sets.py` | Loads a source (`fraunhofer`, `uci`, `own`) into windows and standard train / validation / test splits |
| `host/features/report.py` | How well each feature separates normal from faulty windows, and how much it moves with speed |
| `host/fanlog/recording.py` | The shared `Recording` format and loaders for every source |

## Part A: Get the development data (once)

In a terminal at the repo root:

```
.venv\Scripts\python -m pip install -r requirements.txt
curl -f -o data\external\fraunhofer-unbalance\fraunhofer_eas_dataset_for_unbalance_detection_v1.zip --create-dirs https://fordatis.fraunhofer.de/bitstream/fordatis/151.2/1/fraunhofer_eas_dataset_for_unbalance_detection_v1.zip
```

That is 2.7 GB. Use curl rather than `python -m fanlog.datasets fraunhofer-unbalance`, because
Python's certificate list lacks the root certificate the Fordatis site uses; curl uses Windows' list
and still checks the certificate. The first time any step loads the data, it parses the CSVs and
caches them (about 3 minutes); after that it takes seconds.

## Part B: Look at the features

```
.venv\Scripts\python -m features.report --source fraunhofer
```

**What should happen:** one line per feature with its frequency range, its AUROC (normal vs fault) and
its correlation with speed. On Fraunhofer:

- No single feature separates faults well (AUROC 0.20–0.68). The model has to combine them.
- Almost every feature correlates 0.8–0.9 with speed. **Speed is the main thing that moves the
  features**, which is why benign drift is the central problem for steps 3 and 4.
- Unbalance acts at the 1× rotation frequency (10–40 Hz at 600–2300 rpm), but the first bands are
  11 Hz wide, so that region is coarse.

## Part C: Fix the spec on our own recordings (after step 0)

> The current features are a provisional baseline. The full list of feature-engineering experiments
> to run (order-normalised bands, ablation, feature count, audio, normalisation, ...) is in
> [`../implementation_plan.md`](../implementation_plan.md#feature-engineering-to-do-step-1). The steps
> below are the minimum.

```
.venv\Scripts\python -m features.report --source own
.venv\Scripts\python -m features.report --source own --window 1024 --bands 32
```

Things to decide, and how:

1. **Window length.** 512 samples (0.54 s, 1.86 Hz resolution) is the starting point. Try 1024 if
   the 1× peak at the lowest fan speed needs finer resolution. Longer windows mean fewer decisions per
   minute and more RAM (3 × window × 4 bytes for the samples).
2. **Band layout.** Our fans have a **tach**, so try bands at multiples of the rotation frequency
   (1×, 2×, blade-pass = blades × 1×, ...) instead of fixed Hz. That would make the features much
   less speed-dependent. It needs a small change to `window_features()`, with the window's speed
   passed in.
3. **Upper limit.** Keep `f_hi_hz` below the LSM9DS1 Nyquist (476 Hz). Check where the blade-pass
   frequency sits at maximum PWM.
4. Write the chosen values into `DEFAULT_SPEC` in `host/features/spec.py`, rerun the tests and
   record the decision in `docs/implementation_plan.md`.

## How to tell it worked

```
.venv\Scripts\python -m pytest host
```

`test_features.py` checks that a pure sine lands in the right band, that scaling the signal shifts
only the log features, and that bands stop below Nyquist.

## Done when

- [ ] `features.report` run on our own recordings
- [ ] Feature-engineering experiments from the plan run, and the chosen set justified with references
- [ ] Window length and band layout chosen and written into `host/features/spec.py`
- [ ] Decision and reason recorded in `docs/implementation_plan.md`
- [ ] Tests pass

**Next:** step 2 compares anomaly models on these features.
