#!/bin/sh
# Encode cost, old vs new pattern, alternating, 18 s at 1024x768 with the recorder codec (x264 reports speed=).
OLD='testsrc2=size=1024x768:rate=60'
NEW='testsrc2=size=1024x768:rate=60,eq=contrast=0.4:brightness=(3*n-7*floor(3*n/7)-3)*0.11:eval=frame'
for round in 1 2; do
for name in old new; do
  if [ $name = old ]; then G="$OLD"; else G="$NEW"; fi
  s=$(date +%s.%N)
  /usr/bin/ffmpeg -nostdin -v error -f lavfi -i "$G" -t 18 -pix_fmt bgr0 -f rawvideo - | \
  /usr/bin/ffmpeg -nostdin -y -v error -stats -f rawvideo -pix_fmt bgr0 -video_size 1024x768 -framerate 60 -i - -an -c:v libx264 -preset ultrafast -crf 28 -pix_fmt yuv420p -threads 2 /tmp/kp-r12-cost-$name.mp4 2> /tmp/kp-r12-cost-$name.err
  e=$(date +%s.%N)
  printf '%s round%s wall=%.1fs size=%s %s\n' $name $round $(echo "$e - $s" | bc) $(stat -c %s /tmp/kp-r12-cost-$name.mp4) "$(tr '\r' '\n' < /tmp/kp-r12-cost-$name.err | grep speed | tail -1 | sed 's/.*bitrate=/bitrate=/')"
done; done
rm -f /tmp/kp-r12-cost-*.mp4 /tmp/kp-r12-cost-*.err
uptime
