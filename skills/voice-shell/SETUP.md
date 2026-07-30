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
| macOS（Apple Silicon） | **B**（※未実装） |
| それ以外（GPU なし・VRAM 不足） | **C**（※未実装） |

## A. NVIDIA GPU — 動作確認済み

```bash
conda create -n qwen3-asr python=3.12 -y
conda activate qwen3-asr
pip install -U "qwen-asr[vllm]" aiohttp soxr
hf download Qwen/Qwen3-ASR-1.7B
```

録音コマンド: Linux は `sudo apt install alsa-utils`、Windows は `winget install ffmpeg`。

**モデル**: [Qwen/Qwen3-ASR-1.7B](https://huggingface.co/Qwen/Qwen3-ASR-1.7B)（約3.5GB、Apache-2.0）
VRAM が足りなければ [Qwen/Qwen3-ASR-0.6B](https://huggingface.co/Qwen/Qwen3-ASR-0.6B) を
`--model` に指定するか、`--max-model-len 8192` を付ける。

**必要 VRAM**: 1.7B + `--max-model-len 16384` で実測 12.3GB（RTX 4080 SUPER で確認）。
vLLM の既定 65536 では KV キャッシュに 7GiB 要求され 16GB でも起動しないので、
本スキルは 16384 を明示している。

## B. macOS（Apple Silicon）— エンジン差し替えが未実装

**この環境ではまだ動かない。** 案内する前にそのことを伝える。

CUDA が無いので MLX 版を使うことになる:
[qwen3-asr-mlx](https://pypi.org/project/qwen3-asr-mlx/) または
[mlx-qwen3-asr](https://github.com/moona3k/mlx-qwen3-asr)。
どちらも `qwen_asr` とは別 API なので、`asr_mic.py` の `load_model()` と
`stream_utterances()` を差し替える必要がある（`IDEAS.md` 参照）。

## C. GPU なし — エンジン差し替えが未実装

**この環境ではまだ動かない。** 案内する前にそのことを伝える。

ONNX 版の 0.6B が候補:
[Daumee/Qwen3-ASR-0.6B-ONNX-CPU](https://huggingface.co/Daumee/Qwen3-ASR-0.6B-ONNX-CPU)。
Intel N100 で RTF 0.71（実時間に間に合う）の報告がある。B と同じく差し替えが必要。

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
