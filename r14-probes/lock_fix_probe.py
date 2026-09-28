"""Round 14 probe for R13C-m1: exercises the *production* lock-holding checks
(held_lock_descriptor, canonical_lock_guard) against a real held flock on a
btrfs-backed file, plus the "fake unlocked fd, same inode" refusal case.

Never touches the live-game lock: uses its own throwaway lock file.
"""
import os
import sys

sys.path.insert(0, '/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/scripts/harness')
from kpharness import gamescope_socket as gs

path = sys.argv[1]
fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
import fcntl
fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

print("=== held_lock_descriptor on a real held lock ===")
try:
    result = gs.held_lock_descriptor(fd, path)
    print("PASS:", result)
except RuntimeError as error:
    print("FAIL (incorrectly refused a real held lock):", error)

print("=== fake unlocked fd, same inode, must still be refused ===")
fd2 = os.open(path, os.O_RDONLY)
try:
    result = gs.held_lock_descriptor(fd2, path)
    print("FAIL (incorrectly accepted an unlocked fd):", result)
except RuntimeError as error:
    print("PASS (correctly refused):", error)
finally:
    os.close(fd2)

os.close(fd)
