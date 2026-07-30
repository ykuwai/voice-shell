#!/usr/bin/env bash
# 音声プロンプト常駐デーモンのラッパー。
# どのプロジェクトからでも同じコマンドで起動できるようにする。
#
#   voice-shell.sh start [--language Japanese]
#   voice-shell.sh stop
#   voice-shell.sh status
#   voice-shell.sh viewer / viewer-stop
#   voice-shell.sh log-path / wait-ready

set -euo pipefail

# スクリプト自身の場所を基準にする（シンボリックリンク経由でも実体を辿る）
HERE="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"

# Python 環境を探す。VOICE_SHELL_PYTHON で明示指定できる。
find_python() {
  if [[ -n "${VOICE_SHELL_PYTHON:-}" ]]; then echo "$VOICE_SHELL_PYTHON"; return; fi
  # conda / mamba の qwen3-asr 環境を各所から探す
  for base in "$HOME/miniforge3" "$HOME/miniconda3" "$HOME/anaconda3" \
              "$HOME/mambaforge" "/opt/homebrew/Caskroom/miniforge/base" "/opt/conda"; do
    for env in qwen3-asr voice-shell; do
      [[ -x "$base/envs/$env/bin/python" ]] && { echo "$base/envs/$env/bin/python"; return; }
    done
  done
  # 見つからなければ、qwen_asr が入っている python を使う
  for c in python3 python; do
    if command -v "$c" >/dev/null && "$c" -c "import qwen_asr" 2>/dev/null; then
      command -v "$c"; return
    fi
  done
}

PY="$(find_python || true)"
APP="$HERE/voice_daemon.py"

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

case "$cmd" in
  start)
    if "$PY" "$APP" --status | grep -q 稼働中; then
      echo "すでに稼働しています。"; exit 0
    fi
    mkdir -p "$STATE_DIR"
    # GPU を占有する他のプロセスがいると起動に失敗するので先に知らせる
    if pgrep -f "VLLM::EngineCore" >/dev/null; then
      echo "警告: 別のプロセスが GPU を使用中です。" >&2
      echo "  同じ GPU を使う音声プロセスを止めてから再実行してください。" >&2
      exit 1
    fi
    # 古いパスで動いているビューアを片付ける（構成を変えたときの取り残し）
    pkill -f "voice-shell/scripts/viewer\.py" 2>/dev/null || true
    # 日本語に固定する。自動判定だと物音を中国語などに誤認識しやすい（実測）。
    # 英語を話しても認識自体は追従する（単語間に入る読点はビューア側で除去）。
    # 別言語を主に使うなら `voice-shell.sh start --language English` のように渡す。
    nohup "$PY" "$APP" --language Japanese "$@" > "$BOOT_LOG" 2>&1 &
    echo "起動中… (モデル読み込みに1〜2分かかります)"
    echo "  発話ログ: $LOG_FILE"
    echo "  起動ログ: $BOOT_LOG"
    # ビューアも一緒に立ち上げる（毎回 viewer を打つのを忘れないように）。
    # GPU もマイクも使わないので、常駐と同時に動いてよい。
    "$0" viewer
    ;;
  stop)
    "$PY" "$APP" --stop
    # vLLM ワーカーが残ることがあるので確実に落とす
    pgrep -f "VLLM::EngineCore" | xargs -r kill -9 2>/dev/null || true
    "$0" viewer-stop
    ;;
  engine-stop)
    # 認識だけ止めて GPU を解放する。ビューアは残すので、
    # ブラウザから「聞き取りを再開」で戻せる。
    "$PY" "$APP" --stop 2>/dev/null || true
    # PID ファイルは読み込み完了後に書かれる。起動途中で止めると
    # ファイルが無いまま本体が残るので、名前でも確実に落とす。
    pkill -f "voice_daemon\.py --language" 2>/dev/null || true
    sleep 1
    pkill -9 -f "voice_daemon\.py --language" 2>/dev/null || true
    pgrep -f "VLLM::EngineCore" | xargs -r kill -9 2>/dev/null || true
    ;;
  engine-start)
    # 認識だけ立ち上げ直す（ビューアには触らない）。
    # setsid で切り離す。デーモンは終了時に自分の子を全部 kill するので、
    # 呼び出し元（ビューア）にぶら下げると巻き込まれる。
    if "$PY" "$APP" --status | grep -q 稼働中; then
      echo "すでに稼働しています。"; exit 0
    fi
    mkdir -p "$STATE_DIR"
    setsid nohup "$PY" "$APP" --language Japanese "$@" > "$BOOT_LOG" 2>&1 &
    echo "起動中… (モデル読み込みに1〜2分かかります)"
    ;;
  status)
    "$PY" "$APP" --status
    ;;
  log-path)
    echo "$LOG_FILE"
    ;;
  viewer)
    # ログを追尾するだけのビューア。GPU もマイクも使わないので常駐と共存できる。
    if pgrep -f "voice-shell/scripts/viewer.py" >/dev/null; then
      echo "すでに起動しています → http://127.0.0.1:8090"; exit 0
    fi
    mkdir -p "$STATE_DIR"
    # setsid で切り離す。デーモンが終了時に自分の子を全部 kill するため、
    # 同じ系統にいるとデーモンを止めたときビューアまで落ちる。
    setsid nohup "$PY" "$HERE/viewer.py" "$@" \
      > "$STATE_DIR/viewer.out" 2>&1 &
    sleep 2
    if pgrep -f "voice-shell/scripts/viewer.py" >/dev/null; then
      echo "ビューアを起動しました → http://127.0.0.1:8090"
    else
      echo "起動に失敗しました:" >&2; tail -5 "$STATE_DIR/viewer.out" >&2; exit 1
    fi
    ;;
  viewer-stop)
    pkill -f "voice-shell/scripts/viewer.py" && echo "ビューアを停止しました" \
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
    echo "使い方: voice-daemon.sh {start|stop|status|log-path|wait-ready}" >&2
    exit 1
    ;;
esac
