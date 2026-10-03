# Documentation

The decision log ([`DECISIONS.md`](../../DECISIONS.md)), dated test results
([`TESTS_AND_RESULTS.md`](../../TESTS_AND_RESULTS.md)) and work log
([`WORKLOG.md`](../../WORKLOG.md)) are at the repository root. This folder
holds everything else.

## The requirement

- [PROBLEM_STATEMENT.md](PROBLEM_STATEMENT.md): SIH26158 as issued, and the
  team's evaluation framework for it.

## Accuracy and evidence

- [VIDEO_ACCURACY_MARS_LVIG.md](VIDEO_ACCURACY_MARS_LVIG.md): native video
  against same-flight LiDAR. How each metric was validated, what was fixed,
  and current accuracy.
- [BENCHMARK.md](BENCHMARK.md), with raw runs in [benchmarks/](benchmarks/):
  the truth harness, and the rule that no accuracy claim is published unless
  it generated it.
- [RASTERS.md](RASTERS.md): DSM, DTM, orthophoto and land-cover layers. The DSM
  is checked against LiDAR; the land cover is scored against OpenStreetMap and
  is experimental.
- [EVALUATION.md](EVALUATION.md): how ground-truth evaluation is run.
- [performance_2026_09_23/](performance_2026_09_23/): the optimisation plan
  and baselines behind the 12.2-minute DJI run (DEC-041).
- [review_checks/](review_checks/): scripts that re-check specific claims.

## Running and operating

- [ENVIRONMENT.md](ENVIRONMENT.md): the reproducible environment.
- [TELEMETRY.md](TELEMETRY.md): accepted telemetry formats.
- [OPTIONAL_MODELS.md](OPTIONAL_MODELS.md): optional reconstruction backends.
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md): common problems and air-gapped
  deployment.
- [DEMO.md](DEMO.md) and [demo/](demo/): the five-minute demo script and its
  assets.
- The public read-only showcase is documented in
  [`../deploy/showcase/server/README.md`](../deploy/showcase/server/README.md).

## Reviews

- [NTRO_CRITICAL_REVIEW_AND_IMPROVEMENTS_2026-09-21.md](NTRO_CRITICAL_REVIEW_AND_IMPROVEMENTS_2026-09-21.md)
  and its [verification](CRITICAL_REVIEW_VERIFICATION_2026-09-21.md).
- [review_2026_09_22/](review_2026_09_22/): critical review and project report
  of 22 September, with the official SIH26158 attachment.
- [V3_1_REVIEW_AND_FUTURE_WORK.md](V3_1_REVIEW_AND_FUTURE_WORK.md): the V3.1
  plan against the code, and prioritised future work.
- [UNCOMMON_AND_DISTINCTIVE_IDEAS.md](UNCOMMON_AND_DISTINCTIVE_IDEAS.md):
  research ideas not yet built.
- [ui-ux/](ui-ux/): screenshots from the UI redesign.

## History

- [REPOSITORY_AUDIT_AND_IMPROVEMENT_ROADMAP.md](REPOSITORY_AUDIT_AND_IMPROVEMENT_ROADMAP.md),
  [ENGINEERING_DECISION_LOG.md](ENGINEERING_DECISION_LOG.md) and
  [WORK_LOG.md](WORK_LOG.md): the audit and logs from the first weeks, to
  11 September. The root decision log and work log continue them.
- [archive/](archive/): superseded plans and reports that other documents
  cite.
