# voice-shell — 声で Claude Code に指示を出す

Claude Code に**話しかけて指示を出す**ための仕組み。キーボードは要らない。

Alibaba Qwen チームの音声認識モデル **Qwen3-ASR-1.7B**（Apache-2.0）をローカルで動かし、
発話が確定するたびに1行 JSON を書き出す。Claude Code はその行を Monitor で受け取り、
ユーザーからの指示として扱う。**既定では、音声は手元から出ない。**

非力な端末や、モデルを入れずに試したい場合のために、**Chrome の認識を使う道**も
用意してある（設定から入切）。こちらは**音声が Google のサーバへ送られる**ので、
手元だけで完結させたい場合は使わないこと。画面のその場にも警告を出している。

```
マイク → Qwen3-ASR（ローカル GPU） → JSONL → Monitor → Claude Code
```

作業中に思いついたことをそのまま口に出せば、Enter を押さなくても指示が届く。

## 使い方

Claude Code で `/voice-shell` と打つか、「音声モードにして」と言う。以降は話すだけ。

| 操作 | 動作 |
|---|---|
| 即時 | 話すとそのまま Claude Code に届く |
| 手直し | 発話を溜めて、直してから送る（誤認識の修正用） |
| 一時停止 | 止めている間の発話はどこにも残らない（別作業中に） |

## 認識のやり方を選ぶ

| やり方 | 何が要るか | 音声の行き先 | 向いている場面 |
|---|---|---|---|
| Qwen3-ASR（既定・Linux） | GPU 約12GB | 手元だけ | GPU のある機械 |
| Apple のオンデバイス（既定・macOS） | macOS 26 以降 | 手元だけ | Mac。軽い |
| Whisper | CPU でも動く | 手元だけ | 固有名詞に強い。Windows 向け |
| **Chrome の認識** | Chrome だけ | **Google のサーバ** | 非力な端末。準備が要らない |

Chrome の認識は設定の「このブラウザで認識する」から入れる。デーモンが動いて
いなくても使える。7〜10 秒黙るとセッションが切れる仕様だが、**黙っているあいだに
先回りして張り直す**ので、話し始めを落とさない（実測: 30 秒の無音で切れ目 0ms）。

認識した文は、デーモンで認識したときと同じ道を通す — 辞書の言い換え、無視する発話、
最小文字数、つなぎ言葉の除去、一時停止中の保留。認識のやり方で届く文は変わらない。

## 誰が聞いているか確かめる

```bash
voice-shell.sh listeners     # status にも同じ一覧が出る
```

発話ログを追尾している Claude Code のセッションを並べる。`tail -F` は止め忘れると
生き続け、デーモンを入れ直してもつながり直すため、本人は気づけない。実際に8日前の
セッションが聞いたままで、同じ発話が2つのセッションへ配られていたことがある。

```
  claude 88851（tail 16764）
    起動 : Tue Aug 18 17:20:49 2026
    場所 : /Users/ykuwai/development
    切る : kill 16764
```

## ビューア

http://127.0.0.1:8090 — 認識中の文字がそのまま伸び、送った履歴が残る。

横にブラウザを並べずに済むよう、**手前に浮かぶ小窓**へ移せる（設定の「手前に浮かせる」）。
Chrome の Document Picture-in-Picture を使うので、追加の実行環境は要らない。

波形はブラウザ側でも同じマイクを開いて描く。許可しなければデーモンが出す音量だけで
動くので、画面は成立したまま使える。バー / 流れる / 球 / 格子 から選べる。

### 設定

歯車から開く。つまみは動かした時点で効く（デーモンの再起動は不要）。

| 項目 | 何を決めるか | 既定 |
|---|---|---|
| マイク | 使う入力装置。既定は「システムの既定」 | システムの既定 |
| 感度 | 0〜100。小さいほど微かな音まで拾う | macOS 41 / Linux 74 |
| 確定までの無音 | これだけ黙るとひと区切りとして確定する | 1.5 秒 |
| 最小文字数 | これより短い認識結果は物音とみなして捨てる | 15 文字 |
| 「えーと」を消す | つなぎ言葉を落としてから送る | 切 |
| テーマ | 自動 / ダーク / ライト | 自動 |
| 言語 | 自動 / English / 日本語 | 自動（OS に従う） |

