# voice-shell

[English](README.md) · [日本語](README.ja.md) · [Español](README.es.md) · [Français](README.fr.md) · Deutsch · [简体中文](README.zh.md) · [한국어](README.ko.md)

Das Original ist [README.md](README.md) auf Englisch. Bei Widersprüchen gilt das
Englische.

Ein Agent Skill, um Claude Code per Sprache Anweisungen zu geben. Ohne Tastatur.
Du sprichst, und die Anweisung geht durch.

> Mikro → Spracherkennung → eine Zeile JSONL → Monitor → Claude Code

Sag beim Arbeiten einfach, was dir einfällt, und es kommt an, ohne dass du Enter
drückst. Es läuft mit Claude Code und ebenso mit anderen Agenten wie Codex.

## Installation

```bash
npx skills add ykuwai/voice-shell
pip install numpy aiohttp sounddevice
```

Wenn du Chrome hast, reicht das schon. **Kein Modell zum Herunterladen, kein Warten.**

## Benutzung

Tippe `/voice-shell` in Claude Code oder sag „Sprachmodus“. Danach sprichst du
einfach. Zum Beenden sag „Sprachmodus beenden“.

Ein eigenes Fenster öffnet sich unter http://127.0.0.1:8090, und die gehörten Wörter
wachsen dort mit, während du sprichst. Lass es im Vordergrund schweben, dann behältst
du es im Blick, während du an etwas anderem arbeitest.

| Art zu senden | Was passiert |
|---|---|
| Sofort | Was du sagst, geht direkt durch |
| Prüfen | Es sammelt sich, du kannst es vor dem Senden korrigieren |
| Pausiert | Nichts, was du in der Pause sagst, wird irgendwo aufbewahrt |

Auch mit vollen Händen **kannst du allein per Stimme umschalten**. „Mikro aus“ und
„Mikrofon einschalten“ schalten das Mikrofon ab und wieder an, „Entwurf“ und
„Sofortmodus“ ändern die Art zu senden. Beende einen Satz mit „streich das“, und
genau diese Äußerung wird verworfen statt gesendet. (Nur bei der Erkennung im
Browser gibt das Stummschalten das Audio selbst her, schalte das Mikrofon also im
Fenster wieder ein.)

Du kannst für jede Arbeit einen eigenen Sprachmodus laufen lassen und **im Fenster
wählen, wer deine Worte bekommt.** Die Stimme wählt ebenfalls („Sitzung 2“).

Eigennamen, die falsch verstanden werden, kommen in ein Wörterbuch
(`cloud code → Claude Code`). Eingetragene Ersetzungen greifen auch auf Wörter, die
gerade noch erkannt werden.

## Wohin deine Stimme geht

**Voreingestellt ist die Erkennung im Browser, das Audio geht also an Googles
Server.** Wenn es auf deinem Rechner bleiben soll, wähle in den Einstellungen im
Fenster eine andere Art. Derselbe Hinweis steht dort an Ort und Stelle.

| Art | Was sie braucht | Wohin das Audio geht |
|---|---|---|
| **Dieser Browser** (Voreinstellung) | Chrome. Läuft nur bei geöffnetem Fenster | **Googles Server** |
| Apple auf dem Gerät | macOS 26 oder neuer. Nichts zusätzlich zu installieren | Bleibt auf dem Rechner |
| Whisper | `faster-whisper`. Stark bei Eigennamen | Bleibt auf dem Rechner |

Die gewählte Art wird gemerkt, beim nächsten Mal startet es also genauso. Die beiden
Arten, die alles lokal halten, stehen in [SETUP.md](skills/voice-shell/SETUP.md).

Welche Sprachen erkannt werden, entscheidet die gewählte Art. Der Browser bietet, was
Chrome mitbringt, Apple die im System installierten Locales, Whisper das, was das
Modell abdeckt. Das Fenster selbst gibt es in sieben Sprachen.

## Befehle

```bash
voice-shell.sh start [--engine X] [--no-gui]
voice-shell.sh stop
voice-shell.sh status
voice-shell.sh engines
```

| Befehl | Was er tut |
|---|---|
| `start` | Startet es und merkt sich die zuletzt gewählte Art |
| `stop` | Beendet es |
| `status` | Was läuft, und welche Sitzung zuhört |
| `engines` | Die Arten, wie Sprache erkannt werden kann |

Alle Einstellungen bleiben in `~/.config/voice-shell/` und überstehen einen Neustart.

## Wenn etwas schiefgeht

Unter Linux braucht es zum Aufnehmen `arecord`.

```bash
sudo apt install alsa-utils      # Linux
```

| Was du siehst | Was zu tun ist |
|---|---|
| Du sprichst und nichts kommt an | Die Auslöseschwelle ist zu hoch. Zieh die Marke unter dem Mikrofon im Fenster so weit herunter, bis der Balken sie beim Sprechen überschreitet |
| Geräusche senden von allein | Die Auslöseschwelle ist zu niedrig. Zieh dieselbe Marke so weit herauf, bis nur noch deine Stimme darüber kommt |
| `No Python it can run was found` | `export VOICE_SHELL_PYTHON=/path/to/.venv/bin/python` |
| Der Start meldet `FAILED` | Führe `voice-shell.sh status` aus und lies das Ende von `daemon.out` |

## Noch etwas mehr

Die beiden unten gibt es nur auf Englisch. Was die meisten brauchen, steht schon
weiter oben.

| Was zu lesen ist | Was drinsteht |
|---|---|
| [SETUP.md](skills/voice-shell/SETUP.md) | Die Installation je nach Umgebung, und was zu tun ist, wenn es hakt |
| [SKILL.md](skills/voice-shell/SKILL.md) | Die Schritte, die der Agent liest. Das feine Verhalten steht hier |

## Verweise

- [Web Speech API (MDN)](https://developer.mozilla.org/docs/Web/API/SpeechRecognition)
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)

## Lizenz

MIT
