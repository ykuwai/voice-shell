---
name: "voice-shell"
description: "音声でプロンプトを送れるようにする。マイクを聞き続ける常駐プロセスを起動し、ユーザーが喋った内容を Monitor 経由で受け取って指示として扱う。「音声モード」「声で指示したい」「マイクで話す」「ハンズフリー」「音声で操作」、または \"voice mode\", \"talk to me\", \"hands-free\", \"dictate my prompts\", \"speak instead of typing\" と言われたときに使う。停止は「音声モード終了」/ \"stop voice mode\"。「voice-shell をセットアップして」と言われた場合は SETUP.md の手順で環境（NVIDIA GPU / Apple Silicon / CPU のみ）を判別して案内する。"
version: "0.1.0"
license: "MIT"
argument-hint: "[start | stop | status]"
allowed-tools:
  - Bash(${CLAUDE_SKILL_DIR}/scripts/voice-shell.sh *)
  - Bash(tail *)
  - Bash(cat *)
  - Monitor
---

# 音声プロンプトモード

ユーザーが喋った内容を、キーボードを使わずにプロンプトとして受け取る。

裏で Qwen3-ASR の常駐プロセスがマイクを聞き、発話が確定するたびに JSONL へ1行追記する。
そのログを Monitor で tail し、届いた行をユーザーからの指示として扱う。

引数: `$ARGUMENTS`（`start` / `stop` / `status` / `setup`。省略時は `start`）

## まだセットアップされていないとき

`start` が「Python が見つかりません」で失敗した場合、またはユーザーが
「セットアップして」と言った場合は [SETUP.md](SETUP.md) の手順で案内する。

いま動くのは **NVIDIA GPU（VRAM 12GB 以上）の環境だけ**。Apple Silicon と
CPU のみの環境はエンジン差し替えが未実装なので、その場で正直に伝える。

## 開始する

1. デーモンを起動する:

   ```bash
   ${CLAUDE_SKILL_DIR}/scripts/voice-shell.sh start
   ```

2. 起動完了まで待つ（モデル読み込みに1〜2分かかる。この間は他の作業を進めてよい）:

   ```bash
   ${CLAUDE_SKILL_DIR}/scripts/voice-shell.sh wait-ready
   ```

   `FAILED` が返ったら、表示されたエラーをユーザーに伝える。よくある原因は
   GPU の二重使用（webapp.py 等が動いている）。

3. 発話ログを Monitor で監視する。**`persistent: true` を必ず指定する**
   （音声モードはセッション中ずっと続くため）:

   `-F`（大文字）にすること。デーモンを再起動するとログが作り直されるため、
   `-f` だと古いファイルを見続けて音声が届かなくなる。

   ```
   Monitor(
     command: "tail -F -n 0 \"$(${CLAUDE_SKILL_DIR}/scripts/voice-shell.sh log-path)\"",
     description: "ユーザーの音声プロンプト",
     persistent: true
   )
   ```

**モニターは1つだけにする** — 起動し直すときは古い Monitor を必ず TaskStop で
止める。2つ生きていると同じ発話が二重に届く。

## 音声が届いたときの扱い

Monitor から届く各行は JSON。本文だけが入っている:

```json
{"text": "テストを実行して"}
```

ビューアで手直ししてから送られた行には `"edited": true` が付く。
これは**ユーザーが意図して整えた文**なので、認識誤りとして読み替えず素直に受け取る。

`text` を**ユーザーからの指示として扱い、通常どおり実行する**。以下に注意する:

- **認識誤りを織り込む** — 音声認識なので固有名詞や技術用語は崩れる。
  「クロードコード」→ Claude Code、「ギット」→ git のように、文脈から補って解釈する。
  どうしても意味が取れない場合だけ聞き返す。
- **フィラーは無視する** — 「あの」「まあ」「えっと」は意味を持たない。
- **短い相槌はデーモンが捨てている** — 「はい」「うん」等の単独発話は
  物音を拾った誤認識のことが多いため、そもそも届かない（`voice_daemon.py` の
  `NOISE_ONLY`）。それでも意味の薄い行が来たら、指示として扱わず待つ。
- **細切れの発話はつなげて解釈する** — 1文が複数行に分かれて届くことがある。
  文が途中で切れている場合は、続きが来るのを待ってからまとめて解釈する。
- **破壊的な操作は必ず確認する** — 音声は誤認識しうるので、削除・push・
  デプロイ等は実行前に「〜でよろしいですか」と確認する。
- **イベントはユーザーの発言だが、返答を催促するものではない** — 作業中に
  届いたら、いま行っている作業を終えてから対応してよい。

## ライブビューア

`start` で一緒に立ち上がる（**http://127.0.0.1:8090**）。起動を伝えるときは
この URL も併せて案内する。ログを追尾するだけで GPU もマイクも使わないため、
常駐と同時に動いてよい。

できること:
- 認識途中のテキストがリアルタイムに伸びる
- 各発話が「送信済み」か「手直し送信」かガターに表示される
- **マイクを切る** — 切っている間の発話はどこにも残らない（別作業中に使う）
- **手直ししてから送る** — 発話がテキストエリアに溜まり、直して「送信する」を
  押すと届く（誤認識の修正用）。この経路で送った行には `"edited": true` が付く

```bash
${CLAUDE_SKILL_DIR}/scripts/voice-shell.sh viewer        # → http://127.0.0.1:8090
${CLAUDE_SKILL_DIR}/scripts/voice-shell.sh viewer-stop
```

## 状態を確認する

```bash
${CLAUDE_SKILL_DIR}/scripts/voice-shell.sh status
```

## 停止する

```bash
${CLAUDE_SKILL_DIR}/scripts/voice-shell.sh stop
```

停止したら Monitor も TaskStop で止める。GPU メモリ（約12GB）が解放される。

## ユーザー辞書

誤認識しやすい語の言い換えと、無視する発話を登録できる。ビューアの「辞書」から
編集し、保存すると**次の発話から効く**（デーモンの再起動は不要）。

実体は `~/.config/voice-shell/dictionary.json`。CSV の読み込み・書き出しもできる。
ユーザーが同じ誤認識を繰り返し直しているようなら、辞書への登録を提案してよい。

## 制約

- **GPU を約12GB使う** — 同じ GPU を使う別の音声プロセスとは同時に動かせない
- マイクは `arecord`（Linux）または `ffmpeg`（macOS / Windows）経由で取得する
- セットアップが済んでいない環境では `start` が「Python が見つかりません」で
  失敗する。その場合はリポジトリの README のセットアップ手順を案内する
