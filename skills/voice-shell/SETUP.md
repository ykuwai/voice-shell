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
| `assemblyai` | `ASSEMBLYAI_API_KEY` | 日本語は上位モデル限定。接続時間で課金される |
| `openai` | `OPENAI_API_KEY` | 課金は音声の長さのみ。一日中開けておく用途に向く |

**課金の形に注意**: 接続している時間で課金する会社がある（AssemblyAI は
公式に明記）。voice-shell はマイクを開けっぱなしにするため、黙っている間は
接続しない実装にしてあるが、料金は最初に短く試して確かめてほしい。

**未検証**: この経路は API キーが手元に無いため実際に接続して確かめていない。
各社のドキュメントに沿って書いてある。最初に使うときは短い発話で試すこと。

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
