#!/usr/bin/env bash
# Wrapper around the voice prompt daemon.
# So the same command starts it from any project.
#
#   voice-shell.sh start [--engine X] [--no-gui]
#   voice-shell.sh stop
#   voice-shell.sh status
#   voice-shell.sh viewer / viewer-stop
#   voice-shell.sh log-path / wait-ready
#   voice-shell.sh listen                 tail the utterance log (for Monitor, shaped so double starts show)
#   voice-shell.sh codex-forward          send new utterances to this Codex App Server thread
#   voice-shell.sh engines                the ways of recognizing on offer, and the last choice
#   voice-shell.sh listeners              the sessions listening right now
#   voice-shell.sh name "NAME"            give this session a display name
#   voice-shell.sh whisper                recognize with Whisper (strong on proper nouns)
#   voice-shell.sh apple                  run on the recognition that ships with macOS 26 (light)

set -euo pipefail

# Everything is relative to where the script itself sits (even through a symlink, follow to the real file)
HERE="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"

# Git Bash (Windows) has no pgrep/pkill/setsid. When they are missing, give up
# on the feature and let it pass through (only the process check and the double
# start check stop working, starting and stopping themselves still do).
have() { command -v "$1" >/dev/null 2>&1; }

# Python on Windows uses the system locale for file I/O by default (cp932 on a
# Japanese install). It tries to open JSON and logs written as UTF-8 with cp932
# and dies with UnicodeDecodeError, so force UTF-8 mode (PEP 540).
# Harmless on macOS / Linux (already UTF-8, so nothing changes).
export PYTHONUTF8=1

# Look for a Python environment. VOICE_SHELL_PYTHON names one explicitly.
find_python() {
  if [[ -n "${VOICE_SHELL_PYTHON:-}" ]]; then echo "$VOICE_SHELL_PYTHON"; return; fi
  # .venv at the top of the repo (a setup without conda, the standard one on macOS)
  if [[ -x "$HERE/../../../.venv/bin/python" ]]; then
    echo "$HERE/../../../.venv/bin/python"; return
  fi
  # A venv on Windows keeps it in Scripts/python.exe, not bin/
  if [[ -x "$HERE/../../../.venv/Scripts/python.exe" ]]; then
    echo "$HERE/../../../.venv/Scripts/python.exe"; return
  fi
  # For people on conda / mamba. The env name matches the name of this tool.
  for base in "$HOME/miniforge3" "$HOME/miniconda3" "$HOME/anaconda3" \
              "$HOME/mambaforge" "/opt/homebrew/Caskroom/miniforge/base" "/opt/conda"; do
    [[ -x "$base/envs/voice-shell/bin/python" ]] && { echo "$base/envs/voice-shell/bin/python"; return; }
  done
  # If nothing turns up, look for a python that is enough to run this.
  #
  # The default browser recognition needs only numpy and aiohttp, no model.
  # Gating on a model here means the default, the one that should run with
  # nothing installed, cannot start on a machine without one. That really happened.
  for c in python3 python; do
    command -v "$c" >/dev/null || continue
    if "$c" -c "import numpy, aiohttp" 2>/dev/null; then
      command -v "$c"; return
    fi
  done
}

# Remember which engine was used last time. The viewer's "start listening"
# calls engine-start, and engine-start does not know the original command.
# Without the memory, whisper chosen last time loads some other model.
#
# The result goes into the array ENGINE_ARGS, not a string. A Whisper model
# can also be a folder on this machine, and that path can contain spaces.
# Make it a string, leave it to word splitting, and it breaks right there.
ENGINE_ARGS=()
set_engine_args() {
  ENGINE_ARGS=()
  # The remembered choice (~/.config/voice-shell/config.json) is the truth.
  # It used to read a file under /tmp, and when a reboot wiped that, it
  # quietly fell back to the built-in default and disagreed with config.
  local e m
  e="$("$PY" "$APP" --resolve-engine "" 2>/dev/null || true)"
  [[ -n "$e" && "$e" != "browser" ]] || return 0
  ENGINE_ARGS=(--engine "$e")
  # Whisper is the only one where a model can be picked. Passing --model
  # empty makes faster-whisper take the empty string as a model name and
  # die, so add it only when there is something remembered.
  if [[ "$e" == "whisper" ]]; then
    m="$("$PY" "$APP" --resolve-model 2>/dev/null || true)"
    [[ -n "$m" ]] && ENGINE_ARGS+=(--model "$m")
  fi
  return 0
}

