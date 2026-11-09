#!/usr/bin/env bash
# THE RECORDING ENCODER SIDECAR, container side (docs/planning/gpu-recording.md 9.1; built for
# stage 2, the side-by-side check, and since stage 3 -- ADR-0024, Batt 2026-11-09 -- the encoder
# of every RDP recording: the video holds the frames). Runs in the media-probe IMAGE as the
# long-lived compose service
# `media-rec` (profile mediarec; tests/test_guards.py pins it): no network, a read-only root, the
# render node only, user 1000, exactly two data binds:
#   /ctl  the host's /dev/shm/poring-lab-mediarec (RAM): the job file, the frame pipe, status files
#   /rec  the host's ~/poring-lab-rec/.media-rec (the local disk): the bitstream, written
#         sequentially; dot-named, so dataset_ship never lists it
# Started and removed ONLY by guarded_build.py (start:media-rec@60, rm:media-rec); between the two
# it idles here, waiting for a job.
#
# One job at a time; the host side is scripts/media_rec.py VideoFeed (record_session.py --backend
# rdp: the default format vpp-hevc444-10-q20, or with --also-png stage 2's PNG twin beside it):
#   /ctl/job               "start <session id> <width> <height> <max bytes>" (the host, atomically)
#   /ctl/frames.fifo       the named pipe the host feeds: raw BGRA, width x height x 4 bytes a frame
#   /ctl/running           SID=<id> while its ffmpeg runs (this script is its only writer)
#   /ctl/done-<id>         SID / RC / BYTES / ENDED / NOTE lines once the job ends (atomically)
#   /rec/.<id>.hevc        the HEVC elementary stream; the host renames it into the session
#   /rec/.<id>.ffmpeg.log  ffmpeg's log (no per-frame lines: a stats line every 60 s)
# The host closing its end of the pipe is the end of the session: ffmpeg reads end-of-file,
# finishes the stream and exits. A stop of the container (SIGTERM) ends a running job the same way
# (SIGINT to ffmpeg: it finishes the stream). An all-intra elementary stream needs no trailer: a
# cut stream still decodes up to its cut.
#
# The encoder is round 3's CANDIDATE, exactly (gpu_rec_bench.ARMS "vpp-hevc444-10-q20", doc 8.4;
# test_media_rec.py pins every option to the bench's): the BGRA frame uploaded, scale_vaapi to
# 10-bit 4:4:4 (xv30) with BT.709, FULL range and the primaries / transfer named (doc 8.1), then
# hevc_vaapi low-power, RExt (Main 4:4:4 10), CQP 20, every frame an IDR, access unit delimiters,
# the stream tagged BT.709 pc. The input is raw BGRA from the pipe at a nominal 1 fps (the frame
# index matches the PNG twin: video.idx.csv; -fps_mode passthrough keeps one output frame per input
# frame). Nothing of the job's text reaches ffmpeg but the four checked fields.
set -uo pipefail

CTL=${MEDIAREC_CTL:-/ctl}     # the overrides exist for the host-side stub test only
REC=${MEDIAREC_REC:-/rec}     # (test_media_rec); the compose service sets no environment
DEV=${PROBE_DEVICE:-/dev/dri/renderD128}
POLL=${MEDIAREC_POLL:-0.5}           # s between looks for a job
OPEN_WAIT=${MEDIAREC_OPEN_WAIT:-60}  # s: no output by then = the host never opened its end
FIFO="$CTL/frames.fifo"
RUNNING_NAME=running
VPP="out_color_matrix=bt709:out_range=full:out_color_primaries=bt709:out_color_transfer=bt709"
SW=xv30
ENC=(-c:v hevc_vaapi -low_power 1 -profile:v rext -rc_mode CQP -qp 20 -g 1 -bf 0 -aud 1)
TAGS=(-color_range pc -colorspace bt709 -color_primaries bt709 -color_trc bt709)
# the session id record_session makes for an rdp recording (media_rec.SID_RE / JOB_RE)
JOB_RE='^start ([0-9]{8}T[0-9]{6}-rdp-[A-Za-z0-9_.-]{1,64}) ([1-9][0-9]{1,4}) ([1-9][0-9]{1,4}) ([1-9][0-9]{0,12})$'

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
say() { printf '%s mediarec: %s\n' "$(ts)" "$*"; } # the container's log (docker logs)
STOP=0
FFPID=""
on_term() {
  STOP=1
  [[ -n "$FFPID" ]] && kill -INT "$FFPID" 2>/dev/null
  return 0
}
trap on_term TERM INT

