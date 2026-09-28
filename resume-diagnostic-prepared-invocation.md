# Prepared single capture diagnostic — not executed

The host-only resume wave has not authorized or launched Gamescope, mpv, Wine, or a game. This is a concrete invocation for the later authorized diagnostic. No snapshot directory has been created: the driver must create and validate it itself.

Prerequisites: final current-source capture reviews accepted; foreign Wine/capture processes absent on a fresh read-only identity check; explicit user authorization for one attempt; source/tool hashes and protected-display inventory recorded. The last read-only check found foreign PotPlayer and two wineservers. Their owner must resolve that conflict; this task must not signal them. Recheck rather than relying on those historical PID values.

Run from the validation worktree after assigning new unused run/snapshot paths and a durable external commitment-log path:

```bash
PYTHONPATH=/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/scripts/harness \
/usr/bin/python3.14 -S -B -m kpharness.capture_diagnostic run \
  --run-root /home/brunner56/kp-live-20260922/r15-authorized-diagnostic \
  --snapshot /home/brunner56/kp-live-20260922/r15-authorized-diagnostic-snapshot \
  --cleanup-commitment-log /home/brunner56/kp-live-20260922/r15-authorized-diagnostic-commitments.jsonl \
  --source-root /run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/scripts/harness \
  --ffmpeg /usr/bin/ffmpeg \
  --ffprobe /home/linuxbrew/.linuxbrew/bin/ffprobe \
  --authorized-single-run
```

The driver owns canonical lock acquisition; do not wrap this in another flock. Do not retry automatically. Retain any failed run, cleanup ledger, commitment head, process-start identities, and final source/tool hashes. Post-run review must verify protected displays and no owned survivors. A 34-second media window is not a 34-second total execution deadline: startup and bounded decoding/cleanup can take much longer. The offline 2040-frame sample is performance evidence only, not live-display proof.
