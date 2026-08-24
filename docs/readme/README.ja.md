# Voice Shell

[English](../../README.md) · 日本語 · [Español](README.es.md) · [Français](README.fr.md) · [Deutsch](README.de.md) · [简体中文](README.zh.md) · [한국어](README.ko.md)

<p align="center">
  <img src="https://img.shields.io/github/license/ykuwai/voice-shell" alt="ライセンス">
  <img src="https://img.shields.io/github/last-commit/ykuwai/voice-shell" alt="最終コミット">
</p>

原文は [README.md](../../README.md)（英語）。内容が食い違ったら英語版が正しい。

**声で Claude Code に指示を出す。キーボードは要らない。**

作業しながら頭に浮かんだことをそのまま口に出せば、Enterを押さなくてもプロンプト
として届く。テキスト欄に音声入力を貼り付けただけの仕組みとは違う。ミュートも、
聞き直しも、取り消しも、どのセッションに届けるかの選択も、全部声だけで済ませられる。
手は今やっていることに置いたままでいい。

<p align="center">
  <img src="images/viewer.png" alt="Voice Shellのビューア。認識中の文字と、送信先の選択、送り方が並ぶウィンドウ" width="360">
</p>

## 特徴

- **送るのに何も押さなくていい。** たいていの音声入力ツールは、テキスト欄に
  文字を溜めて送信を押すのを待つ。ここでは聞き取った瞬間にそのまま届く。
  ボタンも、確認も、クリックして開くウィンドウも要らない。
- **試すのに何もインストールしなくていい。** 既定の認識はブラウザが行うので、
  モデルのダウンロードも待ち時間もない。手元だけで完結させたくなったら、設定を
  ひとつ変えるだけでApple・Whisperのオンデバイス認識に切り替えられる。覚え直す
  ことは何もない。
- **マイクのアイコンだけの仕組みじゃない。** 「ミュート」「手直し」「即時」
  「キャンセル」「2番目」、文の最後にこう言うだけで、手を使わず切り替えられる。
  画面には、聞き取った内容がそのまま伸びていく。
- **複数の作業で同時に使える。** 何セッションでも音声モードを立ち上げておいて、
  どれに届けるかを画面からでも声からでも選べる。
- **聞き間違えた固有名詞は覚えさせられる。** 一度辞書に登録すれば
  （「クロードコード → Claude Code」）、以降はずっと直る。認識している最中の
  文字にも反映される。

## インストール

```bash
npx skills add ykuwai/voice-shell
pip install numpy aiohttp
```

Chromeがあれば、これだけで動く。

Claude Codeで `/voice-shell` と打つか、「音声モードにして」と言えば始まる。
そこから先の手順は [SKILL.md](../../skills/voice-shell/SKILL.md) にある。

## 音声がどこへ行くか

> [!NOTE]
> 既定はブラウザの認識なので、音声は Google のサーバへ送られる。
> 手元から出したくないときは、画面の設定から選び直す。画面のその場にも同じ注意が出る。

| やり方 | 何が要るか | 音声の行き先 |
|---|---|---|
| **このブラウザ**（既定） | Chrome。画面を開いている間だけ動く | **Google のサーバ** |
| Apple のオンデバイス | macOS 26 以降。追加で入れるものは無い | その機械の中だけ |
| Whisper | `faster-whisper`。固有名詞に強い | その機械の中だけ |

選んだやり方は覚えているので、次からはそのまま起動する。手元で完結させる2つの
入れ方は [SETUP.md](../../skills/voice-shell/SETUP.md) にある。

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
