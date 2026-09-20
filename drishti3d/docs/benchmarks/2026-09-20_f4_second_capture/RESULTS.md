# F4 gate on further test beds: does the targeted arm's advantage hold?

_Run 2026-09-20 by `python -m eval.f4_experiment`. Per-question records and the
frozen question sets are in `firsthalf/` and `secondhalf/`._

**Result: targeted refinement beat the uniform control on answer yield in all
three test beds, with zero regressions against the control's four to seven. It
cost 2–4× more compute in every one.**

**Read the independence caveat first.** These are not three captures. They are
one flight, partitioned. The genuinely separate AGZ segment could not run this
experiment at all, for a reason worth recording — see below.

## Why the second capture could not be used

`agz_segment_two` (AGZ image ids 64531–70021, 62 frames, 174.8 m flown) is the
only other flight segment in this checkout. Reconstructed at all three keyframe
presets it gives the same answer:

| Preset | Keyframes kept | Registered | SfM |
|---|---:|---:|---:|
| fast | 62 of 62 | 19 | 63.2 s |
| balanced | 62 of 62 | 19 | 64.4 s |
| quality | 62 of 62 | 19 | 63.6 s |

Keyframe selection declines to thin it, correctly: at a 2.8 m median baseline the
inter-frame image shift exceeds the sparse-capture guard in `keyframes.select`,
which exists because thinning a photo-survey-like capture destroys it. The
consequence for this experiment is structural:

- **The targeted arm has no candidate pool.** Every decoded frame is already a
  keyframe, so every candidate is rejected `already_in_reconstruction`.
- **The uniform arm has nowhere to go.** No denser preset adds frames.

The F4 comparison needs a capture that is *over-sampled relative to what
reconstruction needs*. `agz_dense_pass` (184 frames, 1.17 m baseline) is;
`agz_segment_two` is not, and no denser frame set for those image ids exists on
disk. Also worth noting: only 19 of 62 frames register there, against 80 of 184
on the dense pass.

## What was used instead

`agz_dense_pass` split into two halves by image id, each built as its own
mission. Different scene content, same flight, same camera, same conditions.

| | Frames | Baseline keyframes | Uniform keyframes | Uniform added SfM |
|---|---:|---:|---:|---:|
| `agz_dense_firsthalf` (57211–59941) | 92 | 46 | 82 | +57.2 s |
| `agz_dense_secondhalf` (59971–62701) | 92 | 46 | 82 | +58.2 s |

Both register 100% of their keyframes. Their georeferencing differs sharply —
0.41 m median as-georeferenced error on the first half against 4.73 m on the
second — so they are not interchangeable scenes.

20 questions per half, frozen before either arm ran.

## Results

Answer yield is "measurements blocked only by calibration", the closest
available proxy while no calibration profile exists.

| Test bed | Baseline | **Targeted** | Uniform | Targeted regressions | Uniform regressions |
|---|---:|---:|---:|---:|---:|
| `agz_dense_pass` (full, 184 frames) | 8 | **14** | 10 | **0** | 5 |
| `agz_dense_firsthalf` | 7 | **13** | 5 | **0** | 7 |
| `agz_dense_secondhalf` | 9 | **15** | 9 | **0** | 4 |

| Test bed | Targeted compute | Uniform compute | Break-even questions |
|---|---:|---:|---:|
| `agz_dense_pass` | 206.7 s | 135.4 s | 13.1 |
| `agz_dense_firsthalf` | 239.3 s | 57.2 s | 4.8 |
| `agz_dense_secondhalf` | 223.9 s | 58.2 s | 5.2 |

Supporting evidence, both halves:

| | Targeted | Uniform |
|---|---|---|
| Median supporting views | 3 → **7.0** | 3 → 3 |
| Median measured parallax (first half) | 8.18° → **27.58°** | 8.18° → 4.93° |
| Median measured parallax (second half) | 9.08° → **26.74°** | 9.08° → 7.48° |
| Questions with a frame recovered | 20/20 and 15/20 | n/a |

## The uniform arm made measurements worse

This is the result that did not appear on the full pass, and it is worth stating
plainly: **on the first half, doubling the keyframes took answer yield from 7
down to 5**, regressing seven measurements. On the second half it regressed four
and moved yield not at all.

The new blockers it introduced:

| New blocker | First half | Second half |
|---|---:|---:|
| `outside_established_coverage` | 4 | 1 |
| `interval_exceeds_tolerance` | 3 | 3 |
| `insufficient_views` | 2 | 2 |

A denser reconstruction is a different cloud, not a strictly better one. Its
endpoints re-snap to different points, its coverage grid has different
boundaries, and its median measurement sigma on the first half got *worse*
(0.183 m → 0.260 m). "More frames" is not monotone in measurement standing,
which is not how the first experiment's result would have led one to expect it.

The targeted arm regressed nothing on any test bed. It does not rebuild the
cloud, so it cannot move anything it was not asked about.

## What this establishes, and what it does not

**Establishes**, on this flight: the yield advantage is not an artefact of one
question set or one part of the scene. It reproduced on two disjoint halves with
markedly different georeferencing quality, and in the direction of a larger
margin than the full pass showed.

**Does not establish**:

- **Generalisation to another flight.** All three test beds are partitions of
  one capture. This is the weakest part of the evidence and it is not fixable
  with the data in this checkout.
- **Anything about accuracy.** No reference dimensions exist, so both arms are
  scored on measurement standing and interval width, never on error against
  truth.
- **That the advantage survives where the capture is not over-sampled.** The one
  segment that is not, `agz_segment_two`, cannot run the experiment at all.
- **That "blocked only by calibration" means accepted.** It is a proxy.

## Consequences

Same-pass refinement stays **experimental**. The evidence is stronger than it
was — three test beds, consistent direction, zero regressions throughout — and
still comes from a single flight with no truth.

The compute gap is now the clearer of the two findings: break-even falls to
about five questions on the halves, against thirteen on the full pass, because
the uniform arm's fixed cost is smaller there while the targeted arm's
per-question cost is unchanged. Reducing that per-question cost is what would
turn a split result into an unambiguous one.

Recorded as [DEC-016](../../../DECISIONS.md).

## Reproducing

```bash
cd drishti3d
.venv/bin/python scripts/build_agz_mission.py --source data/real_drone/agz_dense \
    --name agz_dense_firsthalf --imgid-max 59941 --overwrite
.venv/bin/python scripts/build_agz_mission.py --source data/real_drone/agz_dense \
    --name agz_dense_secondhalf --imgid-min 59971 --overwrite
for h in firsthalf secondhalf; do
  for p in balanced quality; do
    .venv/bin/python scripts/run_mission.py --mission agz_dense_${h} \
        --max-frames 92 --engine colmap --preset $p --tag $p
  done
  .venv/bin/python -m eval.f4_experiment --mission agz_dense_${h} \
      --baseline balanced --uniform quality --n-questions 20 \
      --out docs/benchmarks/2026-09-20_f4_second_capture/${h}
done
```

The frozen question sets are reused if present. Delete them only to start a
genuinely new experiment.
