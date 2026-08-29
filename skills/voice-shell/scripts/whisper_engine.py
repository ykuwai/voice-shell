#!/usr/bin/env python3
"""Make Whisper usable as a streaming recognizer.

Whisper is built to handle 30 seconds of audio in one shot and is not really
meant for streaming. So instead the collected audio is recognized over and
over at short intervals. It carries the 3 methods asr_mic.py calls
(init_streaming_state / streaming_transcribe / finish_streaming_transcribe),
so asr_mic.py works the same whichever engine is picked.

Measured, it differs from Apple's on-device recognition as follows.
  - Strong on proper nouns. It rarely drops names of people or products
  - Holds together in noisy places and with several people talking
  - Downloads and loads a model, so it starts slowly and uses memory
"""
import sys

import numpy as np

SAMPLE_RATE = 16000

# Whisper only takes a 2 letter code like "ja".
# voice-shell hands every engine the spelled-out "Japanese", so fix it here
# (passing that straight through dies with ValueError).
_LANG = {
    "japanese": "ja", "english": "en", "chinese": "zh", "korean": "ko",
    "french": "fr", "german": "de", "spanish": "es", "italian": "it",
    "portuguese": "pt", "russian": "ru",
}


def _lang_code(name):
    """Turn "Japanese", "ja" or "ja-JP" into "ja", whichever one arrives."""
    if not name:
        return None
    s = str(name).strip().lower()
    return _LANG.get(s, s.split("-")[0][:2])


# Every language Whisper handles (code → display name). The viewer builds its
# language dropdown from this (no keeping two lists in step). The set of codes
# follows the faster-whisper tokenizer.
LANGUAGE_NAMES = {
    "af": "Afrikaans", "am": "Amharic", "ar": "Arabic", "as": "Assamese",
    "az": "Azerbaijani", "ba": "Bashkir", "be": "Belarusian",
    "bg": "Bulgarian", "bn": "Bengali", "bo": "Tibetan", "br": "Breton",
    "bs": "Bosnian", "ca": "Catalan", "cs": "Czech", "cy": "Welsh",
    "da": "Danish", "de": "German", "el": "Greek", "en": "English",
    "es": "Spanish", "et": "Estonian", "eu": "Basque", "fa": "Persian",
    "fi": "Finnish", "fo": "Faroese", "fr": "French", "gl": "Galician",
    "gu": "Gujarati", "ha": "Hausa", "haw": "Hawaiian", "he": "Hebrew",
    "hi": "Hindi", "hr": "Croatian", "ht": "Haitian Creole",
    "hu": "Hungarian", "hy": "Armenian", "id": "Indonesian",
    "is": "Icelandic", "it": "Italian", "ja": "Japanese", "jw": "Javanese",
    "ka": "Georgian", "kk": "Kazakh", "km": "Khmer", "kn": "Kannada",
    "ko": "Korean", "la": "Latin", "lb": "Luxembourgish", "ln": "Lingala",
    "lo": "Lao", "lt": "Lithuanian", "lv": "Latvian", "mg": "Malagasy",
    "mi": "Maori", "mk": "Macedonian", "ml": "Malayalam", "mn": "Mongolian",
    "mr": "Marathi", "ms": "Malay", "mt": "Maltese", "my": "Myanmar",
    "ne": "Nepali", "nl": "Dutch", "nn": "Nynorsk", "no": "Norwegian",
    "oc": "Occitan", "pa": "Punjabi", "pl": "Polish", "ps": "Pashto",
    "pt": "Portuguese", "ro": "Romanian", "ru": "Russian",
    "sa": "Sanskrit", "sd": "Sindhi", "si": "Sinhala", "sk": "Slovak",
    "sl": "Slovenian", "sn": "Shona", "so": "Somali", "sq": "Albanian",
    "sr": "Serbian", "su": "Sundanese", "sv": "Swedish", "sw": "Swahili",
    "ta": "Tamil", "te": "Telugu", "tg": "Tajik", "th": "Thai",
    "tk": "Turkmen", "tl": "Tagalog", "tr": "Turkish", "tt": "Tatar",
    "uk": "Ukrainian", "ur": "Urdu", "uz": "Uzbek", "vi": "Vietnamese",
    "yi": "Yiddish", "yo": "Yoruba", "yue": "Cantonese", "zh": "Chinese",
}


def available_languages():
    """The list for the language dropdown. Automatic is the code ""."""
    langs = [{"code": c, "name": n} for c, n in LANGUAGE_NAMES.items()]
    langs.sort(key=lambda x: x["name"])
    return langs

# Sample sentences for getting speech that mixes Japanese and English written
# down as the mix it is. Whisper can hold only one language token, so left alone
# each utterance leans one way or the other (measured, what was said in English
# arrived as Japanese). Showing up front that such sentences turn up normally
# weakens the lean.
MIXED_PROMPT = (
    "これは日本語と English が混ざった会話です。"
    "Claude Code で GitHub の pull request を確認しました。"
    "That's fine. じゃあ deploy しておきます。"
)

# Interval for redoing recognition. Shorter puts text up sooner but runs more
# inference. Every run rereads all the audio, so longer utterances cost more.
REFRESH_SEC = 0.7

# Past this, everything before it is cut loose as settled.
# Letting it grow without limit makes each recognition slower.
MAX_WINDOW_SEC = 28.0


