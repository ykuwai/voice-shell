#!/usr/bin/env bash
# 音声プロンプト常駐デーモンのラッパー。
# どのプロジェクトからでも同じコマンドで起動できるようにする。
#
#   voice-shell.sh start [--engine X] [--no-gui]
#   voice-shell.sh stop
#   voice-shell.sh status
#   voice-shell.sh viewer / viewer-stop
#   voice-shell.sh log-path / wait-ready
#   voice-shell.sh listen                 発話ログを tail する（Monitor 用。多重起動を検知できる形）
#   voice-shell.sh engines                選べる認識のやり方と、前回の選択
#   voice-shell.sh listeners              いま listen しているセッションの一覧
#   voice-shell.sh name "…"               このセッションの表示名を付ける
#   voice-shell.sh whisper                Whisper で認識する（固有名詞に強い）
#   voice-shell.sh apple                  macOS 26 付属の認識で動かす（軽い）
#   voice-shell.sh remote                 LAN の端末からも受ける
#   voice-shell.sh remote-conf            設定ファイルの場所
#   voice-shell.sh remote-log             届いた発話の置き場

set -euo pipefail

# スクリプト自身の場所を基準にする（シンボリックリンク経由でも実体を辿る）
HERE="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"

# Git Bash (Windows) には pgrep/pkill/setsid が無い。無ければ機能を諦めて
# 素通しする（プロセス確認・多重起動チェックが効かなくなるだけで、
# 起動・停止そのものはできる）。
have() { command -v "$1" >/dev/null 2>&1; }

# Windows の Python は既定でファイル I/O にシステムのロケール（日本語版なら
# cp932）を使う。UTF-8 で書いた JSON やログを cp932 で開こうとして
# UnicodeDecodeError で落ちるため、UTF-8 モード（PEP 540）を強制する。
# macOS / Linux では無害（すでに UTF-8 なので変化しない）。
export PYTHONUTF8=1

# Python 環境を探す。VOICE_SHELL_PYTHON で明示指定できる。
find_python() {
  if [[ -n "${VOICE_SHELL_PYTHON:-}" ]]; then echo "$VOICE_SHELL_PYTHON"; return; fi
  # リポジトリ直下の .venv（conda を使わない構成。macOS はこちらが標準）
  if [[ -x "$HERE/../../../.venv/bin/python" ]]; then
    echo "$HERE/../../../.venv/bin/python"; return
  fi
  # Windows の venv は Scripts/python.exe に入る（bin/ ではない）
  if [[ -x "$HERE/../../../.venv/Scripts/python.exe" ]]; then
    echo "$HERE/../../../.venv/Scripts/python.exe"; return
  fi
  # conda / mamba の qwen3-asr 環境を各所から探す
  for base in "$HOME/miniforge3" "$HOME/miniconda3" "$HOME/anaconda3" \
              "$HOME/mambaforge" "/opt/homebrew/Caskroom/miniforge/base" "/opt/conda"; do
    for env in qwen3-asr voice-shell; do
      [[ -x "$base/envs/$env/bin/python" ]] && { echo "$base/envs/$env/bin/python"; return; }
    done
  done
  # 見つからなければ、動かすのに足りる python を探す。
  #
  # 既定のブラウザ認識に要るのは numpy と aiohttp だけで、認識のモデルは
  # 要らない。ここでモデルの有無を条件にすると、「何も入れずに動く」はずの
  # 既定が、モデルの無い機械では起動すらできなくなる（実際そうなっていた）。
  for c in python3 python; do
    command -v "$c" >/dev/null || continue
    if "$c" -c "import numpy, aiohttp" 2>/dev/null; then
      command -v "$c"; return
    fi
  done
}

