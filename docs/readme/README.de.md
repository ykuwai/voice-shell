# Voice Shell

[English](../../README.md) · [日本語](README.ja.md) · [Español](README.es.md) · [Français](README.fr.md) · Deutsch · [简体中文](README.zh.md) · [한국어](README.ko.md)

<p align="center">
  <img src="https://img.shields.io/github/license/ykuwai/voice-shell" alt="License">
  <img src="https://img.shields.io/github/last-commit/ykuwai/voice-shell" alt="Last commit">
</p>

Das Original ist [README.md](../../README.md) auf Englisch. Bei Widersprüchen gilt das
Englische.

**Sprechen Sie mit Claude Code. Keine Tastatur.**

Sie denken beim Arbeiten laut, und der Satz kommt als Prompt an, ganz ohne Enter zu
drücken. Das ist keine Diktierfunktion, die nachträglich an ein Textfeld geklebt
wurde. Stummschalten, Gegenlesen, Rückgängigmachen und die Wahl, welche Sitzung Sie
hört, all das per Stimme, während Ihre Hände bei der eigentlichen Arbeit bleiben.

<p align="center">
  <img src="images/viewer.png" alt="Der Voice-Shell-Viewer. Ein schwebendes Fenster mit laufender Transkription, Sitzungsauswahl und Sendemodus" width="360">
</p>

## 💡 Warum Voice Shell

- **Nichts zu drücken, um es abzuschicken.** Die meisten Sprachwerkzeuge füllen
  ein Textfeld und warten, bis Sie auf Senden klicken. Hier geht der Satz direkt
  durch, sobald er erkannt ist, kein Knopf, kein Bestätigungsschritt, kein
  Fenster zum Anklicken.
- **Zum Ausprobieren müssen Sie nichts installieren.** Die Spracherkennung läuft
  standardmäßig im Browser. Kein Modell zum Herunterladen, kein Warten. Wollen
  Sie es später ganz privat, wechseln Sie mit einer einzigen Einstellung zur
  Erkennung auf dem Gerät (Apple oder Whisper), ohne etwas neu lernen zu müssen.
- **Eine vollständige Sprachbedienung, nicht nur ein Mikrofon-Symbol.**
  Stummschalten, zwischen Entwurf und Sofortmodus wechseln, das gerade Gesagte
  rückgängig machen, wählen, welche Sitzung zuhört, all das funktioniert auch
  per Stimme. Siehe „Was Sie sagen können" weiter unten. Das schwebende
  Fenster zeigt genau das, was gerade erkannt wird, während Sie sprechen.
- **Für mehr als eine Sache gleichzeitig nutzbar.** Lassen Sie den Sprachmodus in
  mehreren Claude-Code-Sitzungen gleichzeitig an und wählen Sie im Fenster oder
  per Stimme, welche Ihre Worte bekommt.
- **Falsch verstandene Namen korrigieren sich von selbst.** Tragen Sie die
  Korrektur einmal ein („cloud code → Claude Code"), und sie gilt von da an,
  sogar bei Text, der gerade noch erkannt wird.

## 📦 Voice Shell installieren

```bash
pip install numpy aiohttp "sounddevice>=0.5.6"
npx skills add ykuwai/voice-shell -g -a claude-code -y
```

Wenn Sie Chrome haben, reicht das schon. `-g` legt es in `~/.claude/skills/` ab,
damit steht es in jedem Projekt zur Verfügung. Nur in einem Projekt
ausprobieren? `-g` weglassen, dann landet es nur im `.claude/skills/` dieses
Projekts. `-a claude-code` benennt Claude Code direkt, statt es `npx` raten zu
lassen, und `-y` überspringt die Bestätigung, die sonst käme.

Tippen Sie `/voice-shell` in Claude Code, oder sagen Sie „Sprachmodus", um zu
starten. Die Schritte, denen ein Agent von da an folgt, stehen in
[SKILL.md](../../skills/voice-shell/SKILL.md).

### 🔄 Aktualisieren

```bash
npx skills update voice-shell -y
```

Ohne `-y` fragt es zuerst. Ohne den Namen aktualisiert es alle installierten
Skills, diesen eingeschlossen.

## 🔒 Wohin Ihre Stimme geht

Zwei der drei Arten schicken Ihre Stimme nie irgendwohin außerhalb dieses
Rechners, und der Wechsel zu einer davon ist nur eine Einstellung entfernt.
Welche Art gerade aktiv ist, sehen Sie immer im Fenster.

> [!NOTE]
> Voreingestellt ist die Erkennung im Browser, das Audio geht also an Googles
> Server. Wenn es auf Ihrem Rechner bleiben soll, wählen Sie in den
> Einstellungen im Fenster eine andere Art. Derselbe Hinweis steht dort an
> Ort und Stelle.

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

## 🗣️ Was Sie sagen können

Sagen Sie eines dieser Worte allein, ohne sonst etwas im Satz, und es wirkt
sofort.

| Sagen Sie das | Was passiert |
|---|---|
| „Stummschalten" oder „Mikro aus" | Das Mikrofon geht aus |
| „Stummschaltung aufheben" | Das Mikrofon kommt zurück (nur solange ein Modell auf diesem Rechner zuhört, nicht im Browser) |
| „Entwurf" oder „Entwurfsmodus" | Was Sie ab hier sagen, sammelt sich, statt rauszugehen, sodass Sie es vor dem Senden korrigieren können |
| „Sofortmodus" | Zurück zum direkten Senden |
| „Sitzung 2" oder „Nummer zwei" | Legt fest, welche Sitzung Ihre Worte bekommt, wenn mehr als eine zuhört |

Hängen Sie eines davon an das Ende dessen an, was Sie sagen, und es gilt nur
für diesen einen Satz.

| Sagen Sie das | Was passiert |
|---|---|
| „streich das" | Der Satz, den Sie gerade gesagt haben, wird verworfen |
| „das ändere ich" | Der Satz landet im Feld statt rauszugehen, sodass Sie ihn zuerst korrigieren können |

Jedes der oben genannten Worte lässt sich in den Einstellungen abschalten,
und Sie können ihm Ihre eigene Formulierung beibringen, alles im Fenster.
Die vollständige Liste, in allen sieben Sprachen des Fensters, steckt hinter
dem Glühbirnen-Symbol auf dem Bildschirm.

## 📖 Zum Weiterlesen

Die beiden unten gibt es nur auf Englisch. Was die meisten brauchen, steht schon
weiter oben.

| Was zu lesen ist | Was drinsteht |
|---|---|
| [SETUP.md](../../skills/voice-shell/SETUP.md) | Die Installation je nach Umgebung, und was zu tun ist, wenn es hakt |
| [SKILL.md](../../skills/voice-shell/SKILL.md) | Die Schritte, die der Agent liest. Das feine Verhalten steht hier |

## 🔗 Verweise

- [Web Speech API (MDN)](https://developer.mozilla.org/docs/Web/API/SpeechRecognition)
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)

## 📄 Lizenz

MIT
