import os, sys
sys.path.insert(0, '/tmp/r14-red-check')
from kpharness import gamescope_socket as gs
path = sys.argv[1]
fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
import fcntl
fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
print("=== (RED, unpatched) held_lock_descriptor on a real held btrfs lock ===")
try:
    result = gs.held_lock_descriptor(fd, path)
    print("would PASS:", result)
except RuntimeError as error:
    print("FAILS as expected (this is the bug):", error)
os.close(fd)
