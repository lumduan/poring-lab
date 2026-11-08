#!/usr/bin/env bash
# The GPU RECORDING BENCH, container side (docs/planning/gpu-recording.md section 7; its bars
# PRE-REGISTERED 2026-11-08 before any number existed). Runs in the media-probe IMAGE as the
# one-shot compose service `media-recbench` (profile recbench; tests/test_guards.py pins it):
# no network, a read-only root, the render node only, /in read-only, /out the only writable path
# (both under the host's /dev/shm/poring-lab-recbench, RAM), user 1000.
#
# Input (written by scripts/gpu_rec_bench.py sample):
#   /in/arms.tsv                       the arms, one per line (Arm's fields, args last)
#   /in/timing_reps                    encode timing passes per arm (absent: 1, round 1's)
#   /in/<sample>/{kind,fps,size,map}   ref (PNG sessions, 1 fps) or motion (30 / 10 / 5 fps)
#   /in/<sample>/r<k>/NNNNNN.png       contiguous runs of real lab frames (the recorder's PNGs)
# Output (read by scripts/gpu_rec_bench.py score):
#   /out/status.tsv    arm sample run status bytes note   (ok | unavailable | failed | skipped)
#   /out/timing.tsv    name frames rtime utime stime status note   (ffmpeg -benchmark)
#   /out/enc/<sample>/<arm>/<run>.<ext>        every encoded run (and the raw ctl frames)
#   /out/md5/<sample>/<arm>/<run>.{va,sw}.md5  the VA-API and the software decoder's frame md5s
#   /out/vainfo*.txt, /out/help-*.txt, /out/packages.txt, /out/results.txt, /out/logs/*.log
#
# The colour convention (gpu_rec_bench.COLOR): BGR -> YUV by swscale with BT.709, FULL range, the
# streams tagged so; the host inverts it with the same matrix and range. The ctl arms measure that
# round trip alone (bar V1). An arm may DECLARE a limited range instead (its color_range field, tv:
# the stream's tag and the host's inverse follow it). vpp / gctl arms convert on the GPU with
# scale_vaapi and the arm's own options (its vpp field); gctl downloads the GPU's YUV planes raw
# (round 2, doc 6.6). Round 3 (doc 6.7): the upload field names the software format uploaded before
# scale_vaapi ("-" = bgra, rounds 1 and 2's; bgr0 = the same bytes without alpha), and the timing
# input is declared in it; a 10-bit arm uploads BGRA and writes xv30 (VA's Y410). Every ffmpeg runs
# with -nostdin; its log goes to /out/logs.
set -euo pipefail