PY="$(find_python || true)"
APP="$HERE/voice_daemon.py"

# Asking the viewer. curl gets turned away in some environments (it printed
# "Permission denied" on Windows). Python is always there, so knock with that.
#   http_get <path>        body to stdout. returns 1 when nothing arrives
#   port_open              only looks at whether the port is open
http_get() {
  "$PY" - "$VIEWER_URL$1" <<'HTTPGET' 2>/dev/null
import sys, urllib.request
try:
    with urllib.request.urlopen(sys.argv[1], timeout=2) as r:
        sys.stdout.write(r.read().decode("utf-8", "replace"))
except Exception:
    sys.exit(1)
HTTPGET
}

http_post() {
  "$PY" - "$VIEWER_URL$1" "$2" <<'HTTPPOST' 2>/dev/null
import sys, urllib.request
req = urllib.request.Request(sys.argv[1], data=sys.argv[2].encode("utf-8"),
                             headers={"content-type": "application/json"})
try:
    urllib.request.urlopen(req, timeout=2).read()
except Exception:
    sys.exit(1)
HTTPPOST
}

port_open() {
  "$PY" - "$PORT" <<'PORT' 2>/dev/null
import socket, sys
s = socket.socket(); s.settimeout(0.6)
sys.exit(0 if s.connect_ex(("127.0.0.1", int(sys.argv[1]))) == 0 else 1)
PORT
}

# Start a process cut loose from the caller's process tree.
# macOS has no setsid, so there we make do with nohup alone
# (the daemon only kills its direct children via pgrep -P, so that is enough).
detach() {
  if command -v setsid >/dev/null; then
    setsid nohup "$@"
  else
    nohup "$@"
  fi
}

if [[ -z "$PY" ]]; then
  echo "No Python it can run was found." >&2
  echo "  For recognizing in the browser, this much is enough." >&2
  echo "    pip install numpy aiohttp" >&2
  echo "  To recognize with a model on this machine, see SETUP.md." >&2
  echo "  To name one outright, write export VOICE_SHELL_PYTHON=/path/to/python" >&2
  exit 1
fi
if ! PORT="$("$PY" "$HERE/port_config.py")"; then
  exit 2
fi
VIEWER_URL="http://127.0.0.1:$PORT"
# Named after the recognition model once, so it was "qwen-voice". It now takes
# the name of the tool, but so nothing already running breaks, the old one stays
# in use when it is there and the new one is not (it moves once /tmp empties).
STATE_DIR="${XDG_RUNTIME_DIR:-/tmp}/voice-shell"
_legacy_state="${XDG_RUNTIME_DIR:-/tmp}/qwen-voice"
if [ ! -d "$STATE_DIR" ] && [ -d "$_legacy_state" ]; then
  STATE_DIR="$_legacy_state"
fi
LOG_FILE="$STATE_DIR/utterances.jsonl"
BOOT_LOG="$STATE_DIR/daemon.out"

# On Windows (Git Bash) the "/tmp" bash sees and the "/tmp" plain Python resolves
# on its own are different real directories (the first is the real folder MSYS
# mount-translates to, the second is C:\tmp, which pathlib puts at the drive
# root). Convert the real path settled on here into Windows form with cygpath and
# hand it explicitly to the child Python process (otherwise where the daemon
# writes and where Monitor tails drift apart, and utterances arrive nowhere).
if command -v cygpath >/dev/null 2>&1; then
  export VOICE_SHELL_STATE_DIR="$(cygpath -w "$STATE_DIR")"
fi

cmd="${1:-status}"; shift || true

