"""Run one reconstruction job in its own process.

The API used to run the pipeline on a thread inside the server. A heavy mission
then grew inside the server's own memory, with no cap: an 11-minute video is
exactly the job ``scripts/run_capped.sh`` exists for, and the web path was the
one way to start it without the cap. :mod:`app.jobs` now starts this module as a
child process, inside the capped scope when one is available, so an overrun
kills the job and leaves the API, the browser and the editor running.

Progress travels back as one JSON object per line on stdout, each prefixed with
:data:`PREFIX` so it cannot be confused with anything the pipeline or a library
prints. Everything else on stdout is log output.

Usage (by :mod:`app.jobs`, not by hand)::

    python -m app.worker <job-spec.json>

The spec holds ``project_dir``, ``video``, ``telemetry`` (or null) and
``params``, a dict of :class:`drishti_recon.pipeline.PipelineParams` fields.

Deliberately imports nothing from :mod:`app`: the worker needs the pipeline
and nothing of the server, database or configuration.
"""
from __future__ import annotations

import json
import sys
import time
import traceback
from pathlib import Path

PREFIX = "@@drishti "

#: Minimum seconds between progress events within one stage. Frame decoding
#: reports every frame, which is thousands of lines on a long video.
_MIN_INTERVAL_S = 0.25


def emit(**event) -> None:
    sys.stdout.write(PREFIX + json.dumps(event) + "\n")
    sys.stdout.flush()


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: python -m app.worker <job-spec.json>", file=sys.stderr)
        return 2
    spec = json.loads(Path(argv[0]).read_text())

    try:
        from drishti_recon import pipeline
        params = pipeline.PipelineParams(**spec["params"])
    except Exception as e:                                 # noqa: BLE001
        emit(event="error", error=f"invalid job: {e}",
             traceback=traceback.format_exc())
        return 1

    last = {"t": 0.0, "stage": None}

    def progress(stage, frac, msg=""):
        now = time.monotonic()
        if stage == last["stage"] and now - last["t"] < _MIN_INTERVAL_S and frac < 1.0:
            return
        last["t"], last["stage"] = now, stage
        emit(event="progress", stage=stage, progress=round(float(frac), 4),
             message=msg)

    try:
        result = pipeline.run(spec["project_dir"], spec["video"],
                              spec.get("telemetry"), params=params,
                              progress=progress)
    except Exception as e:                                 # noqa: BLE001
        emit(event="error", error=f"{e}", traceback=traceback.format_exc())
        return 1
    emit(event="done", warnings=list(result.warnings))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