感度は **自動調整**できる。数秒喋って数秒黙ると、部屋の音と声の差から決める。
差が足りないときは値を決めず、マイクを近づけるよう伝える。
波形の下にあるオレンジの印を**つまんで動かしても**変えられる。

送り先が「即時」のままでも、未送信カードの鉛筆を押せば**その一言だけ**溜めて
直してから送れる。誤字を見つけたときのため。送るか消すと即時に戻る。

これらは `~/.config/voice-shell/tuning.json` に残り、デーモンが 0.5 秒おきに読み直す。

### ユーザー辞書

設定の「辞書」から2種類のルールを登録できる。保存すると**次の発話から効く**
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
- **または macOS 26 以降の Mac** — OS 付属の音声認識（`--engine apple`、
  macOS では既定）で動く。モデルの追加ダウンロードも GPU メモリも要らない
- **または Apple Silicon Mac（macOS 25 以前）** — MLX 版（`--engine mlx`）で動く。
  ユニファイドメモリを約4GB使う
- **または GPU なし（CPU のみ）** — Whisper（`--engine whisper`、faster-whisper 版）で動く。
  `--model base --whisper-compute int8` なら 4 コア級 CPU でも RTF 0.15 程度で動く
  （既定の `large-v3-turbo` は CPU では重すぎる）。GPU メモリはもちろん不要
- **Python 3.12**（macOS / Whisper 経路は 3.10〜3.13）と conda または venv
- **Claude Code**

動作確認したのは下記の環境。Windows は Whisper 経路のみ確認済み
（Qwen3-ASR の vLLM/MLX 経路は NVIDIA GPU か Apple Silicon が要るため未検証）。

| 項目 | Linux + NVIDIA | macOS（apple） | macOS（mlx） | Windows（whisper・CPU） |
|---|---|---|---|---|
| 機種 | RTX 4080 SUPER (16GB) — VRAM 12.3GB | Mac mini (M4 Pro, 24GB) — OS 側 | 同左 — 約4GB | 4コア級 Core i5（内蔵 GPU のみ） |
| OS | Ubuntu (GNOME / Wayland / PipeWire) | macOS 26.5.2 | macOS 26 | Windows 11 |
| 主要パッケージ | `qwen-asr` 0.0.6, vLLM 0.14.0, PyTorch 2.9.1+cu128 | OS 付属（Speech.framework） | `mlx-qwen3-asr` 0.3.5, MLX 0.32.0 | `faster-whisper` 1.2.1（`base` / int8） |
| 認識速度 | RTF 0.30 | RTF 0.03 | RTF 0.31（確定の一括認識） | RTF 0.15 |
| 起動 | 1〜2 分 | 1 秒未満 | 1〜2 分 | 数秒〜（モデルは初回のみ自動DL） |

## セットアップ

```bash
conda create -n qwen3-asr python=3.12 -y
conda activate qwen3-asr
pip install -U "qwen-asr[vllm]" aiohttp soxr
hf download Qwen/Qwen3-ASR-1.7B          # 約3.5GB
```

macOS 26 以降は OS 付属の音声認識を使う（`--engine apple` が既定）。
認識モデルの追加ダウンロードは要らず、Swift のヘルパを初回起動時に
自動でビルドする（Xcode か `xcode-select --install` が必要）:

```bash
cd voice-shell
python3 -m venv .venv                    # 3.10〜3.13
.venv/bin/pip install -U numpy aiohttp soxr
```

macOS 25 以前は `SpeechTranscriber` が無いので MLX 版を入れる
（`--engine mlx` を明示する）:

```bash
cd voice-shell
python3 -m venv .venv                    # 3.10〜3.13
.venv/bin/pip install -U mlx-qwen3-asr aiohttp soxr
.venv/bin/hf download Qwen/Qwen3-ASR-1.7B    # 約3.4GB
```

録音に使うコマンドを入れる（OS ごとに違う）:

| OS | 必要なもの | 備考 |
|---|---|---|
| Linux | `alsa-utils`（`arecord`） | PipeWire がマイクを占有していても取れる |
| macOS | `brew install ffmpeg` | avfoundation 経由。初回にマイク許可のダイアログが出る |
| Windows | `winget install ffmpeg` | dshow 経由。Whisper 経路で確認済み |

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
**Windows の既定値は dshow では認識されないので、実質必須で指定が要る**
（`audio=default` という名前のデバイスは存在しない）。
別のマイクを使うなら `--device` で指定する:

```bash
skills/voice-shell/scripts/voice-shell.sh start --device plughw:2,0   # Linux
arecord -L                                    # Linux でデバイス一覧
ffmpeg -f avfoundation -list_devices true -i ""   # macOS
ffmpeg -list_devices true -f dshow -i dummy       # Windows（一覧に出た名前をそのまま
                                                   # --device audio=<名前> に渡す）
```

## 構成

```
skills/voice-shell/       Claude Code スキル（~/.claude/skills/ からリンク）
├─ SKILL.md               スキル定義。音声の解釈ルールもここに書いてある
└─ scripts/
   ├─ voice-shell.sh      起動・停止・状態確認・ビューア
   ├─ voice_daemon.py     マイクを聞いて JSONL に書く常駐プロセス
   ├─ asr_mic.py          録音・無音判定・認識ループ
   ├─ engine_apple.py     macOS 26 付属の認識を使うエンジン（ローカル完結）
   ├─ speech_helper.swift 同上の Swift ヘルパ（初回起動時に自動ビルド）
   ├─ engine_mlx.py       Apple Silicon 用エンジン（MLX、ローカル完結）
   ├─ engines.py          クラウド API エンジン（Deepgram 等、GPU 不要）
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

## Windows（Git Bash）で動かすには何点か直しが要った

`voice_daemon.py` / `voice-shell.sh` は元々 Linux/macOS しか想定しておらず、
Windows（Git Bash 上の bash）で動かすと以下がすべて刺さった。いずれも修正済み。

- **`import fcntl`** — POSIX 専用モジュールで Windows には無く、起動直後に
  `ModuleNotFoundError` で落ちる。Windows では `msvcrt.locking` で
  二重起動防止ロックを代替した
- **`os.kill(pid, 0)`**（生存確認）— Windows では未対応で `SystemError` になる。
  `OpenProcess` が取れるかで代替した
- **`pgrep` / `pkill` / `setsid`** — Git Bash に無い。`voice-shell.sh` は
  リスナー一覧・二重起動チェック・停止処理でこれらに依存していたため、
  無ければその機能だけ諦めて素通しするようガードを入れた
  （ビューアの起動確認は pgrep が無ければポートへの応答で代用する）
- **`/tmp` の解釈が bash と Python でずれる** — Git Bash（MSYS）の `/tmp` は
  実際の Windows パス（例: `...\AppData\Local\Temp`）へマウント変換されるが、
  素の Windows Python が同じ文字列 `"/tmp"` を受け取ると `C:\tmp` と解釈する。
  両者が同じ意味のつもりで別ディレクトリを見てしまい、デーモンの書き込み先と
  Monitor の `tail -F` 先がずれて**発話がどこにも届かない**という壊れ方をする。
  `voice-shell.sh` が `cygpath -w` で実パスに変換し、`VOICE_SHELL_STATE_DIR`
  環境変数で子プロセスへ明示的に渡すことで解決した
- **文字コード** — Windows の Python はファイル I/O に既定でシステムの
  ロケール（日本語版なら cp932）を使う。UTF-8 で書いた JSON やログを
  読もうとして `UnicodeDecodeError` になり、状態確認の文字列比較
  （`grep -q 稼働中` 等）も一致しなくなる。`voice-shell.sh` で
  `PYTHONUTF8=1` を強制して回避した（macOS/Linux では無害）
- **ffmpeg の dshow マイク名** — README/SETUP.md の既定値 `audio=default` は
  実際には認識されない。`ffmpeg -list_devices true -f dshow -i dummy` で
  出てくる実際のデバイス名をそのまま `--device audio=<名前>` に渡す必要がある

## macOS は OS 付属の認識を既定にした（Qwen3-ASR は重すぎた）

Mac では `--engine apple`（`engine_apple.py`）を既定にしている。macOS 26 の
`SpeechAnalyzer` / `SpeechTranscriber` を使うので、モデルの追加ダウンロードも
GPU メモリの確保も要らない。実測（M4 Pro / macOS 26.5.2）で 3.1 秒の日本語音声が
0.10 秒、句読点まで含めて正しく出た（RTF 0.03）。起動も 0.83 秒で、MLX 版の
1〜2 分と比べ物にならない。音声はこの Mac の中だけで処理される。

Swift の API しか無いので、`speech_helper.swift` を常駐させて WAV のパスを
渡し、結果を JSON で受け取る形にした。ヘルパは初回起動時に `swiftc` で
自動ビルドする（`scripts/build/` に置く。git には入れない）。

### ストリーム給餌ではなくファイル渡しにした

`SpeechAnalyzer` には `start(inputSequence:)` で `AsyncStream` に音声を流す
API もあるが、署名なしの CLI から呼ぶと `nilError` で落ちた（`.app` 化して
いる `LiveDictation` では動く）。`analyzeSequence(from: AVAudioFile)` は
同じ条件で問題なく動くので、発話 1 つ分を WAV に書いて渡している。
RTF 0.03 なので、途中経過のために全体を何度も認識し直しても間に合う。

### マイクは Python 側が持つ

ヘルパは音声を受け取って文字にするだけで、マイクには触らない。そのため
TCC の許可も `.app` 化も要らず、`swiftc` で作った素の実行ファイルのまま動く。
録音と発話の区切り（VAD）は従来どおり `asr_mic.py` の担当。

（この構成は同じ Mac で先に検証した
[live-dictation](https://github.com/ykuwai/live-dictation) の知見を使っている。）

## macOS 25 以前は MLX 版で動かす（partial も確定も全体を認識し直す）

`SpeechTranscriber` が使えない Apple Silicon には CUDA も無いので
[mlx-qwen3-asr](https://github.com/moona3k/mlx-qwen3-asr) を使う
（`engine_mlx.py`、`--engine mlx`）。vLLM 版と同じ3メソッドを持つ
アダプタなので、認識ループは共通のまま。

同ライブラリの増分デコード（KV キャッシュ再利用）も試したが、チャンク境界
ごとに読点が入り語も割れる（実測で「くだ。ください」）。vLLM 版の
「毎秒すべてを認識し直す」表示と比べて明らかに見劣りするため、
**partial も確定も、溜めた音声全体の一括認識**にした。1回の認識は
RTF 約0.31 なので、partial の更新間隔は発話長×0.3 で自然に伸びる
（5秒の発話なら約1.5秒ごと）。確定も同じだけ待つ。

partial の認識はワーカースレッドでやる。メインループで認識すると、
その間マイクを読めず ffmpeg のパイプ（約0.7秒分）が溢れて録音を
取りこぼす。スレッド化で feed は 15ms 以下になった（増分デコードを
メインループで回していたときは毎チャンク約500ms 止まっていた）。

確定文の品質は一括認識のほうが明確に良い（partial で「修復の方針を立案」と
崩れた 20 秒の発話が、確定では「修正の方針を提案」と正しく出た）。

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
`polish()` で除去している）。

ビューアの表示言語は認識する言語とは別で、英語と日本語を持つ（設定で切り替え）。

## 参考

- [QwenLM/Qwen3-ASR](https://github.com/QwenLM/Qwen3-ASR)
- [Qwen/Qwen3-ASR-1.7B (Hugging Face)](https://huggingface.co/Qwen/Qwen3-ASR-1.7B)
- [Qwen3-ASR Technical Report (arXiv:2601.21337)](https://arxiv.org/html/2601.21337v1)

## ライセンス

このリポジトリのコードは MIT。Qwen3-ASR モデル自体は Apache-2.0。
