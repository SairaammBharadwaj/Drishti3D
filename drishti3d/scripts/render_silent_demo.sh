#!/usr/bin/env bash
set -euo pipefail

# Produces the silent 6:30 visual edit. Voice-over and music are intentionally
# absent so the final narration can be recorded and mixed later.
root_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
output_dir="$root_dir/docs/demo/final_video"
scratch_dir=$(mktemp -d /tmp/drishti-silent-edit.XXXXXX)
mkdir -p "$output_dir"

render_still() {
  local name=$1 duration=$2 source=$3
  ffmpeg -y -hide_banner -loglevel error -loop 1 -framerate 60 -t "$duration" -i "$source" \
    -vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=0x161715,fps=60" \
    -an -c:v libx264 -preset fast -crf 18 -pix_fmt yuv420p "$scratch_dir/$name.mp4"
}

render_video() {
  local name=$1 duration=$2 source=$3 start=${4:-0}
  ffmpeg -y -hide_banner -loglevel error -stream_loop -1 -ss "$start" -t "$duration" -i "$source" \
    -vf "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps=60" \
    -an -c:v libx264 -preset fast -crf 18 -pix_fmt yuv420p "$scratch_dir/$name.mp4"
}

render_video 01 10 "$HOME/Downloads/DJI_1003_1080p.mp4" 180
render_video 02 12 "$root_dir/docs/demo/video_capture/raw/hkisland03-hero-closeup.mp4"
render_video 03 18 "$root_dir/docs/demo/video_capture/raw/hkisland03-hero-closeup.mp4"
render_still 04 25 "$root_dir/docs/demo/video_capture/missions.png"
render_still 05 20 "$root_dir/docs/demo/video_capture/showcase.png"
render_still 06 25 "$root_dir/docs/demo/video_capture/showcase-results.png"
render_still 07 20 "$root_dir/docs/demo/video_capture/showcase-results.png"
render_video 08 25 "$root_dir/docs/demo/video_capture/raw/hkisland03-hero-closeup.mp4"
render_video 09 30 "$root_dir/docs/demo/video_capture/raw/hkisland03-provenance.mp4"
render_still 10 30 "$root_dir/docs/demo/video_capture/research-prototype.png"
render_still 11 20 "$root_dir/docs/demo/video_capture/hkisland03-single-pass.png"
render_still 12 35 "$root_dir/docs/demo/video_capture/hkisland03-single-pass.png"
render_still 13 25 "$root_dir/docs/demo/video_capture/hkisland02-single-pass.png"
render_still 14a 20 "$root_dir/docs/demo/video_capture/hkisland02-single-pass.png"
render_still 14b 20 "$root_dir/docs/demo/video_capture/hkisland03-single-pass.png"
render_still 15 20 "$root_dir/docs/demo/video_capture/evidence-report.png"
render_still 16 15 "$root_dir/docs/demo/video_capture/hkisland03-full-window.png"
render_video 17 20 "$root_dir/docs/demo/video_capture/raw/hkisland03-provenance.mp4"

for name in 01 02 03 04 05 06 07 08 09 10 11 12 13 14a 14b 15 16 17; do
  printf "file '%s'\n" "$scratch_dir/$name.mp4"
done > "$scratch_dir/concat.txt"

ffmpeg -y -hide_banner -loglevel error -f concat -safe 0 -i "$scratch_dir/concat.txt" -c copy "$scratch_dir/picture-lock.mp4"
ffmpeg -y -hide_banner -loglevel error -i "$scratch_dir/picture-lock.mp4" \
  -vf "subtitles=$output_dir/timeline.srt:force_style='FontName=DejaVu Sans,FontSize=7,PrimaryColour=&H00F7F2EA,OutlineColour=&H00161410,BorderStyle=1,Outline=1,Shadow=1,Alignment=2,MarginV=70'" \
  -an -c:v libx264 -preset slow -crf 17 -pix_fmt yuv420p -movflags +faststart "$output_dir/Drishti3D_silent_demo_6m30s.mp4"

ffprobe -v error -show_entries format=duration,size -of default=noprint_wrappers=1 "$output_dir/Drishti3D_silent_demo_6m30s.mp4"
