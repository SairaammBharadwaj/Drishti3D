#!/usr/bin/env bash
# Run a heavy job in its own memory-capped systemd scope, outside the editor.
#
# A pipeline run on 2448x2048 MARS-LVIG frames reached 11.9 GB on this 15 GB
# machine. It had been started from VS Code's terminal, so it lived in VS Code's
# cgroup, and the kernel OOM killer took the editor down with it. In its own
# scope with MemoryMax, an overrun kills only the job.
#
# There is deliberately no MemoryHigh. Throttling at 90% of the cap was tried:
# it kept the editor safe, but a PatchMatch stage that takes 6 minutes when it
# fits sat reclaiming for over 2 hours with the GPU idle. A job that does not
# fit should fail fast and say so, not hang.
#
# The job also holds a sleep lock (systemd-inhibit: suspend, idle sleep and lid
# close) for exactly as long as it runs. A laptop suspending mid-run froze a
# pipeline job; the lock is released automatically when the job exits or dies.
#
# The job is also the preferred OOM victim (choom 900) and runs at low CPU
# weight and nice 10, so the editor stays responsive while all cores are busy.
#
# Usage:
#   scripts/run_capped.sh [--mem 6G] -- <command ...>
#   scripts/run_capped.sh -- .venv/bin/python scripts/run_mission.py ...
# The 6G default was measured: at 9G a MARS run left under 1 GB for the desktop,
# editor and browser on this 15 GB machine. Frames cost ~10.6 MB each at 1600 px
# (2448x2048 source), so size --max-frames to fit: 400 frames is ~4.2 GB.
set -euo pipefail

MEM_MAX=6G
while [ $# -gt 0 ]; do
  case "$1" in
    --mem) MEM_MAX=$2; shift 2 ;;
    --) shift; break ;;
    *) break ;;
  esac
done
[ $# -gt 0 ] || { echo "usage: $0 [--mem 6G] -- <command ...>" >&2; exit 2; }

exec systemd-run --user --scope --quiet --collect \
  --unit="drishti-job-$(date +%s)" \
  -p MemoryMax="$MEM_MAX" -p MemorySwapMax=1G \
  -p CPUWeight=20 -p IOWeight=20 \
  systemd-inhibit --what=sleep:idle:handle-lid-switch --mode=block \
    --who=drishti3d --why="drishti3d job: ${*:0:120}" \
  nice -n 10 choom -n 900 -- "$@"
