#!/bin/sh
# quick candidate check: $1 = name, $2 = graph; 2 s at 1024x768, recorder codec
set -e
G="$2"
/usr/bin/ffmpeg -nostdin -v error -f lavfi -i "$G" -t 2 -pix_fmt bgr0 -f rawvideo - | \
/usr/bin/ffmpeg -nostdin -y -v error -f rawvideo -pix_fmt bgr0 -video_size 1024x768 -framerate 60 -i - -an -c:v libx264 -preset ultrafast -crf 28 -pix_fmt yuv420p -threads 2 "q_$1.mp4"
/home/linuxbrew/.linuxbrew/bin/ffprobe -v error -f lavfi -i "movie=q_$1.mp4,signalstats" -show_entries frame_tags=lavfi.signalstats.YDIF,lavfi.signalstats.YAVG,lavfi.signalstats.YMIN,lavfi.signalstats.YMAX -of csv=p=0 > "q_$1.csv"
echo "$1"; head -12 "q_$1.csv"; sort -t, -k2 -g "q_$1.csv" | awk -F, 'NR>1{print "min ydif-ish row", $0; exit}'
