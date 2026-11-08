#!/usr/bin/env bash
# The THROWAWAY media probe (Batt 2026-11-08): what the Arc A380 does with VA-API, measured.
#
# Everything happens in /tmp (a tmpfs, RAM): a synthetic 1440x900, 30 fps, 20 s clip made here
# (testsrc2 + a moving patch, libx264 on the CPU), 30 raw frames (NV12 and BGRA) looped 20 times
# for the encode and JPEG runs. Each timed run is one ffmpeg with -benchmark; the result line gives
# frames, rtime, fps, utime + stime and cores = (utime + stime) / rtime. The GPU's own time is NOT
# in utime/stime: cores is what the CPU pays. Nothing is written outside /tmp; no network.
#
# Output: plain lines, `<UTC time> RESULT <name> key=value ...`, one per run; FAILED lines carry
# the tail of ffmpeg's log.
set -euo pipefail

DEV=${PROBE_DEVICE:-/dev/dri/renderD128}
W=1440
H=900
FPS=30
SECS=20
FRAMES=$((FPS * SECS)) # 600
RAWN=30                # raw frames kept in RAM (NV12 58 MB, BGRA 155 MB)
LOOPS=$((FRAMES / RAWN - 1))
BITRATE=6M
WORK=/tmp/probe
CLIP=$WORK/clip.mp4
NV12=$WORK/nv12.raw
BGRA=$WORK/bgra.raw

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
say() { printf '%s %s\n' "$(ts)" "$*"; }
section() { printf '\n%s ===== %s =====\n' "$(ts)" "$*"; }

FF=(ffmpeg -hide_banner -nostdin -y -benchmark)
HW=(-init_hw_device "vaapi=va:${DEV}" -filter_hw_device va)
HWDEC=(-hwaccel vaapi -hwaccel_device "${DEV}" -hwaccel_output_format vaapi)
RAW_NV12=(-stream_loop "${LOOPS}" -f rawvideo -pix_fmt nv12 -s "${W}x${H}" -r "${FPS}" -i "${NV12}")
RAW_BGRA=(-stream_loop "${LOOPS}" -f rawvideo -pix_fmt bgra -s "${W}x${H}" -r "${FPS}" -i "${BGRA}")

# run NAME NOTE OUTFILE -- ffmpeg arguments. OUTFILE ("-" for none) is measured (bytes, bitrate)
# and kept for psnr_of; returns ffmpeg's exit code (the caller decides on a fallback).
run() {
  local name=$1 note=$2 out=$3
  shift 4
  local log=$WORK/$name.log rc=0
  "${FF[@]}" "$@" >"$log" 2>&1 || rc=$?
  if ((rc != 0)); then
    say "RESULT $name FAILED rc=$rc ($note)"
    tr '\r' '\n' <"$log" | grep -v '^\s*$' | tail -n 6 | sed 's/^/    | /'
    return "$rc"
  fi
  local frames u s r
  frames=$(tr '\r' '\n' <"$log" | grep -oE 'frame= *[0-9]+' | tail -1 | grep -oE '[0-9]+' || true)
  u=$(grep -oE 'utime=[0-9.]+' "$log" | tail -1 | cut -d= -f2)
  s=$(grep -oE 'stime=[0-9.]+' "$log" | tail -1 | cut -d= -f2)
  r=$(grep -oE 'rtime=[0-9.]+' "$log" | tail -1 | cut -d= -f2)
  local size=""
  if [[ "$out" != "-" && -f "$out" ]]; then
    local bytes
    bytes=$(stat -c %s "$out")
    size=$(awk -v b="$bytes" -v f="${frames:-0}" -v fps="$FPS" 'BEGIN {
      if (f > 0) printf " out_bytes=%d bytes_per_frame=%d kbit_s=%.0f", b, b / f, b * 8 / (f / fps) / 1000
    }')
  fi
  awk -v n="$name" -v f="${frames:-0}" -v u="${u:-0}" -v s="${s:-0}" -v r="${r:-0}" \
    -v t="$(ts)" -v note="$note" -v size="$size" 'BEGIN {
      fps = (r > 0) ? f / r : 0; cores = (r > 0) ? (u + s) / r : 0
      msf = (f > 0) ? r * 1000 / f : 0; cpums = (f > 0) ? (u + s) * 1000 / f : 0
      printf "%s RESULT %s frames=%d rtime=%.3fs fps=%.1f utime=%.3fs stime=%.3fs cores=%.2f " \
             "ms_per_frame=%.2f cpu_ms_per_frame=%.2f%s (%s)\n", t, n, f, r, fps, u, s, cores, msf,
             cpums, size, note
    }'
}

