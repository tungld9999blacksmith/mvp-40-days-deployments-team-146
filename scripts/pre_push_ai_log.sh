#!/usr/bin/env bash
# Log failures stay visible, never block push.
if ! bash scripts/_pyrun.sh scripts/log_antigravity.py --auto; then
  echo '[ai-log] WARNING: prompt sweep failed; some prompts may not have been collected.' >&2
fi
if ! bash scripts/_pyrun.sh scripts/submit_log.py; then
  echo '[ai-log] WARNING: log submission failed; inspect the error above and retry after fixing configuration.' >&2
fi
exit 0
