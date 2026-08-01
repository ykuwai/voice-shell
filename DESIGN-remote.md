# LAN 内の複数端末から音声を入れる

家の GPU（RTX 4080 SUPER）に載っているモデルを、Windows PC やスマホからも
使えるようにする。クラウドの音声 API は従量課金で高くつくので、既に持っている
GPU を使い回したい、という動機。

## 決めたこと

- **OpenAI Realtime WebSocket 互換**にする。喋っている途中の経過が返るので、
  ちゃんと届いているかが分かる。ファイル POST 形式（`/v1/audio/transcriptions`）
  だと録り終わるまで無反応で、リアルタイム感が出ない。
- **家庭内 LAN に閉じる**。外出先からは今回対象にしない。TLS を持ち込むと
  一気に面倒になる。
- **リモートの発話は `utterances.jsonl` に書かない**。あのファイルは今動いて
  いる Claude Code セッションの入力そのもの。他の端末の音声が混ざると、
  別の人の発言がそのまま指示として実行されてしまう。

## 前提（実測で確認済み）

| | 値 | 出どころ |
|---|---|---|
| GPU | RTX 4080 SUPER 16GB | `nvidia-smi` |
| 常駐時の使用量 | 12.8GB | 同上 |
| **GPU 利用率** | **1%** | 同上（喋っていない間はほぼ遊んでいる） |
| KV cache | 5.71GiB / 53,424 tokens | 起動ログ |

### 推論はロックで直列化する

`streaming_transcribe` の中身を読んだところ、こうなっていた。

```python
# qwen_asr/inference/qwen3_asr.py（streaming_transcribe の末尾）
outputs = self.model.generate([inp], sampling_params=..., use_tqdm=False)
#         ^^^^^^^^^^ 全員で共有する vllm.LLM   ^^^^^ 1件ずつ
```

state を呼び出し側が持つのは **ASR の文脈が話者ごとに独立する**という意味で、
モデル呼び出しが並行安全という意味ではない。共有の `self.model` に素で入って
いき、ロックも無い。

なので `self.model` を触る箇所は **`threading.Lock` で直列化する**。
ローカルマイクの経路も同じロックを通す（後述）。

直列でも足りる根拠:

- 1発話の推論は 0.1〜0.5 秒
- 人は喋り続けない。GPU 利用率 1% がそれを示している
- 2〜5人なら待ちは体感できない

`transcribe()` はリストを受けてバッチ処理できるが、それは今回使う
ストリーミングとは別の経路。並行性の根拠にはならない。

### モデルは1プロセスに1つ

GPU に 12.8GB 載っており、`voice-shell.sh` にも二重起動を止めるガードがある。
別プロセスからモデルを読むことはできないので、**WebSocket サーバはデーモンの
中に同居させる**。ローカルマイクは「音声の出どころの1つ」に格下げされ、
リモート接続と並ぶ形になる。

## 構成

```
Windows / スマホ                  RTX 4080 SUPER の PC
┌──────────┐                   ┌──────────────────────────┐
│ ブラウザ  │ ── WebSocket ──→ │ voice_daemon.py          │
│ or CLI   │   16kHz PCM       │  ├ ローカルマイク（既存） │
│          │ ←─ 認識結果 ───  │  ├ WS サーバ（新規）      │
└──────────┘   途中経過つき    │  └ 接続ごとに state      │
                               │      ↓                   │
                               │  remote/<name>.jsonl     │
                               └──────────────────────────┘
```

### 接続ごとに持つもの

| | 内容 |
|---|---|
| `state` | `init_streaming_state()` の戻り値。話者ごとに独立 |
| `name` | トークンに紐づく名前。書き出し先のファイル名になる |
| 出力先 | `remote/<name>.jsonl`。ローカルの `utterances.jsonl` とは分ける |

## プロトコル

OpenAI Realtime の transcription intent に寄せる。`engines.py` に
クライアント側の実装があるので、その反対側を書く形になる。

### 接続

```
ws://<host>:8091/v1/realtime?intent=transcription
Authorization: Bearer <token>
```

### クライアント → サーバ

```jsonc
// 接続直後に来る。中身は使わないが、知らない type として弾かないこと
{"type": "transcription_session.update",
 "session": {"input_audio_format": "pcm16",
             "input_audio_transcription": {"model": "...", "language": "ja"},
             "turn_detection": null}}

{"type": "input_audio_buffer.append", "audio": "<base64 の 16kHz PCM>"}
{"type": "input_audio_buffer.commit"}   // 発話の区切り。ここで確定を返す
```