# psnr_of NAME FILE -- the reference input arguments: the encoded file against its source.
psnr_of() {
  local name=$1 file=$2
  shift 3
  [[ -f "$file" ]] || return 0
  local log=$WORK/$name.psnr.log rate=()
  [[ "$file" == *.mjpeg ]] && rate=(-framerate "$FPS") # a raw MJPEG stream has no timestamps
  if ffmpeg -hide_banner -nostdin "${rate[@]}" -i "$file" "$@" -lavfi '[0:v][1:v]psnr' -f null - >"$log" 2>&1
  then
    say "QUALITY $name $(grep -oE 'PSNR .*average:[0-9.inf]+' "$log" | tail -1)"
  else
    say "QUALITY $name psnr FAILED"
    tail -n 3 "$log" | sed 's/^/    | /'
  fi
}

# range_check NAME FILE: frame 0's sample statistics (signalstats YMIN/YMAX/YAVG, U/V min/max) and
# frame 0 itself (base64, between FRAME0 lines) for a look on the host. Limited-range samples in a
# JFIF (full-range by definition) show as YMIN ~16 / YMAX ~235 where the CPU control reaches 0-255:
# a washed-out picture in every browser. (Run 3's RGB-space "read as limited" PSNR was inconclusive:
# it may never have re-ranged a yuvj420p input.)
yuv_stats() { # ffmpeg input arguments -> "YMIN=.. YMAX=.. ..." of the first frame
  ffmpeg -hide_banner -nostdin "$@" -frames:v 1 -vf signalstats,metadata=print:file=- -f null - \
    2>/dev/null | grep -oE 'signalstats\.(YMIN|YMAX|YAVG|UMIN|UMAX|VMIN|VMAX)=[0-9.]+' \
    | sed 's/signalstats\.//' | tr '\n' ' ' || true
}
range_check() {
  local name=$1 file=$2
  [[ -f "$file" ]] || return 0
  say "RANGE $name frame0 $(yuv_stats -framerate "$FPS" -i "$file")"
  say "FRAME0 $name begin"
  { ffmpeg -hide_banner -nostdin -loglevel error -framerate "$FPS" -i "$file" -frames:v 1 -c copy \
      -f mjpeg - | base64 -w 0; } || true
  echo
  say "FRAME0 $name end"
}

lists() { grep -qE "$1[[:space:]]*:[[:space:]]*$2\$" "$WORK/vainfo.txt"; }

mkdir -p "$WORK"
section "media probe start"
say "host: $(uname -r) $(nproc) cpus visible; user $(id)"
say "dri nodes: $(ls /dev/dri 2>&1 | tr '\n' ' ')"
say "cgroup cpu.max: $(cat /sys/fs/cgroup/cpu.max 2>/dev/null || echo n/a);" \
    "memory.max: $(cat /sys/fs/cgroup/memory.max 2>/dev/null || echo n/a)"
say "ffmpeg: $(ffmpeg -hide_banner -version | head -1)"
say "packages:"
sed 's/^/    /' /opt/probe-packages.txt
say "ffmpeg hwaccels: $(ffmpeg -hide_banner -hwaccels | tail -n +2 | tr -s ' \n' ' ')"
ffmpeg -hide_banner -encoders >"$WORK/encoders.txt" 2>/dev/null || true
# never `ffmpeg -encoders | grep -q`: grep's early exit SIGPIPEs ffmpeg, and pipefail then says
# "missing" (run 2, 2026-11-08: libx265 / libsvtav1 were reported absent although linked)
has_encoder() { grep -qE "^ [A-Z.]{6} $1 " "$WORK/encoders.txt"; }
say "ffmpeg vaapi encoders: $(awk '/vaapi/ {print $2}' "$WORK/encoders.txt" | tr '\n' ' ')"
say "ffmpeg CPU encoders of interest: $(awk '$2 ~ /^(libx264|libx265|libsvtav1|libaom-av1|mjpeg)$/ {print $2}' "$WORK/encoders.txt" | tr '\n' ' ')"

