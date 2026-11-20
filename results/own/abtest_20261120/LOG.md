# Fault blocks part 1 (imbalance), 20 Nov 2026: log

Protocol: `docs/experiments/2026-11-19_imbalance_ABA.md` (revised plan, part 1). Fan `pc01`, mount `flat4`,
logger 0.3.2, profile `ab_block`. Jonathan handled the fan; Claude ran the recordings.

| # | Block | Session | Power off / on | What changed | Notes |
|---|---|---|---|---|---|
| 0 | (healthy campaign) | ends `20261120-171249` | – | daytime campaign stopped with STOP after its session | – |
| 1 | A0 | `20261120-172948_pc01_normal_none` | – | nothing, nobody touching the fan | 256 audio samples dropped (16 ms) |
| 2 | Sham | `20261120-174647_pc01_normal_sham` | 17:43 / 17:46 | blade 1 held 10 s, empty tape strip on blade 1 at 25 mm | – |
| 3 | B 0.2 g | `20261120-180634_pc01_imbalance_0.2g-25mm` | not noted / about 18:06 | sham strip off, 0.2 g Blu-Tack on blade 1 at 25 mm under a fresh strip | **a tape edge was sticking out** (found by Jonathan when removing the mass) |
| 4 | A | `20261120-182701_pc01_normal_none` | 18:20 / 18:25 | mass removed, fresh empty strip | – |

From the sham on, blade 1 always carries one tape strip: empty in the A blocks, over the mass in the B blocks.
A0 is the only block without tape.

## Observations during the run (quick looks, not the pre-registered analysis)

- **Sham vs A0:**
  - in-plane 1× changed little: ×0.98–1.18 per step, combined about ×1.07, z ≈ 1.6;
  - axial 1× fell to ×0.53–0.60 at every step (z −11 to −14), and the audio blade-pass tone changed too.
  - Likely the fan shifted on its taped corners during handling: a change in the blade's imbalance would move
    in-plane and axial together. Jonathan was asked to steady the frame with his other hand from block 3 on.
- **0.2 g vs sham:**
  - in-plane 1× ×4.4 / ×11 / ×16 / ×64 / ×53 at 40 / 50 / 60 / 70 / 80 % (141.5 mg at 70 %, 208 mg at 80 %);
  - the fan's own 1× is only about 2 mg in-plane, so 0.2 g at 25 mm is about 50× its own imbalance.
  - Audio 2–7.9 kHz (`aud_hi`) ×15–18 at 50–80 %. An imbalance shouldn't do that. Jonathan then found a tape edge
    sticking out, which most likely flapped in the airflow. **`aud_hi` in block 3 is a tape artefact, not an
    imbalance effect.**

## Deviations from the protocol (decided before the data they affect)

- **Extra A blocks during the dinner break (decided 18:26, before block 4 ended).** Jonathan is away from about
  18:25 until after 20:00. Instead of leaving the fan idle, healthy `ab_block` blocks are recorded back to back
  with no handling (fault `normal`, notes "extra A block N during the dinner break"), until he returns.
  - They are A blocks and go into the analysis in recorded order, like every other block.
  - The 0.1 g block's "A before" is then the last complete one before he handles the fan, not block 4.
  - A block cut short when he returns is excluded (`abtest.py` warns about it as aborted or short).
- **Proposed, not yet decided: a smaller mass.** Because 0.2 g is so large against this fan's own imbalance, a
  block with about 0.03 g (one staple or a crumb of Blu-Tack) on blade 1 at 25 mm, followed by an A block, was
  proposed after the 0.1 g block. Jonathan decides; it will be logged here before it is recorded.