# 残った vLLM ワーカーを落とす。kill -9 を撃つので誤爆は許されない:
#   - パターンを [V] と書いて pgrep 自身のコマンドラインに当たらないようにする
#   - 呼び出し元のシェル（自分の親やプロセスグループ）は明示的に除外する
# 素の `pgrep -f "VLLM::EngineCore" | xargs kill -9` はこの行を含むシェルに
# マッチしうるため、自分自身を撃って停止処理ごと落ちることがある。
kill_engine_cores() {
  have pgrep || return 0
  local pid
  for pid in $(pgrep -f "[V]LLM::EngineCore" 2>/dev/null); do
    [[ "$pid" == "$$" || "$pid" == "$PPID" ]] && continue
    kill -9 "$pid" 2>/dev/null || true
  done
  return 0
}

# 前回どのエンジンで起動したかを覚えておく。ビューアの「聞き取りを
# 始める」は engine-start を呼ぶが、そちらは元のコマンドを知らない。
# 覚えていないと whisper で立ち上げたのに Qwen3-ASR が載ってしまう。
engine_args() {
  # 覚えている選択（~/.config/voice-shell/config.json）を正とする。
  # 以前は /tmp のファイルを見ていたが、再起動で消えると黙って
  # コンパイル時の既定に戻り、config と食い違っていた。
  local e
  e="$("$PY" "$APP" --resolve-engine "" 2>/dev/null || true)"
  [[ -n "$e" && "$e" != "browser" ]] && echo "--engine $e"
}

PY="$(find_python || true)"
APP="$HERE/voice_daemon.py"

# プロセスを呼び出し元の系統から切り離して起動する。
# macOS には setsid が無いので、その場合は nohup だけで済ませる
# （デーモンの子 kill は pgrep -P による直接の子だけなので、これで足りる）。
detach() {
  if command -v setsid >/dev/null; then
    setsid nohup "$@"
  else
    nohup "$@"
  fi
}

if [[ -z "$PY" ]]; then
  echo "動かせる Python が見つかりません。" >&2
  echo "  ブラウザで認識するだけなら、これだけで足ります:" >&2
  echo "    pip install numpy aiohttp" >&2
  echo "  手元のモデルで認識する場合は SETUP.md を参照してください。" >&2
  echo "  場所を直接指定する場合: export VOICE_SHELL_PYTHON=/path/to/python" >&2
  exit 1
fi
STATE_DIR="${XDG_RUNTIME_DIR:-/tmp}/qwen-voice"
LOG_FILE="$STATE_DIR/utterances.jsonl"
BOOT_LOG="$STATE_DIR/daemon.out"

# Windows(Git Bash) では bash が見る "/tmp" と、素の Python が単独で解釈する
# "/tmp" が別の実ディレクトリになる（前者は MSYS がマウント変換した実フォルダ、
# 後者は pathlib がドライブ直下として扱う C:\tmp）。ここで確定した実パスを
# cygpath で Windows 形式に変換し、子の Python プロセスへ明示的に渡す
# （そうしないとデーモンの書き込み先と Monitor の tail 先がずれ、
# 発話がどこにも届かなくなる）。
if command -v cygpath >/dev/null 2>&1; then
  export VOICE_SHELL_STATE_DIR="$(cygpath -w "$STATE_DIR")"
fi

cmd="${1:-status}"; shift || true

# ビューアを独立したウィンドウで開く。
#
# Chrome の --app はタブもURL欄も無い窓になり、コマンドから開ける。
# 「常に最前面」にしたい場合は、開いた窓のヘッダから手で浮かせる
# （Document Picture-in-Picture は人が触らないと開けない決まりのため）。
open_gui() {
  local url="http://127.0.0.1:8090"
  local args=(--app="$url" --window-size=420,780)
  case "$(uname)" in
    Darwin)
      for app in "Google Chrome" "Chromium" "Microsoft Edge"; do
        if [[ -d "/Applications/$app.app" ]]; then
          open -na "$app" --args "${args[@]}" 2>/dev/null && return 0
        fi
      done
      ;;
    *)
      for c in google-chrome chromium chromium-browser microsoft-edge; do
        if command -v "$c" >/dev/null; then
          nohup "$c" "${args[@]}" >/dev/null 2>&1 & return 0
        fi
      done
      # Windows(Git Bash)
      if command -v cmd.exe >/dev/null; then
        cmd.exe /c start chrome --app="$url" --window-size=420,780 >/dev/null 2>&1 && return 0
      fi
      ;;
  esac
  echo "  ブラウザを自動で開けませんでした → $url" >&2
  return 1
}