section "vainfo --display drm --device ${DEV}"
if vainfo --display drm --device "${DEV}" >"$WORK/vainfo.txt" 2>&1; then
  cat "$WORK/vainfo.txt"
else
  cat "$WORK/vainfo.txt"
  say "vainfo FAILED: no VA-API on ${DEV}; the CPU runs follow alone"
fi

section "inputs (made in /tmp, a tmpfs)"
run make_clip "libx264 veryfast zerolatency ${BITRATE} high, the decode input; NOT a result" \
  "$CLIP" -- -f lavfi -i "testsrc2=size=${W}x${H}:rate=${FPS}:duration=${SECS}" \
  -f lavfi -i "testsrc=size=240x240:rate=${FPS}:duration=${SECS}" \
  -filter_complex "[0:v][1:v]overlay=x='mod(t*420,W-w)':y='abs(mod(t*260,2*(H-h))-(H-h))'" \
  -c:v libx264 -preset veryfast -tune zerolatency -profile:v high -pix_fmt yuv420p \
  -b:v "${BITRATE}" -maxrate "${BITRATE}" -bufsize 3M -g 300 -an "$CLIP" || exit 1
ffprobe -hide_banner -v error -show_entries stream=codec_name,profile,width,height,r_frame_rate,nb_frames,bit_rate \
  -of compact "$CLIP" | sed 's/^/    /'
run make_nv12 "first ${RAWN} decoded frames as NV12; NOT a result" "$NV12" -- \
  -i "$CLIP" -frames:v "${RAWN}" -f rawvideo -pix_fmt nv12 "$NV12" || exit 1
run make_bgra "first ${RAWN} decoded frames as BGRA (an X frame); NOT a result" "$BGRA" -- \
  -i "$CLIP" -frames:v "${RAWN}" -f rawvideo -pix_fmt bgra "$BGRA" || exit 1
say "raw sizes: nv12 $(stat -c %s "$NV12") B, bgra $(stat -c %s "$BGRA") B (${RAWN} frames, looped x$((LOOPS + 1)))"

section "a) H.264 decode, 600 frames of the ${W}x${H} clip"
run dec_cpu_t1 "libavcodec h264, 1 thread, frames stay YUV" - -- -threads 1 -i "$CLIP" -f null - || true
run dec_cpu_auto "libavcodec h264, default threads, frames stay YUV" - -- -i "$CLIP" -f null - || true
run dec_cpu_t1_bgr0 "1 thread + swscale to BGRX (what a client draws)" - -- \
  -threads 1 -i "$CLIP" -vf format=bgr0 -f null - || true
run dec_cpu_auto_bgr0 "default threads + swscale to BGRX" - -- -i "$CLIP" -vf format=bgr0 -f null - || true
run dec_va_gpu "VA-API, frames stay on the GPU (surfaces)" - -- "${HWDEC[@]}" -i "$CLIP" -f null - || true
run dec_va_dl_nv12 "VA-API + hwdownload to NV12 in system memory" - -- "${HWDEC[@]}" -i "$CLIP" \
  -vf hwdownload,format=nv12 -f null - || true
run dec_va_dl_cpu_bgr0 "VA-API + download NV12 + swscale to BGRX on the CPU" - -- "${HWDEC[@]}" \
  -i "$CLIP" -vf hwdownload,format=nv12,format=bgr0 -f null - || true
