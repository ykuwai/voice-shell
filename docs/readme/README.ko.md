# Voice Shell

[English](../../README.md) · [日本語](README.ja.md) · [Español](README.es.md) · [Français](README.fr.md) · [Deutsch](README.de.md) · [简体中文](README.zh.md) · 한국어

<p align="center">
  <img src="https://img.shields.io/github/license/ykuwai/voice-shell" alt="라이선스">
  <img src="https://img.shields.io/github/last-commit/ykuwai/voice-shell" alt="최근 커밋">
</p>

원문은 영어로 된 [README.md](../../README.md)입니다. 내용이 어긋나면 영어 쪽이 맞습니다.

**말로 Claude Code에 지시하세요. 키보드는 필요 없습니다.**

작업하다 머릿속에 떠오른 생각을 그대로 말하면, Enter를 누르지 않아도 그 문장이
프롬프트로 전달됩니다. 텍스트 입력창에 음성 인식을 갖다 붙인 것과는 다릅니다.
음소거, 다시 듣기, 취소, 어느 세션으로 보낼지 고르는 것까지 전부 목소리만으로
처리할 수 있어서, 손은 하던 일에 그대로 둘 수 있습니다.

<p align="center">
  <img src="images/viewer.png" alt="Voice Shell 뷰어 창. 실시간으로 인식되는 문자와 세션 선택, 전송 방식이 함께 나타난다" width="360">
</p>

## 특징

- **보낼 때 누를 것이 없습니다.** 대부분의 음성 도구는 텍스트 상자를 채우고
  전송을 누르길 기다립니다. 여기서는 듣는 순간 그대로 전달됩니다. 버튼도,
  확인 단계도, 클릭해서 열 창도 필요 없습니다.
- **써 보는 데 아무것도 설치할 필요가 없습니다.** 기본 인식은 브라우저가
  처리하므로 모델을 내려받거나 기다릴 것이 없습니다. 완전히 내 컴퓨터
  안에서만 처리하고 싶어지면 설정 하나만 바꿔서 Apple이나 Whisper의
  온디바이스 인식으로 전환할 수 있습니다. 새로 익힐 것은 없습니다.
- **마이크 아이콘 하나로 끝나는 방식이 아닙니다.** "음소거", "초안 모드",
  "즉시 모드", "이건 취소", "세션 2", 문장 끝에 이렇게 말하는 것만으로
  손대지 않고 다 됩니다. 창에는 말하는 그대로 인식된 내용이 바로 나타납니다.
- **여러 작업에서 동시에 쓸 수 있습니다.** 여러 Claude Code 세션에서 동시에
  음성 모드를 켜 두고, 어느 세션에 말을 전달할지 창에서든 목소리로든 고를
  수 있습니다.
- **잘못 알아들은 이름은 한 번만 가르치면 됩니다.** (`cloud code → Claude Code`처럼)
  한 번 등록해 두면 그다음부터는 계속 고쳐지고, 아직 인식 중인 글자에도
  바로 반영됩니다.

## 설치

```bash
npx skills add ykuwai/voice-shell
pip install numpy aiohttp "sounddevice>=0.5.6"
```

Chrome만 있으면 이것으로 끝입니다.

Claude Code에서 `/voice-shell`이라고 치거나 "음성 모드"라고 말하면 시작됩니다.
그다음부터 에이전트가 따르는 절차는 [SKILL.md](../../skills/voice-shell/SKILL.md)에
있습니다.

에이전트에서 실행하거나 스크립트에서 실행할 때는 자동 감지에 맡기지 말고
Claude Code를 직접 지정하고, `-y`로 확인도 건너뛰세요.

```bash
npx skills add ykuwai/voice-shell -a claude-code -y
```

## 업데이트

```bash
npx skills update voice-shell -y
```

`-y`를 빼면 먼저 묻습니다. 이름을 빼면 이 스킬을 포함해서 설치된 스킬을 전부
한꺼번에 업데이트합니다.

## 목소리가 어디로 가나

> [!NOTE]
> 기본은 브라우저 인식이라서 소리가 Google 서버로 보내집니다. 내 컴퓨터
> 밖으로 내보내고 싶지 않으면 창의 설정에서 다른 방식을 고르면 됩니다. 같은
> 주의가 그 자리에도 쓰여 있습니다.

| 방식 | 필요한 것 | 소리가 가는 곳 |
|---|---|---|
| **이 브라우저**(기본) | Chrome. 창이 열려 있는 동안만 동작 | **Google 서버** |
| Apple 온디바이스 | macOS 26 이상. 따로 설치할 것 없음 | 이 컴퓨터 안에만 |
| Whisper | `faster-whisper`. 고유명사에 강함 | 이 컴퓨터 안에만 |

고른 방식을 기억하므로 다음에도 그대로 시작합니다. 전부 로컬에서 끝내는 두
가지 방식은 [SETUP.md](../../skills/voice-shell/SETUP.md)에 있습니다.

어떤 언어를 인식할 수 있는지는 고른 방식이 정합니다. 브라우저는 Chrome이
가진 목록, Apple은 OS에 설치된 로케일, Whisper는 모델이 다루는 범위입니다.
창 자체는 일곱 가지 언어로 나옵니다.

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