IN=${RECBENCH_IN:-/in}   # the overrides exist for the host-side stub test only (test_gpu_rec_bench);
OUT=${RECBENCH_OUT:-/out} # the compose service sets no environment at all (test_guards)
DEV=${PROBE_DEVICE:-/dev/dri/renderD128}
OUT_CAP=${RECBENCH_OUT_CAP:-1200000000} # gpu_rec_bench.OUT_CAP: the container is charged for /out
TFRAMES=30                              # raw BGRA frames kept in /tmp for the timing pass
TLOOPS=19                               # looped to 600 frames
CONV="scale=out_color_matrix=bt709:out_range=full:flags=accurate_rnd"
FF=(ffmpeg -hide_banner -nostdin -y)
HW=(-init_hw_device "vaapi=va:${DEV}" -filter_hw_device va)
HWDEC=(-hwaccel vaapi -hwaccel_device "${DEV}" -hwaccel_output_format vaapi)

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
# the stream's colour tags: the arm's declared range (pc | tv), always BT.709
tags() { TAGS=(-color_range "$1" -colorspace bt709 -color_primaries bt709 -color_trc bt709); }
say() { printf '%s %s\n' "$(ts)" "$*" | tee -a "$OUT/results.txt"; }
status() { printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$@" >>"$OUT/status.tsv"; } # arm sample run st bytes note
die() { say "FATAL $*"; exit 1; }
LAST_ERR=""

[[ -f "$IN/arms.tsv" ]] || die "no $IN/arms.tsv (run gpu_rec_bench.py sample first)"
[[ -z "$(ls -A "$OUT")" ]] || die "$OUT is not empty: a fresh run needs a fresh directory"
mkdir -p "$OUT/logs" "$OUT/enc" "$OUT/md5"
: >"$OUT/status.tsv"
: >"$OUT/timing.tsv"

# --- capabilities: the questions the design leaves to this run ------------------------------------
say "recbench start: $(uname -r), $(nproc) cpus, user $(id -u):$(id -g), dri: $(ls /dev/dri | tr '\n' ' ')"
say "cgroup memory.max $(cat /sys/fs/cgroup/memory.max 2>/dev/null || echo n/a)"
ffmpeg -hide_banner -version | head -1 | tee -a "$OUT/results.txt"
cp /opt/probe-packages.txt "$OUT/packages.txt" 2>/dev/null || say "no /opt/probe-packages.txt"
vainfo --display drm --device "$DEV" >"$OUT/vainfo.txt" 2>&1 || say "vainfo FAILED"
vainfo --display drm --device "$DEV" -a >"$OUT/vainfo-all.txt" 2>&1 || say "vainfo -a FAILED"
for c in h264_vaapi hevc_vaapi av1_vaapi; do
  ffmpeg -hide_banner -h "encoder=$c" >"$OUT/help-$c.txt" 2>&1 || true
done
ffmpeg -hide_banner -h filter=scale_vaapi >"$OUT/help-scale_vaapi.txt" 2>&1 || true
TREPS=1 # encode timing passes per arm (gpu_rec_bench.TIMING_REPS; the median is graded)
[[ -s "$IN/timing_reps" ]] && TREPS=$(tr -d '[:space:]' <"$IN/timing_reps")
[[ "$TREPS" =~ ^[1-9]$ ]] || die "timing_reps: '$TREPS' is not 1..9"
grep -E 'VAProfile.*VAEntrypointEnc' "$OUT/vainfo.txt" | sed 's/^/    /' | tee -a "$OUT/results.txt" || true
has_profile() { [[ "$1" == "-" ]] || grep -qE "^[[:space:]]*$1[[:space:]]*:[[:space:]]*VAEntrypointEncSliceLP[[:space:]]*\$" "$OUT/vainfo.txt"; }
out_used() { du -sb "$OUT" | cut -f1; }

# ffmpeg -benchmark parse (as services/media-probe/probe.sh's run): one timing.tsv row
timed() { # NAME NOTE -- ffmpeg arguments
  local name=$1 note=$2 log="$OUT/logs/t-$1.log" rc=0
  shift 3
  "${FF[@]}" -benchmark "$@" >"$log" 2>&1 || rc=$?
  local frames u s r
  frames=$(tr '\r' '\n' <"$log" | grep -oE 'frame= *[0-9]+' | tail -1 | grep -oE '[0-9]+' || true)
  u=$(grep -oE 'utime=[0-9.]+' "$log" | tail -1 | cut -d= -f2 || true)
  s=$(grep -oE 'stime=[0-9.]+' "$log" | tail -1 | cut -d= -f2 || true)
  r=$(grep -oE 'rtime=[0-9.]+' "$log" | tail -1 | cut -d= -f2 || true)
  local st=ok
  ((rc == 0)) || st=failed
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$name" "${frames:-0}" "${r:-0}" "${u:-0}" "${s:-0}" \
    "$st" "$note rc=$rc" >>"$OUT/timing.tsv"
  say "TIMING $name $st frames=${frames:-0} rtime=${r:-0} utime=${u:-0} stime=${s:-0} ($note)"
  return "$rc"
}

# encode one run: ARM-fields... SAMPLE RUN FPS. SW may list alternatives ("vuyx|vuya"): the
# first that encodes is used, and remembered for the timing pass ($OUT/logs/fmt-<arm>).
encode_run() {
  local name=$1 mode=$2 codec=$3 sws=$4 frames=$5 ext=$6 mux=$7 args=$8 s=$9 r=${10} fps=${11}
  local vpp=${12} crange=${13} up=${14}
  local sw rc=1
  local -a alts
  IFS='|' read -r -a alts <<<"$sws"
  for sw in "${alts[@]}"; do
    rc=0
    encode_fmt "$name" "$mode" "$codec" "$sw" "$frames" "$ext" "$mux" "$args" "$s" "$r" "$fps" \
      "$vpp" "$crange" "$up" || rc=$?
    if ((rc == 0)); then
      echo "$sw" >"$OUT/logs/fmt-$name"
      [[ "$sw" == "${alts[0]}" ]] || say "NOTE $name: upload format $sw, not ${alts[0]}"
      return 0
    fi
  done
  status "$name" "$s" "$r" failed 0 "$LAST_ERR"
  return "$rc"
}

encode_fmt() {
  local name=$1 mode=$2 codec=$3 sw=$4 frames=$5 ext=$6 mux=$7 args=$8 s=$9 r=${10} fps=${11}
  local vpp=${12} crange=${13} up=${14}
  local upf=bgra # what is uploaded before scale_vaapi (vpp / gctl): the arm's upload, "-" = bgra
  [[ "$up" == "-" ]] || upf=$up
  local dir="$OUT/enc/$s/$name" in="$IN/$s/$r/%06d.png" log="$OUT/logs/e-$s-$name-$r.log"
  local out="$dir/$r.$ext" lim=() rc=0
  mkdir -p "$dir"
  rm -f "$out"
  ((frames > 0)) && lim=(-frames:v "$frames")
  local src=(-framerate "$fps" -start_number 0 -i "$in")
  tags "$crange"
  case "$mode" in
    ctl)
      "${FF[@]}" "${src[@]}" -vf "$CONV,format=$sw" "${lim[@]}" -f rawvideo -pix_fmt "$sw" \
        "$out" >"$log" 2>&1 || rc=$? ;;
    gctl)
      # the GPU's conversion alone: BGRA (or the arm's upload) up, scale_vaapi, the planes down, raw
      "${FF[@]}" "${HW[@]}" "${src[@]}" \
        -vf "format=$upf,hwupload,scale_vaapi=$vpp:format=$sw,hwdownload,format=$sw" "${lim[@]}" \
        -f rawvideo -pix_fmt "$sw" "$out" >"$log" 2>&1 || rc=$? ;;
    vpp)
      # shellcheck disable=SC2086 # $args is the arm's option list, split on purpose
      "${FF[@]}" "${HW[@]}" "${src[@]}" -vf "format=$upf,hwupload,scale_vaapi=$vpp:format=$sw" \
        "${lim[@]}" -fps_mode passthrough -c:v "$codec" -low_power 1 $args "${TAGS[@]}" \
        -f "$mux" "$out" >"$log" 2>&1 || rc=$? ;;
    *)
      # shellcheck disable=SC2086
      "${FF[@]}" "${HW[@]}" "${src[@]}" -vf "$CONV,format=$sw,hwupload" "${lim[@]}" \
        -fps_mode passthrough -c:v "$codec" -low_power 1 $args "${TAGS[@]}" -f "$mux" "$out" \
        >"$log" 2>&1 || rc=$? ;;
  esac
  if ((rc != 0)) || [[ ! -s "$out" ]]; then
    # the caller records it once every alternative has failed (encode_run)
    LAST_ERR="$sw rc=$rc: $(tr '\r' '\n' <"$log" | grep -v '^\s*$' | tail -n 2 | tr '\t\n' '  ')"
    rm -f "$out"
    return 1
  fi
  status "$name" "$s" "$r" ok "$(stat -c %s "$out")" "$sw"
}

