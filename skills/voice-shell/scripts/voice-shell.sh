#!/usr/bin/env bash
# 音声プロンプト常駐デーモンのラッパー。
# どのプロジェクトからでも同じコマンドで起動できるようにする。
#
#   voice-shell.sh start [--language Japanese]
#   voice-shell.sh stop
#   voice-shell.sh status
#   voice-shell.sh viewer / viewer-stop
#   voice-shell.sh log-path / wait-ready
#   voice-shell.sh whisper                Whisper で認識する（固有名詞に強い）
#   voice-shell.sh apple                  macOS 26 付属の認識で動かす（軽い）
#   voice-shell.sh remote                 LAN の端末からも受ける
#   voice-shell.sh remote-conf            設定ファイルの場所
#   voice-shell.sh remote-log             届いた発話の置き場

set -euo pipefail

# スクリプト自身の場所を基準にする（シンボリックリンク経由でも実体を辿る）
HERE="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"

# Python 環境を探す。VOICE_SHELL_PYTHON で明示指定できる。
find_python() {
  if [[ -n "${VOICE_SHELL_PYTHON:-}" ]]; then echo "$VOICE_SHELL_PYTHON"; return; fi
  # リポジトリ直下の .venv（conda を使わない構成。macOS はこちらが標準）
  if [[ -x "$HERE/../../../.venv/bin/python" ]]; then
    echo "$HERE/../../../.venv/bin/python"; return
  fi
  # conda / mamba の qwen3-asr 環境を各所から探す
  for base in "$HOME/miniforge3" "$HOME/miniconda3" "$HOME/anaconda3" \
              "$HOME/mambaforge" "/opt/homebrew/Caskroom/miniforge/base" "/opt/conda"; do
    for env in qwen3-asr voice-shell; do
      [[ -x "$base/envs/$env/bin/python" ]] && { echo "$base/envs/$env/bin/python"; return; }
    done
  done
  # 見つからなければ、認識エンジンが入っている python を使う。
  # apple エンジン（macOS 26 付属）は OS 側が認識するので numpy だけあればよい。
  for c in python3 python; do
    command -v "$c" >/dev/null || continue
    if "$c" -c "import qwen_asr" 2>/dev/null || \
       "$c" -c "import mlx_qwen3_asr" 2>/dev/null || \
       { [[ "$(uname)" == Darwin ]] && "$c" -c "import numpy" 2>/dev/null; }; then
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
  local f="${XDG_RUNTIME_DIR:-/tmp}/qwen-voice/engine"
  [[ -s "$f" ]] && echo "--engine $(cat "$f")"
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
  echo "Qwen3-ASR が入った Python が見つかりません。" >&2
  echo "  セットアップ手順は README を参照してください。" >&2
  echo "  場所を直接指定する場合: export VOICE_SHELL_PYTHON=/path/to/python" >&2
  exit 1
fi
STATE_DIR="${XDG_RUNTIME_DIR:-/tmp}/qwen-voice"
LOG_FILE="$STATE_DIR/utterances.jsonl"
BOOT_LOG="$STATE_DIR/daemon.out"

cmd="${1:-status}"; shift || true

# 発話ログを追尾しているセッションを一覧する。
#
# Monitor を止め忘れると、古いセッションに音声が届き続ける。tail は -F なので
# デーモンを入れ直してもつながり直してしまい、本人は気づけない。実際に8日前の
# セッションが生きていて、同じ発話が2つのセッションへ配られていたことがある。
list_listeners() {
  local pids found=0
  pids=$(pgrep -f "tail .*$(basename "$LOG_FILE")" 2>/dev/null || true)
  for pid in $pids; do
    # tail の親はラッパーのシェル、その親が claude 本体
    local sh cl target start cwd
    sh=$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d " ")
    cl=$(ps -o ppid= -p "${sh:-0}" 2>/dev/null | tr -d " ")
    target=${cl:-$pid}
    start=$(ps -o lstart= -p "$target" 2>/dev/null | tr -s " ")
    cwd=$(lsof -a -p "$target" -d cwd -Fn 2>/dev/null | sed -n "s/^n//p")
    printf "  claude %s（tail %s）\n" "$target" "$pid"
    printf "    起動 : %s\n" "${start:-不明}"
    printf "    場所 : %s\n" "${cwd:-不明}"
    printf "    切る : kill %s\n" "$pid"
    found=1
  done
  [ "$found" = 1 ] || echo "  なし（音声はどこにも届いていません）"
}

