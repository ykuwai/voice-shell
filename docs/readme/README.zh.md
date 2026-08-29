<p align="center">
  <img src="images/logo.svg" alt="Voice Shell" width="88">
</p>

# Voice Shell

[English](../../README.md) · [日本語](README.ja.md) · [Español](README.es.md) · [Français](README.fr.md) · [Deutsch](README.de.md) · 简体中文 · [한국어](README.ko.md)

<p align="center">
  <img src="https://img.shields.io/github/license/ykuwai/voice-shell" alt="许可证">
  <img src="https://img.shields.io/github/last-commit/ykuwai/voice-shell" alt="最近一次提交">
</p>

原文是英文的 [README.md](../../README.md)。两边对不上时，以英文为准。

**说话就能指挥 Claude Code，不用键盘。**

工作的时候，您心里想到什么就直接说出来，一句话就变成指令送过去，不用按 Enter。
这不是往文本框里贴语音输入那种做法。静音、查看、撤销，还有挑哪个会话来听您
说话，这些全都只靠说话就能做到，手可以一直放在手头的事情上。

<p align="center">
  <img src="images/viewer.png" alt="Voice Shell 的悬浮查看窗口，显示正在识别的文字、会话选择和发送方式" width="360">
</p>

## 💡 特点

- **不用按任何东西来发送。** 大多数语音工具是把内容填进文本框，然后等您去点
  发送。这里是一听到就直接发出去，没有按钮，没有确认步骤，也不用点开某个
  窗口。
- **想试试的话，什么都不用装。** 默认用浏览器识别，不用下模型，也不用等。想让
  一切都留在本地的时候，只要改一个设置，就能切换到 Apple 或 Whisper 的设备端
  识别，不用重新学任何东西。
- **是一整套语音操作界面，不是一个麦克风图标而已。** 静音、在草稿模式和即时
  模式之间切换、撤销刚说的话、挑哪个会话来听，这些也全都能靠说话完成。详见
  下面的「说话能做到的事」。悬浮窗口会把听到的内容原样显示出来，边说边长
  出来。
- **可以同时用在好几件事上。** 在多个 Claude Code 会话里都开着语音模式，说的
  话要送给哪一个，从窗口里选，或者直接用说的选都行。
- **听错的名字自己就改过来了。** 教它一次（「cloud code → Claude Code」），
  之后就一直会自动改，连正在识别中的文字也会跟着改。

## 📦 安装 Voice Shell

```bash
pip install numpy aiohttp "sounddevice>=0.5.6"
npx skills add ykuwai/voice-shell -g -a claude-code -y
```

有 Chrome 的话，这样就够了。加上 `-g` 会装到 `~/.claude/skills/`，所有项目都能用。
只想在一个项目里试试的话，去掉 `-g`，就只装到那个项目自己的 `.claude/skills/` 里。
`-a claude-code` 直接指定 Claude Code，不用交给 `npx` 自己判断，`-y` 跳过原本
会问的确认。

在 Claude Code 里输入 `/voice-shell`，或者说「进入语音模式」，就会开始。之后
的步骤写在 [SKILL.md](../../skills/voice-shell/SKILL.md) 里。

### 🔄 更新

```bash
npx skills update voice-shell -y
```

不加 `-y` 会先问一下。不写名字的话，会把装的所有技能一起更新，这个也包括在内。

## 🔒 您的声音去了哪里

三种方式里有两种从不把您的声音送到这台机器以外的任何地方，切换只需要改
一个设置。当前用的是哪一种，窗口里始终能看到。

> [!NOTE]
> 默认是用浏览器识别的，所以音频会送到 Google 的服务器。想让它留在本地
> 的时候，在窗口的设置里换一种方式。同样的提醒在那里也写着。

| 方式 | 需要什么 | 音频去哪里 |
|---|---|---|
| **这个浏览器**（默认） | Chrome。只在窗口开着的时候能用 | **Google 的服务器** |
| Apple 设备端 | macOS 26 以上。不用另外装东西 | 留在本地 |
| Whisper | `faster-whisper`。专有名词很强 | 留在本地 |

选过的方式它会记住，下次照样启动。两种全程在本地跑的方式写在
[SETUP.md](../../skills/voice-shell/SETUP.md) 里。

能识别哪些语言，由选的方式决定。浏览器给的是 Chrome 自带的那些，Apple 给的是
系统里装了的区域设置，Whisper 给的是模型覆盖的范围。窗口本身有七种语言。

## 🗣️ 说话能做到的事

单独说出下面这句话，不加别的内容，就会立刻生效。

| 这样说 | 会发生什么 |
|---|---|
| 「静音」 | 麦克风关闭 |
| 「解除静音」 | 麦克风恢复（仅限这台机器上的模型在监听时，浏览器识别下不行） |
| 「草稿模式」或「暂存模式」 | 从这里开始说的话会先存着，不直接发出去，发送前可以修改 |
| 「即时模式」 | 回到直接发送的状态 |
| 「会话2」或「第2个」 | 有两个以上会话在听的时候，选定由哪一个接收 |

把下面这句加在一句话的末尾，只对那一句话生效。

| 这样说 | 会发生什么 |
|---|---|
| 「这句不要了」 | 刚说的那一句整句被丢弃 |
| 「这句我来改」 | 刚说的那一句不发出去，转到下面的框里，发送前可以修改 |

以上每一种说法都能在设置里关掉，也能教它您自己的说法，都在窗口的设置里。
窗口支持的全部七种语言的完整列表，在屏幕上的灯泡图标里。

## 📖 延伸阅读

下面这两份只有英文。大多数人需要的，上面都写了。

| 读什么 | 里面有什么 |
|---|---|
| [SETUP.md](../../skills/voice-shell/SETUP.md) | 各种环境下怎么装，卡住了怎么办 |
| [SKILL.md](../../skills/voice-shell/SKILL.md) | 智能体读的步骤。细的行为都在这里 |

## 🔗 参考链接

- [Web Speech API (MDN)](https://developer.mozilla.org/docs/Web/API/SpeechRecognition)
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)

## 📄 许可证

MIT
