# Bench setup

| Mount id | Fan placement | Used | Status |
|---|---|---|---|
| `tapeCorner` | Standing on its edge, free on the floor; board taped on the frame's top edge | 18–19 Nov 2026 (bring-up, 7.4 h healthy overnight campaign) | Retired 19 Nov |
| (new, e.g. `flat4`) | Lying flat on four corner supports, blowing up; board on a side wall | From 19 Nov 2026 | Being set up: photo and axes to be added |

The rest of this page describes `tapeCorner` (standing).

![tapeCorner setup, fan standing on its edge](2026-11-19_tapeCorner_standing.jpg)

## Fan `pc01`

- **Model:** Thermalright **TL-H12-X28-R7**. 120 × 120 × 28 mm, 4-pin PWM, 12 V, rated 2400 rpm. The hub label reads "S-FDB Bearing V2" (fluid dynamic bearing).
- **Measured on the bench:**
  - About 720 rpm at 30 % duty and about 2490 rpm at 100 %.
  - Tach gives 2 pulses per revolution.
  - **7 blades:** the audio blade-pass peak is at 7× rotation.
  - **4-pole motor:** the magnetometer peak is at 2× rotation.
  - A 12× family in accel and audio is probably motor cogging.
- **Placement:** stands upright on its edge, **free on a wooden floor** (not clamped), axis horizontal. Nothing holds it in place but its weight.

## Board and mount (`--mount tapeCorner`)

- **Board:** Adafruit Feather nRF52840 Sense (original revision, LSM6DS33), lying flat on the **top edge of the fan frame near one corner**. It is held by clear tape wrapped around the frame.
- **Wires:** three jumper wires (PWM, tach, GND) run from the board's header to a breadboard about 30 cm away. The breadboard joins the fan's 4-pin cable, the 12 V supply and the shared ground. The USB cable leaves the board towards the PC.
- **Board axes vs fan,** deduced from the data (gravity, and the magnetometer's 2× signal, which lies in the rotor plane):

  | Board axis | Fan direction |
  |---|---|
  | z | vertical, up (gravity +1.005 g) |
  | y | along the fan axis (fore-aft, the direction of the airflow) |
  | x | horizontal, in the rotor plane (along the top edge) |

## What this setup does to the signals (19 Nov overnight data)

- **The healthy 1× is almost all fore-aft rocking.**
  - Accel 1× is along y at 29–37 mg; x and z are only 1–4 mg.
  - Gyro 1× is mostly rotation about x.
  - The fan tips back and forth on its narrow 28 mm base once per revolution; that is the softest mode of a fan standing free.
- **At 90–100 % the same rocking appears at 0.5×.** Accel y reaches 37 mg and gyro about x 1.4 dps. That is the frame rattling on the floor, not the tape.
- **Where an added mass should show.** A static imbalance (Blu-Tack on one blade) adds a force that rotates in the rotor plane. It should show most in **x and z 1×**, where the healthy baseline is small.
- **Things that can shift the baseline:**
  - Pulling the wires or USB cable.
  - Moving the fan on the floor.
  - Pressing on the frame.

## Rules for a fault night on this setup

- **Mark the fan's position on the floor** (tape at two corners) and the cable routing before the run.
- When adding or removing mass, hold the frame still with one hand. Don't lift or slide the fan, and don't touch the board or its wires.
- Use A-B-A with a sham-touch run (see `results/own/overnight/REPORT.md`, section 9).
- **Unplug the 12 V supply** before touching the blades.

## Possible improvement later (as a new mount id, not mid-experiment)

- Fix the fan to a heavy base or plank through its screw holes, or stand it on a rubber mat.
- Strain-relieve the jumper wires and the USB cable a few cm from the board.

This should remove most of the rocking and the slow drift. Record it under a new `--mount`, which also gives a second mount for the benign-drift scenario.