# 発話ログを追尾しているセッションを一覧する。
#
# Monitor を止め忘れると、古いセッションに音声が届き続ける。tail は -F なので
# デーモンを入れ直してもつながり直してしまい、本人は気づけない。実際に8日前の
# セッションが生きていて、同じ発話が2つのセッションへ配られていたことがある。
# `voice-shell.sh listen` が起動時に自分を登録したファイル（$STATE_DIR/listeners/
# 以下、ファイル名がその聞き手の PID）を Python 側（_pid_alive で生存確認、
# Windows でも動く）に数えさせる。pgrep には頼らない。
list_listeners() {
  "$PY" "$APP" --listeners
}

case "$cmd" in
  start)
    # 使うエンジンを決める（指定 > 前回の選択 > 自動）。
    # 「前回の選択」は ~/.config/voice-shell/config.json に残るので、
    # 再起動しても選び直しにならない。
    # 初回かどうか（覚えている選択がまだ無い）を、解決する前に見ておく
    conf="${XDG_CONFIG_HOME:-$HOME/.config}/voice-shell/config.json"
    first_run=0; [[ -f "$conf" ]] || first_run=1

    want=""
    no_gui=0
    rest=()
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --engine) want="${2:-}"; shift 2 ;;
        --engine=*) want="${1#*=}"; shift ;;
        --no-gui) no_gui=1; shift ;;
        *) rest+=("$1"); shift ;;
      esac
    done
    export VOICE_SHELL_NO_GUI="$no_gui"
    set -- "${rest[@]+"${rest[@]}"}"
    engine="$("$PY" "$APP" --resolve-engine "$want")"
    "$PY" "$APP" --remember-engine "$engine"

    # ブラウザで認識するなら、この機械にモデルを積む必要がない。
    # ビューアだけ立ち上げて終わる（画面を開いた時点で認識が始まる）。
    if [[ "$engine" == "browser" ]]; then
      mkdir -p "$STATE_DIR"
      # デーモン起動と揃える。残しておくと前回の発話が画面に並び直す。
      : > "$LOG_FILE"
      echo "このブラウザ（Chrome）で認識します。モデルの読み込みはありません。"
      echo "  発話ログ: $LOG_FILE"
      # 初回だけ、音声の行き先と、この機械で使える代わりを名指しで伝える。
      # 一般論だと「では何を選べば」で止まるので、具体名まで出す。
      if [[ "$first_run" == 1 ]]; then
        echo
        echo "※ 音声は認識のため Google のサーバへ送られます。"
        alt="$("$PY" "$APP" --list-engines | sed -n '2p' | awk '{print $1}')"
        if [[ -n "$alt" ]]; then
          echo "   手元だけで完結させたい場合、この機械では次も使えます:"
          echo "     voice-shell.sh start --engine $alt"
        fi
      fi
      listeners_now="$(list_listeners)"
      if [ -n "$listeners_now" ]; then
        echo
        echo "※ すでにこの音声を聞いているセッションがあります:"
        echo "$listeners_now"
      fi
      "$0" viewer
      echo
      echo "Chrome でビューアを開き、マイクを許可すると認識が始まります。"
      echo "開くまでは、話しても何も届きません。"
      exit 0
    fi
    if "$PY" "$APP" --status | grep -q 稼働中; then
      echo "すでに稼働しています。"; exit 0
    fi
    mkdir -p "$STATE_DIR"
    # GPU を占有する他のプロセスがいると起動に失敗するので先に知らせる。
    # パターンを [V] と書くのは自己マッチ避け。pgrep -f はコマンドライン全体を
    # 見るため、素で書くとこの行を実行しているシェル自身に当たって誤検知する。
    if have pgrep && pgrep -f "[V]LLM::EngineCore" >/dev/null; then
      echo "警告: 別のプロセスが GPU を使用中です。" >&2
      echo "  同じ GPU を使う音声プロセスを止めてから再実行してください。" >&2
      exit 1
    fi
    # 古いパスで動いているビューアを片付ける（構成を変えたときの取り残し）
    have pkill && pkill -f "voice-shell/scripts/viewer\.p[y]" 2>/dev/null || true
    # 日本語に固定する。自動判定だと物音を中国語などに誤認識しやすい（実測）。
    # 英語を話しても認識自体は追従する（単語間に入る読点はビューア側で除去）。
    # 別言語を主に使うなら `voice-shell.sh start --language English` のように渡す。
    # setsid で切り離す。付けないと呼び出し元と同じプロセスグループに残り、
    # このスクリプトの終了時に一緒に片付けられてしまう（ビューアだけ残る）。
    detach "$PY" "$APP" --language Japanese $(engine_args) "$@" \
      > "$BOOT_LOG" 2>&1 &
    echo "起動中… (モデル読み込みに1〜2分かかります)"
    echo "  発話ログ: $LOG_FILE"
    echo "  起動ログ: $BOOT_LOG"
    # 前のセッションが聞いたままだと、同じ発話が両方へ届く。
    # 起動のときに気づけるようにここで知らせる（デーモン自身も、動き出した
    # あとは5秒おきに同じことを確認して発話ログへ警告を書く）。
    listeners_now="$(list_listeners)"
    if [ -n "$listeners_now" ]; then
      echo
      echo "※ すでにこの音声を聞いているセッションがあります:"
      echo "$listeners_now"
      echo "  身に覚えが無ければ、使っていないものを停止してください。"
    fi
    # ビューアも一緒に立ち上げる（毎回 viewer を打つのを忘れないように）。
    # GPU もマイクも使わないので、常駐と同時に動いてよい。
    "$0" viewer
    ;;
  stop)
    "$PY" "$APP" --stop
    # vLLM ワーカーが残ることがあるので確実に落とす
    kill_engine_cores
    "$0" viewer-stop
    ;;
  engine-stop)
    # 認識だけ止めて GPU を解放する。ビューアは残すので、
    # ブラウザから「聞き取りを再開」で戻せる。
    "$PY" "$APP" --stop 2>/dev/null || true
    # PID ファイルは読み込み完了後に書かれる。起動途中で止めると
    # ファイルが無いまま本体が残るので、名前でも確実に落とす。
    if have pkill; then
      pkill -f "voice_daemon\.p[y] --language" 2>/dev/null || true
      sleep 1
      pkill -9 -f "voice_daemon\.p[y] --language" 2>/dev/null || true
    fi
    kill_engine_cores
    ;;
  engine-start)
    if [[ "$("$PY" "$APP" --resolve-engine "")" == "browser" ]]; then
      echo "ブラウザ認識が選ばれています。この機械にモデルは積みません。" >&2
      exit 0
    fi
    # 認識だけ立ち上げ直す（ビューアには触らない）。
    # setsid で切り離す。デーモンは終了時に自分の子を全部 kill するので、
    # 呼び出し元（ビューア）にぶら下げると巻き込まれる。
    #
    # ここの確認は PID ファイル頼みなので、読み込み中はすり抜ける。
    # 二重起動はデーモン側のロックで確実に止めている。
    if "$PY" "$APP" --status | grep -q 稼働中; then
      echo "すでに稼働しています。"; exit 0
    fi
    mkdir -p "$STATE_DIR"
    detach "$PY" "$APP" --language Japanese $(engine_args) "$@" \
      > "$BOOT_LOG" 2>&1 &
    echo "起動中… (モデル読み込みに1〜2分かかります)"
    ;;
  whisper)
    # Qwen3-ASR の代わりに Whisper を使う。固有名詞に強い。
    "$0" start --engine whisper "$@"
    ;;
  apple)
    # macOS 26 付属のオンデバイス認識を使う。GPU メモリを積まないので Mac 向け。
    "$0" start --engine apple "$@"
    ;;
  remote)
    # LAN の端末からも音声を受ける形で立ち上げる。
    # 設定は ~/.config/voice-shell/remote.json（無ければ雛形を作って止まる）。
    #
    # これは「エンジン」ではなく「モード」。この機械が認識役になるので、
    # ブラウザ認識では成立しない。新規環境（覚えている選択が無い）だと
    # browser に解決されて --remote ごと捨てられていたので、auto を強制する。
    if [[ "$("$PY" "$APP" --resolve-engine "")" == "browser" ]]; then
      "$0" start --engine auto --remote "$@"
    else
      "$0" start --remote "$@"
    fi
    ;;
  remote-conf)
    # 設定ファイルの場所を教える（編集しやすいように）
    echo "${XDG_CONFIG_HOME:-$HOME/.config}/voice-shell/remote.json"
    ;;
  remote-log)
    # LAN から届いた発話の置き場。Monitor で追うときに使う。
    echo "${XDG_STATE_HOME:-$HOME/.local/state}/voice-shell/remote"
    ;;
  status)
    # ブラウザで認識しているときは、この機械にデーモンが居ないのが正常。
    # 素の「停止しています」だけだと壊れているように読めるので、
    # 何で認識しているのかを先に言う。
    engine="$("$PY" "$APP" --resolve-engine "")"
    if [[ "$engine" == "browser" ]]; then
      echo "このブラウザで認識します（この機械にモデルは積みません）"
      if ! curl -sf -o /dev/null --max-time 2 http://127.0.0.1:8090; then
        echo "  ビューアが動いていません → voice-shell.sh viewer" >&2
      else
        echo "  ビューア: http://127.0.0.1:8090"
        # 画面が実際に聞いているかまで見る。ここを見ないと、開いていない・
        # マイクを拒否された状態と、ちゃんと聞いている状態を区別できない。
        curl -sf --max-time 2 http://127.0.0.1:8090/api/asr-status \
          | "$PY" "$HERE/asr_status.py" || echo "  画面の状態を確認できませんでした"
      fi
    else
      echo "認識のやり方: $engine"
      "$PY" "$APP" --status
    fi
    echo
    echo "この音声を聞いているセッション:"
    listeners_now="$(list_listeners)"
    if [ -n "$listeners_now" ]; then echo "$listeners_now"
    else echo "  なし（音声はどこにも届いていません）"; fi
    ;;
  engines)
    # 選べる認識のやり方。何が入っていて、前回どれを選んだかを出す。
    "$PY" "$APP" --list-engines
    ;;
  listeners)
    listeners_now="$(list_listeners)"
    if [ -n "$listeners_now" ]; then echo "$listeners_now"
    else echo "  なし（音声はどこにも届いていません）"; fi
    ;;
  listen)
    # Monitor から使う。発話ログを tail しつつ、自分がいることを
    # $STATE_DIR/listeners/ に登録する（ファイル名は自分の PID）。
    # デーモン側（Python）はこのファイル名を実 PID として生存確認するため、
    # Windows(Git Bash/MSYS) では $$ ではなく /proc/$$/winpid の値を使う
    # （$$ は MSYS 内部の仮想 PID で、実際の Win32 PID とは別物。素の $$
    # を使うと生存確認が常に失敗し、登録した瞬間に「死んでいる」とみなされて
    # 消されてしまう）。
    reg_pid="$$"
    [[ -r "/proc/$$/winpid" ]] && reg_pid="$(cat "/proc/$$/winpid" 2>/dev/null || echo "$$")"
    mkdir -p "$STATE_DIR/listeners"
    reg="$STATE_DIR/listeners/$reg_pid"

    # どの道具から呼ばれたかと、その会話の id を控える。
    # 会話に題名が付いたら、デーモンがそれを引いて表示名に使う
    # （起動した時点では、何の作業か本人にも決まっていないため）。
    agent=""; session=""
    if [[ -n "${CLAUDE_CODE_SESSION_ID:-}" ]]; then
      agent="claude"; session="$CLAUDE_CODE_SESSION_ID"
    elif [[ -n "${CODEX_THREAD_ID:-}" ]]; then
      agent="codex"; session="$CODEX_THREAD_ID"
    elif [[ -n "${CODEX_SESSION_ID:-}" ]]; then
      agent="codex"; session="$CODEX_SESSION_ID"
    fi
    # どの道具でも名乗れる逃げ道。VOICE_SHELL_NAME があれば最優先。
    "$PY" - "$reg" "$agent" "$session" "${VOICE_SHELL_NAME:-}" <<'REG' || true
