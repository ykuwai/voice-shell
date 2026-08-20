#!/usr/bin/env python3
"""Whisper をストリーミングとして使えるようにする。

Whisper は 30 秒の音声をまとめて処理する作りで、本来ストリーミング向き
ではない。そこで、溜まった音声を短い間隔で繰り返し認識し直す形にする。
asr_mic.py が呼ぶ 3 つのメソッド（init_streaming_state /
streaming_transcribe / finish_streaming_transcribe）を備えているので、
どのエンジンを選んでも asr_mic.py 側は同じコードで扱える。

Apple のオンデバイス認識との違いは、実測では次のとおり。
  - 固有名詞に強い。人名や製品名の取りこぼしが少ない
  - 騒がしい場所や複数人の声でも崩れにくい
  - モデルを落として積むので、起動が遅くメモリを使う
"""
import sys

import numpy as np

SAMPLE_RATE = 16000

# Whisper は "ja" のような 2 文字コードしか受け付けない。
# voice-shell はどのエンジンにも "Japanese" と綴りで渡すので、ここで直す
# （そのまま渡すと ValueError で落ちる）。
_LANG = {
    "japanese": "ja", "english": "en", "chinese": "zh", "korean": "ko",
    "french": "fr", "german": "de", "spanish": "es", "italian": "it",
    "portuguese": "pt", "russian": "ru",
}


def _lang_code(name):
    """「Japanese」「ja」「ja-JP」のどれで来ても "ja" にする。"""
    if not name:
        return None
    s = str(name).strip().lower()
    return _LANG.get(s, s.split("-")[0][:2])


# Whisper が対応する全言語（コード → 表示名）。ビューアの認識言語プルダウンを
# ここから作る（一覧を二重管理しない）。コードの一覧は faster-whisper の
# トークナイザに合わせる。
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
    """認識言語プルダウン用の一覧。「自動」はコード "" で表す。"""
    langs = [{"code": c, "name": n} for c, n in LANGUAGE_NAMES.items()]
    langs.sort(key=lambda x: x["name"])
    return langs

# 日本語と英語が混ざった発話を、混ざったまま書き起こさせるための例文。
# Whisper は言語トークンを 1 つしか持てないため、放っておくと発話ごとに
# どちらか一方へ寄る（実測でも、英語で話したぶんが日本語になって届いた）。
# こういう文が普通に出てくる、と先に見せておくと寄りが弱まる。
MIXED_PROMPT = (
    "これは日本語と English が混ざった会話です。"
    "Claude Code で GitHub の pull request を確認しました。"
    "That's fine. じゃあ deploy しておきます。"
)

# 認識をやり直す間隔。短いほど早く文字が出るが、そのぶん推論が増える。
# 溜まった音声を毎回まるごと読み直すので、長い発話ほど 1 回が重くなる。
REFRESH_SEC = 0.7

# ここを超えたら、それより前は確定したものとして切り離す。
# 際限なく伸ばすと 1 回の認識が遅くなっていく。
MAX_WINDOW_SEC = 28.0


class WhisperState:
    """発話 1 つ分の途中経過。"""

    def __init__(self, language=None):
        # 名前は他のエンジンの state と揃えてある。asr_mic は発話の長さを
        # 測るのにこれを読む（属性が無いとそこで落ちる）。
        self.audio_accum = np.zeros(0, dtype=np.float32)
        self.text = ""
        self.language = language
        self.settled = ""      # 窓から押し出して確定させたぶん
        self._since_run = 0.0  # 前回の認識からの秒数


class WhisperModel:
    """faster-whisper を、他のエンジンと同じ呼び出し方で使えるようにする。"""

    def __init__(self, name="large-v3-turbo", device="cuda",
                 compute_type="float16", language=None):
        from faster_whisper import WhisperModel as FW

        print(f"Whisper ({name} / {compute_type}) を読み込んでいます…",
              file=sys.stderr, flush=True)
        self._m = FW(name, device=device, compute_type=compute_type)
        # None のままにして自動判定させる。voice-shell は --language Japanese を
        # 常に渡してくるが、それをそのまま効かせると英語が日本語に訳されて
        # 届く。言語を固定したいときは --whisper-language で明示する。
        self._lang = _lang_code(language)

    # ── asr_mic が呼ぶ 3 つ ──────────────────────

    def init_streaming_state(self, language=None, **_ignored):
        """発話の始まり。使わない引数は他のエンジンに合わせて受け流す。"""
        return WhisperState(_lang_code(language) or self._lang)

    def streaming_transcribe(self, pcm16k, state):
        """音を受けて、頃合いを見て認識し直す。"""
        state.audio_accum = np.concatenate([state.audio_accum, pcm16k])
        state._since_run += len(pcm16k) / SAMPLE_RATE

        if state._since_run < REFRESH_SEC:
            return state
        state._since_run = 0.0

        # 窓が長くなりすぎたら、前半を確定させて切り離す
        if len(state.audio_accum) / SAMPLE_RATE > MAX_WINDOW_SEC:
            keep = int(MAX_WINDOW_SEC * SAMPLE_RATE * 0.5)
            head, state.audio_accum = state.audio_accum[:-keep], state.audio_accum[-keep:]
            state.settled += self._run(head, state)

        state.text = state.settled + self._run(state.audio_accum, state)
        return state

    def finish_streaming_transcribe(self, state):
        """発話の終わり。最後にもう一度だけ通す。"""
        if state.audio_accum.size:
            state.text = state.settled + self._run(state.audio_accum, state)
        return state

    # ── 中身 ──────────────────────────────────

    def _run(self, audio, state) -> str:
        """溜まった音声を認識する。

        beam_size=1 と condition_on_previous_text=False は、途中経過が
        コロコロ変わるのを抑えるため。前の推測を引きずらせると、認識を
        やり直すたびに文が書き換わって読みにくい。

        language は既定で渡さない。Whisper は指定した言語で書き出そうと
        するので、"ja" に固定すると英語で話したぶんまで日本語に訳されて
        しまう（実測でも "I found that..." が日本語になって届いた）。
        自動判定なら話した言語のまま出る。
        """
        if audio.size < SAMPLE_RATE * 0.3:      # 短すぎると誤認識しやすい
            return ""
        segments, info = self._m.transcribe(
            audio,
            language=self._lang,                # None なら自動判定
            task="transcribe",                  # translate にはしない
            # 言語トークンは 1 つしか持てず、発話ごとに 1 言語へ寄る。
            # 日本語に混ざった英語まで日本語で書こうとするので、
            # 混在があると分かる例文を先に読ませて引っぱる。
            initial_prompt=MIXED_PROMPT,
            beam_size=1,
            condition_on_previous_text=False,
            vad_filter=True,                    # 無音を捨てて幻聴を減らす
            vad_parameters={"min_silence_duration_ms": 300},
        )
        state.language = info.language or state.language
        return "".join(s.text for s in segments).strip()


def load(args):
    """asr_mic.load_model から呼ばれる。

    --language は見ない。voice-shell は常に Japanese を渡してくるが、
    Whisper でそれを効かせると英語で話したぶんまで日本語に訳される。
    固定したいときは --whisper-language。
    """
    return WhisperModel(
        name=getattr(args, "model", None) or "large-v3-turbo",
        device=getattr(args, "whisper_device", None) or "cuda",
        compute_type=getattr(args, "whisper_compute", None) or "float16",
        language=getattr(args, "whisper_language", None),
    )
