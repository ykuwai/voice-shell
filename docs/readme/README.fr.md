# Voice Shell

[English](../../README.md) · [日本語](README.ja.md) · [Español](README.es.md) · Français · [Deutsch](README.de.md) · [简体中文](README.zh.md) · [한국어](README.ko.md)

La version d'origine est [README.md](../../README.md), en anglais. En cas de désaccord,
c'est l'anglais qui fait foi.

Un Agent Skill pour donner des instructions à Claude Code à la voix. Sans clavier.
Vous parlez et l'instruction part.

> micro → reconnaissance vocale → une ligne de JSONL → Monitor → Claude Code

Dites ce qui vous vient pendant que vous travaillez, ça arrive sans appuyer sur
Entrée. Fonctionne avec Claude Code et avec d'autres agents comme Codex.

## Installation

```bash
npx skills add ykuwai/voice-shell
pip install numpy aiohttp "sounddevice>=0.5.6"
```

Si vous avez Chrome, il n'en faut pas plus. **Aucun modèle à télécharger, rien à
attendre.**

## Utilisation

Tapez `/voice-shell` dans Claude Code, ou dites « mode vocal ». Ensuite, vous n'avez
qu'à parler. Dites « arrête le mode vocal » pour terminer.

Une fenêtre à part s'ouvre sur http://127.0.0.1:47865 et les mots entendus s'y
allongent au fil de la parole. Gardez-la au premier plan et vous pouvez la surveiller
en travaillant sur autre chose.

| Façon d'envoyer | Ce qui se passe |
|---|---|
| Direct | Ce que vous dites part tel quel |
| Relecture | Ça s'accumule, vous corrigez avant d'envoyer |
| En pause | Rien de ce que vous dites en pause n'est conservé où que ce soit |

Même les mains prises, **vous pouvez basculer à la voix seule** : « couper le micro »
et « réactiver le micro » l'éteignent et le rallument, « relecture » et « direct »
changent la façon d'envoyer. Terminez une phrase par « annule ça » et cette phrase-là
est jetée au lieu d'être envoyée. (Avec la reconnaissance du navigateur seulement,
couper le micro libère l'audio lui-même, donc rallumez-le depuis la fenêtre.)

Vous pouvez laisser un mode vocal ouvert par chantier et **choisir depuis la fenêtre
celui qui reçoit vos mots.** La voix choisit aussi (« session 2 »).

Les noms propres mal entendus peuvent aller dans un dictionnaire
(`cloud code → Claude Code`). Les remplacements enregistrés touchent aussi les mots
pendant qu'ils sont encore en cours de reconnaissance.

## Où va votre voix

**Par défaut c'est le navigateur qui reconnaît, donc l'audio part vers les serveurs
de Google.** Si vous voulez qu'il reste sur votre machine, choisissez une autre façon
dans les réglages de la fenêtre. Le même avertissement y figure sur place.

| Façon | Ce qu'il faut | Où va l'audio |
|---|---|---|
| **Ce navigateur** (par défaut) | Chrome. Ne marche que fenêtre ouverte | **Serveurs de Google** |
| Apple sur l'appareil | macOS 26 ou plus récent. Rien à installer en plus | Reste sur la machine |
| Whisper | `faster-whisper`. Solide sur les noms propres | Reste sur la machine |

La façon choisie est retenue, donc au démarrage suivant c'est la même. Les deux
façons qui gardent tout en local sont dans [SETUP.md](skills/voice-shell/SETUP.md).

Les langues reconnues dépendent de la façon choisie. Le navigateur propose celles que
Chrome embarque, Apple les locales installées dans le système, Whisper celles que
couvre le modèle. La fenêtre elle-même existe en sept langues.

## Commandes

```bash
voice-shell.sh start [--engine X] [--no-gui]
voice-shell.sh stop
voice-shell.sh status
voice-shell.sh engines
```

| Commande | Ce qu'elle fait |
|---|---|
| `start` | Démarre, en retenant la façon choisie la fois précédente |
| `stop` | Arrête |
| `status` | Ce qui tourne, et quelle session écoute |
| `engines` | Les façons de reconnaître la parole |

Tous vos réglages restent dans `~/.config/voice-shell/` et survivent à un redémarrage.

## Quand ça coince

Sous Linux, pour enregistrer il faut `arecord`.

```bash
sudo apt install alsa-utils      # Linux
```

| Ce que vous voyez | Quoi faire |
|---|---|
| Vous parlez et rien n'arrive | Le seuil de déclenchement est trop haut. Baissez le repère sous le micro dans la fenêtre jusqu'à ce que la barre le dépasse quand vous parlez |
| Les bruits envoient tout seuls | Le seuil de déclenchement est trop bas. Remontez ce même repère jusqu'à ce que seule votre voix le dépasse |
| `No Python it can run was found` | `export VOICE_SHELL_PYTHON=/path/to/.venv/bin/python` |
| Le démarrage affiche `FAILED` | Lancez `voice-shell.sh status` et lisez la fin de `daemon.out` |

## Pour aller plus loin

Les deux ci-dessous sont en anglais uniquement. L'essentiel pour la plupart des gens
est déjà au-dessus.

| À lire | Ce qu'on y trouve |
|---|---|
| [SETUP.md](../../skills/voice-shell/SETUP.md) | L'installation selon l'environnement, et quoi faire quand ça bloque |
| [SKILL.md](../../skills/voice-shell/SKILL.md) | Les étapes que lit l'agent. Le comportement fin est là |

## Références

- [Web Speech API (MDN)](https://developer.mozilla.org/docs/Web/API/SpeechRecognition)
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)

## Licence

MIT