class WhisperState:
    """The work in progress for one utterance."""

    def __init__(self, language=None):
        # The names line up with the state of the other engines. asr_mic reads
        # this to measure utterance length (a missing attribute dies there).
        self.audio_accum = np.zeros(0, dtype=np.float32)
        self.text = ""
        self.language = language
        self.settled = ""      # the part pushed out of the window and settled
        self._since_run = 0.0  # seconds since the last recognition


class WhisperModel:
    """Make faster-whisper callable the same way as the other engines."""

    def __init__(self, name="large-v3-turbo", device="cuda",
                 compute_type="float16", language=None):
        from faster_whisper import WhisperModel as FW

        print(f"Loading Whisper ({name} / {compute_type})",
              file=sys.stderr, flush=True)
        self._m = FW(name, device=device, compute_type=compute_type)
        # Loading alone says nothing about whether it can actually run.
        # ctranslate2 only touches the CUDA runtime (cuBLAS/cuDNN) once
        # transcribe() really executes, and segments is a generator, so even
        # calling transcribe() does nothing until it is iterated. On a
        # machine missing those libraries this construction still succeeds,
        # wait-ready reports READY, and the daemon dies on the very first
        # real utterance instead, with nothing on screen explaining why the
        # mic was clearly picking sound up. vad_filter is off here on
        # purpose (real transcribing leaves it on): plain digital silence
        # would otherwise let VAD skip the model outright, which would
        # "pass" this without ever touching the GPU it exists to test.
        try:
            list(self._m.transcribe(np.zeros(SAMPLE_RATE, dtype=np.float32),
                                     beam_size=1, vad_filter=False)[0])
        except Exception as e:
            if device == "cuda" and "libcu" in str(e).lower():
                raise RuntimeError(
                    f"{e}\n"
                    "The model loaded, but this machine's CUDA runtime "
                    "(cuBLAS/cuDNN) could not actually run it. See "
                    "SETUP.md's Whisper section for how to point "
                    "ctranslate2 at nvidia-cublas-cu12 / nvidia-cudnn-cu12."
                ) from e
            raise
        # Leave it None so it auto-detects. voice-shell always passes
        # --language Japanese, but letting that bite makes English arrive
        # translated into Japanese. Pin the language with --whisper-language.
        self._lang = _lang_code(language)

    # ── The 3 asr_mic calls ──────────────────────

    def init_streaming_state(self, language=None, **_ignored):
        """Start of an utterance. Unused arguments pass through, to match the rest."""
        return WhisperState(_lang_code(language) or self._lang)

    def streaming_transcribe(self, pcm16k, state):
        """Take the sound in and, when the time is right, recognize again."""
        state.audio_accum = np.concatenate([state.audio_accum, pcm16k])
        state._since_run += len(pcm16k) / SAMPLE_RATE

        if state._since_run < REFRESH_SEC:
            return state
        state._since_run = 0.0

        # If the window has grown too long, settle the first half and cut it loose
        if len(state.audio_accum) / SAMPLE_RATE > MAX_WINDOW_SEC:
            keep = int(MAX_WINDOW_SEC * SAMPLE_RATE * 0.5)
            head, state.audio_accum = state.audio_accum[:-keep], state.audio_accum[-keep:]
            state.settled += self._run(head, state)

        state.text = state.settled + self._run(state.audio_accum, state)
        return state

    def finish_streaming_transcribe(self, state):
        """End of an utterance. Put it through once more, one last time."""
        if state.audio_accum.size:
            state.text = state.settled + self._run(state.audio_accum, state)
        return state

    # ── Innards ───────────────────────────────

    def _run(self, audio, state) -> str:
        """Recognize the collected audio.

        beam_size=1 and condition_on_previous_text=False hold down how much
        the partial text flips about. Dragging the previous guess along
        rewrites the sentence on every rerun and it gets hard to read.

        language is not passed by default. Whisper tries to write in the
        language it is given, so pinning "ja" translates even the parts
        spoken in English into Japanese (measured, "I found that..." arrived
        as Japanese). Auto-detect leaves speech in the language it was said in.
        """
        if audio.size < SAMPLE_RATE * 0.3:      # too short and it misreads easily
            return ""
        segments, info = self._m.transcribe(
            audio,
            language=self._lang,                # None means auto-detect
            task="transcribe",                  # never translate
            # Only one language token is possible, so each utterance leans to
            # one language. It tries to write even the English mixed into the
            # Japanese as Japanese, so feed it a sample that shows the mix.
            initial_prompt=MIXED_PROMPT,
            beam_size=1,
            condition_on_previous_text=False,
            vad_filter=True,                    # drop silence, hallucinate less
            vad_parameters={"min_silence_duration_ms": 300},
        )
        state.language = info.language or state.language
        return "".join(s.text for s in segments).strip()


def load(args):
    """Called from asr_mic.load_model.

    --language is ignored. voice-shell always passes Japanese, but letting
    that bite in Whisper translates even the parts spoken in English into
    Japanese. To pin it, use --whisper-language.
    """
    return WhisperModel(
        name=getattr(args, "model", None) or "large-v3-turbo",
        device=getattr(args, "whisper_device", None) or "cuda",
        compute_type=getattr(args, "whisper_compute", None) or "float16",
        language=getattr(args, "whisper_language", None),
    )
