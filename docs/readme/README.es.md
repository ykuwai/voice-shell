# Voice Shell

[English](../../README.md) · [日本語](README.ja.md) · Español · [Français](README.fr.md) · [Deutsch](README.de.md) · [简体中文](README.zh.md) · [한국어](README.ko.md)

El original es [README.md](../../README.md), en inglés. Si algo no coincide, manda el inglés.

Un Agent Skill para darle instrucciones a Claude Code con la voz. Sin teclado.
Hablas y la instrucción llega.

> micrófono → reconocimiento de voz → una línea de JSONL → Monitor → Claude Code

Di lo que se te ocurra mientras trabajas y llega sin que pulses Enter. Funciona con
Claude Code y también con otros agentes como Codex.

## Instalación

```bash
npx skills add ykuwai/voice-shell
pip install numpy aiohttp "sounddevice>=0.5.6"
```

Si tienes Chrome, con eso basta. **No hay modelo que descargar ni nada que esperar.**

## Uso

Escribe `/voice-shell` en Claude Code o di «modo voz». A partir de ahí solo hablas.
Di «salir del modo voz» para terminar.

Se abre una ventana propia en http://127.0.0.1:47865 y las palabras que oye van
creciendo ahí mientras hablas. Déjala flotando encima y podrás mirarla mientras
trabajas en otra cosa.

| Cómo envía | Qué pasa |
|---|---|
| Directo | Lo que dices sale tal cual |
| Revisar | Se va acumulando, así puedes corregirlo antes de enviarlo |
| En pausa | Nada de lo que digas en pausa se guarda en ningún sitio |

Aunque tengas las manos ocupadas, **puedes cambiar solo con la voz**: «silenciar» y
«quitar silencio» apagan y encienden el micrófono, «revisar» y «directo» cambian la
forma de enviar. Termina una frase con «cancela eso» y esa frase se descarta en vez
de enviarse. (Solo con el reconocimiento del navegador, silenciar suelta el audio en
sí, así que vuelve a encender el micrófono desde la ventana.)

Puedes dejar un modo voz abierto para cada tarea y **elegir desde la ventana a cuál
le llega lo que dices.** También se elige con la voz («sesión 2»).

Los nombres propios que se oyen mal pueden ir en un diccionario
(`cloud code → Claude Code`). Las sustituciones que registres también alcanzan a las
palabras mientras se están reconociendo.

## A dónde va tu voz

**Por defecto reconoce el navegador, así que el audio se envía a los servidores de
Google.** Cuando quieras que no salga de tu máquina, elige otra forma en los ajustes
de la ventana. Allí mismo aparece este mismo aviso.

| Forma | Qué necesita | A dónde va el audio |
|---|---|---|
| **Este navegador** (por defecto) | Chrome. Solo funciona mientras la ventana está abierta | **Servidores de Google** |
| Apple en el dispositivo | macOS 26 o posterior. Nada que instalar | Se queda en la máquina |
| Whisper | `faster-whisper`. Fuerte con los nombres propios | Se queda en la máquina |

Recuerda la forma que elegiste, así que la próxima vez arranca igual. Las dos formas
que dejan todo en local están en [SETUP.md](skills/voice-shell/SETUP.md).

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

## Cuando algo va mal

En Linux, para grabar hace falta `arecord`.

```bash
sudo apt install alsa-utils      # Linux
```

| Lo que ves | Qué hacer |
|---|---|
| Hablas y no llega nada | El nivel de activación está demasiado alto. Baja la marca que hay bajo el micrófono en la ventana hasta que la barra la pase cuando hablas |
| Los ruidos envían cosas solos | El nivel de activación está demasiado bajo. Sube esa misma marca hasta que solo tu voz la pase |
| `No Python it can run was found` | `export VOICE_SHELL_PYTHON=/path/to/.venv/bin/python` |
| El arranque dice `FAILED` | Ejecuta `voice-shell.sh status` y mira el final de `daemon.out` |

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
