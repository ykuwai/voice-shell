#!/bin/sh
# いま音声を聞いている Claude Code を一覧にする。
#
# 発話は utterances.jsonl に書かれ、各セッションが tail で読む。つまり
# tail の本数 = 聞いている口の数。ターミナルを閉じ忘れると、喋るたびに
# 複数のセッションが同じ指示を受け取り、同じファイルを取り合う。
#
#   sh who-listens.sh

_base="${XDG_RUNTIME_DIR:-/tmp}"
_state="$_base/voice-shell"
[ ! -d "$_state" ] && [ -d "$_base/qwen-voice" ] && _state="$_base/qwen-voice"
LOG="${VOICE_SHELL_LOG:-$_state/utterances.jsonl}"
[ -f "$LOG" ] || { echo "発話ログが見つかりません: $LOG"; exit 1; }

echo "発話ログ: $LOG"
echo

n=0
for pid in $(lsof -t "$LOG" 2>/dev/null); do
  # 書き込み側（デーモン）と読み出し側（セッション）を分ける
  cmd=$(ps -o comm= -p "$pid" 2>/dev/null)
  case "$cmd" in *tail*) ;; *) continue ;; esac

  n=$((n + 1))
  # tail → シェル → claude 本体、と親をたどる
  cur=$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' ')
  claude_pid=""
  i=0
  while [ -n "$cur" ] && [ "$cur" != "1" ] && [ $i -lt 6 ]; do
    if ps -o command= -p "$cur" 2>/dev/null | grep -q "^claude"; then
      claude_pid="$cur"; break
    fi
    cur=$(ps -o ppid= -p "$cur" 2>/dev/null | tr -d ' ')
    i=$((i + 1))
  done

  if [ -n "$claude_pid" ]; then
    started=$(ps -o lstart= -p "$claude_pid" 2>/dev/null)
    cwd=$(lsof -a -p "$claude_pid" -d cwd -Fn 2>/dev/null | grep '^n' | cut -c2-)
    echo "  [$n] Claude PID $claude_pid"
    echo "      起動: $started"
    echo "      場所: ${cwd:-不明}"
  else
    echo "  [$n] tail PID $pid（親の Claude をたどれませんでした）"
  fi
done

echo
if [ "$n" -eq 0 ]; then
  echo "聞いているセッションはありません。"
elif [ "$n" -eq 1 ]; then
  echo "1つだけです。正常。"
else
  echo "!! $n つが同じ音声を受け取っています。"
  echo "   同じ指示が全部に届き、同じファイルを取り合います。"
  echo "   使っていない方のターミナルを閉じてください。"
fi