# Open the viewer in a window of its own.
#
# Chrome's --app gives a window with no tabs and no URL bar, and it opens from
# the command line. To keep it always on top, float it by hand from the header of
# the window that opened (the rule is that Document Picture-in-Picture only opens
# when a person acts on it). Own window, and remember once opened. Every retype of
# start or viewer popped a new one, and 10 really lined up. One window per viewer.
open_gui() {
  local url="$VIEWER_URL"
  local flag="$STATE_DIR/gui_opened"
  mkdir -p "$STATE_DIR"
  # mkdir is one atomic filesystem call (POSIX guarantees only one caller can
  # be the one to actually create a given directory), unlike the old
  # test-for-a-file-then-create-it pair, which let two near-simultaneous
  # callers (start racing viewer's own reopen-if-nobody-is-looking check,
  # say) both see nothing there yet and both go on to open a window.
  mkdir "$flag" 2>/dev/null || return 0
  # An ordinary tab, indistinguishable from any other, not Chrome's --app mode
  # (a window with no tabs and no address bar). Opening straight into that
  # shape has been mistaken for phishing in the wild (a window with nowhere
  # to check what site it really is), and it skipped past the one press
  # floatAsk exists to ask for. A plain URL argument is enough, Chrome routes
  # it to a tab in whatever window is already open, or a new one if none is.
  case "$(uname)" in
    Darwin)
      for app in "Google Chrome" "Chromium" "Microsoft Edge"; do
        if [[ -d "/Applications/$app.app" ]]; then
          open -na "$app" --args "$url" 2>/dev/null && return 0
        fi
      done
      ;;
    *)
      for c in google-chrome chromium chromium-browser microsoft-edge; do
        if command -v "$c" >/dev/null; then
          nohup "$c" "$url" >/dev/null 2>&1 & return 0
        fi
      done
      # Windows(Git Bash)
      if command -v cmd.exe >/dev/null; then
        # "start chrome" only works if Chrome happens to be registered
        # under that exact name (an installer is supposed to set an App
        # Paths registry key for this, but not every install path does),
        # and cmd.exe's own start returns success either way regardless of
        # whether anything it tried to open actually exists. A silent
        # failure here read on screen as "listening has started" with no
        # window ever opening and no line telling anyone to open the URL
        # by hand instead (measured on a real Windows machine).
        #
        # Look for the real executable directly in the places an installer
        # puts it instead (per-machine, then the per-user one a no-admin
        # install uses), so success or failure is judged by whether the
        # file is actually there, not by what a loosely defined shell
        # built-in happens to return. The empty "" ahead of the path is
        # start's own way of saying "that quoted thing is the target, not
        # a window title", needed the moment the path itself contains a
        # space, which Program Files always does.
        win_local_appdata=""
        if [[ -n "${LOCALAPPDATA:-}" ]] && command -v cygpath >/dev/null 2>&1; then
          win_local_appdata="$(cygpath -u "$LOCALAPPDATA" 2>/dev/null || true)"
        fi
        for exe in \
          "/c/Program Files/Google/Chrome/Application/chrome.exe" \
          "/c/Program Files (x86)/Google/Chrome/Application/chrome.exe" \
          "${win_local_appdata:+$win_local_appdata/Google/Chrome/Application/chrome.exe}" \
          "/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe" \
          "/c/Program Files/Microsoft/Edge/Application/msedge.exe"
        do
          [[ -n "$exe" && -f "$exe" ]] || continue
          cmd.exe /c start "" "$(cygpath -w "$exe")" "$url" >/dev/null 2>&1 && return 0
        done
        # None of the usual install paths panned out. Try the name-based
        # form as a last resort, in case Chrome is registered under it by
        # some other means (the Microsoft Store build, for one).
        cmd.exe /c start "" chrome "$url" >/dev/null 2>&1 && return 0
      fi
      ;;
  esac
  echo "  Could not open a browser for you. Open $url" >&2
  return 1
}

# List the sessions tailing the utterance log.
#
# Forget to stop Monitor and voice keeps reaching the old session. tail is -F, so
# it reconnects even when the daemon is reinstalled, and the person cannot notice.
# A session from 8 days back really was alive, and the same utterance went out to
# two sessions. Have Python count the files `voice-shell.sh listen` registers at
# startup (under $STATE_DIR/listeners/, the filename being that listener's PID).
# Python checks life with _pid_alive and works on Windows too. Do not lean on pgrep.
list_listeners() {
  "$PY" "$APP" --listeners
}

