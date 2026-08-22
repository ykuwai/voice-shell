# Voice Shell

[English](../../README.md) · [日本語](README.ja.md) · [Español](README.es.md) · [Français](README.fr.md) · [Deutsch](README.de.md) · [简体中文](README.zh.md) · 한국어

원문은 영어로 된 [README.md](../../README.md)입니다. 내용이 어긋나면 영어 쪽이 맞습니다.

목소리로 Claude Code에 지시를 내리는 Agent Skill. 키보드 없이 말하면 지시가 그대로
전달됩니다.

> 마이크 → 음성 인식 → JSONL 한 줄 → Monitor → Claude Code

작업하다 떠오른 것을 그냥 말하면 Enter를 누르지 않아도 전달됩니다. Claude Code
말고도 Codex 같은 다른 에이전트에서도 쓸 수 있습니다.

## 설치

```bash
npx skills add ykuwai/voice-shell
pip install numpy aiohttp "sounddevice>=0.5.6"
```

Chrome만 있으면 이것으로 끝입니다. **내려받을 모델도, 기다릴 것도 없습니다.**

## 사용

Claude Code에서 `/voice-shell`이라고 치거나 "음성 모드"라고 말합니다. 그다음부터는
말만 하면 됩니다. 끝낼 때는 "음성 모드 끝".

http://127.0.0.1:8090 에 창이 따로 열리고, 들은 말이 말하는 대로 그 자리에서
늘어납니다. 맨 앞에 띄워 두면 다른 일을 하면서도 지켜볼 수 있습니다.

| 보내는 방식 | 무슨 일이 일어나나 |
|---|---|
| 바로 전달 | 말한 것이 그대로 갑니다 |
| 고쳐서 | 쌓아 두었다가 고친 뒤에 보냅니다 |
| 멈춤 | 멈춘 동안 한 말은 어디에도 남지 않습니다 |

손이 바빠도 **목소리만으로 바꿀 수 있습니다.** "음소거"와 "음소거 해제"로 마이크를
끄고 켜고, "초안 모드"와 "즉시 모드"로 보내는 방식을 바꿉니다. 문장 끝에 "이건 취소"를
붙이면 그 한마디는 보내지 않고 버립니다. (브라우저 인식으로 껐을 때만은 소리 자체를
놓기 때문에 창에서 마이크를 다시 켜야 합니다.)

일마다 음성 모드를 따로 띄워 두고 **어느 쪽으로 갈지 창에서 고를 수 있습니다.**
목소리로도 고릅니다("세션 2").

잘못 들리는 고유명사는 사전에 넣어 둘 수 있습니다(`cloud code → Claude Code`).
넣어 둔 치환은 아직 인식 중인 글자에도 적용됩니다.

## 목소리가 어디로 가나

**기본은 브라우저 인식이라서 소리가 Google 서버로 보내집니다.** 내 컴퓨터 밖으로
내보내고 싶지 않으면 창의 설정에서 다른 방식을 고르면 됩니다. 같은 주의가 그 자리에도
쓰여 있습니다.

| 방식 | 필요한 것 | 소리가 가는 곳 |
|---|---|---|
| **이 브라우저**(기본) | Chrome. 창이 열려 있는 동안만 동작 | **Google 서버** |
| Apple 온디바이스 | macOS 26 이상. 따로 설치할 것 없음 | 이 컴퓨터 안에만 |
| Whisper | `faster-whisper`. 고유명사에 강함 | 이 컴퓨터 안에만 |

고른 방식을 기억하므로 다음에도 그대로 시작합니다. 전부 로컬에서 끝내는 두 가지
방식은 [SETUP.md](skills/voice-shell/SETUP.md)에 있습니다.

어떤 언어를 인식할 수 있는지는 고른 방식이 정합니다. 브라우저는 Chrome이 가진 목록,
Apple은 OS에 설치된 로케일, Whisper는 모델이 다루는 범위입니다. 창 자체는 일곱 가지
언어로 나옵니다.

## 명령

```bash
voice-shell.sh start [--engine X] [--no-gui]
voice-shell.sh stop
voice-shell.sh status
voice-shell.sh engines
```

| 명령 | 하는 일 |
|---|---|
| `start` | 시작합니다. 지난번에 고른 방식을 기억합니다 |
| `stop` | 멈춥니다 |
| `status` | 무엇이 돌고 있는지와, 어느 세션이 듣고 있는지 |
| `engines` | 고를 수 있는 인식 방식 |

설정한 것은 모두 `~/.config/voice-shell/`에 남아 다시 켜도 그대로입니다.

## 잘 안 될 때

Linux에서는 녹음에 `arecord`가 필요합니다.

```bash
sudo apt install alsa-utils      # Linux
```

| 이런 때 | 이렇게 |
|---|---|
| 말해도 아무것도 오지 않는다 | 반응하는 소리 크기가 너무 높습니다. 창의 마이크 아래에 있는 표시를, 말할 때 막대가 넘어가는 곳까지 내립니다 |
| 소리만 나도 저절로 보내진다 | 반응하는 소리 크기가 너무 낮습니다. 같은 표시를, 자기 목소리만 넘어가는 곳까지 올립니다 |
| `No Python it can run was found` | `export VOICE_SHELL_PYTHON=/path/to/.venv/bin/python` |
| 시작할 때 `FAILED`가 나온다 | `voice-shell.sh status`를 보고 `daemon.out`의 끝부분을 읽습니다 |

## 조금 더

아래 두 가지는 영어로만 있습니다. 대부분에게 필요한 것은 위에 이미 적혀 있습니다.

| 읽을 것 | 무엇이 들어 있나 |
|---|---|
| [SETUP.md](../../skills/voice-shell/SETUP.md) | 환경별 설치 방법과, 막혔을 때 할 일 |
| [SKILL.md](../../skills/voice-shell/SKILL.md) | 에이전트가 읽는 절차. 세세한 동작은 여기에 |

## 참고

- [Web Speech API (MDN)](https://developer.mozilla.org/docs/Web/API/SpeechRecognition)
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)

## 라이선스

MIT
