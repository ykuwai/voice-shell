# voice-shell — 声で Claude Code に指示を出す

Claude Code に**話しかけて指示を出す**ための仕組み。キーボードは要らない。

Alibaba Qwen チームの音声認識モデル **Qwen3-ASR-1.7B**（Apache-2.0）をローカルで動かし、
発話が確定するたびに1行 JSON を書き出す。Claude Code はその行を Monitor で受け取り、
ユーザーからの指示として扱う。**クラウドに音声を送らない。**

```
マイク → Qwen3-ASR（ローカル GPU） → JSONL → Monitor → Claude Code
```

作業中に思いついたことをそのまま口に出せば、Enter を押さなくても指示が届く。

## 使い方

Claude Code で `/voice-shell` と打つか、「音声モードにして」と言う。以降は話すだけ。

| 操作 | 動作 |
|---|---|
| 話す | そのまま Claude Code に届く |
| マイクを切る | 切っている間の発話はどこにも残らない（別作業中に） |
| 手直ししてから送る | 発話を溜めて、直してから送る（誤認識の修正用） |

送信内容はブラウザでも確認できる（http://127.0.0.1:8090）。
このビューアは JSONL を追尾するだけで GPU もマイクも使わないので、音声モードと同時に動く。

### ユーザー辞書

ビューアの「辞書」から2種類のルールを登録できる。保存すると**次の発話から効く**
（デーモンの再起動は不要）。実体は `~/.config/voice-shell/dictionary.json`。

| 種類 | 用途 | 例 |
|---|---|---|
| 無視する発話 | これ単独で認識されたら送らない | `チャンネル登録` |
| 置き換え | 誤認識しやすい固有名詞を直す | `クロードコード → Claude Code` |

置き換えは既定で `クロードコード`/`クラウドコード` → `Claude Code`、
`ギットハブ` → `GitHub` が入っている。

## 必要なもの

- **NVIDIA GPU（VRAM 12GB 以上）** — Qwen3-ASR-1.7B の実測使用量が 12.3GB。
  それ未満なら `--max-model-len` を下げる（8192 など）か、より軽い
  `Qwen/Qwen3-ASR-0.6B` を `--model` に指定する
- **Python 3.12** と conda（miniforge 等）
- **Claude Code**

動作確認したのは下記の環境。macOS / Windows 向けのコードは書いてあるが未検証。

| 項目 | 値 |
|---|---|
| GPU | RTX 4080 SUPER (16GB) — VRAM 使用 12.3GB |
| OS | Ubuntu (GNOME / Wayland / PipeWire) |
| 主要パッケージ | `qwen-asr` 0.0.6, vLLM 0.14.0, PyTorch 2.9.1+cu128 |
| 認識速度 | RTF 0.30（実時間の 1/3 で処理） |

## セットアップ

```bash
conda create -n qwen3-asr python=3.12 -y
conda activate qwen3-asr
pip install -U "qwen-asr[vllm]" aiohttp soxr
hf download Qwen/Qwen3-ASR-1.7B          # 約3.5GB
```

録音に使うコマンドを入れる（OS ごとに違う）:

| OS | 必要なもの | 備考 |
|---|---|---|
| Linux | `alsa-utils`（`arecord`） | PipeWire がマイクを占有していても取れる |
| macOS | `brew install ffmpeg` | avfoundation 経由。未検証 |
| Windows | `winget install ffmpeg` | dshow 経由。未検証 |

スキルを Claude Code に認識させる（実体はこのリポジトリのまま、リンクを張る）:

```bash
ln -s "$(pwd)/skills/voice-shell" ~/.claude/skills/voice-shell
```

