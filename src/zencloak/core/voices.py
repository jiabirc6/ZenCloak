"""Locale-matched TTS voice lists for speechSynthesis spoofing.

Windows exposes its installed SAPI voices through
``speechSynthesis.getVoices()``. The kernel does not patch that surface, so
a profile whose locale is zh-HK on a machine with only en-US/en-GB voices
leaks the real OS language environment ("voice_top vs ip_country" checks).

This module builds a realistic voice list per locale and renders an init
script that replaces ``getVoices`` with native-looking ``SpeechSynthesisVoice``
instances, including a ``Function.prototype.toString`` guard so the patched
function reports ``[native code]``.
"""

# Real Windows SAPI (Microsoft) voice sets per BCP-47 locale. The first
# entry is flagged default; en-US base voices are appended for locales
# whose machines realistically still carry them.
VOICE_SETS: dict[str, list[tuple[str, str]]] = {
    "en-US": [("Microsoft David", "en-US"), ("Microsoft Zira", "en-US"), ("Microsoft Mark", "en-US")],
    "en-GB": [("Microsoft Hazel", "en-GB"), ("Microsoft George", "en-GB"), ("Microsoft David", "en-US")],
    "en-AU": [("Microsoft Catherine", "en-AU"), ("Microsoft David", "en-US")],
    "en-CA": [("Microsoft Heather", "en-CA"), ("Microsoft David", "en-US")],
    "en-IN": [("Microsoft Heera", "en-IN"), ("Microsoft David", "en-US")],
    "en-SG": [("Microsoft Tessa", "en-SG"), ("Microsoft David", "en-US")],
    "zh-CN": [("Microsoft Huihui", "zh-CN"), ("Microsoft Kangkang", "zh-CN"), ("Microsoft Yaoyao", "zh-CN")],
    "zh-TW": [("Microsoft Hanhan", "zh-TW"), ("Microsoft Zhiwei", "zh-TW"), ("Microsoft David", "en-US")],
    "zh-HK": [("Microsoft Tracy", "zh-HK"), ("Microsoft David", "en-US"), ("Microsoft Hazel", "en-GB")],
    "zh-SG": [("Microsoft Huihui", "zh-CN"), ("Microsoft David", "en-US"), ("Microsoft Zira", "en-US")],
    "ja-JP": [("Microsoft Haruka", "ja-JP"), ("Microsoft Ayumi", "ja-JP"), ("Microsoft Ichiro", "ja-JP")],
    "ko-KR": [("Microsoft Heami", "ko-KR"), ("Microsoft David", "en-US")],
    "de-DE": [("Microsoft Hedda", "de-DE"), ("Microsoft David", "en-US")],
    "fr-FR": [("Microsoft Julie", "fr-FR"), ("Microsoft Henri", "fr-FR"), ("Microsoft David", "en-US")],
    "es-ES": [("Microsoft Helena", "es-ES"), ("Microsoft Laura", "es-ES"), ("Microsoft David", "en-US")],
    "es-MX": [("Microsoft Paulina", "es-MX"), ("Microsoft Raul", "es-MX"), ("Microsoft David", "en-US")],
    "pt-BR": [("Microsoft Daniel", "pt-BR"), ("Microsoft Maria", "pt-BR"), ("Microsoft David", "en-US")],
    "it-IT": [("Microsoft Elsa", "it-IT"), ("Microsoft David", "en-US")],
    "nl-NL": [("Microsoft Fenna", "nl-NL"), ("Microsoft David", "en-US")],
    "pl-PL": [("Microsoft Adam", "pl-PL"), ("Microsoft Zosia", "pl-PL"), ("Microsoft David", "en-US")],
    "ru-RU": [("Microsoft Irina", "ru-RU"), ("Microsoft Pavel", "ru-RU"), ("Microsoft David", "en-US")],
    "uk-UA": [("Microsoft Polina", "uk-UA"), ("Microsoft David", "en-US")],
    "tr-TR": [("Microsoft Tolga", "tr-TR"), ("Microsoft Filiz", "tr-TR"), ("Microsoft David", "en-US")],
    "sv-SE": [("Microsoft Kristina", "sv-SE"), ("Microsoft David", "en-US")],
    "da-DK": [("Microsoft Helle", "da-DK"), ("Microsoft David", "en-US")],
    "fi-FI": [("Microsoft Sofia", "fi-FI"), ("Microsoft David", "en-US")],
    "cs-CZ": [("Microsoft Ivana", "cs-CZ"), ("Microsoft David", "en-US")],
    "el-GR": [("Microsoft Stefanos", "el-GR"), ("Microsoft David", "en-US")],
    "th-TH": [("Microsoft Pimratha", "th-TH"), ("Microsoft David", "en-US")],
    "vi-VN": [("Microsoft Le An", "vi-VN"), ("Microsoft David", "en-US")],
    "id-ID": [("Microsoft Gadis", "id-ID"), ("Microsoft David", "en-US")],
    "ms-MY": [("Microsoft Melissa", "ms-MY"), ("Microsoft David", "en-US")],
    "fil-PH": [("Microsoft David", "en-US"), ("Microsoft Hazel", "en-GB")],
    "ar-SA": [("Microsoft Naayf", "ar-SA"), ("Microsoft David", "en-US")],
    "ar-EG": [("Microsoft Naayf", "ar-SA"), ("Microsoft David", "en-US")],
    "he-IL": [("Microsoft Asaf", "he-IL"), ("Microsoft David", "en-US")],
    "pt-PT": [("Microsoft Virginia", "pt-PT"), ("Microsoft David", "en-US")],
    "en-NZ": [("Microsoft David", "en-US"), ("Microsoft Hazel", "en-GB")],
    "en-IE": [("Microsoft David", "en-US"), ("Microsoft Hazel", "en-GB")],
    "ro-RO": [("Microsoft Carmen", "ro-RO"), ("Microsoft David", "en-US")],
    "hu-HU": [("Microsoft Noemi", "hu-HU"), ("Microsoft David", "en-US")],
}

