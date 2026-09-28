#!/bin/bash
# usage: mkgame.sh <dir>
P=/home/brunner56/kp-live-20260922/review-probes-w0w1
rm -rf "$1"; mkdir -p "$1"; cp $P/fake_exe.bin "$1/swkotor.exe"; cp $P/fake_bink.bin "$1/binkw32.dll"; echo data > "$1/chitin.key"
