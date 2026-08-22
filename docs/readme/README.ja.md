# Voice Shell

[English](../../README.md) · 日本語 · [Español](README.es.md) · [Français](README.fr.md) · [Deutsch](README.de.md) · [简体中文](README.zh.md) · [한국어](README.ko.md)

原文は [README.md](../../README.md)（英語）。内容が食い違ったら英語版が正しい。

声で Claude Code に指示を出す Agent Skill。キーボードを使わずに、話しかけて指示を送る。

> マイク → 音声認識 → JSONL に1行 → Monitor → Claude Code

作業中に思いついたことをそのまま口に出せば、Enter を押さなくても届く。
Claude Code のほか、Codex など他のエージェントからも使える。

## 入れる

```bash
npx skills add ykuwai/voice-shell
pip install numpy aiohttp "sounddevice>=0.5.6"
```

Chrome があれば、これだけで動く。**モデルのダウンロードも待ち時間もない。**

## 使う

Claude Code で `/voice-shell` と打つか、「音声モードにして」と言う。以降は話すだけ。
止めるときは「音声モード終了」。

画面が独立した小窓（http://127.0.0.1:8090）で開き、認識している文字がその場で伸びる。
手前に浮かせておけば、他の作業をしながら様子を見ていられる。

| 送り方 | 何が起きるか |
|---|---|
| 即時 | 話すとそのまま届く |
| 手直し | 溜めておいて、直してから送る |
| 一時停止 | 止めている間の発話はどこにも残らない |

手が塞がっていても、**声だけで切り替えられる。** 「ミュート」「ミュート解除」で
マイクの入切、「手直し」「即時」で送り方。文の最後に「キャンセル」と言えば、
その一言ごと送らずに捨てる（ブラウザの認識で切ったときだけは、音声そのものを
手放すので画面から戻す）。

別々の作業でそれぞれ音声モードを立ち上げておき、**どれへ届けるかを画面から選ぶ**
こともできる。声でも選べる（「2番目」）。

誤認識しやすい固有名詞は辞書に登録できる（`クロードコード → Claude Code`）。
登録した言い換えは、認識している最中の文字にも当たる。

## 音声がどこへ行くか

**既定はブラウザの認識なので、音声は Google のサーバへ送られる。**
手元から出したくないときは、画面の設定から選び直す。画面のその場にも同じ注意が出る。

| やり方 | 何が要るか | 音声の行き先 |
|---|---|---|
| **このブラウザ**（既定） | Chrome。画面を開いている間だけ動く | **Google のサーバ** |
| Apple のオンデバイス | macOS 26 以降。追加で入れるものは無い | その機械の中だけ |
| Whisper | `faster-whisper`。固有名詞に強い | その機械の中だけ |

選んだやり方は覚えているので、次からはそのまま起動する。手元で完結させる2つの
入れ方は [SETUP.md](skills/voice-shell/SETUP.md) にある。

認識できる言語は、選んだやり方が決める。ブラウザは Chrome が持つ一覧、Apple は OS に
入っているロケール、Whisper はモデルの対応言語。画面の表示は7言語ある。

## コマンド

```bash
voice-shell.sh start [--engine X] [--no-gui]
voice-shell.sh stop
voice-shell.sh status
voice-shell.sh engines
```

| コマンド | 何をするか |
|---|---|
| `start` | 起動する。前回選んだやり方を覚えている |
| `stop` | 停止する |
| `status` | 稼働状況と、聞いているセッション |
| `engines` | 選べる認識のやり方 |

設定はすべて `~/.config/voice-shell/` に残り、再起動をまたいで消えない。

## うまくいかないとき

Linux では録音に `arecord` が要る。

```bash
sudo apt install alsa-utils      # Linux
```

| 出ていること | どうするか |
|---|---|
| 話しても何も届かない | 反応する音の大きさが高すぎる。画面のマイクの下にある印を、話したときに棒が越えるところまで下げる |
| 物音で勝手に送られる | 反応する音の大きさが低すぎる。同じ印を、自分の声だけが越えるところまで上げる |
| `No Python it can run was found` | `export VOICE_SHELL_PYTHON=/path/to/.venv/bin/python` |
| 起動が `FAILED` になる | `voice-shell.sh status` を見て、`daemon.out` の末尾を読む |

## もう少し詳しく

下の2つは英語だけ。ほとんどの人に要ることは、ここまでに書いてある。

| 読むもの | 中身 |
|---|---|
| [SETUP.md](../../skills/voice-shell/SETUP.md) | 環境ごとの入れ方と、つまずいたときの対処 |
| [SKILL.md](../../skills/voice-shell/SKILL.md) | エージェントが読む手順。細かい振る舞いはここ |

## 参考

- [Web Speech API (MDN)](https://developer.mozilla.org/docs/Web/API/SpeechRecognition)
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)

## ライセンス

MIT