# Windows always ships some English base voices; keep them trailing so the
# locale voice dominates the distribution without looking sterile.
_BASE_VOICES: list[tuple[str, str]] = [("Microsoft David", "en-US")]


def voice_list_for_locale(locale: str | None) -> list[dict]:
    """Return a realistic voice spec list whose first entry matches locale."""
    key = (locale or "en-US").strip()
    entries = VOICE_SETS.get(key)
    if entries is None:
        region = key.rsplit("-", 1)[-1].upper() if "-" in key else "US"
        lang = f"{key.split('-')[0].lower()}-{region}"
        entries = [(f"Microsoft {(key.split('-')[0].capitalize())}", lang)]
    seen: set[tuple[str, str]] = set()
    result: list[dict] = []
    for index, (name, lang) in enumerate(entries + _BASE_VOICES):
        spec = (name, lang)
        if spec in seen:
            continue
        seen.add(spec)
        result.append(
            {
                "name": name,
                "lang": lang,
                "voiceURI": name,
                "localService": True,
                "default": index == 0,
            }
        )
    return result


_INIT_SCRIPT = """(() => {
  const VOICES = %(voices_json)s;
  if (!window.SpeechSynthesisVoice || !window.speechSynthesis) return;
  const proto = SpeechSynthesisVoice.prototype;
  const props = ["name", "lang", "voiceURI", "localService", "default"];

  function makeVoice(spec) {
    const voice = Object.create(proto);
    for (const key of props) {
      Object.defineProperty(voice, key, {
        get: () => spec[key],
        enumerable: true,
        configurable: true,
      });
    }
    return voice;
  }

  const voices = VOICES.map(makeVoice);
  const getVoices = function getVoices() {
    return voices.slice();
  };

  const nativeToString = Function.prototype.toString;
  const spoofed = new WeakSet([getVoices]);
  function patchedToString() {
    if (spoofed.has(this)) {
      return "function " + this.name + "() { [native code] }";
    }
    return nativeToString.call(this);
  }
  spoofed.add(patchedToString);
  Object.defineProperty(Function.prototype, "toString", {
    value: patchedToString,
    writable: true,
    configurable: true,
  });

  Object.defineProperty(window.speechSynthesis, "getVoices", {
    value: getVoices,
    writable: true,
    configurable: true,
  });
  window.dispatchEvent(new Event("voiceschanged"));
})();
"""


def build_voices_init_script(locale: str | None) -> str:
    import json

    voices_json = json.dumps(
        voice_list_for_locale(locale), ensure_ascii=False, separators=(",", ":")
    )
    return _INIT_SCRIPT % {"voices_json": voices_json}