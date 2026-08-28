# Voice Shell

[English](../../README.md) · [日本語](README.ja.md) · Español · [Français](README.fr.md) · [Deutsch](README.de.md) · [简体中文](README.zh.md) · [한국어](README.ko.md)

<p align="center">
  <img src="https://img.shields.io/github/license/ykuwai/voice-shell" alt="Licencia">
  <img src="https://img.shields.io/github/last-commit/ykuwai/voice-shell" alt="Último commit">
</p>

El original es [README.md](../../README.md), en inglés. Si algo no coincide, manda el inglés.

**Habla con Claude Code. Sin teclado.**

Piensas en voz alta mientras trabajas, y la frase llega como instrucción, sin
tocar Enter. No es dictado pegado a un cuadro de texto: silenciar, revisar,
deshacer y elegir a qué sesión le llega lo que dices, todo con la voz, con las
manos donde ya las tenías.

<p align="center">
  <img src="images/viewer.png" alt="La ventana de Voice Shell: transcripción en vivo, selección de sesión y forma de envío, todo en una ventana flotante" width="360">
</p>

## Por qué

- **No hay nada que pulsar para enviarlo.** La mayoría de las herramientas de
  voz llenan un cuadro de texto y esperan a que le des a enviar. Aquí la frase
  pasa directamente en el momento en que se oye, sin botón, sin paso de
  confirmación, sin ventana en la que hacer clic.
- **No hay que instalar nada para probarlo.** El reconocimiento por defecto lo
  hace el navegador. Sin descargar modelos ni esperas. Cuando quieras que todo
  quede en tu máquina, cambia a reconocimiento en el dispositivo (Apple o
  Whisper) con un solo ajuste, sin tener que aprender nada nuevo.
- **Una interfaz de voz completa, no un icono de micrófono.** «Silenciar»,
  «revisar», «directo», «cancela eso», «sesión 2»: dicho al final de una
  frase, todo funciona sin usar las manos. La ventana flotante muestra
  exactamente lo que va oyendo, según lo dices.
- **Úsalo en más de una cosa a la vez.** Deja el modo voz activo en varias
  sesiones de Claude Code y elige a cuál le llega lo que dices, desde la
  ventana o con la voz.
- **Los nombres que se oyen mal se corrigen solos.** Enséñaselo una vez
  («cloud code → Claude Code») y la corrección se aplica desde ese momento,
  incluso al texto que todavía se está reconociendo.

## Instalación

```bash
npx skills add ykuwai/voice-shell
pip install numpy aiohttp "sounddevice>=0.5.6"
```

Si tienes Chrome, con eso basta.

Escribe `/voice-shell` en Claude Code, o di «modo voz», para empezar. Los
pasos que sigue el agente a partir de ahí están en
[SKILL.md](../../skills/voice-shell/SKILL.md).

Si lo ejecutas desde un agente, o desde un script, añade `-y` para que no se
detenga a preguntar para qué agente instalarlo.

```bash
npx skills add ykuwai/voice-shell -y
```

## Actualizar

```bash
npx skills update voice-shell -y
```

Sin `-y` pregunta antes. Sin el nombre, actualiza todas las skills que
tengas instaladas, esta incluida.

## A dónde va tu voz

> [!NOTE]
> Por defecto reconoce el navegador, así que el audio se envía a los
> servidores de Google. Cuando quieras que no salga de tu máquina, elige otra
> forma en los ajustes de la ventana. Allí mismo aparece este mismo aviso.

| Forma | Qué necesita | A dónde va el audio |
|---|---|---|
| **Este navegador** (por defecto) | Chrome. Solo funciona mientras la ventana está abierta | **Servidores de Google** |
| Apple en el dispositivo | macOS 26 o posterior. Nada que instalar | Se queda en la máquina |
| Whisper | `faster-whisper`. Fuerte con los nombres propios | Se queda en la máquina |

Recuerda la forma que elegiste, así que la próxima vez arranca igual. Las dos formas
que dejan todo en local están en [SETUP.md](../../skills/voice-shell/SETUP.md).

Qué idiomas puede reconocer lo decide la forma que elijas. El navegador ofrece los
que trae Chrome, Apple los locales instalados en el sistema, Whisper los que cubra el
modelo. La ventana en sí viene en siete idiomas.

## Comandos

```bash
voice-shell.sh start [--engine X] [--no-gui]
voice-shell.sh stop
voice-shell.sh status
voice-shell.sh engines
```

| Comando | Qué hace |
|---|---|
| `start` | Lo arranca y recuerda la forma que elegiste la última vez |
| `stop` | Lo para |
| `status` | Qué está en marcha y qué sesión está escuchando |
| `engines` | Las formas que tiene de reconocer la voz |

Todo lo que configures se queda en `~/.config/voice-shell/` y sobrevive a un reinicio.

## Un poco más

Los dos de abajo están solo en inglés. Lo que necesita casi todo el mundo ya está
más arriba.

| Qué leer | Qué contiene |
|---|---|
| [SETUP.md](../../skills/voice-shell/SETUP.md) | Cómo instalarlo según el entorno y qué hacer si te atascas |
| [SKILL.md](../../skills/voice-shell/SKILL.md) | Los pasos que lee el agente. El comportamiento fino está aquí |

## Referencias

- [Web Speech API (MDN)](https://developer.mozilla.org/docs/Web/API/SpeechRecognition)
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)

## Licencia

MIT
