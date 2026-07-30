# セットアップ手順（Claude Code が案内するための手順書）

ユーザーの環境を確かめてから、当てはまる節だけを案内する。
**勝手に全部入れない** — GPU の有無やインストーラの好みで選択肢が変わるため、
どれで進めるかユーザーに確認してから実行する。

## 1. 環境を調べる

```bash
uname -s -m                                   # OS と CPU
nvidia-smi --query-gpu=name,memory.total --format=csv 2>/dev/null   # NVIDIA GPU
python3 -c "import sys; print(sys.version)"   # Python
command -v conda mamba micromamba             # conda 系
```

結果から下表のどれに当たるか判断する。

| 条件 | 進む節 | 音声認識をどこで動かすか |
|---|---|---|
| NVIDIA GPU が 12GB 以上 | **A** | GPU（いちばん速い） |
| macOS + Apple Silicon | **B** | Metal（MLX） |
| 上記以外（GPU なし・Windows のみ等） | **C** | CPU（ONNX、0.6B） |

いずれも音声はローカルで処理し、クラウドに送らない。

## A. NVIDIA GPU（Linux / Windows）

VRAM 12GB 以上で 1.7B が動く。8GB 前後なら `--max-model-len 8192` を付けるか
0.6B（`--model Qwen/Qwen3-ASR-0.6B`）にする。

```bash
conda create -n qwen3-asr python=3.12 -y
conda activate qwen3-asr
pip install -U "qwen-asr[vllm]" aiohttp soxr
hf download Qwen/Qwen3-ASR-1.7B          # 約3.5GB
```

録音コマンドを入れる:

| OS | コマンド |
|---|---|
| Linux | `sudo apt install alsa-utils`（`arecord`） |
| Windows | `winget install ffmpeg` |

## B. macOS（Apple Silicon）

CUDA は使えないので MLX 版を使う。Metal で動く。

```bash
brew install ffmpeg                      # 録音用
conda create -n qwen3-asr python=3.12 -y
conda activate qwen3-asr
pip install -U qwen3-asr-mlx aiohttp soxr
```

**注意**: MLX 版は `qwen_asr` とは別 API なので、`asr_mic.py` の
`load_model()` / `stream_utterances()` を MLX 用に差し替える必要がある。
まだ実装していない（`IDEAS.md` の「エンジンの差し替え」）。
未実装であることをユーザーに伝え、勝手に動くふりをしない。

メモリの目安: 0.6B は 8GB でも動く。1.7B は 16GB 以上が安心。

## C. GPU なし（CPU のみ）

ONNX 版の 0.6B を使う。Intel N100 クラスでも実時間に間に合う（RTF 0.71 の報告）。

```bash
conda create -n qwen3-asr python=3.12 -y
conda activate qwen3-asr
pip install -U onnxruntime librosa tokenizers aiohttp soxr
hf download Daumee/Qwen3-ASR-0.6B-ONNX-CPU
```

**注意**: B と同じく、エンジン差し替えが未実装。伝えたうえで、
NVIDIA GPU が使える別マシンがあるならそちらを勧める。

## 2. スキルを認識させる

リポジトリを置いた場所からリンクを張る:

```bash
ln -s "$(pwd)/skills/voice-shell" ~/.claude/skills/voice-shell
```

`npx skills add ykuwai/voice-shell` で入れた場合はこの手順は不要。

## 3. Python の場所を教える（自動で見つからない場合）

`voice-shell.sh` は conda の `qwen3-asr` 環境を自動で探す。
`Qwen3-ASR が入った Python が見つかりません` と出たら:

```bash
export VOICE_SHELL_PYTHON=/path/to/envs/qwen3-asr/bin/python
```

`~/.bashrc` や `~/.zshrc` に書いておけば次回も効く。

## 4. マイクを確かめる

既定のデバイスは Linux `pipewire` / macOS `:0` / Windows `audio=default`。
別のマイクを使うなら一覧から選んで `--device` に渡す:

```bash
arecord -L                                        # Linux
ffmpeg -f avfoundation -list_devices true -i ""   # macOS
ffmpeg -list_devices true -f dshow -i dummy       # Windows
```

無音判定のしきい値（`--silence-threshold`、既定 0.054）はマイクのノイズフロアに
合わせる。ビューアのメーターに縦線でしきい値が出るので、声を出したときバーが
それを越えるか見て調整する。越えないなら下げる、無音でも越えるなら上げる。

## 5. 動かしてみる

```bash
${CLAUDE_SKILL_DIR}/scripts/voice-shell.sh start
${CLAUDE_SKILL_DIR}/scripts/voice-shell.sh wait-ready
```

`READY` が出たら http://127.0.0.1:8090 を開いて、話しかけてもらう。

## つまずきやすいところ

| 症状 | 原因と対処 |
|---|---|
| `Python が見つかりません` | 手順3で `VOICE_SHELL_PYTHON` を設定 |
| `arecord が見つかりません` | `alsa-utils` を入れる（Linux） |
| `ffmpeg が見つかりません` | `brew install ffmpeg` / `winget install ffmpeg` |
| 起動が `FAILED` | GPU を別プロセスが使用中。`pgrep -f VLLM::EngineCore` で確認 |
| VRAM 不足のエラー | `--max-model-len 8192` を付ける、または 0.6B に変える |
| 喋っても何も届かない | しきい値が高すぎる。ビューアのメーターを見て `--silence-threshold` を下げる |
| 物音で勝手に届く | しきい値が低すぎる。上げる |
