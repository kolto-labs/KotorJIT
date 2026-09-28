import os, fcntl, sys

path = sys.argv[1]
fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
actual = os.fstat(fd)
expected = os.stat(path, follow_symlinks=False)
print("fstat(fd).st_dev  =", actual.st_dev, "major:minor=%02x:%02x" % (os.major(actual.st_dev), os.minor(actual.st_dev)))
print("stat(path).st_dev =", expected.st_dev, "major:minor=%02x:%02x" % (os.major(expected.st_dev), os.minor(expected.st_dev)))
print("match:", actual.st_dev == expected.st_dev and actual.st_ino == expected.st_ino)

with open(f"/proc/self/fdinfo/{fd}") as f:
    fdinfo = f.read()
print("--- fdinfo ---")
print(fdinfo)
key = "%02x:%02x:%d" % (os.major(actual.st_dev), os.minor(actual.st_dev), actual.st_ino)
print("computed key:", key)
print("key present in fdinfo:", key in fdinfo)
os.close(fd)
