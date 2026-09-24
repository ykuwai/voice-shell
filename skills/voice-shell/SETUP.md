# Setup

The procedure Claude Code follows when it walks someone through this. Look at the
environment first and **ask the user which way to go before running anything**
(do not install everything on your own).

**Most of the time there is nothing to install.** The default uses **the
browser's own built-in speech recognition** (Chrome's Web Speech API), and
`pip install numpy aiohttp` is enough to run it. No model to load, nothing to
wait for. It recognizes locally while Chrome holds a model for the language,
and on Google's servers when it holds none. The note in the settings says which
of the two is happening.

What follows is for when you want everything to stay on your machine, or when you
want to use it without opening the window.

## 1. Look at the environment

```bash
uname -s -m
sw_vers -productVersion 2>/dev/null      # on macOS
```

| Environment | Which section |
|---|---|
| Just trying it out, or a weak machine | **Nothing to install** (the default browser recognition) |
| macOS 26 or later | **A**. The recognition that ships with the OS, no model to download |
| Anything else, or you want it strong on proper nouns | **B**. Run Whisper on your own machine |

With A and B the audio never leaves the machine, and nothing has to be
downloaded by Chrome first. In a recent Chrome the settings also offer a browser
choice called "local only", which keeps the audio here too once Chrome has the
language model.

## A. macOS 26 or later (the recognition that ships with the OS)

Uses `SpeechAnalyzer` and `SpeechTranscriber` (`engine_apple.py`).
Runs with `--engine apple`.

```bash
cd <this repository>
python3 -m venv .venv                    # Python 3.10 to 3.13
.venv/bin/pip install -U numpy aiohttp soxr "sounddevice>=0.5.6"
```

The Swift helper (`speech_helper.swift`) is built automatically on the first run,
so Xcode or the Command Line Tools have to be there.

```bash
xcode-select --install                   # if you do not have them
swiftc --version                         # check that the macOS 26 SDK is visible
```

The OS pulls down the speech model for the language by itself on the first run
(tens of seconds). It stays on the machine after that, so there is no wait.

The memory is held by the OS, not by us. Startup is under a second, and a 3.5 second
utterance takes about 0.1 seconds to recognize (measured on Apple Silicon).

**macOS 25 and earlier have no `SpeechTranscriber`.** Go to B in that case.

## B. Whisper (faster-whisper)

Runs with `--engine whisper` (`whisper_engine.py`). Inside it is
[faster-whisper](https://github.com/SYSTRAN/faster-whisper), the CTranslate2 build
of Whisper, which runs on any OS.

```bash
cd <this repository>
python3 -m venv .venv                    # Python 3.10 to 3.13
.venv/bin/pip install -U faster-whisper aiohttp soxr numpy "sounddevice>=0.5.6"
```

If `nvidia-smi` shows an NVIDIA GPU on the machine, the defaults (`cuda` /
`float16`) are the right ones, but **the pip line above alone is not enough on
Linux.** `ctranslate2` (what faster-whisper actually runs on) needs the CUDA
12 build of cuBLAS and cuDNN, and unlike PyTorch it does not know to look
inside its own `site-packages` copy for them, so a plain `pip install` step
that only reaches `faster-whisper` leaves it unable to find either at the
moment it actually runs (loading the model still succeeds either way, the
first real utterance is where this shows up: `RuntimeError: Library
libcublas.so.12 is not found or cannot be loaded`, or the equivalent for
`libcudnn`).

```bash
.venv/bin/pip install -U nvidia-cublas-cu12 nvidia-cudnn-cu12
export LD_LIBRARY_PATH="$(.venv/bin/python -c '
import os, nvidia.cublas, nvidia.cudnn
print(os.pathsep.join(os.path.dirname(m.__file__) + "/lib"
                       for m in (nvidia.cublas, nvidia.cudnn)))
')${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
```

Put the `export` line in your shell's own startup file (`~/.bashrc` and
similar) so it survives past this one session, since `voice-shell.sh` calls
the interpreter directly rather than going through any `conda activate` or
venv `activate` step, so a fix written into either of *those* alone is never
picked up.

**On Windows it is the same two libraries, pointed at a different way.** The
wheels above carry Windows builds as well, but there the dlls land in `bin`
rather than `lib`, and `LD_LIBRARY_PATH` means nothing. ctranslate2 looks them
up through the plain `PATH`, so that is what has to hold the two folders
(`os.add_dll_directory` on its own is not enough, its loader does not go
through it).

```powershell
.venv\Scripts\pip install -U nvidia-cublas-cu12 nvidia-cudnn-cu12
$p = .venv\Scripts\python -c "import os, nvidia.cublas, nvidia.cudnn; print(os.pathsep.join(os.path.join(os.path.dirname(m.__file__), 'bin') for m in (nvidia.cublas, nvidia.cudnn)))"
if (-not $p) { throw "the two packages are not in this venv" }
$env:PATH = "$p;$env:PATH"
```

Keep `$p`. The next step wants it, and without the `throw` a line that failed
here would quietly put an empty entry at the front of `PATH` instead of saying
anything.

