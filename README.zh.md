# voice-shell

[English](README.md) · [日本語](README.ja.md) · [Español](README.es.md) · [Français](README.fr.md) · [Deutsch](README.de.md) · 简体中文 · [한국어](README.ko.md)

原文是英文的 [README.md](README.md)。两边对不上时，以英文为准。

用说话给 Claude Code 下指令的 Agent Skill。不用键盘，说出来指令就送到了。

> 麦克风 → 语音识别 → 一行 JSONL → Monitor → Claude Code

干活的时候想到什么就直接说，不用按 Enter 也会送到。除了 Claude Code，Codex 这类别的
智能体也能用。

## 安装

```bash
npx skills add ykuwai/voice-shell
pip install numpy aiohttp sounddevice
```

有 Chrome 的话，这样就够了。**不用下模型，也不用等。**

## 使用

在 Claude Code 里输入 `/voice-shell`，或者说「进入语音模式」。之后说话就行了。
想停下来就说「退出语音模式」。

会单独开一个窗口，地址是 http://127.0.0.1:8090，听到的字会在那里边说边长出来。
把它浮在最上面，一边做别的事一边就能看着。

| 怎么送出去 | 会发生什么 |
|---|---|
| 直送 | 说的话直接送过去 |
| 先改 | 先攒着，改好了再送 |
| 暂停 | 暂停期间说的话哪里都不留 |

手上腾不开的时候，**光靠说话也能切换。**「静音」和「解除静音」关掉和打开麦克风，
「草稿模式」和「即时模式」换送出去的方式。一句话说完接一句「这句不要了」，这一句就
丢掉不送。（只有用浏览器识别的时候，静音会把音频本身放掉，所以要从窗口里把麦克风
重新打开。）

可以给每件事各开一个语音模式，**在窗口里挑说的话送给哪一个。** 用说的也能挑
（「会话2」）。

容易听错的专有名词可以登记到词典里（`cloud code → Claude Code`）。登记的替换，对还在
识别过程中的字也管用。

## 你的声音去了哪里

**默认是用浏览器识别的，所以音频会送到 Google 的服务器。** 想让它留在自己机器上的
时候，在窗口的设置里换一种方式。同样的提醒在那里也写着。

| 方式 | 需要什么 | 音频去哪里 |
|---|---|---|
| **这个浏览器**（默认） | Chrome。只在窗口开着的时候能用 | **Google 的服务器** |
| Apple 设备端 | macOS 26 以上。不用另外装东西 | 留在这台机器里 |
| Whisper | `faster-whisper`。专有名词很强 | 留在这台机器里 |

选过的方式它会记住，下次照样启动。两种全程在本地跑的方式写在
[SETUP.md](skills/voice-shell/SETUP.md) 里。

能识别哪些语言，由选的方式决定。浏览器给的是 Chrome 自带的那些，Apple 给的是系统里
装了的区域设置，Whisper 给的是模型覆盖的范围。窗口本身有七种语言。

## 命令

```bash
voice-shell.sh start [--engine X] [--no-gui]
voice-shell.sh stop
voice-shell.sh status
voice-shell.sh engines
```

| 命令 | 做什么 |
|---|---|
| `start` | 启动，并且记着上次选的方式 |
| `stop` | 停止 |
| `status` | 现在跑着什么，以及哪个会话在听 |
| `engines` | 能选的识别方式 |

设置的东西全都留在 `~/.config/voice-shell/`，重启也不会没。

## 出问题的时候

在 Linux 上录音需要 `arecord`。

```bash
sudo apt install alsa-utils      # Linux
```

| 看到的情况 | 怎么办 |
|---|---|
| 说了话但什么都没送到 | 触发的音量定得太高。把窗口里麦克风下面那个记号往下拉，拉到说话时横条能越过去为止 |
| 有点响动就自己送出去 | 触发的音量定得太低。把同一个记号往上拉，拉到只有自己的声音能越过去为止 |
| `No Python it can run was found` | `export VOICE_SHELL_PYTHON=/path/to/.venv/bin/python` |
| 启动显示 `FAILED` | 跑一下 `voice-shell.sh status`，再看 `daemon.out` 的末尾 |

## 再详细一点

下面这两份只有英文。大多数人需要的，上面都写了。

| 读什么 | 里面有什么 |
|---|---|
| [SETUP.md](skills/voice-shell/SETUP.md) | 各种环境下怎么装，卡住了怎么办 |
| [SKILL.md](skills/voice-shell/SKILL.md) | 智能体读的步骤。细的行为都在这里 |

## 参考

- [Web Speech API (MDN)](https://developer.mozilla.org/docs/Web/API/SpeechRecognition)
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)

## 许可

MIT
