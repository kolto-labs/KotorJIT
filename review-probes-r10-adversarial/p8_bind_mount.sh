#!/bin/sh
# R10: commitment log reached through an unprivileged user-namespace bind mount of the run dir.
rm -rf /tmp/kp-r10-bind && mkdir -p /tmp/kp-r10-bind/run /tmp/kp-r10-bind/out/bind && touch /tmp/kp-r10-bind/run/log
unshare -Urm sh -c "mount --bind /tmp/kp-r10-bind/run /tmp/kp-r10-bind/out/bind && cd /run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation && PYTHONPATH=scripts/harness python3 -c \"
from kpharness import creative_accept as A
try: A.validate_commitment_log('/tmp/kp-r10-bind/out/bind/log', '/tmp/kp-r10-bind/run'); print('bind_mount_alias_of_run_log: accepted')
except ValueError as e: print('bind_mount_alias_of_run_log: refused', e)
\""
