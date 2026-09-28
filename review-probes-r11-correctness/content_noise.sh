#!/bin/sh
# Synthetic lavfi encodes only (no x11grab/capture). Same encoder settings as the recorder.
set -e
cd "$(dirname "$0")"
enc() { /usr/bin/ffmpeg -nostdin -y -v error -f lavfi -i "$1" -t "$2" -an -c:v libx264 -preset ultrafast -crf 28 -pix_fmt yuv420p "$3"; }
enc "color=c=0x406080:s=1024x768:r=60" 10 static_flat.mp4
enc "testsrc2=s=1024x768:r=60,trim=end_frame=1,loop=loop=-1:size=1,setpts=N/60/TB" 10 static_pattern.mp4
enc "testsrc2=s=1024x768:r=60,trim=end_frame=1,loop=loop=-1:size=1,setpts=N/60/TB,noise=alls=2:allf=t" 10 static_pattern_sensor_noise.mp4
enc "testsrc2=s=1024x768:r=30,fps=60" 10 half_dup.mp4
enc "testsrc2=s=1024x768:r=6,fps=60" 10 tenth_fresh.mp4
enc "testsrc2=s=1024x768:r=60" 10 anim60.mp4
