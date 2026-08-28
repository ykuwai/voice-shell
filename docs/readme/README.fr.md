# Voice Shell

[English](../../README.md) · [日本語](README.ja.md) · [Español](README.es.md) · Français · [Deutsch](README.de.md) · [简体中文](README.zh.md) · [한국어](README.ko.md)

<p align="center">
  <img src="https://img.shields.io/github/license/ykuwai/voice-shell" alt="Licence">
  <img src="https://img.shields.io/github/last-commit/ykuwai/voice-shell" alt="Dernier commit">
</p>

La version d'origine est [README.md](../../README.md), en anglais. En cas de désaccord,
c'est l'anglais qui fait foi.

**Parlez à Claude Code. Sans clavier.**

Vous pensez tout haut en travaillant, et la phrase arrive telle quelle comme
instruction, sans toucher à la touche Entrée. Ce n'est pas de la dictée collée
sur un champ de texte : couper le micro, se relire, annuler, choisir quelle
session vous écoute, tout cela se fait à la voix, pendant que vos mains
restent sur ce que vous étiez en train de faire.

<p align="center">
  <img src="images/viewer.png" alt="La fenêtre de Voice Shell : une fenêtre flottante affichant la transcription en direct, le choix de la session et le mode d'envoi" width="360">
</p>

## Points forts

- **Rien à cliquer pour l'envoyer.** La plupart des outils vocaux remplissent
  un champ de texte et attendent que vous cliquiez sur envoyer. Ici, la
  phrase passe directement au moment où elle est entendue, sans bouton, sans
  étape de confirmation, sans fenêtre où cliquer.
- **Rien à installer pour essayer.** La reconnaissance par défaut se fait dans
  le navigateur. Aucun modèle à télécharger, aucune attente. Le jour où vous
  voulez que tout reste privé, un seul réglage suffit pour passer à la
  reconnaissance sur l'appareil (Apple, ou Whisper), sans rien réapprendre.
- **Une véritable interface vocale, pas une icône de micro.** « Coupe le
  micro », « relecture », « direct », « annule ça », « session 2 » — dits en
  fin de phrase, tout fonctionne mains libres. La fenêtre flottante affiche
  exactement ce qu'elle entend, au fil de la parole.
- **Utilisable sur plusieurs chantiers à la fois.** Gardez le mode vocal actif
  dans plusieurs sessions Claude Code et choisissez laquelle reçoit vos mots,
  depuis la fenêtre ou à la voix.
- **Les noms mal entendus se corrigent tout seuls.** Enregistrez-le une fois
  dans le dictionnaire (« cloud code → Claude Code ») et la correction
  s'applique dès lors, même au texte encore en cours de reconnaissance.

## Installation

```bash
npx skills add ykuwai/voice-shell
pip install numpy aiohttp "sounddevice>=0.5.6"
```

Si vous avez Chrome, il n'en faut pas plus.

Tapez `/voice-shell` dans Claude Code, ou dites « mode vocal », pour démarrer.
Les étapes que suit l'agent à partir de là sont dans
[SKILL.md](../../skills/voice-shell/SKILL.md).

Depuis un agent, ou depuis un script, nommez Claude Code plutôt que de le
laisser le détecter tout seul, et ajoutez `-y` pour sauter la confirmation.

```bash
npx skills add ykuwai/voice-shell -a claude-code -y
```

## Mettre à jour

```bash
npx skills update voice-shell -y
```

Sans `-y`, il demande d'abord. Sans le nom, il met à jour toutes les skills
installées, celle-ci comprise.

## Où va votre voix

> [!NOTE]
> Par défaut c'est le navigateur qui reconnaît, donc l'audio part vers les
> serveurs de Google. Si vous voulez qu'il reste sur votre machine, choisissez
> une autre façon dans les réglages de la fenêtre. Le même avertissement y
> figure sur place.

| Façon | Ce qu'il faut | Où va l'audio |
|---|---|---|
| **Ce navigateur** (par défaut) | Chrome. Ne marche que fenêtre ouverte | **Serveurs de Google** |
| Apple sur l'appareil | macOS 26 ou plus récent. Rien à installer en plus | Reste sur la machine |
| Whisper | `faster-whisper`. Solide sur les noms propres | Reste sur la machine |

La façon choisie est retenue, donc au démarrage suivant c'est la même. Les
deux façons qui gardent tout en local sont dans
[SETUP.md](../../skills/voice-shell/SETUP.md).

Les langues reconnues dépendent de la façon choisie. Le navigateur propose
celles que Chrome embarque, Apple les locales installées dans le système,
Whisper celles que couvre le modèle. La fenêtre elle-même existe en sept
langues.

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

Tous vos réglages restent dans `~/.config/voice-shell/` et survivent à un
redémarrage.

## Pour aller plus loin

Les deux ci-dessous sont en anglais uniquement. L'essentiel pour la plupart
des gens est déjà au-dessus.

| À lire | Ce qu'on y trouve |
|---|---|
| [SETUP.md](../../skills/voice-shell/SETUP.md) | L'installation selon l'environnement, et quoi faire quand ça bloque |
| [SKILL.md](../../skills/voice-shell/SKILL.md) | Les étapes que lit l'agent. Le comportement fin est là |

## Références

- [Web Speech API (MDN)](https://developer.mozilla.org/docs/Web/API/SpeechRecognition)
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)

## Licence

MIT