case "$cmd" in
  start)
    # --engine を明示せずに start したら Qwen3-ASR に戻す
    [[ "$*" == *--engine* ]] || rm -f "$STATE_DIR/engine"
    if "$PY" "$APP" --status | grep -q 稼働中; then
      echo "すでに稼働しています。"; exit 0
    fi
    mkdir -p "$STATE_DIR"
    # GPU を占有する他のプロセスがいると起動に失敗するので先に知らせる。
    # パターンを [V] と書くのは自己マッチ避け。pgrep -f はコマンドライン全体を
    # 見るため、素で書くとこの行を実行しているシェル自身に当たって誤検知する。
    if pgrep -f "[V]LLM::EngineCore" >/dev/null; then
      echo "警告: 別のプロセスが GPU を使用中です。" >&2
      echo "  同じ GPU を使う音声プロセスを止めてから再実行してください。" >&2
      exit 1
    fi
    # 古いパスで動いているビューアを片付ける（構成を変えたときの取り残し）
    pkill -f "voice-shell/scripts/viewer\.p[y]" 2>/dev/null || true
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
    # 起動のときに気づけるようにここで知らせる。
    if [ -n "$(pgrep -f "tail .*$(basename "$LOG_FILE")" 2>/dev/null || true)" ]; then
      echo
      echo "※ すでにこの音声を聞いているセッションがあります:"
      list_listeners
      echo "  身に覚えが無ければ、上の kill で切ってください。"
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
    pkill -f "voice_daemon\.p[y] --language" 2>/dev/null || true
    sleep 1
    pkill -9 -f "voice_daemon\.p[y] --language" 2>/dev/null || true
    kill_engine_cores
    ;;
  engine-start)
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
    mkdir -p "$STATE_DIR"
    echo whisper > "$STATE_DIR/engine"
    "$0" start --engine whisper "$@"
    ;;
  apple)
    # macOS 26 付属のオンデバイス認識を使う。GPU メモリを積まないので Mac 向け。
    mkdir -p "$STATE_DIR"
    echo apple > "$STATE_DIR/engine"
    "$0" start --engine apple "$@"
    ;;
  remote)
    # LAN の端末からも音声を受ける形で立ち上げる。
    # 設定は ~/.config/voice-shell/remote.json（無ければ雛形を作って止まる）。
    "$0" start --remote "$@"
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
    "$PY" "$APP" --status
    echo
    echo "この音声を聞いているセッション:"
    list_listeners
    ;;
  listeners)
    list_listeners
    ;;
  log-path)
    echo "$LOG_FILE"
    ;;
  viewer)
    # ログを追尾するだけのビューア。GPU もマイクも使わないので常駐と共存できる。
    if pgrep -f "voice-shell/scripts/viewer\.p[y]" >/dev/null; then
      echo "すでに起動しています → http://127.0.0.1:8090"; exit 0
    fi
    mkdir -p "$STATE_DIR"
    # setsid で切り離す。デーモンが終了時に自分の子を全部 kill するため、
    # 同じ系統にいるとデーモンを止めたときビューアまで落ちる。
    detach "$PY" "$HERE/viewer.py" "$@" \
      > "$STATE_DIR/viewer.out" 2>&1 &
    sleep 2
    if pgrep -f "voice-shell/scripts/viewer\.p[y]" >/dev/null; then
      echo "ビューアを起動しました → http://127.0.0.1:8090"
    else
      echo "起動に失敗しました:" >&2; tail -5 "$STATE_DIR/viewer.out" >&2; exit 1
    fi
    ;;
  viewer-stop)
    pkill -f "voice-shell/scripts/viewer\.p[y]" && echo "ビューアを停止しました" \
      || echo "動いていません"
    ;;
  wait-ready)
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
    echo "使い方: voice-shell.sh {start|stop|status|listeners|log-path|wait-ready}" >&2
    echo "        voice-shell.sh {apple|whisper|remote|remote-conf|remote-log}" >&2
    exit 1
    ;;
esac