case "$cmd" in
  start)
    # Decide which engine to use (given > last choice > automatic).
    # The last choice stays in ~/.config/voice-shell/config.json, so a
    # restart does not mean choosing all over again.
    # Look at whether this is a first run (nothing remembered yet) before resolving
    conf="${XDG_CONFIG_HOME:-$HOME/.config}/voice-shell/config.json"
    first_run=0; [[ -f "$conf" ]] || first_run=1

    want=""
    want_model=""
    model_given=0
    no_gui=0
    rest=()
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --engine) want="${2:-}"; shift 2 ;;
        --engine=*) want="${1#*=}"; shift ;;
        # Remember the Whisper model the same way as the engine. The
        # viewer's "start listening" does not know the original command, so
        # without remembering here it drops back to the default the moment
        # it is brought up again from the screen. Passed empty means back to
        # the default, so track whether it was passed apart from what it held.
        --model) want_model="${2:-}"; model_given=1; shift 2 ;;
        --model=*) want_model="${1#*=}"; model_given=1; shift ;;
        --no-gui) no_gui=1; shift ;;
        *) rest+=("$1"); shift ;;
      esac
    done
    export VOICE_SHELL_NO_GUI="$no_gui"
    set -- "${rest[@]+"${rest[@]}"}"
    engine="$("$PY" "$APP" --resolve-engine "$want")"
    "$PY" "$APP" --remember-engine "$engine"
    [[ "$model_given" == 1 ]] && "$PY" "$APP" --remember-model "$want_model"

    # Recognizing in the browser means no model has to be loaded here.
    # Bring up only the viewer and finish (opening the screen starts it).
    if [[ "$engine" == "browser" ]]; then
      mkdir -p "$STATE_DIR"
      # Same as daemon startup. Leave it and last time's utterances line up again.
      : > "$LOG_FILE"
      # Here the screen itself does the recognizing, so speak up once it is up.
      # Its own line ("The viewer started at ..." / "It is already running at
      # ...") carries the URL through to whoever is reading this output, since
      # opening a window here is not something to count on (closed by hand
      # since the last time, or nothing installed that this script knows how
      # to open) and that URL is the fallback either way.
      "$0" viewer
      # Print only whether it started and what to do next.
      # The log path and the list of other listening sessions both come from status.
      echo "Listening has started."
      echo "Open the screen in Chrome and allow the microphone, and it starts arriving."
      # On a first run only, name how this is recognizing and the stand-in this
      # machine can use. General wording stalls at "so which do I pick", so go
      # all the way to the name. Never after that. It only gets in the way.
      if [[ "$first_run" == 1 ]]; then
        echo
        echo "Note. This uses the browser's built-in speech recognition feature to transcribe your voice."
        alt="$("$PY" "$APP" --list-engines | sed -n '2p' | awk '{print $1}')"
        if [[ -n "$alt" ]]; then
          echo "   To keep it all on this machine, this one can be used here too."
          echo "     voice-shell.sh start --engine $alt"
        fi
      fi
      exit 0
    fi
    if "$PY" "$APP" --status | grep -q "^Running"; then
      echo "It is already running."; exit 0
    fi
    mkdir -p "$STATE_DIR"
    # Clear away a viewer running under the old path (left behind by a layout change)
    have pkill && pkill -f "voice-shell/scripts/viewer\.p[y]" 2>/dev/null || true
    # Pin it to Japanese. Auto detection easily hears noise as Chinese and such
    # (measured). Speaking English still follows (the commas that land between
    # words get stripped viewer side). For another main language, pass it like
    # `voice-shell.sh start --language English`. Detach with setsid, or it stays
    # in the caller's process group and dies with this script (viewer survives).
    set_engine_args
    detach "$PY" "$APP" --language Japanese "${ENGINE_ARGS[@]+"${ENGINE_ARGS[@]}"}" "$@" \
      > "$BOOT_LOG" 2>&1 &
    # Print only whether it started and what to do next.
    # The log path and the list of other listening sessions both come from status.
    # Print before the viewer. By this point the daemon is on its way, so even
    # if bringing up the screen fails, the fact that it started should land.
    echo "Listening has started."
    echo "The model takes a little while to be ready. voice-shell.sh wait-ready waits for it."
    # Bring the viewer up alongside it (so nobody has to remember to type viewer).
    # It does not use the mic, so it can run with the daemon. Drop the output.
    "$0" viewer >/dev/null
    ;;
  stop)
    "$PY" "$APP" --stop
    "$0" viewer-stop
    ;;
  engine-stop)
    # Stop only the recognition. It lets go of the mic, and with Whisper the
    # memory the model took comes back too. The viewer stays, so it can be
    # started again from the screen.
    #
    # Cut it mid speech and that whole utterance is lost. The longer someone
    # talks the easier that is, so wait for the partial to clear (--now skips it).
    if [[ "${1:-}" != "--now" ]]; then
      for _ in $(seq 1 60); do          # at most 15 seconds
        [ -s "$STATE_DIR/partial.txt" ] || break
        sleep 0.25
      done
    fi
    "$PY" "$APP" --stop 2>/dev/null || true
    # The PID file is written after loading finishes. Stop it mid startup and
    # the process is left with no file, so kill by name as well to be sure.
    if have pkill; then
      pkill -f "voice_daemon\.p[y] --language" 2>/dev/null || true
      sleep 1
      pkill -9 -f "voice_daemon\.p[y] --language" 2>/dev/null || true
    fi
    ;;
  engine-start)
    if [[ "$("$PY" "$APP" --resolve-engine "")" == "browser" ]]; then
      echo "Browser recognition is the choice. No model is loaded on this machine." >&2
      exit 0
    fi
    # Bring only the recognition back up (leave the viewer alone).
    # Detach with setsid. The daemon kills every one of its children when it
    # exits, so hanging off the caller (the viewer) gets caught in that.
    #
    # This check leans on the PID file, so it slips through during loading.
    # A double start is stopped for certain by the lock on the daemon side.
    if "$PY" "$APP" --status | grep -q "^Running"; then
      echo "It is already running."; exit 0
    fi
    mkdir -p "$STATE_DIR"
    set_engine_args
    detach "$PY" "$APP" --language Japanese "${ENGINE_ARGS[@]+"${ENGINE_ARGS[@]}"}" "$@" \
      > "$BOOT_LOG" 2>&1 &
    echo "Starting up. Loading the model takes 1 to 2 minutes"
    ;;
  whisper)
    # Use Whisper for recognition. Strong on proper nouns.
    "$0" start --engine whisper "$@"
    ;;
  apple)
    # Use the on-device recognition that ships with macOS 26. No model to load, so it starts fast.
    "$0" start --engine apple "$@"
    ;;
  status)
    # When the browser is doing the recognizing, having no daemon on this
    # machine is normal. A bare "Stopped." on its own reads as broken,
    # so say what is doing the recognizing first.
    engine="$("$PY" "$APP" --resolve-engine "")"
    if [[ "$engine" == "browser" ]]; then
      echo "This browser does the recognizing. No model is loaded on this machine"
      if ! port_open; then
        echo "  The viewer is not running. Start it with voice-shell.sh viewer" >&2
      else
        echo "  The viewer is at $VIEWER_URL"
        # Go as far as whether the screen is really listening. Without this,
        # not open or mic refused cannot be told from properly listening.
        http_get /api/asr-status \
          | "$PY" "$HERE/asr_status.py" || echo "  Could not check the state of the screen"
      fi
    else
      echo "The way of recognizing is $engine"
      "$PY" "$APP" --status
    fi
    echo
    echo "Sessions listening to this voice"
    listeners_now="$(list_listeners)"
    if [ -n "$listeners_now" ]; then echo "$listeners_now"
    else echo "  none (the voice is reaching nowhere)"; fi
    ;;
  engines)
    # The ways of recognizing on offer. Prints what is installed and what was picked last time.
    "$PY" "$APP" --list-engines
    ;;
  listeners)
    listeners_now="$(list_listeners)"
    if [ -n "$listeners_now" ]; then echo "$listeners_now"
    else echo "  none (the voice is reaching nowhere)"; fi
    ;;
  codex-forward)
    if [[ -z "${CODEX_THREAD_ID:-}" ]]; then
      echo "codex-forward needs CODEX_THREAD_ID from a Codex CLI or App Server thread." >&2
      echo "  It does not attach to an arbitrary ChatGPT desktop task." >&2
      exit 2
    fi
    mkdir -p "$STATE_DIR"
    forward_pipe="$STATE_DIR/codex-forward-$$.pipe"
    rm -f "$forward_pipe"
    mkfifo "$forward_pipe"
    "$HERE/voice-shell.sh" listen > "$forward_pipe" &
    listen_pid=$!
    trap 'rm -f "$forward_pipe"; kill "$listen_pid" 2>/dev/null || true; wait "$listen_pid" 2>/dev/null || true' EXIT INT TERM HUP
    "$PY" -u "$HERE/codex_app_server.py" --input-filtered < "$forward_pipe"
    ;;
  listen)
    # Used from Monitor. Tails the utterance log and registers its own presence
    # in $STATE_DIR/listeners/ (the filename is its own PID).
    # The daemon side (Python) checks life by treating that filename as a real
    # PID, so on Windows (Git Bash/MSYS) it uses the value in /proc/$$/winpid
    # rather than $$ ($$ is MSYS's internal virtual PID, a different thing from
    # the real Win32 PID. With plain $$ the life check always fails, and the
    # moment it registers it counts as dead and gets deleted).
    reg_pid="$$"
    [[ -r "/proc/$$/winpid" ]] && reg_pid="$(cat "/proc/$$/winpid" 2>/dev/null || echo "$$")"
    mkdir -p "$STATE_DIR/listeners"
    reg="$STATE_DIR/listeners/$reg_pid"

    # Note down which tool called this and the id of that conversation.
    # Once the conversation gets a title, the daemon pulls it in as the display
    # name (at start time not even the person knows what the work is yet).
    agent=""; session=""
    if [[ -n "${CLAUDE_CODE_SESSION_ID:-}" ]]; then
      agent="claude"; session="$CLAUDE_CODE_SESSION_ID"
    elif [[ -n "${CODEX_THREAD_ID:-}" ]]; then
      agent="codex"; session="$CODEX_THREAD_ID"
    elif [[ -n "${CODEX_SESSION_ID:-}" ]]; then
      agent="codex"; session="$CODEX_SESSION_ID"
    fi

    # One conversation, one listener. Compacting is the usual way a second one
    # shows up (#81): the conversation survives with the same session id, but
    # whatever was watching the old `listen` forgets it is already there and
    # starts a fresh one, doubling the same session in the chip row and
    # leaving an orphaned pipe still running behind it. A session id never
    # legitimately runs two of these at once, so any other registration
    # carrying this same one is always a leftover, safe to retire outright
    # rather than merely warn about.
    if [[ -n "$session" && -d "$STATE_DIR/listeners" ]]; then
      for f in "$STATE_DIR/listeners"/*; do
        [[ -f "$f" ]] || continue
        other_pid="$(basename "$f")"
        [[ "$other_pid" == "$reg_pid" ]] && continue
        other_session="$("$PY" -c '
import json, sys
try:
    print(json.load(open(sys.argv[1])).get("session", ""))
except Exception:
    pass
' "$f" 2>/dev/null || true)"
        if [[ -n "$other_session" && "$other_session" == "$session" ]]; then
          kill "$other_pid" 2>/dev/null || true
          rm -f "$f"
        fi
      done
    fi

    # An escape hatch so any tool can name itself. VOICE_SHELL_NAME wins outright.
    "$PY" - "$reg" "$agent" "$session" "${VOICE_SHELL_NAME:-}" <<'REG' || true
import json, os, sys, time
from pathlib import Path
reg, agent, session, name = sys.argv[1:5]
now = time.time()

# The order on screen comes from this moment, when the skill started listening
# just now. A session that sat quiet for days does not keep a claim on an
# early spot from back then (#74).
json.dump({"started": time.strftime("%Y-%m-%d %H:%M:%S"), "since": now,
           "cwd": os.getcwd(), "agent": agent, "session": session, "name": name},
          open(reg, "w", encoding="utf-8"), ensure_ascii=False)
REG
    # With exec the trap is not carried over (process replacement makes bash
    # itself disappear), so the automatic cleanup on exit stops working.
    #
    # Put tail in the background and wait on it. Left in the foreground,
    # SIGTERM kills only bash and tail is left an orphan (the registration is
    # gone yet utterances still come in, which slips past the double detection).
    # Slot in the addressee filter. Drop a line that is not addressed to us,
    # including one with no addressee at all (#73, not arriving beats arriving
    # at the wrong desk).
    tail -F -n 0 "$LOG_FILE" | "$PY" -u "$HERE/listen_filter.py" "$reg_pid" &
    tail_pid=$!

    # A registration missing while its process is still running used to turn
    # into a broadcast the moment the daemon fell back to "everyone" (#62/#73,
    # fixed on the daemon side too, but a healed registry is still the better
    # outcome). The cause was never pinned down, so heal instead of chasing it
    # further. Keep the exact bytes written above (not a fresh write) so
    # "since" never moves and this session does not jump to the front of the
    # destination order on every heartbeat.
    #
    # The touch after it is a second, separate job: a heartbeat. A forceful
    # kill (TaskStop on Windows, #82) can take out this loop's own listen
    # process without the EXIT trap below ever running, so the registration
    # is left behind with nothing to remove it. The daemon side now treats a
    # registration whose mtime has gone quiet for three of these in a row as
    # gone, whatever the PID itself still answers to (voice_daemon.py,
    # HEARTBEAT_STALE). Reading "since" out of this file's own content rather
    # than off its mtime is what keeps that from fighting the healing above,
    # both touch the same file for different reasons now.
    reg_bytes="$(cat "$reg" 2>/dev/null || true)"
    ( while kill -0 "$tail_pid" 2>/dev/null; do
        sleep 30
        [ -s "$reg" ] || printf '%s' "$reg_bytes" > "$reg" 2>/dev/null
        touch "$reg" 2>/dev/null
      done ) &
    heal_pid=$!

    trap 'rm -f "$reg"; kill "$tail_pid" "$heal_pid" 2>/dev/null || true' EXIT INT TERM HUP
    wait "$tail_pid"
    ;;
  name)
    # Put a display name on this session by hand. For use from tools where the
    # agent gives no title, or when the automatic title does not fit the work.
    # Called from a different shell than listen, so look up by conversation id, not PID.
    "$PY" - "$STATE_DIR/listeners" "${CLAUDE_CODE_SESSION_ID:-${CODEX_THREAD_ID:-${CODEX_SESSION_ID:-}}}" "${1:-}" <<'NAMEIT'
import json, os, sys
from pathlib import Path
d, session, name = sys.argv[1:4]
if not session:
    sys.exit("This tool has no session id. "
             "Set VOICE_SHELL_NAME and run listen again.")

# Keep it on the config side too. Restarting voice mode rebuilds the registration
# file, so without this the name given here vanishes and the auto title comes back.
conf = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "voice-shell"
conf.mkdir(parents=True, exist_ok=True)
names_file = conf / "names.json"
try:
    names = json.loads(names_file.read_text(encoding="utf-8"))
except (OSError, ValueError):
    names = {}
if name:
    names[session] = name
else:
    names.pop(session, None)          # called empty means back to the auto title
names_file.write_text(json.dumps(names, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")

hit = 0
for f in os.scandir(d) if os.path.isdir(d) else []:
    try:
        info = json.load(open(f.path, encoding="utf-8"))
    except Exception:
        continue
    if info.get("session") != session:
        continue
    info["name"] = name
    json.dump(info, open(f.path, "w", encoding="utf-8"), ensure_ascii=False)
    hit += 1
if not name:
    print("Back to the automatic title")
elif hit:
    print(f"The display name is now {name!r}")
else:
    print(f"Remembered {name!r} as the display name. "
          "This session is not listening yet, so it shows once it starts")
NAMEIT
    ;;
  hold)
    # Switch to the side that holds utterances back. Meant for Claude itself to
    # call (small talk or a phone call is going on and what lands is no order).
    # Do not mute. Cut it and the utterance is left nowhere, and a user who is
    # not watching the screen cannot tell that nothing is getting through.
    http_post /api/pause \
      "$(printf '{"paused":true,"note":%s}' "$(printf '%s' "${1:-}" | "$PY" -c 'import json,sys; print(json.dumps(sys.stdin.read()))')")" \
      && echo "Switched to the side that collects. It can be sent from the screen" \
      || { echo "The viewer is not running" >&2; exit 1; }
    ;;
  live)
    # Back to the side where utterances land as they come
    http_post /api/pause '{"paused":false}' \
      && echo "Back to the side where it arrives as it comes" \
      || { echo "The viewer is not running" >&2; exit 1; }
    ;;
  log-path)
    echo "$LOG_FILE"
    ;;
  viewer)
    # A viewer that only tails the log. No mic, so it lives alongside the daemon.
    [[ "${1:-}" == "--no-gui" ]] && { export VOICE_SHELL_NO_GUI=1; shift; }
    viewer_running() {
      port_open
    }
    if viewer_running; then
      # Whether to open a window here turns on whether one is actually still
      # open, not on whether one was opened at some point (closed by hand
      # since the last start, or the whole machine rebooted under a daemon
      # that survived it, and neither leaves anything to reopen). /api/state's
      # "viewers" count comes off the live WebSocket connections a real open
      # tab holds (handle_ws in viewer.py), so it says so accurately. Only
      # when it is 0 does opening one add rather than duplicate (the very
      # thing the old flat skip here existed to avoid, back when every retry
      # popped a fresh window regardless).
      # Python, not grep, so a server old enough to answer with no "viewers"
      # key at all (or nothing, or something broken) reads as 0 rather than
      # taking the whole script down. grep -o found nothing to match in
      # exactly that case and exited 1, and set -euo pipefail up top turned
      # that into start dying here in total silence, no line printed at all,
      # whenever the viewer already running belonged to an older version.
      viewers="$(http_get /api/state | "$PY" -c '
import json, sys
try:
    print(json.loads(sys.stdin.read()).get("viewers", 0))
except Exception:
    print(0)
' 2>/dev/null || true)"
      if [[ "${viewers:-0}" == "0" ]]; then
        rm -rf "$STATE_DIR/gui_opened"
        [[ "${VOICE_SHELL_NO_GUI:-0}" == "1" ]] || open_gui || true
      fi
      echo "It is already running at $VIEWER_URL"
      exit 0
    fi
    mkdir -p "$STATE_DIR"
    rm -rf "$STATE_DIR/gui_opened"      # started fresh, so open one window too
    # Detach with setsid. The daemon kills every one of its children when it
    # exits, so on the same line stopping the daemon takes the viewer down too.
    detach "$PY" "$HERE/viewer.py" "$@" \
      > "$STATE_DIR/viewer.out" 2>&1 &
    # A flat 2 seconds here used to read as "It failed to start." on a first
    # run where a local engine's own setup (the Swift build behind `apple`,
    # for one) is compiling at the same moment and eats the CPU this needs to
    # so much as get its own interpreter up. The viewer does none of that
    # work itself, it was only ever caught waiting behind it.
    #
    # Polled on viewer_running alone, nothing smarter. viewer.py prints
    # exactly one line, and only once the port is already open, so there is
    # no line in this log that means "still starting, but fine" to tell apart
    # from "already failed". A first attempt at reading the log for an early
    # failure (Traceback, "Error:") missed the plainer sys.exit(str) messages
    # viewer.py itself raises (no traceback, no such prefix), which would
    # have sat there the same 2 seconds as before, this time misread as an
    # early real failure instead of a slow real success, the exact mistake
    # this fix exists to undo. A genuine failure still gets reported, at
    # worst 15 seconds later than a keyword match might have caught it.
    ok=0
    for _ in $(seq 1 30); do          # up to 15 seconds
      if viewer_running; then ok=1; break; fi
      sleep 0.5
    done
    if [[ "$ok" == 1 ]]; then
      echo "The viewer started at $VIEWER_URL"
      # Open in a window of its own (--no-gui means do not open)
      [[ "${VOICE_SHELL_NO_GUI:-0}" == "1" ]] || open_gui || true
    else
      echo "It failed to start." >&2; tail -5 "$STATE_DIR/viewer.out" >&2; exit 1
    fi
    ;;
  viewer-stop)
    if have pkill; then
      rm -rf "$STATE_DIR/gui_opened"
      pkill -f "voice-shell/scripts/viewer\.p[y]" && echo "The viewer stopped" \
        || echo "It is not running"
    else
      echo "This OS cannot stop it for you, because there is no pkill." >&2
      echo "  End the python process for viewer.py from the task manager." >&2
    fi
    ;;
  wait-ready)
    # Recognizing in the browser loads no model, so there is nothing to wait for
    if [[ "$("$PY" "$APP" --resolve-engine "")" == "browser" ]]; then
      echo READY; exit 0
    fi
    # Wait until startup finishes (or errors out)
    for _ in $(seq 1 90); do
      if grep -q "Listening. Speak and it gets appended" "$BOOT_LOG" 2>/dev/null; then echo READY; exit 0; fi
      if grep -qE "Traceback|Error:|Already running" "$BOOT_LOG" 2>/dev/null; then
        echo FAILED; tail -5 "$BOOT_LOG" >&2; exit 1
      fi
      sleep 2
    done
    echo TIMEOUT; exit 1
    ;;
  *)
    echo "Usage is voice-shell.sh {start [--engine X] [--no-gui]|stop|status|engines}" >&2
    echo "        voice-shell.sh {listen|codex-forward|listeners|name|hold|live|log-path|wait-ready|viewer}" >&2
    echo "        voice-shell.sh {apple|whisper}" >&2
    exit 1
    ;;
esac
