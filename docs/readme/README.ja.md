<p align="center">
  <img src="images/logo.svg" alt="Voice Shell" width="88">
</p>

# Voice Shell

[English](../../README.md) · 日本語 · [Español](README.es.md) · [Français](README.fr.md) · [Deutsch](README.de.md) · [简体中文](README.zh.md) · [한국어](README.ko.md)

<p align="center">
  <img src="https://img.shields.io/github/license/ykuwai/voice-shell" alt="ライセンス">
  <img src="https://img.shields.io/github/last-commit/ykuwai/voice-shell" alt="最終コミット">
</p>

**声だけで Claude Code に指示を出そう！**

作業しながら頭に浮かんだことをそのまま口に出せば、Enterキーを押さなくてもプロンプトとして届きます。


<p align="center">
  <img src="images/viewer.png" alt="Voice Shellのビューア。認識中の文字と、送信先の選択、送り方が並ぶウィンドウ" width="360">
</p>

## 💡 特徴

- **プロンプトを送信するときに、キーボードを使う必要がありません。** たいていの音声入力ツールは、
  テキスト欄に文字が溜まるので、Enterキーを押す必要があります。でも、Voice Shell なら、喋り終わって一定の時間が経過したら自動的にClaude Codeに送信されます。
  キーボードに触れずにClaude Codeに指示を出せるので、とても便利です。
- **完全無料で、すぐに音声入力が使えます。** ブラウザに搭載された音声認識機能（Web Speech API）で実行すれば、APIキーも不要で、すぐに使い始められます。
  さらに、ローカルだけで完結させたくなったら、設定をひとつ変えるだけでAppleやWhisperのローカルのリアルタイム音声認識に切り替えれます。
- **音声コマンドも用意しました** 一時的に音声認識を止めたいときは、「ミュート」と言えば、マイクがオフになります。 途中まで話していて、やっぱり話すのをやめたいときは「キャンセル」と言えば、送信されません。
- **複数の作業で同時に使えます。** 複数のClaude Codeのセッションに対応しています。送信先をVoice Shell側から切り替えることができるので、同時に作業しているときにも便利です。 
- **聞き間違いは、辞書機能に登録できます** 辞書機能があるので、例えば「クロードコード → Claude Code」 のように変更したい場合には、登録できます。

## 📦 Voice Shellをインストール

```bash
pip install numpy aiohttp "sounddevice>=0.5.6"
npx skills add ykuwai/voice-shell -g -a claude-code -y
```

Google Chromeがあれば、ターミナルで上記コマンドを入力するだけですぐに動きます！

Claude Codeで `/voice-shell` と打つか、「音声モードにして」と言えば
始まります。そこから先の手順は
[SKILL.md](../../skills/voice-shell/SKILL.md) にあります。

### 🔄 アップデート

```bash
npx skills update voice-shell -y
```

どんどん機能をアップデートしています。
たまにこのアップデートのコマンドを実行してみてください。

## 🔒 音声がどこへ行くか

既定のWeb Speech API（ブラウザ標準の音声認識）が、一番簡単に始められます。
ブラウザの音声認識機能は、 Googleのサーバーで音声が処理されます。
ローカルで音声認識をしたいときには、Macの場合は Apple の音声認識、 Windows や Linux の場合は Whisper を使ってみてください。

> [!NOTE]
> 既定はブラウザの認識なので、音声はGoogleのサーバーへ送られます。
> ローカルにとどめたいときは、Claude Code に「Apple の音声認識を使いたい」のように伝えてみてください。
> 一度設定すれば、次回からは設定が反映されます。

| やり方 | 何が要るか | 音声の行き先 |
|---|---|---|
| **このブラウザ**（既定） | Chrome。画面を開いている間だけ動きます | **Googleのサーバ** |
| Appleのオンデバイス | macOS 26以降。追加で入れるものはありません | ローカルだけ |
| Whisper | `faster-whisper`。固有名詞に強い | ローカルだけ |

選んだやり方は覚えているので、次回からはそのまま起動します。ローカルで
完結する2つの入れ方は
[SETUP.md](../../skills/voice-shell/SETUP.md) にあります。

認識できる言語は、選んだやり方で変わります。ブラウザはChromeが対応する
言語、AppleはOSが対応する言語、Whisperはモデルが対応する言語です。
画面の表示は7言語あります。

## 🗣️ 音声コマンド

この一言だけを言えば、キーボードを使わずに切り替えられます。

| 言うこと | 何が起きるか |
|---|---|
| 「ミュート」 | マイクが切れます |
| 「ミュート解除」 | マイクが戻ります（オンデバイスのモデルはミュート中も聞き続けています。ブラウザでは戻せません） |
| 「手直し」「エディット」 | ここから話した分は溜まるだけで、送られなくなります。送る前に直せます |
| 「即時」「そのまま送る」 | また、そのまま届く状態に戻ります |
| 「セッション2」「2番」 | 聞いているセッションが2つ以上あるとき、どれに届けるかを選べます |

話している文の終わりにこれを付け加えると、その一文だけに効きます。

| 言うこと | 何が起きるか |
|---|---|
| 「キャンセル」 | 直前に言った一文が、丸ごと捨てられます |
| 「あとで直す」 | 直前に言った一文が、送られずに下の欄へ回ります。送る前に直せます |

上に挙げた言い方は、どれも画面の設定で切ることができ、自分の言い方を
教えることもできます。7言語すべての完全な一覧は、画面の電球アイコンの
中にあります。

## 📖 もっと詳しい資料

下の2つは英語だけです。ほとんどの人に必要なことは、ここまでに
書いてあります。

| 読むもの | 中身 |
|---|---|
| [SETUP.md](../../skills/voice-shell/SETUP.md) | 環境ごとの入れ方と、つまずいたときの対処 |
| [SKILL.md](../../skills/voice-shell/SKILL.md) | エージェントが読む手順。細かい振る舞いはここにあります |

## 🔗 参考リンク

- [Web Speech API (MDN)](https://developer.mozilla.org/docs/Web/API/SpeechRecognition)
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)

## 📄 ライセンス

MIT

原文は [README.md](../../README.md)（英語）です。内容が食い違う場合は、英語版が正しいです。
