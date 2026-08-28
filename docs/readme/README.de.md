# Voice Shell

[English](../../README.md) · [日本語](README.ja.md) · [Español](README.es.md) · [Français](README.fr.md) · Deutsch · [简体中文](README.zh.md) · [한국어](README.ko.md)

<p align="center">
  <img src="https://img.shields.io/github/license/ykuwai/voice-shell" alt="License">
  <img src="https://img.shields.io/github/last-commit/ykuwai/voice-shell" alt="Last commit">
</p>

Das Original ist [README.md](../../README.md) auf Englisch. Bei Widersprüchen gilt das
Englische.

**Sprich mit Claude Code. Keine Tastatur.**

Du denkst beim Arbeiten laut, und der Satz kommt als Prompt an, ganz ohne Enter zu
drücken. Das ist keine Diktierfunktion, die nachträglich an ein Textfeld geklebt
wurde. Stummschalten, Gegenlesen, Rückgängigmachen und die Wahl, welche Sitzung dich
hört, all das per Stimme, während deine Hände bei der eigentlichen Arbeit bleiben.

<p align="center">
  <img src="images/viewer.png" alt="Der Voice-Shell-Viewer. Ein schwebendes Fenster mit laufender Transkription, Sitzungsauswahl und Sendemodus" width="360">
</p>

## Warum Voice Shell

- **Nichts zu drücken, um es abzuschicken.** Die meisten Sprachwerkzeuge füllen
  ein Textfeld und warten, bis du auf Senden klickst. Hier geht der Satz direkt
  durch, sobald er erkannt ist, kein Knopf, kein Bestätigungsschritt, kein
  Fenster zum Anklicken.
- **Zum Ausprobieren musst du nichts installieren.** Die Spracherkennung läuft
  standardmäßig im Browser. Kein Modell zum Herunterladen, kein Warten. Willst du es
  später ganz privat, wechselst du mit einer einzigen Einstellung zur Erkennung auf
  dem Gerät (Apple oder Whisper), ohne etwas neu lernen zu müssen.
- **Eine vollständige Sprachbedienung, nicht nur ein Mikrofon-Symbol.** Sag „Mikro
  aus", „Entwurf", „Sofortmodus", „streich das" oder „Sitzung 2" am Ende eines
  Satzes, und schon funktioniert es ganz ohne Hände. Das schwebende Fenster zeigt
  genau das, was gerade erkannt wird, während du sprichst.
- **Für mehr als eine Sache gleichzeitig nutzbar.** Lass den Sprachmodus in mehreren
  Claude-Code-Sitzungen gleichzeitig an und wähle im Fenster oder per Stimme, welche
  deine Worte bekommt.
- **Falsch verstandene Namen korrigieren sich von selbst.** Trag die Korrektur
  einmal ein („cloud code → Claude Code"), und sie gilt von da an, sogar bei Text,
  der gerade noch erkannt wird.

## Installation

```bash
npx skills add ykuwai/voice-shell -g
pip install numpy aiohttp "sounddevice>=0.5.6"
```

Wenn du Chrome hast, reicht das schon. `-g` legt es in `~/.claude/skills/` ab,
damit steht es in jedem Projekt zur Verfügung. Nur in einem Projekt
ausprobieren? `-g` weglassen, dann landet es nur im `.claude/skills/` dieses
Projekts.

Tippe `/voice-shell` in Claude Code, oder sag „Sprachmodus", um zu starten. Die
Schritte, denen ein Agent von da an folgt, stehen in
[SKILL.md](../../skills/voice-shell/SKILL.md).

Aus einem Agenten heraus, oder aus einem Skript, Claude Code namentlich
angeben statt es selbst erkennen zu lassen, und `-y` dazuschreiben, um die
Bestätigung zu überspringen.

```bash
npx skills add ykuwai/voice-shell -g -a claude-code -y
```

## Aktualisieren

```bash
npx skills update voice-shell -y
```

Ohne `-y` fragt es zuerst. Ohne den Namen aktualisiert es alle installierten
Skills, diesen eingeschlossen.

## Wohin deine Stimme geht

> [!NOTE]
> Voreingestellt ist die Erkennung im Browser, das Audio geht also an Googles
> Server. Wenn es auf deinem Rechner bleiben soll, wähle in den Einstellungen
> im Fenster eine andere Art. Derselbe Hinweis steht dort an Ort und Stelle.

| Art | Was sie braucht | Wohin das Audio geht |
|---|---|---|
| **Dieser Browser** (Voreinstellung) | Chrome. Läuft nur bei geöffnetem Fenster | **Googles Server** |
| Apple auf dem Gerät | macOS 26 oder neuer. Nichts zusätzlich zu installieren | Bleibt auf dem Rechner |
| Whisper | `faster-whisper`. Stark bei Eigennamen | Bleibt auf dem Rechner |

Die gewählte Art wird gemerkt, beim nächsten Mal startet es also genauso. Die beiden
Arten, die alles lokal halten, stehen in
[SETUP.md](../../skills/voice-shell/SETUP.md).

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

## Noch etwas mehr

Die beiden unten gibt es nur auf Englisch. Was die meisten brauchen, steht schon
weiter oben.

| Was zu lesen ist | Was drinsteht |
|---|---|
| [SETUP.md](../../skills/voice-shell/SETUP.md) | Die Installation je nach Umgebung, und was zu tun ist, wenn es hakt |
| [SKILL.md](../../skills/voice-shell/SKILL.md) | Die Schritte, die der Agent liest. Das feine Verhalten steht hier |

## Verweise

- [Web Speech API (MDN)](https://developer.mozilla.org/docs/Web/API/SpeechRecognition)
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)

## Lizenz

MIT
</content>
</invoke>