# the two decoders' frame md5s of one run, in the arm's planar format (bar D2)
md5_run() { # NAME DL PLANE EXT SAMPLE RUN
  local name=$1 dl=$2 plane=$3 ext=$4 s=$5 r=$6
  local f="$OUT/enc/$s/$name/$r.$ext" dir="$OUT/md5/$s/$name"
  mkdir -p "$dir"
  local fmt ok=0
  for fmt in "$dl" vuyx vuya xv30 nv12; do
    if "${FF[@]}" "${HWDEC[@]}" -i "$f" -vf "hwdownload,format=$fmt,format=$plane" -f framemd5 \
         "$dir/$r.va.md5" >"$OUT/logs/m-$s-$name-$r-va.log" 2>&1; then
      ok=1
      [[ "$fmt" == "$dl" ]] || say "NOTE $name: VA download format $fmt, not $dl"
      break
    fi
  done
  ((ok)) || { rm -f "$dir/$r.va.md5"; say "MD5 $name $s $r VA decode FAILED"; }
  "${FF[@]}" -threads 1 -i "$f" -vf "format=$plane" -f framemd5 "$dir/$r.sw.md5" \
    >"$OUT/logs/m-$s-$name-$r-sw.log" 2>&1 || { rm -f "$dir/$r.sw.md5"; say "MD5 $name $s $r SW decode FAILED"; }
}