nap() { # SECONDS: a sleep the TERM trap can interrupt
  sleep "$1" &
  wait $! 2>/dev/null
  return 0
}

finish_job() { # SID RC NOTE
  local sid=$1 rc=$2 note=${3//[^A-Za-z0-9 ._:=-]/_} bytes=0 tmp="$CTL/.done-$1.tmp"
  [[ -f "$REC/.$sid.hevc" ]] && bytes=$(stat -c %s "$REC/.$sid.hevc")
  printf 'SID=%s\nRC=%s\nBYTES=%s\nENDED=%s\nNOTE=%s\n' "$sid" "$rc" "$bytes" "$(ts)" "$note" \
    >"$tmp"
  rm -f "$CTL/$RUNNING_NAME" # first: a done file always means nothing runs
  mv -f "$tmp" "$CTL/done-$sid"
  say "job $sid ended: rc=$rc bytes=$bytes ($note)"
}

run_job() { # SID W H MAX
  local sid=$1 w=$2 h=$3 max=$4 part="$REC/.$1.hevc" log="$REC/.$1.ffmpeg.log" rc=0 i
  if [[ ! -p "$FIFO" ]]; then
    finish_job "$sid" 2 "refused: no frame pipe"
    return
  fi
  if [[ -e "$part" || -e "$log" ]]; then
    finish_job "$sid" 2 "refused: its output exists"
    return
  fi
  printf 'SID=%s\n' "$sid" >"$CTL/.running.tmp" && mv -f "$CTL/.running.tmp" "$CTL/$RUNNING_NAME"
  say "job $sid: ${w}x${h} BGRA in, at most $max bytes out"
  ffmpeg -hide_banner -nostdin -n -loglevel info -stats_period 60 \
    -init_hw_device "vaapi=va:${DEV}" -filter_hw_device va \
    -f rawvideo -pix_fmt bgra -video_size "${w}x${h}" -framerate 1 -i "$FIFO" \
    -vf "format=bgra,hwupload,scale_vaapi=${VPP}:format=${SW}" -fps_mode passthrough \
    "${ENC[@]}" "${TAGS[@]}" -fs "$max" -f hevc "$part" </dev/null >"$log" 2>&1 &
  FFPID=$!
  # ffmpeg's open of the pipe waits for the host's end (a signal does not end that wait). If no
  # output appears in OPEN_WAIT s, or the container is stopping first, the host never opened it (or
  # died first): open and close a writer here, so ffmpeg reads end-of-file and the job ends instead
  # of waiting for ever. With the host's end open this does nothing (no bytes are written, and the
  # host's writer keeps the pipe open).
  for ((i = 0; i < OPEN_WAIT * 2 && STOP == 0; i++)); do
    [[ -e "$part" ]] && break
    kill -0 "$FFPID" 2>/dev/null || break
    nap 0.5
  done
  if [[ ! -e "$part" ]] && kill -0 "$FFPID" 2>/dev/null; then
    say "job $sid: no output yet (stop=$STOP): a writer opened and closed (ends it if the host never came)"
    timeout 5 bash -c ': >"$1"' _ "$FIFO" || true
  fi
  rc=0
  wait "$FFPID" || rc=$?
  while kill -0 "$FFPID" 2>/dev/null; do # a trapped signal interrupted the wait: ffmpeg finishes
    rc=0
    wait "$FFPID" || rc=$?
  done
  FFPID=""
  finish_job "$sid" "$rc" "ffmpeg exit"
}

[[ -d "$CTL" && -w "$CTL" ]] || { say "FATAL $CTL is not a writable directory"; exit 1; }
[[ -d "$REC" && -w "$REC" ]] || { say "FATAL $REC is not a writable directory"; exit 1; }
# nothing runs at this start, so a job left from before is never taken (its host has timed out)
rm -f "$CTL/job" "$CTL/$RUNNING_NAME" "$CTL/.running.tmp"
say "ready: $(ffmpeg -hide_banner -version 2>&1 | head -1); user $(id -u):$(id -g); dri: $(ls /dev/dri 2>/dev/null | tr '\n' ' ')"
while ((STOP == 0)); do
  if [[ -f "$CTL/job" && ! -L "$CTL/job" ]]; then
    line=$(head -c 256 "$CTL/job")
    rm -f "$CTL/job"
    if [[ "$line" =~ $JOB_RE ]]; then
      run_job "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}" "${BASH_REMATCH[3]}" "${BASH_REMATCH[4]}"
    else
      say "refused a malformed job (${#line} bytes)" # no trusted id to answer: the host times out
    fi
  fi
  nap "$POLL"
done
say "stopped"
