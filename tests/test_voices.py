import json

from zencloak.core.voices import build_voices_init_script, voice_list_for_locale


def _langs(voices):
    return [v["lang"] for v in voices]


def test_zh_hk_locale_yields_tracy_dominant():
    voices = voice_list_for_locale("zh-HK")
    assert voices[0]["name"] == "Microsoft Tracy"
    assert voices[0]["lang"] == "zh-HK"
    assert voices[0]["default"] is True
    # 其余为 en-US/en-GB 基础语音，zh-HK 占主导
    assert _langs(voices).count("zh-HK") == 1
    assert set(_langs(voices)) == {"zh-HK", "en-US", "en-GB"}


def test_zh_tw_and_zh_cn_sets():
    tw = voice_list_for_locale("zh-TW")
    assert tw[0]["lang"] == "zh-TW"
    cn = voice_list_for_locale("zh-CN")
    assert cn[0]["name"] == "Microsoft Huihui"
    assert cn[0]["lang"] == "zh-CN"


def test_en_us_has_no_duplicates_and_one_default():
    voices = voice_list_for_locale("en-US")
    names = [v["name"] for v in voices]
    assert len(names) == len(set(names))
    assert sum(1 for v in voices if v["default"]) == 1


def test_unknown_locale_falls_back_to_locale_lang():
    voices = voice_list_for_locale("sw-KE")
    assert voices[0]["lang"] == "sw-KE"
    assert voices[-1]["lang"] == "en-US"


def test_none_locale_defaults_to_en_us():
    voices = voice_list_for_locale(None)
    assert voices[0]["lang"] == "en-US"


def test_init_script_embeds_voice_json_and_native_spoof():
    script = build_voices_init_script("zh-HK")
    assert "Microsoft Tracy" in script
    assert "getVoices" in script
    assert "[native code]" in script
    assert "SpeechSynthesisVoice.prototype" in script
    # 内嵌 JSON 可解析且与 voice_list_for_locale 一致
    payload = script.split("const VOICES = ", 1)[1].split(";\n", 1)[0]
    assert json.loads(payload) == voice_list_for_locale("zh-HK")