SAMPLES=()
for d in "$IN"/*/; do SAMPLES+=("$(basename "$d")"); done
REFS=()
for s in "${SAMPLES[@]}"; do [[ "$(cat "$IN/$s/kind")" == ref ]] && REFS+=("$s"); done
((${#REFS[@]})) || die "no ref sample in $IN"
say "samples: ${SAMPLES[*]} (ref: ${REFS[*]})"

# --- 1. every arm on every sample it names, in the table's order -----------------------------------
while IFS=$'\t' read -r -u 3 name mode codec sw dl plane prof samples timing ext mux frames vpp \
  crange up args; do
  [[ -z "$name" || "$name" == \#* ]] && continue
  for s in "${SAMPLES[@]}"; do
    kind=$(cat "$IN/$s/kind")
    [[ "$samples" == all || "$samples" == "$kind" ]] || continue
    for rd in "$IN/$s"/r*/; do
      r=$(basename "$rd")
      if ! has_profile "$prof"; then
        status "$name" "$s" "$r" unavailable 0 "vainfo lists no $prof with VAEntrypointEncSliceLP"
        continue
      fi
      if (($(out_used) > OUT_CAP)); then
        status "$name" "$s" "$r" skipped 0 "out_cap $OUT_CAP reached"
        continue
      fi
      encode_run "$name" "$mode" "$codec" "$sw" "$frames" "$ext" "$mux" "$args" "$s" "$r" \
        "$(cat "$IN/$s/fps")" "$vpp" "$crange" "$up" || true
      if [[ ("$mode" == intra || "$mode" == vpp) && "$kind" == ref && -s "$OUT/enc/$s/$name/$r.$ext" ]]; then
        md5_run "$name" "$dl" "$plane" "$ext" "$s" "$r"
      fi
    done
  done
  say "ARM $name done ($(grep -c "^${name}"$'\t' "$OUT/status.tsv" || true) rows; /out $(out_used) B)"
done 3<"$IN/arms.tsv"

# --- 2. timing: raw BGRA in RAM (what the recorder holds) -> encoder, 600 frames -------------------
TS=${REFS[0]}
SIZE=$(cat "$IN/$TS/size")
RAW=${TMPDIR:-/tmp}/t.bgra
"${FF[@]}" -framerate 1 -start_number 0 -i "$IN/$TS/r0/%06d.png" -frames:v "$TFRAMES" \
  -f rawvideo -pix_fmt bgra "$RAW" >"$OUT/logs/t-raw.log" 2>&1 || die "the timing input"
RAWIN=(-stream_loop "$TLOOPS" -f rawvideo -pix_fmt bgra -s "$SIZE" -r 30 -i "$RAW")
say "timing on $TS/r0: $TFRAMES frames looped to $((TFRAMES * (TLOOPS + 1)))"
timed raw_read "read + loop the raw BGRA only" -- "${RAWIN[@]}" -f null - || true
timed conv_nv12 "swscale BGRA -> NV12 (BT.709 full) only" -- "${RAWIN[@]}" -vf "$CONV,format=nv12" \
  -f null - || true