import json, os, subprocess, sys, time
reg, agent, session, name = sys.argv[1:5]
started = time.strftime("%Y-%m-%d %H:%M:%S")
json.dump({"started": started, "since": time.time(), "cwd": os.getcwd(),
           "agent": agent, "session": session, "name": name},
          open(reg, "w"), ensure_ascii=False)
REG
    # exec すると trap が引き継がれず（プロセス置き換えで bash 自体が
    # 消えるため）終了時の自動削除が効かなくなる。
    #
    # tail は背景に回して wait する。前面のまま置くと、SIGTERM で bash だけ
    # 死んで tail が孤児として残る（登録は消えているのに発話は受け取れる、
    # という多重検知から漏れる状態になる）。
    # 宛先の絞り込みを挟む。行に "to" があって自分宛てでなければ落とす
    # （宛先の指定が無い行は全員へ）。
    tail -F -n 0 "$LOG_FILE" | "$PY" -u "$HERE/listen_filter.py" "$reg_pid" &
    tail_pid=$!
    trap 'rm -f "$reg"; kill "$tail_pid" 2>/dev/null || true' EXIT INT TERM HUP
    wait "$tail_pid"
    ;;
  name)
    # このセッションの表示名を手で付ける。エージェントが題名を付けない
    # 道具から使うときや、自動の題名が実態と合わないときのため。
    # listen とは別のシェルから呼ばれるので、PID ではなく会話の id で探す。
    "$PY" - "$STATE_DIR/listeners" "${CLAUDE_CODE_SESSION_ID:-${CODEX_THREAD_ID:-${CODEX_SESSION_ID:-}}}" "${1:-}" <<'NAMEIT'
