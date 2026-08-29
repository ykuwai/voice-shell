# Voice Shell

[English](../../README.md) · [日本語](README.ja.md) · Español · [Français](README.fr.md) · [Deutsch](README.de.md) · [简体中文](README.zh.md) · [한국어](README.ko.md)

<p align="center">
  <img src="https://img.shields.io/github/license/ykuwai/voice-shell" alt="Licencia">
  <img src="https://img.shields.io/github/last-commit/ykuwai/voice-shell" alt="Último commit">
</p>

El original es [README.md](../../README.md), en inglés. Si algo no coincide, manda el inglés.

**Hable con Claude Code. Sin teclado.**

Piensa en voz alta mientras trabaja, y la frase llega como instrucción, sin
tocar Enter. No es dictado pegado a un cuadro de texto. Silenciar, revisar,
deshacer y elegir a qué sesión le llega lo que dice, todo con la voz, con las
manos donde ya las tenía.

<p align="center">
  <img src="images/viewer.png" alt="La ventana de Voice Shell, transcripción en vivo, selección de sesión y forma de envío, todo en una ventana flotante" width="360">
</p>

## Por qué

- **No hay nada que pulsar para enviarlo.** La mayoría de las herramientas de
  voz llenan un cuadro de texto y esperan a que dé a enviar. Aquí la frase
  pasa directamente en el momento en que se oye, sin botón, sin paso de
  confirmación, sin ventana en la que hacer clic.
- **No hay que instalar nada para probarlo.** El reconocimiento por defecto lo
  hace el navegador. Sin descargar modelos ni esperas. Cuando quiera que todo
  quede en su máquina, cambie a reconocimiento en el dispositivo (Apple o
  Whisper) con un solo ajuste, sin tener que aprender nada nuevo.
- **Una interfaz de voz completa, no un icono de micrófono.** Silenciar,
  pasar de revisar a directo, deshacer lo que acaba de decir, elegir a qué
  sesión escucha, todo esto también funciona con la voz. Vea «Lo que puede
  decir» más abajo. La ventana flotante muestra exactamente lo que va
  oyendo, según lo dice.
- **Úselo en más de una cosa a la vez.** Deje el modo voz activo en varias
  sesiones de Claude Code y elija a cuál le llega lo que dice, desde la
  ventana o con la voz.
- **Los nombres que se oyen mal se corrigen solos.** Enséñeselo una vez
  («cloud code → Claude Code») y la corrección se aplica desde ese momento,
  incluso al texto que todavía se está reconociendo.

## Instalación

```bash
pip install numpy aiohttp "sounddevice>=0.5.6"
npx skills add ykuwai/voice-shell -g -a claude-code -y
```

Si tiene Chrome, con eso basta. `-g` lo pone en `~/.claude/skills/`, así
queda disponible en todos sus proyectos. ¿Solo quiere probarlo dentro de un
proyecto? Quite el `-g` y quedará solo en el `.claude/skills/` de ese
proyecto. `-a claude-code` nombra Claude Code directamente en vez de dejar
que `npx` lo adivine, y `-y` salta la confirmación que pediría si no.

Escriba `/voice-shell` en Claude Code, o diga «modo voz», para empezar. Los
pasos que sigue el agente a partir de ahí están en
[SKILL.md](../../skills/voice-shell/SKILL.md).

## Actualizar

```bash
npx skills update voice-shell -y
```

Sin `-y` pregunta antes. Sin el nombre, actualiza todas las skills que
tenga instaladas, esta incluida.

## A dónde va su voz

> [!NOTE]
> Por defecto reconoce el navegador, así que el audio se envía a los
> servidores de Google. Cuando quiera que no salga de su máquina, elija otra
> forma en los ajustes de la ventana. Allí mismo aparece este mismo aviso.

| Forma | Qué necesita | A dónde va el audio |
|---|---|---|
| **Este navegador** (por defecto) | Chrome. Solo funciona mientras la ventana está abierta | **Servidores de Google** |
| Apple en el dispositivo | macOS 26 o posterior. Nada que instalar | Se queda en la máquina |
| Whisper | `faster-whisper`. Fuerte con los nombres propios | Se queda en la máquina |

Recuerda la forma que eligió, así que la próxima vez arranca igual. Las dos formas
que dejan todo en local están en [SETUP.md](../../skills/voice-shell/SETUP.md).

Qué idiomas puede reconocer lo decide la forma que elija. El navegador ofrece los
que trae Chrome, Apple los locales instalados en el sistema, Whisper los que cubra el
modelo. La ventana en sí viene en siete idiomas.

## Lo que puede decir

Diga una de estas frases sola, sin nada más en la oración, y se aplica al
momento.

| Diga esto | Qué pasa |
|---|---|
| «silenciar» | El micrófono se apaga |
| «quitar silencio» | El micrófono vuelve (solo mientras escucha un modelo de esta máquina, no el navegador) |
| «revisar» o «borrador» | Lo que dice desde aquí se acumula en vez de salir, así puede corregirlo antes de enviarlo |
| «directo» | Vuelve a salir todo seguido |
| «sesión 2» o «número dos» | Elige a qué sesión le llega lo que dice, cuando escuchan dos o más |

Añada una de estas al final de lo que está diciendo y se aplica solo a esa
frase.

| Diga esto | Qué pasa |
|---|---|
| «cancela eso» | La frase que acaba de decir se descarta |
| «lo edito yo» | La frase pasa al cuadro en vez de salir, así puede corregirla antes |

Cada una de estas frases se puede desactivar en los ajustes, y puede
enseñarle su propia forma de decirlo, todo desde la ventana. La lista
completa, en los siete idiomas de la ventana, está detrás del icono de la
bombilla en la pantalla.

## Un poco más

Los dos de abajo están solo en inglés. Lo que necesita casi todo el mundo ya está
más arriba.

| Qué leer | Qué contiene |
|---|---|
| [SETUP.md](../../skills/voice-shell/SETUP.md) | Cómo instalarlo según el entorno y qué hacer si se atasca |
| [SKILL.md](../../skills/voice-shell/SKILL.md) | Los pasos que lee el agente. El comportamiento fino está aquí |

## Referencias

- [Web Speech API (MDN)](https://developer.mozilla.org/docs/Web/API/SpeechRecognition)
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)

## Licencia

MIT
