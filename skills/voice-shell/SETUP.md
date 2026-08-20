# セットアップ

Claude Code が案内するための手順書。まず環境を調べ、**どれで進めるかユーザーに
確認してから**実行する（勝手に全部入れない）。

**多くの場合、何も入れなくてよい。** 既定は Chrome の Web Speech API で、
`pip install numpy aiohttp` だけで動く。モデルの読み込みも待ち時間も無い。
ただし**音声は認識のため Google のサーバへ送られる**。

以下は、手元だけで完結させたい場合や、画面を開かずに使いたい場合の手順。

## 1. 環境を調べる

```bash
uname -s -m
sw_vers -productVersion 2>/dev/null                              # macOS のとき
nvidia-smi --query-gpu=name,memory.total --format=csv 2>/dev/null
```

| 環境 | 進む節 |
|---|---|
| まず試したいだけ、または非力な機械 | **入れるものは無い**（既定のブラウザ認識） |
| macOS 26 以降 | **A**。OS 付属の認識で、モデルを落とさずに動く |
| それ以外、または固有名詞に強くしたい | **B**。Whisper を手元で動かす |

A も B も音声はこの機械から出ない。**手元で動かせるのはこの 2 つだけ。**

## A. macOS 26 以降（OS 付属の認識）

`SpeechAnalyzer` と `SpeechTranscriber` を使う（`engine_apple.py`）。
`--engine apple` で動く。

```bash
brew install ffmpeg                      # 録音用
cd <このリポジトリ>
python3 -m venv .venv                    # Python 3.10〜3.13
.venv/bin/pip install -U numpy aiohttp soxr
```

Swift のヘルパ（`speech_helper.swift`）を初回起動時に自動でビルドするので、
Xcode か Command Line Tools が要る。

```bash
xcode-select --install                   # 入っていなければ
swiftc --version                         # macOS 26 SDK が見えるか確認
```

日本語の音声認識モデルは OS が初回に自動で落としてくる（数十秒）。
2 回目以降は端末に残るので待ち時間はない。

メモリは OS 側が持つので、この機械では抱えない。起動は 1 秒未満、
3.5 秒の発話の認識に 0.1 秒ほど（M4 Pro の実測）。

**macOS 25 以前には `SpeechTranscriber` が無い。** その場合は B へ進む。

## B. Whisper（faster-whisper）

`--engine whisper` で動く（`whisper_engine.py`）。中身は
[faster-whisper](https://github.com/SYSTRAN/faster-whisper)（CTranslate2 版の
Whisper）で、OS を選ばない。

```bash
cd <このリポジトリ>
python3 -m venv .venv                    # Python 3.10〜3.13
.venv/bin/pip install -U faster-whisper aiohttp soxr numpy
```

NVIDIA GPU があるなら、そのまま既定で動く。

```bash
voice-shell.sh whisper
```

CPU しか無いなら、モデルを小さくして精度を落とす場所を指定する。

```bash
voice-shell.sh whisper --model base --whisper-device cpu --whisper-compute int8
```

モデルは初回起動時に Hugging Face から自動で落ちてくる（`base` で数十 MB から
100MB 程度）。`--whisper-compute` は精度と速度の兼ね合いで、CPU なら `int8`、
GPU なら `float16` を使う。

### どのモデルを使うか

既定は `large-v3-turbo`。**GPU の無い CPU では重すぎる**ので、4 コア CPU の
実測では `base` が実用的（RTF 約0.15）。`small` は RTF 約0.76 で少し重め。

`--model` は Hugging Face の名前も、手元に置いたフォルダの場所も受ける。
その言語に合わせて調整したモデルを持っているなら、そのまま渡せる。

```bash
voice-shell.sh whisper --model kotoba-tech/kotoba-whisper-v2.0
voice-shell.sh whisper --model /path/to/my-model
```

一度渡したモデルは覚えるので、次からは `start` だけでよい
（`~/.config/voice-shell/config.json`）。既定に戻すときは `--model ""` を渡す。

覚えるのはモデルだけ。`--whisper-device` と `--whisper-compute` は覚えないので、
CPU で使うなら毎回渡す。

Apple のオンデバイス認識との違いは、固有名詞に強いこと、騒がしい場所や
複数人の声でも崩れにくいこと。代わりに起動が遅く、モデルのぶんのメモリを使う。

## 共通

`voice-shell.sh` はリポジトリ直下の `.venv` を自動で見つけるので、
`VOICE_SHELL_PYTHON` の設定は不要。

録音の道具が要る。macOS と Windows は `ffmpeg`、Linux は `arecord`。

```bash
brew install ffmpeg              # macOS
sudo apt install alsa-utils      # Linux
winget install ffmpeg            # Windows
```

macOS では初回起動時に、ターミナルへマイクの許可を求めるダイアログが出るので
許可してもらう（ffmpeg が avfoundation 経由で録音するため）。認識そのものは
マイクを触らないので、追加の許可は要らない。

## 2. スキルを認識させる

```bash
ln -s "$(pwd)/skills/voice-shell" ~/.claude/skills/voice-shell
```

`npx skills add ykuwai/voice-shell` で入れた場合は不要。

## 3. 動かす

```bash
${CLAUDE_SKILL_DIR}/scripts/voice-shell.sh start
${CLAUDE_SKILL_DIR}/scripts/voice-shell.sh wait-ready
```

`READY` が出たら http://127.0.0.1:8090 を開いて話しかけてもらう。

## つまずいたら

| 症状 | 対処 |
|---|---|
| `Python が見つかりません` | `export VOICE_SHELL_PYTHON=/path/to/.venv/bin/python` |
| `arecord`／`ffmpeg` が無い | 上の「共通」で入れる |
| 起動が `FAILED` | `voice-shell.sh status` と `daemon.out` の末尾を見る |
| Whisper が遅い | モデルを小さくする（`--model base`）。CPU なら `--whisper-compute int8` |
| 喋っても届かない | しきい値が高い。ビューアのメーターを見て `--silence-threshold` を下げる |
| 物音で勝手に届く | しきい値が低い。上げる |
| マイクを変えたい | `arecord -L`（Linux）等で一覧を出し `--device` に渡す |