Make it stick from the system settings, or the same way from here. Do not reach
for `setx PATH`, it writes the merged value back into the user's own `PATH` and
cuts it off at 1024 characters.

```powershell
$u = [Environment]::GetEnvironmentVariable('Path', 'User')
[Environment]::SetEnvironmentVariable('Path', "$u;$p", 'User')
```

It survives past this one session for the same reason as on Linux. If you would
rather not have pip carry them at all,
[Purfview's whisper-standalone-win](https://github.com/Purfview/whisper-standalone-win)
hands you the same libraries in one archive, which is where faster-whisper's own
README sends Windows. Unpack it into any folder already on `PATH`.

Which cuDNN you want depends on the version underneath. **ctranslate2 4.5 and
newer want CUDA 12 and cuDNN 9**, which is what the pip line above gives you,
and what a fresh install lands on (faster-whisper asks only for
`ctranslate2<5,>=4.0`, so it comes down at its newest). Only if something is
already holding ctranslate2 at 4.4 or below, an old lock file or a pinned image,
do you want the other pairing. 4.4 is the last one built against cuDNN 8.

```powershell
.venv\Scripts\pip install -U "ctranslate2==4.4.0" "nvidia-cudnn-cu12==8.*"
```

Either way an older system-wide CUDA toolkit on `PATH` will shadow what pip put
there. When it is still not working, ask it what it can see.

```powershell
.venv\Scripts\python -c "import ctranslate2; print(ctranslate2.get_cuda_device_count())"
```

`0` means it is not reaching the GPU at all, so nothing about the model or the
options is going to change it.

```bash
voice-shell.sh whisper
```

With only a CPU, shrink the model and say where you want to give up accuracy.

```bash
voice-shell.sh whisper --model base --whisper-device cpu --whisper-compute int8
```

The model comes down from Hugging Face on the first run (tens of MB up to about
100MB for `base`). `--whisper-compute` is the trade between accuracy and speed, so
use `int8` on a CPU and `float16` on a GPU.

### Which model to use

The default is `large-v3-turbo`. It is **far too heavy on a CPU with no GPU**, and
on a 4 core CPU the measured result was that `base` is the practical one (RTF about
0.15). `small` is a bit heavy at RTF about 0.76.

`--model` takes a Hugging Face name as well as the path of a folder on your machine.
If you have a model tuned for your language, hand it over as it is.

```bash
voice-shell.sh whisper --model kotoba-tech/kotoba-whisper-v2.0
voice-shell.sh whisper --model /path/to/my-model
```

A model you hand over once is remembered, so `start` is enough after that
(`~/.config/voice-shell/config.json`). Pass `--model ""` to go back to the default.

Only the model is remembered. `--whisper-device` and `--whisper-compute` are not,
so pass them every time if you are on a CPU.

Compared with Apple's on-device recognition, Whisper is stronger on proper nouns
and holds up better in a noisy room or with several voices. In exchange it starts
slower and uses the memory the model needs.

## Common to both

`voice-shell.sh` finds the `.venv` at the root of the repository by itself, so there
is no need to set `VOICE_SHELL_PYTHON`.

`sounddevice` in the pip line above is what records on macOS and Windows, and it
arrives as a ready built wheel, so there is nothing else to install there. It is
held at 0.5.6 or newer, because before that it read which chip the machine has
rather than which one the Python was built for, and loaded the wrong dll on a
Windows machine with an ARM chip.

**Linux records through `arecord` instead, always, whether or not
`sounddevice` is installed there too.** `sounddevice` needs the PortAudio
shared library underneath it, which the pip package alone does not carry on
Linux, and importing it without that library installed raises `OSError:
PortAudio library not found` (voice-shell only ever imports it inside its own
try/except, so this cannot crash the tool itself, only a standalone `python3
-c "import sounddevice"` run to check the install). Skip it and go straight
to `alsa-utils`.

```bash
sudo apt install alsa-utils      # Linux
```

On macOS a dialog asks the terminal for mic permission on the first run, so have
the user allow it. The recognition itself never touches the mic, so nothing else
has to be allowed.

## 2. Make the skill visible

```bash
ln -s "$(pwd)/skills/voice-shell" ~/.claude/skills/voice-shell
```

Not needed if it went in with `npx skills add ykuwai/voice-shell`.

## 3. Run it

```bash
${CLAUDE_SKILL_DIR}/scripts/voice-shell.sh start
${CLAUDE_SKILL_DIR}/scripts/voice-shell.sh wait-ready
```

Once `READY` shows up, have the user open http://127.0.0.1:47865 and talk.
Set `VOICE_SHELL_PORT` before starting it to use another port.

## Commands

```bash
voice-shell.sh start [--engine X] [--no-gui]
voice-shell.sh stop
voice-shell.sh status
voice-shell.sh engines
```

| Command | What it does |
|---|---|
| `start` | Starts it, and remembers the way you picked last time |
| `stop` | Stops it |
| `status` | What is running, and which session is listening |
| `engines` | The ways it can recognize speech |

Everything you set stays in `~/.config/voice-shell/` and survives a restart.

## When you get stuck

| Symptom | What to do |
|---|---|
| `No Python it can run was found` | `export VOICE_SHELL_PYTHON=/path/to/.venv/bin/python` |
| Nothing here can record | `pip install "sounddevice>=0.5.6"`. On Linux `sudo apt install alsa-utils` |
| Startup says `FAILED` | Look at `voice-shell.sh status` and the tail of `daemon.out` |
| Whisper is slow | Shrink the model (`--model base`). On a CPU add `--whisper-compute int8` |
| You talk and nothing arrives | Check `voice-shell.sh status` first (a crashed engine reads the same as a quiet one, see the row above). If it says it is running, the trigger level is too high, lower the mark under the mic in the viewer until the bar crosses it when you speak |
| Noises send things on their own | The trigger level is too low. Raise that same mark until only your voice gets past it |
| A session that ended stays in the destination row (Windows) | Fixed in `listen`, see [Notes for Windows](#notes-for-windows). A listen that goes away keeps its chip (faded), number and destination for 2 minutes, and its place in the row for 10, so a re-armed watch of the same session picks up where it left off and receives what was said in between. Stopping on purpose (`stop`, the × on a chip) leaves none. For a leftover from an older version, end its `voice-shell.sh listen` processes in the task manager |
| You want a different mic | Pick it in the viewer, or pass its name to `--device`. On Linux `--device` takes the `-D` of `arecord` (`arecord -L` lists them) |

## Notes for Windows

Windows behaves differently enough here that several fixes only make sense with
the reason written down. The code itself is written to run everywhere; these are
the reasons behind the shape it has.

- **A `listen` outlives the watch it was started in.** Claude Code's Monitor
  ends the wrapper shell and nothing else, so on Windows `listen`, its tail and
  its filter all carried on: still registered, still the chosen destination,
  reading nothing, and whatever was said next was routed to a session nobody was
  reading. `listen` now hands its parent's pid down as `VOICE_SHELL_PARENT_PID`
  and `listen_filter.py` quits when that process goes, which ends the pipeline
  `listen` waits on and lets its `EXIT` trap run. On MSYS the value has to be the
  real Win32 pid, read from `/proc/$PPID/winpid`, because Python is what checks
  it; an MSYS pid handed over would be read as a Win32 one and could land on some
  unrelated process.
- **`os.kill` is `TerminateProcess`, so no `EXIT` trap ever runs.** Stopping a
  listen with a signal killed it where it stood and lost everything its tail had
  not polled up yet, and from inside the session it looked exactly like a crash.
  The disconnect (the × on a chip) now writes the warning line with a `stop` flag
  on it, so the listen prints the line and ends itself: telling it and ending it
  are one thing. The signal stays only as a last resort for a listen that never
  read the line.
- **There is no signal 0 either.** `os.kill(pid, 0)` raises `SystemError` on
  Windows, so liveness is a handle instead. A handle can still be opened on a
  process that has already exited for as long as anything else holds one (MSYS
  children hold one on their parent), so the exit code decides: only
  `STILL_ACTIVE` counts as running. Without that, a `listen` gone from the task
  list kept passing the check and its registration was never cleared.
- **A listener measures where it starts reading before it registers.** The chip
  is clickable the moment the registration appears, so anything written in
  between (the viewer telling this very session it was disconnected) landed
  behind the point tail was told to start from and was never read. Measured from
  before, nothing addressed to this listen can fall in the gap, because it did
  not exist yet.
- **Paths handed to native Python are converted with `cygpath -w`.** The shell
  side runs under MSYS and the Python side does not, so a path like `/c/Users/...`
  is not one Python can open. MSYS converts paths in the arguments to a native
  exe, but never in environment variable values, and the progress and epoch files
  `listen` hands to `listen_filter.py` travel as `VOICE_SHELL_PROGRESS` and
  `VOICE_SHELL_EPOCH_FILE`, so those are converted by hand.
- **`listen` feeds its filter through process substitution, not a pipe.** Under
  Git Bash, waiting on a background pipeline waits for tail as well, and tail is
  held to this listen with `--pid`, so the two waited on each other and the
  filter quitting never let `listen` go.

Two more from the same round of fixes that are not about Windows, kept here so
they are not lost.

- **Starting must not empty the utterance log while another session is
  listening.** Both entry points, `voice-shell.sh start --engine browser` and the
  daemon's own startup for a local engine, go through `empty_log_for_start`,
  which empties only when nobody is listening. What sits in the log while a
  session is listening is what was said a moment ago and has not been handed over
  yet; emptying it takes that away with nothing said anywhere on screen. A new
  epoch is stamped only when it really is emptied, so no offset recorded against
  the old log is ever read against a new one.
- **Everything is folded to half-width before it is matched.** Chrome's on-device
  recognition returns full-width Latin letters and digits, so the user
  dictionary, the end-of-sentence commands and the machine names all go through
  `to_halfwidth` first, or none of them match what was said. The display keeps
  the words as they were sent.