# VPP to a packed RGB format on the GPU, then download: the first format the iHD VPP accepts
# (run 1, 2026-11-08: "Hardware does not support output format bgr0"). The QUALITY line compares
# its pixels with libavcodec + swscale's BGRA: a wrong channel order or range shows as a low PSNR.
# Run 2: bgra downloads at ~2.5 fps (~400 ms a frame), so only the first 90 frames are timed.
for fmt in bgr0 bgra rgb0 rgba 0rgb argb 0bgr abgr; do
  if run "dec_va_gpu_${fmt}_dl" "VA-API + VPP to ${fmt} on the GPU (scale_vaapi) + download, 90 frames" - -- \
       "${HWDEC[@]}" -i "$CLIP" -vf "scale_vaapi=format=${fmt},hwdownload,format=${fmt}" \
       -frames:v 90 -f null -
  then
    log=$WORK/dec_va_gpu_${fmt}_dl.check.log
    if ffmpeg -hide_banner -nostdin "${HWDEC[@]}" -i "$CLIP" -i "$CLIP" -filter_complex \
         "[0:v]scale_vaapi=format=${fmt},hwdownload,format=${fmt},format=bgra[a];[1:v]format=bgra[b];[a][b]psnr" \
         -frames:v 90 -f null - >"$log" 2>&1; then
      say "QUALITY dec_va_gpu_${fmt}_dl vs CPU BGRA $(grep -oE 'PSNR .*average:[0-9.inf]+' "$log" | tail -1)"
    else
      say "QUALITY dec_va_gpu_${fmt}_dl check FAILED"
      tail -n 3 "$log" | sed 's/^/    | /'
    fi
    break
  fi
done
run dec_va_t1_dl_nv12 "VA-API + download, ffmpeg -threads 1" - -- -threads 1 "${HWDEC[@]}" -i "$CLIP" \
  -vf hwdownload,format=nv12 -f null - || true

section "b) H.264 encode at ${BITRATE} CBR-ish, from 600 raw NV12 frames in RAM"
run raw_read_nv12 "baseline: read + loop the raw NV12, no encode" - -- "${RAW_NV12[@]}" -f null - || true
run enc_x264_ultrafast "libx264 ultrafast zerolatency, default threads" "$WORK/x264.mp4" -- \
  "${RAW_NV12[@]}" -c:v libx264 -preset ultrafast -tune zerolatency -b:v "${BITRATE}" \
  -maxrate "${BITRATE}" -bufsize 3M -g 300 -f mp4 "$WORK/x264.mp4" || true
run enc_x264_ultrafast_t1 "libx264 ultrafast zerolatency, 1 thread" "$WORK/x264t1.mp4" -- \
  "${RAW_NV12[@]}" -c:v libx264 -preset ultrafast -tune zerolatency -threads 1 -b:v "${BITRATE}" \
  -maxrate "${BITRATE}" -bufsize 3M -g 300 -f mp4 "$WORK/x264t1.mp4" || true
LP=()
if lists 'VAProfileH264(Main|High|ConstrainedBaseline)' VAEntrypointEncSliceLP \
   && ! lists 'VAProfileH264(Main|High|ConstrainedBaseline)' VAEntrypointEncSlice; then
  LP=(-low_power 1)
fi
say "h264_vaapi mode: ${LP[*]:-full (EncSlice)}"
va_enc() { # va_enc NAME CODEC NOTE OUT -- input + filter arguments
  local name=$1 codec=$2 note=$3 out=$4
  shift 5
  run "$name" "$note, CBR" "$out" -- "$@" -c:v "$codec" "${LP[@]}" -rc_mode CBR -b:v "${BITRATE}" \
    -maxrate "${BITRATE}" -g 300 -f mp4 "$out" \
  || run "${name}_vbr" "$note, VBR (CBR refused)" "$out" -- "$@" -c:v "$codec" "${LP[@]}" \
       -rc_mode VBR -b:v "${BITRATE}" -maxrate "${BITRATE}" -g 300 -f mp4 "$out" || true
}
va_enc enc_h264_vaapi h264_vaapi "h264_vaapi, hwupload of system-memory NV12" "$WORK/vah264.mp4" -- \
  "${HW[@]}" "${RAW_NV12[@]}" -vf format=nv12,hwupload
va_enc enc_h264_vaapi_transcode h264_vaapi "VA decode -> h264_vaapi, all on the GPU (clip input)" \
  "$WORK/vatrans.mp4" -- "${HWDEC[@]}" -i "$CLIP"
run upload_nv12 "baseline: hwupload of the NV12 only, no encode" - -- "${HW[@]}" "${RAW_NV12[@]}" \
  -vf format=nv12,hwupload -f null - || true