timed conv_yuv444p "swscale BGRA -> YUV 4:4:4 only" -- "${RAWIN[@]}" -vf "$CONV,format=yuv444p" \
  -f null - || true
# one encode timing pass of one arm: PASS of TREPS (the scorer grades the median of the passes)
enc_timed() { # NAME MODE CODEC SW VPP CRANGE MUX ARGS PASS UP
  local name=$1 mode=$2 codec=$3 sw=$4 vpp=$5 crange=$6 mux=$7 args=$8 pass=$9 up=${10}
  local vf="$CONV,format=$sw,hwupload" note pf=bgra
  local -a rin=("${RAWIN[@]}")
  if [[ "$mode" == vpp ]]; then
    # the same raw bytes DECLARED as the arm's upload format (bgr0: BGRA's bytes, the alpha byte
    # ignored -- what the recorder would hand over), so no CPU conversion is timed for it
    [[ "$up" == "-" ]] || pf=$up
    rin=(-stream_loop "$TLOOPS" -f rawvideo -pix_fmt "$pf" -s "$SIZE" -r 30 -i "$RAW")
    vf="format=$pf,hwupload,scale_vaapi=$vpp:format=$sw"
  fi
  note="$codec $args, $vf"
  ((TREPS == 1)) || note="$note (pass $pass/$TREPS)"
  tags "$crange"
  # shellcheck disable=SC2086
  timed "enc_$name" "$note" -- "${HW[@]}" "${rin[@]}" -vf "$vf" -fps_mode passthrough \
    -c:v "$codec" -low_power 1 $args "${TAGS[@]}" -f "$mux" /dev/null || true
}
# pass 1 of every timed arm (with its decode timings), then passes 2..TREPS round-robin over the
# arms, so a first-arm warm-up or a drift in the host's load does not land on one arm alone
for ((pass = 1; pass <= TREPS; pass++)); do
  while IFS=$'\t' read -r -u 3 name mode codec sw dl plane prof samples timing ext mux frames vpp \
    crange up args; do
    [[ -z "$name" || "$name" == \#* || "$timing" != 1 ]] && continue
    has_profile "$prof" || continue
    [[ -s "$OUT/logs/fmt-$name" ]] || continue # it never encoded in the quality pass
    sw=$(cat "$OUT/logs/fmt-$name")
    enc_timed "$name" "$mode" "$codec" "$sw" "$vpp" "$crange" "$mux" "$args" "$pass" "$up"
    ((pass == 1)) || continue
    f="$OUT/enc/$TS/$name/r0.$ext"
    [[ -s "$f" ]] || continue
    timed "dec_va_$name" "VA-API decode + download $dl (loop x12)" -- -stream_loop 11 "${HWDEC[@]}" \
      -i "$f" -vf "hwdownload,format=$dl" -f null - \
    || timed "dec_va_$name" "VA-API decode + download $dl (no loop)" -- "${HWDEC[@]}" -i "$f" \
         -vf "hwdownload,format=$dl" -f null - || true
    timed "dec_sw_$name" "software decode, 1 thread (loop x12)" -- -threads 1 -stream_loop 11 \
      -i "$f" -f null - \
    || timed "dec_sw_$name" "software decode, 1 thread (no loop)" -- -threads 1 -i "$f" -f null - \
    || true
  done 3<"$IN/arms.tsv"
done
rm -f "$RAW"

say "recbench end: /out $(out_used) B; $(grep -c $'\tok\t' "$OUT/status.tsv" || true) runs ok, $(grep -c $'\tfailed\t' "$OUT/status.tsv" || true) failed, $(grep -c $'\tunavailable\t' "$OUT/status.tsv" || true) unavailable, $(grep -c $'\tskipped\t' "$OUT/status.tsv" || true) skipped"