`npx skills add <owner>/<repo>` でも入る（[skills.sh](https://skills.sh)）。

### Python が見つからないと言われたら

`voice-shell.sh` は conda の `qwen3-asr` 環境を自動で探す。見つからない場合は
場所を直接指定する:

```bash
export VOICE_SHELL_PYTHON=/path/to/envs/qwen3-asr/bin/python
```

### マイクを指定したいとき

既定は Linux `pipewire` / macOS `:0` / Windows `audio=default`。
別のマイクを使うなら `--device` で指定する:

```bash
skills/voice-shell/scripts/voice-shell.sh start --device plughw:2,0   # Linux
arecord -L                                    # Linux でデバイス一覧
ffmpeg -f avfoundation -list_devices true -i ""   # macOS
ffmpeg -list_devices true -f dshow -i dummy       # Windows
```

## 構成

```
skills/voice-shell/       Claude Code スキル（~/.claude/skills/ からリンク）
├─ SKILL.md               スキル定義。音声の解釈ルールもここに書いてある
└─ scripts/
   ├─ voice-shell.sh      起動・停止・状態確認・ビューア
   ├─ voice_daemon.py     マイクを聞いて JSONL に書く常駐プロセス
   ├─ asr_mic.py          録音・無音判定・認識ループ
   ├─ viewer.py           JSONL を追尾してブラウザに流す（GPU 不使用）
   └─ viewer.html         ビューアの画面
```

## 手動で操作する

```bash
S=skills/voice-shell/scripts/voice-shell.sh
$S start          # 常駐開始（モデル読み込みに1〜2分）
$S wait-ready     # 起動完了まで待つ
$S status         # 稼働状況
$S viewer         # ビューア起動 → http://127.0.0.1:8090
$S stop           # 停止（VRAM 解放）
```

主なオプション（`voice_daemon.py`）:

| オプション | 既定値 | 説明 |
|---|---|---|
| `--language` | Japanese | 固定する言語。自動判定にするなら省略 |
| `--silence-duration` | 1.5 | この秒数の無音で発話を確定する |
| `--silence-threshold` | 0.054 | 無音とみなす RMS。マイクのノイズフロアに合わせる |
| `--max-utterance-sec` | 30 | 1発話の上限（長いほど推論が重くなる） |
| `--keep-noise` | off | 「はい」等の相槌も送る |
| `--drop-non-japanese` | off | 中国語・韓国語等を含む発話を捨てる |

---

# 実装メモ

同じ調査を繰り返さないための記録。すべて実測で確認したもの。

## vLLM のデフォルト設定では 16GB GPU に載らない

`max_model_len` の既定値 65536 は KV キャッシュに 7GiB 必要で、起動に失敗する
(`ValueError: To serve at least one request with the models's max seq len...`)。
本リポジトリは `--max-model-len 16384` を明示して回避している。

公式の `qwen-asr-demo-streaming` CLI はこの値を指定できないため、**そのままでは起動しない**
（`VLLM_MAX_MODEL_LEN` 環境変数も効かない）。自前のスクリプトを書いた理由がこれ。

## 同時に1つしか起動できない

モデルが約12GB使うため、GPU を使う別の音声プロセスとは同時起動できない。
`voice-shell.sh start` は起動前に GPU を確認して警告する。

終了時に vLLM のワーカー (`VLLM::EngineCore`) が残って VRAM を掴んだままになる問題は
`asr_mic.py` の `_kill_engine_on_exit()` で対処済み（Ctrl-C / SIGTERM どちらでも解放）。
それでも残った場合は `pgrep -f "VLLM::EngineCore" | xargs -r kill -9`。

## マイクは arecord 経由で取得している

PipeWire がマイクを占有しており、conda 版 PortAudio は PulseAudio バックエンド無しで
ビルドされているため、`sounddevice` からは USB マイクが見えない。
`arecord -D pipewire` で録音し、soxr で 16kHz に変換している。

リサンプルは `soxr.ResampleStream` を使い回す。ブロックごとに `soxr.resample()` を
呼ぶとフィルタの生成・破棄が毎回走り、実測で約5倍遅い。

## ミュート判定は「世代番号」で行う（フラグでは破綻する）

認識は発話が終わってから確定するため、確定時点だけを見てミュート判定すると、
**切っている間に話した内容が解除後にまとめて流れ込む**（ところてん現象）。

単純な「一度でも切られたらフラグを立てる」方式も破綻する:

- 無音のままミュートしただけでフラグが立ち、**解除後の最初の発話が消える**
- ミュート中に物音が発話として確定すると、そこでフラグが消費され、
  直後の本当の発話が取りこぼされる

`voice_daemon.py` では「マイクを切られた回数」(`mute_generation`) を数え、
発話が始まった時点の値を覚えて、確定時に変化していたらその発話を捨てている。
検証済みシナリオ: 無音ミュート→解除→発話 / ミュート中の物音→解除→発話 /
発話中にミュート / ミュートをまたぐ発話 / 通常。

## 無音でも相槌が出力される

物音や息だけを拾うと、モデルが「はい」「うん」「ご視聴ありがとうございました」等を
出力する。`voice_daemon.py` の `NOISE_ONLY` で、これら単独の発話を捨てている
（`--keep-noise` で無効化）。中身のある発話（「はい、それでは始めます」）は残る。

「ありがとうございました」「お疲れ様でした」は実際に言う言葉なので除外していない。

## 日本語以外への誤認識（既定では何もしない）

物音を拾うと中国語などに誤認識されることがある（実測で `嗯，那嗯嗯。` が出た）。
ただし意図して他言語を話すこともあるため、**既定では素通し**にしている。
`--drop-non-japanese` を付けると簡体字・ハングル・キリル等を含む発話を捨てる
（「時間」「問題」「東京」など日本語と共通の漢字は通すので誤検出しない）。

この判定は発話全体を見るため、日本語の末尾に中国語が混じった場合は通過する。
文の一部だけを落とす実装にはしていない（誤検出で指示本体を失う方が困るため）。

## ストリーミングは音声全体を毎回再投入する

`streaming_transcribe()` はチャンクごとに「それまでの全音声」をモデルに再投入する
(`qwen_asr/inference/qwen3_asr.py:751`)。このため **`--max-utterance-sec` と
`--chunk-size-sec` は独立した遅延つまみではなく、掛け算で効く**。
1発話でエンコードされる音声量は `発話長² / (2 × チャンク長)` に比例する:

| 発話長 | チャンク | エンコード量 | 増幅率 |
|---|---|---|---|
| 30s | 1.0s | 465s | 15.5x |
| 30s | 2.0s | 240s | 8.0x |
| 15s | 1.0s | 120s | 8.0x |

長く喋り続けるほど1チャンクの処理が重くなるので、遅延が気になる場合は
`--max-utterance-sec` を 10〜15 秒に下げるのが効く。

## Monitor は `tail -F` にする

デーモンを再起動するとログファイルが作り直されるため、`-f`（小文字）だと古い inode を
見続けて音声が届かなくなる。モニターを2つ生かすと同じ発話が二重に届く点にも注意。

## 認識できる言語

30言語 + 22中国語方言。日本語・英語のほか、歌唱や BGM 入り音声も認識する。
`--language` は主に出力形式を固定するもので、認識できる言語を制限しない
（日本語固定でも英語を話せば英語で返る。ただし単語間に読点が入るため、
ビューア側で除去している）。

## 参考

- [QwenLM/Qwen3-ASR](https://github.com/QwenLM/Qwen3-ASR)
- [Qwen/Qwen3-ASR-1.7B (Hugging Face)](https://huggingface.co/Qwen/Qwen3-ASR-1.7B)
- [Qwen3-ASR Technical Report (arXiv:2601.21337)](https://arxiv.org/html/2601.21337v1)

## ライセンス

このリポジトリのコードは MIT。Qwen3-ASR モデル自体は Apache-2.0。
