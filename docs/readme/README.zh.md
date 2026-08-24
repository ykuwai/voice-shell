# Voice Shell

[English](../../README.md) · [日本語](README.ja.md) · [Español](README.es.md) · [Français](README.fr.md) · [Deutsch](README.de.md) · 简体中文 · [한국어](README.ko.md)

<p align="center">
  <img src="https://img.shields.io/github/license/ykuwai/voice-shell" alt="许可证">
  <img src="https://img.shields.io/github/last-commit/ykuwai/voice-shell" alt="最近一次提交">
</p>

原文是英文的 [README.md](../../README.md)。两边对不上时，以英文为准。

**说话就能指挥 Claude Code，不用键盘。**

干活的时候，心里想到什么就直接说出来，一句话就变成指令送过去，不用按 Enter。
这不是往文本框里贴语音输入那种做法。静音、查看、撤销，还有挑哪个会话来听你
说话，这些全都只靠说话就能做到，手可以一直放在手头的事情上。

<p align="center">
  <img src="images/viewer.png" alt="Voice Shell 的悬浮查看窗口，显示正在识别的文字、会话选择和发送方式" width="360">
</p>

## 特点

- **不用按任何东西来发送。** 大多数语音工具是把内容填进文本框，然后等你去点
  发送。这里是一听到就直接发出去，没有按钮，没有确认步骤，也不用点开某个
  窗口。
- **想试试的话，什么都不用装。** 默认用浏览器识别，不用下模型，也不用等。想让
  一切都留在本地的时候，只要改一个设置，就能切换到 Apple 或 Whisper 的设备端
  识别，不用重新学任何东西。
- **是一整套语音操作界面，不是一个麦克风图标而已。** 「静音」「暂停」「即时」
  「这句不要」「会话2」，把这些放在一句话的末尾说出来，不动手也能切换。悬浮
  窗口会把听到的内容原样显示出来，边说边长出来。
- **可以同时用在好几件事上。** 在多个 Claude Code 会话里都开着语音模式，说的
  话要送给哪一个，从窗口里选，或者直接用说的选都行。
- **听错的名字自己就改过来了。** 教它一次（「cloud code → Claude Code」），
  之后就一直会自动改，连正在识别中的文字也会跟着改。

## 安装

```bash
npx skills add ykuwai/voice-shell
pip install numpy aiohttp
```

有 Chrome 的话，这样就够了。

在 Claude Code 里输入 `/voice-shell`，或者说「进入语音模式」，就会开始。之后
的步骤写在 [SKILL.md](../../skills/voice-shell/SKILL.md) 里。

## 你的声音去了哪里

> [!NOTE]
> 默认是用浏览器识别的，所以音频会送到 Google 的服务器。想让它留在自己机器上
> 的时候，在窗口的设置里换一种方式。同样的提醒在那里也写着。

| 方式 | 需要什么 | 音频去哪里 |
|---|---|---|
| **这个浏览器**（默认） | Chrome。只在窗口开着的时候能用 | **Google 的服务器** |
| Apple 设备端 | macOS 26 以上。不用另外装东西 | 留在这台机器里 |
| Whisper | `faster-whisper`。专有名词很强 | 留在这台机器里 |

选过的方式它会记住，下次照样启动。两种全程在本地跑的方式写在
[SETUP.md](../../skills/voice-shell/SETUP.md) 里。

能识别哪些语言，由选的方式决定。浏览器给的是 Chrome 自带的那些，Apple 给的是
系统里装了的区域设置，Whisper 给的是模型覆盖的范围。窗口本身有七种语言。

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
| [SETUP.md](../../skills/voice-shell/SETUP.md) | 各种环境下怎么装，卡住了怎么办 |
| [SKILL.md](../../skills/voice-shell/SKILL.md) | 智能体读的步骤。细的行为都在这里 |

## 参考

- [Web Speech API (MDN)](https://developer.mozilla.org/docs/Web/API/SpeechRecognition)
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)

## 许可

MIT