`turn_detection: null` が来るとおり、**発話の区切りはクライアントが決める**。
サーバ側で無音検出はしない。`commit` を受けたら確定を返す。

### サーバ → クライアント

```jsonc
// 認識の途中経過
{"type": "conversation.item.input_audio_transcription.delta", "delta": "こんに"}
// 確定
{"type": "conversation.item.input_audio_transcription.completed", "transcript": "こんにちは"}
```

## テキストの後処理

ローカルと同じ処理を通す。辞書はクラウド API に対する明確な取り柄なので、
リモートでも効かせたい。

```
collapse_letter_acronyms()   略語を詰める（G P U → GPU）
apply_replacements()         辞書（クロードコード → Claude Code）
kanji_numbers_to_arabic()    漢数字（三十秒 → 30秒）
```

**`is_noise()` の握りつぶしはしない。** ローカルでは相槌を捨てているが、
リクエストに応答を返す API で黙って何も返さないのは筋が悪い。空文字を返す。

## 認証

**ブラウザの `new WebSocket(url)` はヘッダを付けられない。** 認証を
`Authorization` ヘッダだけにするとブラウザから繋げないので、3つとも受ける。

| 経路 | 渡し方 | 使うのは |
|---|---|---|
| ヘッダ | `Authorization: Bearer <token>` | CLI、engines.py |
| サブプロトコル | `["realtime", "openai-insecure-api-key.<token>"]` | ブラウザ（OpenAI と同じ手） |
| クエリ | `?token=<token>` | 上2つが使えないとき |

どれか1つでも合えば通す。設定ファイルの一覧と突き合わせる。

```jsonc
// ~/.config/voice-shell/remote.json
{
  "bind": "192.168.0.15",     // 0.0.0.0 は届く範囲が広すぎるので既定にしない
  "port": 8091,
  "tokens": {
    "<token>": "windows-pc"   // 値が書き出し先のファイル名になる
  }
}
```

LAN 内に閉じる前提なので TLS は張らない。`bind` を明示させるのは、
`0.0.0.0` だと VPN や別セグメントなど、意図しないところからも届くため。

## 届いた発話を読む

`remote/<name>.jsonl` は書くだけでは意味がない。Claude Code 側で Monitor を
もう1本張って追尾する。ローカル用と合わせて2本になる。

```
tail -F -n 0 ~/.local/state/voice-shell/remote/windows-pc.jsonl
```

Monitor は増やしすぎると同じ発話が二重に届くので、張り直すときは古いものを
TaskStop で止めること。

## 既存コードに入る変更

「追加だけ」では済まない箇所が1つある。

`main()` は `for ev in asr_mic.stream_utterances(model, args):` を回しており、
この中で `model.streaming_transcribe(...)` が呼ばれる。WS スレッドが同じ
モデルを触る以上、**ローカル経路も同じロックを通す必要がある**。

`asr_mic.stream_utterances` にロックを渡すか、モデルをロック付きの薄い
ラッパで包む。後者のほうが呼び出し側に手を入れずに済む。

## やらないこと

- 外出先からの利用（TLS と公開の手当てが要る）
- 話者の自動判別（トークンで区別すれば足りる）
- ローカルマイクの置き換え（既存の動作はそのまま残す）

## 進め方

既存の動作を壊さないよう、追加だけで進める。

1. `remote_server.py` を単体で書く。認識部分は差し替え可能にして、
   最初は入力をそのまま返すだけのスタブで動かす。GPU もデーモンの再起動も要らない
2. デーモンに組み込む。`--remote` を付けたときだけ起動する。
   モデルはロック付きラッパで包む
3. `voice-shell.sh` に `remote` サブコマンドを足す
4. クライアント（ブラウザ + CLI）

各段階でコミットする。

### 手持ちのクライアントでそのまま試せる

`engines.py` の `openai` は OpenAI Realtime のクライアントそのもので、
接続直後に送るメッセージも待つ応答も、今回作るサーバと同じ形をしている。
**接続先 URL を差し替えられるようにすれば、新しくクライアントを書かずに
端から端まで試せる。** step 1 の検証はこれでやる。

```bash
# 既存のクライアントを自前のサーバに向ける
voice-shell.sh start --engine openai --realtime-url ws://127.0.0.1:8091/v1/realtime
```
