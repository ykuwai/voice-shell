# セットアップ

Claude Code が案内するための手順書。まず環境を調べ、**どれで進めるかユーザーに
確認してから**実行する（勝手に全部入れない）。

## 1. 環境を調べる

```bash
uname -s -m
nvidia-smi --query-gpu=name,memory.total --format=csv 2>/dev/null
command -v conda mamba micromamba
```

| 環境 | 進む節 |
|---|---|
| NVIDIA GPU、VRAM 12GB 以上 | **A** |
| macOS（Apple Silicon） | **B** |
| それ以外（GPU なし・VRAM 不足） | **C** |
| 同じ LAN に GPU 機がある | **E**（そちらに認識だけ任せる。手元は軽いまま） |

クラウドの API に投げる手もある（**D**）。GPU が要らない代わりに音声が
外に出て、従量課金がかかる。手元か家に GPU があるなら E のほうがよい。

## A. NVIDIA GPU

```bash
conda create -n qwen3-asr python=3.12 -y
conda activate qwen3-asr
pip install -U "qwen-asr[vllm]" aiohttp soxr
hf download Qwen/Qwen3-ASR-1.7B
```

録音コマンド: Linux は `sudo apt install alsa-utils`、Windows は `winget install ffmpeg`。

### どのモデルを使うか

モデルページで大きさと対応言語を確認してから決める。要件は更新されるので、
ここに書いた数字ではなく**ページの記載を見る**:

- [Qwen/Qwen3-ASR-1.7B](https://huggingface.co/Qwen/Qwen3-ASR-1.7B) — 精度重視
- [Qwen/Qwen3-ASR-0.6B](https://huggingface.co/Qwen/Qwen3-ASR-0.6B) — 軽量

`hf download <モデル名>` のあと、実際に使う VRAM は起動して確認するのが確実:

```bash
nvidia-smi --query-gpu=memory.used,memory.total --format=csv
```

参考として、この環境では 1.7B + `--max-model-len 16384` で 12.3GB 使った。
足りなければ `--max-model-len 8192` を付けるか 0.6B に変える。

なお vLLM の `max_model_len` は既定 65536 で、KV キャッシュに 7GiB 要求して
16GB でも起動しない。本スキルは 16384 を明示している。

## B. macOS（Apple Silicon）

CUDA が無いので MLX 版を使う。それぞれのページで対応状況と必要メモリを確認する:

- [qwen3-asr-mlx](https://pypi.org/project/qwen3-asr-mlx/)（PyPI）
- [mlx-qwen3-asr](https://github.com/moona3k/mlx-qwen3-asr)

```bash
brew install ffmpeg                      # 録音用
conda create -n qwen3-asr python=3.12 -y && conda activate qwen3-asr
pip install -U qwen3-asr-mlx aiohttp soxr
```

これらは `qwen_asr` と API が違うため、`asr_mic.py` の `load_model()` と
`stream_utterances()` の差し替えが要る（`IDEAS.md` 参照）。ここは未着手なので、
案内するときに現状を伝える。

## C. GPU なし（CPU のみ）

ONNX 版を使う。速度が足りるかはページの記載と実機で確認する:

- [Daumee/Qwen3-ASR-0.6B-ONNX-CPU](https://huggingface.co/Daumee/Qwen3-ASR-0.6B-ONNX-CPU)

```bash
conda create -n qwen3-asr python=3.12 -y && conda activate qwen3-asr
pip install -U onnxruntime librosa tokenizers aiohttp soxr
```

B と同じく差し替えが要る。

## D. クラウドの API を使う（GPU 不要）

モデルを手元で動かさず、音声を API に送って認識させる。GPU が無くても使える。
**音声はその会社に送られる**ので、ローカル完結ではなくなる点は伝えること。

```bash
pip install websockets soxr aiohttp     # モデルも vLLM も要らない
export DEEPGRAM_API_KEY=...             # 使う会社のキーだけでよい
voice-shell.sh start --engine deepgram
```

| `--engine` | キーの環境変数 | 特徴 |
|---|---|---|
| `deepgram` | `DEEPGRAM_API_KEY` | 音声認識専業。速い。日本語と英語の混在に対応 |
| `soniox` | `SONIOX_API_KEY` | $0.12/時と安い。16kHz をそのまま送れる |
| `assemblyai` | `ASSEMBLYAI_API_KEY` | **日本語では使えない**（下記） |
| `openai` | `OPENAI_API_KEY` | 課金は音声の長さのみ。一日中開けておく用途に向く |

**AssemblyAI は日本語で使えない**: リアルタイム認識が対応するのは英語・
スペイン語・ドイツ語・フランス語・ポルトガル語・イタリア語だけで、日本語は
録音済みの音声にしか対応していない。日本語で話すなら他の三つを使うこと。

**課金の形に注意**: 接続している時間で課金する会社がある（AssemblyAI は
公式に明記）。voice-shell はマイクを開けっぱなしにするため、黙っている間は
接続しない実装にしてあるが、料金は最初に短く試して確かめてほしい。

**未検証**: この経路は API キーが手元に無いため実際に接続して確かめていない。
各社のドキュメントに沿って書いてある。最初に使うときは短い発話で試すこと。

## E. 家の GPU 機に認識だけ任せる（GPU 不要・課金なし）

ノート PC のように GPU が非力な端末で使うとき、認識だけを家の GPU 機に
投げる。クラウドの API と違って**音声は家から出ない**し、従量課金もない。

```
ノート PC                          GPU 機（同じ LAN）
┌────────────────────┐           ┌──────────────────┐
│ Claude Code        │           │ voice_daemon.py  │
│ voice-shell スキル  │ ──音声→   │   --remote       │
│ マイクを拾う        │ ←文字─    │ Qwen3-ASR（GPU） │
└────────────────────┘           └──────────────────┘
```

### GPU 機の側（受ける方）

A〜C のどれかでセットアップを済ませてから、接続を許すトークンを決める。

```bash
voice-shell.sh remote-conf          # 設定ファイルの場所が出る
```

そのファイルに、繋いでよい端末を書く。値が発話ログのファイル名になる。

```jsonc
{
  "bind": "192.168.0.10",     // GPU 機自身の LAN アドレス
  "port": 8091,
  "tokens": {
    "好きな長い文字列": "laptop"
  }
}
```

`bind` に `0.0.0.0` と書けばどの経路からでも届くが、VPN や別セグメントにも
開くので、使う経路の IP を書くほうがよい。`ip -4 -o addr` で確認できる。

```bash
voice-shell.sh remote               # ローカルのマイクと LAN の両方を受ける
```

起動時に出る「待ち受け: ws://...」のアドレスを、ノート側で使う。

ファイアウォールがあれば LAN からのポートだけ開ける。

```bash
sudo ufw allow from 192.168.0.0/24 to any port 8091 proto tcp
```

### ノート PC の側（使う方）

**モデルも vLLM も要らない。** 音を拾って送るだけなので軽い。

```bash
pip install websockets soxr aiohttp sounddevice numpy

export VOICE_SHELL_ENGINE=home-lan
export VOICE_SHELL_SERVER=ws://192.168.0.10:8091/v1/realtime   # 上で出たアドレス
export VOICE_SHELL_TOKEN=好きな長い文字列                        # 上で決めたトークン

voice-shell.sh start
```

起動時にこう出れば繋がっている。

```
認識エンジン: home-lan（家の LAN にある GPU 機に認識だけ任せる（課金なし））
  音声は ws://192.168.0.10:8091/v1/realtime に送られます。
```

### 届いた発話はどこに残るか

GPU 機の側で、端末ごとに分かれて残る。

```bash
voice-shell.sh remote-log           # 置き場が出る
tail -f "$(voice-shell.sh remote-log)/laptop.jsonl"
```

GPU 機自身のマイクで喋ったぶん（`utterances.jsonl`）とは**別のファイル**に
する。あちらは動いている Claude Code セッションへの入力そのもので、別の
端末の音声が混ざると、他人の発言がそのまま指示として実行されてしまう。

### つまずいたら

| 症状 | 見るところ |
|---|---|
| 接続できない | GPU 機で `voice-shell.sh status` が「稼働中」か |
| 接続できない | GPU 機で `ss -tlnp \| grep 8091` の待ち受けアドレス |
| 接続できない | ファイアウォールにポートのルールが入っているか |
| すぐ切れる | トークンが合っているか（違うと 1008 で切られる） |
| `local` のまま | 環境変数を設定した後にシェルを開き直したか |
| 急に繋がらない | 有線と無線を切り替えると GPU 機の IP が変わる |

### 同時に使えるか

推論は1つずつ順に処理される（モデルが1つしかないため）。ただし1発話
あたり 0.1〜0.5 秒しかかからず、人は喋り続けないので、数人なら待たされる
感じはしない。4接続を同時に投げたときは全体で 0.18 秒だった。

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
| `Python が見つかりません` | `export VOICE_SHELL_PYTHON=/path/to/envs/qwen3-asr/bin/python` |
| `arecord`／`ffmpeg` が無い | 上の「録音コマンド」を入れる |
| 起動が `FAILED` | GPU を別プロセスが使用中。`pgrep -f VLLM::EngineCore` で確認 |
| VRAM 不足 | `--max-model-len 8192`、または 0.6B に変える |
| 喋っても届かない | しきい値が高い。ビューアのメーターを見て `--silence-threshold` を下げる |
| 物音で勝手に届く | しきい値が低い。上げる |
| マイクを変えたい | `arecord -L`（Linux）等で一覧を出し `--device` に渡す |

## 出典

- [QwenLM/Qwen3-ASR](https://github.com/QwenLM/Qwen3-ASR) — 公式リポジトリ
- [Qwen3-ASR Technical Report](https://arxiv.org/html/2601.21337v1)