REF=(-stream_loop "${LOOPS}" -f rawvideo -pix_fmt nv12 -s "${W}x${H}" -r "${FPS}" -i "${NV12}")
psnr_of enc_x264_ultrafast "$WORK/x264.mp4" -- "${REF[@]}"
psnr_of enc_h264_vaapi "$WORK/vah264.mp4" -- "${REF[@]}"
psnr_of enc_h264_vaapi_transcode "$WORK/vatrans.mp4" -- -i "$CLIP"
rm -f "$WORK/x264t1.mp4" "$WORK/vatrans.mp4"

section "c) HEVC and AV1 encode via VA-API (when vainfo lists them)"
codec_mode() { # LP when only the low-power entrypoint is there
  if lists "$1" VAEntrypointEncSliceLP && ! lists "$1" VAEntrypointEncSlice; then
    echo lp
  elif lists "$1" VAEntrypointEncSlice; then
    echo full
  else
    echo none
  fi
}
for pair in "hevc_vaapi:VAProfileHEVCMain" "av1_vaapi:VAProfileAV1Profile0"; do
  codec=${pair%%:*}
  profile=${pair#*:}
  mode=$(codec_mode "$profile")
  say "$codec: vainfo $profile -> $mode"
  [[ "$mode" == none ]] && continue
  LP=()
  [[ "$mode" == lp ]] && LP=(-low_power 1)
  va_enc "enc_${codec}" "$codec" "$codec, hwupload of system-memory NV12" "$WORK/$codec.mp4" -- \
    "${HW[@]}" "${RAW_NV12[@]}" -vf format=nv12,hwupload
  psnr_of "enc_${codec}" "$WORK/$codec.mp4" -- "${REF[@]}"
  rm -f "$WORK/$codec.mp4"
done
# the CPU side of c), when this ffmpeg has the encoders
if has_encoder libx265; then
  run enc_x265_ultrafast "libx265 ultrafast zerolatency, default threads" "$WORK/x265.mp4" -- \
    "${RAW_NV12[@]}" -c:v libx265 -preset ultrafast -tune zerolatency -b:v "${BITRATE}" \
    -g 300 -f mp4 "$WORK/x265.mp4" || true
  psnr_of enc_x265_ultrafast "$WORK/x265.mp4" -- "${REF[@]}"
  rm -f "$WORK/x265.mp4"
else
  say "libx265 not in this ffmpeg: no CPU HEVC run"
fi
if has_encoder libsvtav1; then
  run enc_svtav1_p12 "libsvtav1 preset 12 (its fastest), default threads" "$WORK/svt.mp4" -- \
    "${RAW_NV12[@]}" -c:v libsvtav1 -preset 12 -b:v "${BITRATE}" -g 300 -f mp4 "$WORK/svt.mp4" \
    || true
  psnr_of enc_svtav1_p12 "$WORK/svt.mp4" -- "${REF[@]}"
  rm -f "$WORK/svt.mp4"
else
  say "libsvtav1 not in this ffmpeg: no CPU AV1 run"
fi
rm -f "$WORK/x264.mp4" "$WORK/vah264.mp4"

section "d) JPEG of ${W}x${H} frames: CPU mjpeg vs mjpeg_vaapi (quality 80)"
say "RANGE source_nv12 frame0 $(yuv_stats -f rawvideo -pix_fmt nv12 -s "${W}x${H}" -i "$NV12")"
run raw_read_bgra "baseline: read + loop the raw BGRA, no encode" - -- "${RAW_BGRA[@]}" -f null - || true
cpu_jpeg() { # cpu_jpeg NAME THREADS NOTE
  local name=$1 threads=$2 note=$3 out=$WORK/$1.mjpeg
  run "$name" "$note" "$out" -- "${RAW_BGRA[@]}" -threads "$threads" -c:v mjpeg -q:v 5 \
    -pix_fmt yuvj420p -f mjpeg "$out" \
  || run "$name" "$note, yuv420p + full range" "$out" -- "${RAW_BGRA[@]}" -threads "$threads" \
       -c:v mjpeg -q:v 5 -pix_fmt yuv420p -color_range pc -strict unofficial -f mjpeg "$out" || true
}
cpu_jpeg jpeg_cpu_t1 1 "ffmpeg mjpeg q:v 5 from BGRA (swscale to 4:2:0 + encode), 1 thread"
cpu_jpeg jpeg_cpu_auto 0 "ffmpeg mjpeg q:v 5 from BGRA, default threads"
REFB=(-stream_loop "${LOOPS}" -f rawvideo -pix_fmt bgra -s "${W}x${H}" -r "${FPS}" -i "${BGRA}")
psnr_of jpeg_cpu_t1 "$WORK/jpeg_cpu_t1.mjpeg" -- "${REFB[@]}"
range_check jpeg_cpu_t1 "$WORK/jpeg_cpu_t1.mjpeg"
rm -f "$WORK"/jpeg_cpu_*.mjpeg
run upload_bgra_vpp "baseline: hwupload BGRA + scale_vaapi to NV12 on the GPU, no encode" - -- \
  "${HW[@]}" "${RAW_BGRA[@]}" -vf format=bgra,hwupload,scale_vaapi=format=nv12 -f null - || true
va_jpeg() { # va_jpeg NAME FILTER NOTE [extra encoder options]
  local name=$1 filter=$2 note=$3 out=$WORK/$1.mjpeg
  shift 3
  run "$name" "$note" "$out" -- "${HW[@]}" "${RAW_BGRA[@]}" -vf "$filter" -c:v mjpeg_vaapi \
    -global_quality 80 "$@" -f mjpeg "$out" || true
}
if lists VAProfileJPEGBaseline VAEntrypointEncPicture; then
  va_jpeg jpeg_va_gpuconv "format=bgra,hwupload,scale_vaapi=format=nv12" \
    "BGRA upload + GPU colour convert + mjpeg_vaapi q80 (pipelined)"
  psnr_of jpeg_va_gpuconv "$WORK/jpeg_va_gpuconv.mjpeg" -- "${REFB[@]}"
  range_check jpeg_va_gpuconv "$WORK/jpeg_va_gpuconv.mjpeg"
  va_jpeg jpeg_va_gpuconv_ad1 "format=bgra,hwupload,scale_vaapi=format=nv12" \
    "the same, -async_depth 1 (one frame in flight: latency-like)" -async_depth 1
  # JFIF is full-range BT.601: run 1's GPU-converted JPEGs scored 27.8 dB (a range mismatch?)
  va_jpeg jpeg_va_gpuconv_full \
    "format=bgra,hwupload,scale_vaapi=format=nv12:out_range=full:out_color_matrix=bt470bg" \
    "BGRA upload + GPU convert to FULL-range BT.601 NV12 + mjpeg_vaapi q80"
  psnr_of jpeg_va_gpuconv_full "$WORK/jpeg_va_gpuconv_full.mjpeg" -- "${REFB[@]}"
  va_jpeg jpeg_va_cpuconv "format=nv12,hwupload" \
    "swscale BGRA->NV12 on the CPU + upload + mjpeg_vaapi q80"
  psnr_of jpeg_va_cpuconv "$WORK/jpeg_va_cpuconv.mjpeg" -- "${REFB[@]}"
  range_check jpeg_va_cpuconv "$WORK/jpeg_va_cpuconv.mjpeg"
  va_jpeg jpeg_va_cpuconv_full "scale=out_color_matrix=bt601:out_range=full,format=nv12,hwupload" \
    "swscale BGRA->FULL-range BT.601 NV12 on the CPU + upload + mjpeg_vaapi q80"
  psnr_of jpeg_va_cpuconv_full "$WORK/jpeg_va_cpuconv_full.mjpeg" -- "${REFB[@]}"
  run jpeg_va_nv12 "NV12 already in RAM: upload + mjpeg_vaapi q80" "$WORK/jpeg_va_nv12.mjpeg" -- \
    "${HW[@]}" "${RAW_NV12[@]}" -vf format=nv12,hwupload -c:v mjpeg_vaapi -global_quality 80 \
    -f mjpeg "$WORK/jpeg_va_nv12.mjpeg" || true
  range_check jpeg_va_nv12 "$WORK/jpeg_va_nv12.mjpeg"
  rm -f "$WORK"/jpeg_va_*.mjpeg
else
  say "vainfo lists no VAProfileJPEGBaseline / VAEntrypointEncPicture: no mjpeg_vaapi run"
fi

section "media probe end"
rm -rf "$WORK"
say "done; /tmp cleaned"