import json, os, sys
d, session, name = sys.argv[1:4]
if not session:
    sys.exit("この道具はセッションの id を持っていません。"
             "VOICE_SHELL_NAME を設定して listen し直してください。")
hit = 0
for f in os.scandir(d) if os.path.isdir(d) else []:
    try:
        info = json.load(open(f.path))
    except Exception:
        continue
    if info.get("session") != session:
        continue
    info["name"] = name
    json.dump(info, open(f.path, "w"), ensure_ascii=False)
    hit += 1
print(f"表示名を「{name}」にしました" if hit else
      "このセッションは聞いていません（先に音声モードを始めてください）")
NAMEIT
    ;;
  hold)
    # 発話を溜める側に回す。Claude 自身が呼ぶことを想定している
    # （雑談や通話が続いていて、届く内容が指示ではないとき）。
    # ミュートにはしない。切ると発話がどこにも残らず、画面を見ていない
    # ユーザーは届いていないことに気づけないため。
    curl -sf -X POST http://127.0.0.1:8090/api/pause \
      -H 'content-type: application/json' \
      -d "$(printf '{"paused":true,"note":%s}' "$(printf '%s' "${1:-}" | "$PY" -c 'import json,sys; print(json.dumps(sys.stdin.read()))')")" \
      >/dev/null && echo "溜める側に切り替えました（画面から送れます）" \
      || { echo "ビューアが動いていません" >&2; exit 1; }
    ;;
  live)
    # そのまま届く側に戻す
    curl -sf -X POST http://127.0.0.1:8090/api/pause \
      -H 'content-type: application/json' -d '{"paused":false}' \
      >/dev/null && echo "そのまま届く側に戻しました" \
      || { echo "ビューアが動いていません" >&2; exit 1; }
    ;;
  log-path)
    echo "$LOG_FILE"
    ;;
  viewer)
    # ログを追尾するだけのビューア。GPU もマイクも使わないので常駐と共存できる。
    [[ "${1:-}" == "--no-gui" ]] && { export VOICE_SHELL_NO_GUI=1; shift; }
    # pgrep が無い環境（Windows/Git Bash 等）ではポートへの応答で代用する。
    viewer_running() {
      if have pgrep; then
        pgrep -f "voice-shell/scripts/viewer\.p[y]" >/dev/null
      else
        curl -sf -o /dev/null http://127.0.0.1:8090
      fi
    }
    if viewer_running; then
      echo "すでに起動しています → http://127.0.0.1:8090"
      [[ "${VOICE_SHELL_NO_GUI:-0}" == "1" ]] || open_gui || true
      exit 0
    fi
    mkdir -p "$STATE_DIR"
    # setsid で切り離す。デーモンが終了時に自分の子を全部 kill するため、
    # 同じ系統にいるとデーモンを止めたときビューアまで落ちる。
    detach "$PY" "$HERE/viewer.py" "$@" \
      > "$STATE_DIR/viewer.out" 2>&1 &
    sleep 2
    if viewer_running; then
      echo "ビューアを起動しました → http://127.0.0.1:8090"
      # 独立したウィンドウで開く（--no-gui なら開かない）
      [[ "${VOICE_SHELL_NO_GUI:-0}" == "1" ]] || open_gui || true
    else
      echo "起動に失敗しました:" >&2; tail -5 "$STATE_DIR/viewer.out" >&2; exit 1
    fi
    ;;
  viewer-stop)
    if have pkill; then
      pkill -f "voice-shell/scripts/viewer\.p[y]" && echo "ビューアを停止しました" \
        || echo "動いていません"
    else
      echo "このOSでは自動停止できません（pkill が無いため）。" >&2
      echo "  タスクマネージャーで viewer.py の python プロセスを終了してください。" >&2
    fi
    ;;
  wait-ready)
    # ブラウザで認識するなら、積むモデルが無いので待つものも無い
    if [[ "$("$PY" "$APP" --resolve-engine "")" == "browser" ]]; then
      echo READY; exit 0
    fi
    # 起動完了（またはエラー）まで待つ
    for _ in $(seq 1 90); do
      if grep -q "聞いています" "$BOOT_LOG" 2>/dev/null; then echo READY; exit 0; fi
      if grep -qE "Traceback|Error:|すでに動いて" "$BOOT_LOG" 2>/dev/null; then
        echo FAILED; tail -5 "$BOOT_LOG" >&2; exit 1
      fi
      sleep 2
    done
    echo TIMEOUT; exit 1
    ;;
  *)
    echo "使い方: voice-shell.sh {start [--engine X] [--no-gui]|stop|status|engines}" >&2
    echo "        voice-shell.sh {listen|listeners|name|hold|live|log-path|wait-ready|viewer}" >&2
    echo "        voice-shell.sh {apple|whisper|remote|remote-conf|remote-log}" >&2
    exit 1
    ;;
esac
