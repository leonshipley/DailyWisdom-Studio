import re
import asyncio
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Dict, Any, List
import edge_tts

BASE_DIR = Path(__file__).resolve().parent
PREVIEWS_DIR = BASE_DIR / "assets" / "voice_previews"
PREVIEWS_DIR.mkdir(parents=True, exist_ok=True)
VOICE_CONFIG_FILE = BASE_DIR / "studio_voice_config.json"

VOICE_CATALOG: Dict[str, List[Dict[str, str]]] = {
    "🇮🇳 Hindi / Indian Accent (hi-IN)": [
        {"id": "hi_madhur", "name": "Madhur — Native Hindi Accent (Male)", "gender": "Male", "voice": "hi-IN-MadhurNeural", "rate": "-4%", "pitch": "+0Hz", "style": "Authentic native Hindi accent (Reads English & Hindi verses)"},
        {"id": "hi_immanuel", "name": "Pastor Immanuel — Deep Hindi Baritone (Male)", "gender": "Male", "voice": "hi-IN-MadhurNeural", "rate": "-8%", "pitch": "-6Hz", "style": "Deep, emotional Indian church prayer & scripture voice"},
        {"id": "hi_yeshua_das", "name": "Brother Yeshua Das — Calm Devotional (Male)", "gender": "Male", "voice": "hi-IN-MadhurNeural", "rate": "-6%", "pitch": "-3Hz", "style": "Gentle, comforting Hindi-accented Bible reader"},
        {"id": "hi_raghav", "name": "Raghav — Uplifting & Clear (Male)", "gender": "Male", "voice": "hi-IN-MadhurNeural", "rate": "+0%", "pitch": "+2Hz", "style": "Clear, energetic Indian accent for youth & encouragement"},
        {"id": "hi_swara", "name": "Swara — Native Hindi Accent (Female)", "gender": "Female", "voice": "hi-IN-SwaraNeural", "rate": "-4%", "pitch": "+0Hz", "style": "Sweet, clear native Hindi female accent (English & Hindi)"},
        {"id": "hi_aaradhya", "name": "Sister Aaradhya — Peaceful Prayer (Female)", "gender": "Female", "voice": "hi-IN-SwaraNeural", "rate": "-8%", "pitch": "-3Hz", "style": "Slow, soothing & deeply spiritual Hindi accent"},
        {"id": "hi_mariam", "name": "Sister Mariam — Motherly Comfort (Female)", "gender": "Female", "voice": "hi-IN-SwaraNeural", "rate": "-6%", "pitch": "-5Hz", "style": "Warm, mature & reassuring devotional voice"},
        {"id": "hi_meera", "name": "Meera — Bright & Hopeful (Female)", "gender": "Female", "voice": "hi-IN-SwaraNeural", "rate": "-1%", "pitch": "+3Hz", "style": "Crisp, expressive Hindi-accented scripture reader"},
    ],
    "🇮🇳 Indian English (en-IN)": [
        {"id": "in_prabhat", "name": "Prabhat — Classic Indian English (Male)", "gender": "Male", "voice": "en-IN-PrabhatNeural", "rate": "-3%", "pitch": "+0Hz", "style": "Clear, natural & professional Indian English"},
        {"id": "in_samuel", "name": "Pastor Samuel — Deep Indian Baritone (Male)", "gender": "Male", "voice": "en-IN-PrabhatNeural", "rate": "-7%", "pitch": "-6Hz", "style": "Deep, solemn & authoritative prayer leader"},
        {"id": "in_aarav", "name": "Aarav — Uplifting & Inspiring (Male)", "gender": "Male", "voice": "en-IN-PrabhatNeural", "rate": "+2%", "pitch": "+3Hz", "style": "Bright, energetic & motivational Indian tone"},
        {"id": "in_neerja_exp", "name": "Neerja Expressive — Warm & Caring (Female)", "gender": "Female", "voice": "en-IN-NeerjaExpressiveNeural", "rate": "-3%", "pitch": "+0Hz", "style": "Richly emotional & comforting Indian English"},
        {"id": "in_grace", "name": "Sister Grace — Soft Devotional (Female)", "gender": "Female", "voice": "en-IN-NeerjaNeural", "rate": "-6%", "pitch": "-3Hz", "style": "Slow, peaceful & meditative prayer voice"},
        {"id": "in_kavya", "name": "Kavya — Crisp & Encouraging (Female)", "gender": "Female", "voice": "en-IN-NeerjaNeural", "rate": "+0%", "pitch": "+3Hz", "style": "Clear, articulate storytelling tone"},
    ],
    "🇺🇸 American English (en-US)": [
        {"id": "us_christopher", "name": "Christopher — Deep Pastoral Baritone (Male)", "gender": "Male", "voice": "en-US-ChristopherNeural", "rate": "-2%", "pitch": "+0Hz", "style": "Authoritative, warm & reverent"},
        {"id": "us_andrew", "name": "Andrew — Warm & Comforting (Male)", "gender": "Male", "voice": "en-US-AndrewNeural", "rate": "-3%", "pitch": "+0Hz", "style": "Natural, close-mic devotional storyteller"},
        {"id": "us_brian", "name": "Brian — Calm Storyteller (Male)", "gender": "Male", "voice": "en-US-BrianNeural", "rate": "-2%", "pitch": "-1Hz", "style": "Smooth, peaceful late-night reflection"},
        {"id": "us_eric", "name": "Eric — Gentle & Reflective (Male)", "gender": "Male", "voice": "en-US-EricNeural", "rate": "-4%", "pitch": "-2Hz", "style": "Soft-spoken, empathetic counseling tone"},
        {"id": "us_guy", "name": "Guy — Inspiring Preacher (Male)", "gender": "Male", "voice": "en-US-GuyNeural", "rate": "+0%", "pitch": "-1Hz", "style": "Clear, strong & encouraging sermon delivery"},
        {"id": "us_steffan", "name": "Steffan — Crisp Motivational (Male)", "gender": "Male", "voice": "en-US-SteffanNeural", "rate": "+1%", "pitch": "+0Hz", "style": "Modern, articulate & uplifting"},
        {"id": "us_roger", "name": "Roger — Wise Elder Baritone (Male)", "gender": "Male", "voice": "en-US-RogerNeural", "rate": "-5%", "pitch": "-4Hz", "style": "Mature, seasoned biblical narrator"},
        {"id": "us_ava", "name": "Ava — Soulful & Compassionate (Female)", "gender": "Female", "voice": "en-US-AvaNeural", "rate": "-3%", "pitch": "+0Hz", "style": "Warm, comforting & deeply expressive"},
        {"id": "us_aria", "name": "Aria — Clear & Encouraging (Female)", "gender": "Female", "voice": "en-US-AriaNeural", "rate": "-2%", "pitch": "+0Hz", "style": "Polished, bright devotional narrator"},
        {"id": "us_jenny", "name": "Jenny — Soft & Peaceful (Female)", "gender": "Female", "voice": "en-US-JennyNeural", "rate": "-4%", "pitch": "-1Hz", "style": "Gentle, soothing bedtime prayer tone"},
    ],
    "🇬🇧 British English (en-GB)": [
        {"id": "gb_ryan", "name": "Ryan — Cinematic British Baritone (Male)", "gender": "Male", "voice": "en-GB-RyanNeural", "rate": "-3%", "pitch": "-1Hz", "style": "Rich, resonant & noble scripture narrator"},
        {"id": "gb_thomas", "name": "Thomas — Reverent Oxford Preacher (Male)", "gender": "Male", "voice": "en-GB-ThomasNeural", "rate": "-4%", "pitch": "-2Hz", "style": "Classic, dignified & calm cathedral delivery"},
        {"id": "gb_arthur", "name": "Father Arthur — Deep Cathedral Voice (Male)", "gender": "Male", "voice": "en-GB-RyanNeural", "rate": "-8%", "pitch": "-7Hz", "style": "Deep, solemn & ancient biblical gravitas"},
        {"id": "gb_sonia", "name": "Sonia — Warm British Narrator (Female)", "gender": "Female", "voice": "en-GB-SoniaNeural", "rate": "-3%", "pitch": "+0Hz", "style": "Comforting, poised & reassuring"},
        {"id": "gb_libby", "name": "Libby — Gentle & Empathetic (Female)", "gender": "Female", "voice": "en-GB-LibbyNeural", "rate": "-4%", "pitch": "-1Hz", "style": "Soft, intimate & heartfelt reflection"},
        {"id": "gb_maisie", "name": "Maisie — Hopeful & Bright (Female)", "gender": "Female", "voice": "en-GB-MaisieNeural", "rate": "-2%", "pitch": "+1Hz", "style": "Uplifting, tender & sincere"},
    ],
}

SCRIPT_MODES = [
    "English Only (Spoken in Selected Accent)",
    "Hindi Only (Pavitra Baibil Vachan & Prarthana)",
    "Both Together: English + Hindi (Reads English First, Then Hindi)",
]

HINDI_BIBLE_VAULT: Dict[str, Dict[str, Any]] = {
    "Debt": {
        "topic": "Debt & Financial Freedom",
        "title": "Karz Mukti Ki Shaktishali Prarthana #shorts",
        "verse_citation": "Philippians chapter 4 verse 19",
        "verse_text": "Mera Parmeshwar apne dhan ke anusaar Krist Yeshu mein aapki har zaroorat ko poora karega.",
        "meaning": "Prabhu chahte hain ki aap har karz ke bojh se azaad ho jayein. Unke bhandaar mein aapke parivaar ke liye koi kami nahi hai.",
        "prayer": "Prabhu Yeshu, mere parivaar ko har karz se mukt karein aur apni barkat ke darwaze khol dein, Amen.",
        "thumbnail_hook": "KARZ SE AZAADI",
        "hashtags": ["#HindiBible", "#YeshuMasih", "#Prarthana", "#Shorts"]
    },
    "Anxiety": {
        "topic": "Anxiety & Stress Relief",
        "title": "Chinta Aur Darr Se Shanti Ki Prarthana #shorts",
        "verse_citation": "Philippians 4:6-7",
        "verse_text": "Kisi bhi baat ki chinta mat karo, parantu har baat mein prarthana ke dwara Parmeshwar ko apne vinti batao.",
        "meaning": "Aapko yeh bojh akele uthane ki zaroorat nahi hai. Apni saari chinta Prabhu Yeshu ke haathon mein saunp dein.",
        "prayer": "Prabhu Yeshu, mere mann ki saari chinta door karein aur mujhe apni swargiya shanti se bhar dein, Amen.",
        "thumbnail_hook": "MANN KI SHANTI",
        "hashtags": ["#HindiPrayer", "#YeshuMasih", "#Shanti", "#Shorts"]
    },
    "Broken Heart": {
        "topic": "Broken Heart & Depression",
        "title": "Toote Dil Koodne Wali Prarthana #shorts",
        "verse_citation": "भजन संहिता, अध्याय 34, वचन 18",
        "verse_text": "Yahowa toote man walon ke samip rehta hai, aur pichde hue logon ka uddhar karta hai.",
        "meaning": "Aap apne aansuon mein kabhi akele nahi hain. Prabhu Yeshu aapke dard ko samajhte hain aur aapko nayi aasha dete hain.",
        "prayer": "Prabhu Yeshu, mere toote hue hriday ko changa karein aur mere jeevan mein phir se anand bhar dein, Amen.",
        "thumbnail_hook": "PRABHU SAATH HAIN",
        "hashtags": ["#HindiBibleVerse", "#Yeshu", "#Prarthana", "#Shorts"]
    },
    "Healing": {
        "topic": "Healing & Sickness",
        "title": "Bimari Se Changai Ki Chamatkari Prarthana #shorts",
        "verse_citation": "Jeremiah 17:14",
        "verse_text": "He Yahowa, mujhe changa kar, tab main changa ho jaunga; mujhe bacha, tab main bach jaunga.",
        "meaning": "Prabhu Yeshu aapke mahaan vaidya hain. Unke kodo ke ghaav se aapke sharir mein abhi changai beh rahi hai.",
        "prayer": "Prabhu Yeshu, apne changai bhare haath se mere sharir ko chhu lein aur har bimari ko door karein, Amen.",
        "thumbnail_hook": "CHAMATKARI CHANGAI",
        "hashtags": ["#ChangaiKiPrarthana", "#YeshuMasih", "#HealingPrayer", "#Shorts"]
    },
}

DEFAULT_SAMPLE_TEXTS: Dict[str, str] = {
    "🇮🇳 Hindi / Indian Accent (hi-IN)": "If you are struggling today, hold onto this verse. भजन संहिता, अध्याय 34, वचन 18. The Lord is near to the brokenhearted, and saves the crushed in spirit. Prabhu Yeshu aapke saath hain. Type Amen.",
    "🇮🇳 Indian English (en-IN)": "If you are walking through a difficult season, hold onto God's promise. Philippians chapter 4 verse 19. And my God will supply every need of yours. Type Amen.",
    "🇺🇸 American English (en-US)": "If your heart feels heavy tonight, pause right here. The Lord is near to the brokenhearted, and His peace will guard your soul. Type Amen.",
    "🇬🇧 British English (en-GB)": "Be still, and know that I am God. Even in the darkest valley, His light surrounds you with unshakeable peace. Type Amen if you believe.",
}

def load_active_voice() -> Dict[str, Any]:
    default_v = dict(VOICE_CATALOG["🇮🇳 Hindi / Indian Accent (hi-IN)"][0])
    default_v["accent"] = "🇮🇳 Hindi / Indian Accent (hi-IN)"
    default_v["script_mode"] = SCRIPT_MODES[0]
    if VOICE_CONFIG_FILE.exists():
        try:
            data = json.loads(VOICE_CONFIG_FILE.read_text(encoding="utf-8"))
            if "voice" in data and "name" in data:
                data.setdefault("script_mode", SCRIPT_MODES[0])
                return data
        except Exception:
            pass
    return default_v

def save_active_voice(voice_profile: Dict[str, Any]) -> None:
    VOICE_CONFIG_FILE.write_text(json.dumps(voice_profile, indent=2), encoding="utf-8")

def combine_prosody(base_val: str, offset_int: int, unit: str) -> str:
    try:
        num = int(base_val.replace(unit, "").replace("+", "").strip())
    except Exception:
        num = 0
    total = max(-35, min(35, num + int(offset_int)))
    return f"{total:+d}{unit}"

def build_spoken_voice_script(script_obj: Any) -> str:
    """
    Guarantees 100% Pure Devanagari Hindi for the ENTIRE video (Hook, Book, Chapter, Verse, Meaning, Prayer, CTA)
    whenever Hindi mode or a Hindi voice is active.
    """
    from bible_database import lookup_reference_bilingual, format_reference_for_speech, translate_any_text_to_hindi
    cfg = load_active_voice()
    mode = cfg.get("script_mode", SCRIPT_MODES[0])
    is_hi_accent = "hi-IN" in cfg.get("voice", "") or "Hindi" in cfg.get("accent", "")

    en_ref_spoken = format_reference_for_speech(script_obj.verse_citation, is_hindi_speech=False)
    hi_ref_spoken = format_reference_for_speech(script_obj.verse_citation, is_hindi_speech=True)
    _, en_v, dev_hi, _ = lookup_reference_bilingual(script_obj.verse_citation)

    clean_t_en = re.sub(r"\(Suggested Verse:.*?\)", "", script_obj.topic).strip()

    if "Both Together" in mode:
        hi_meaning = translate_any_text_to_hindi(script_obj.meaning)
        hi_prayer = translate_any_text_to_hindi(script_obj.prayer)
        return (
            f"Hold onto God's promise in {en_ref_spoken}. {en_v} "
            f"पवित्र बाइबिल में {hi_ref_spoken} में लिखा है: {dev_hi}। "
            f"{hi_meaning} आइए प्रार्थना करें: {hi_prayer} कमेंट में आमीन ज़रूर लिखें।"
        )

    if "Hindi" in mode or is_hi_accent:
        hi_topic = translate_any_text_to_hindi(clean_t_en)
        # Always force pure Devanagari Hindi for the verse, meaning, and prayer!
        hi_verse = dev_hi if re.search(r"[\u0900-\u097F]", dev_hi or "") else translate_any_text_to_hindi(script_obj.verse_text)
        hi_meaning = translate_any_text_to_hindi(script_obj.meaning)
        hi_prayer = translate_any_text_to_hindi(script_obj.prayer)
        full_hi = (
            f"यदि आप अपने जीवन में {hi_topic} का सामना कर रहे हैं, तो परमेश्वर के इस पवित्र वचन को ध्यान से सुनें। "
            f"पवित्र बाइबिल, {hi_ref_spoken}। {hi_verse}। "
            f"इस वचन का अर्थ है: {hi_meaning}। "
            f"आइए मिलकर प्रार्थना करें: {hi_prayer}। "
            f"यदि आप इस आशीष को ग्रहण करते हैं, तो कमेंट में आमीन ज़रूर लिखें।"
        )
        return re.sub(r"(\d+):(\d+)", r"अध्याय \1 वचन \2", full_hi)

    full_en = (
        f"If you are struggling with {clean_t_en}, hold onto this verse. "
        f"{en_ref_spoken}. {en_v if en_v else script_obj.verse_text} "
        f"{script_obj.meaning} Let us pray. {script_obj.prayer} "
        f"Type Amen in the comments to receive this blessing."
    )
    return re.sub(r"(\d+):(\d+)", r"chapter \1 verse \2", full_en)

def synthesize_preview_sample(
    voice_id: str,
    rate_str: str = "-4%",
    pitch_str: str = "+0Hz",
    sample_text: str = "",
) -> Path:
    text = (sample_text or "The Lord is near to the brokenhearted, and saves the crushed in spirit. Type Amen.").strip()
    key_hash = hashlib.md5(f"{voice_id}_{rate_str}_{pitch_str}_{text}".encode("utf-8")).hexdigest()[:12]
    out_mp3 = PREVIEWS_DIR / f"preview_{voice_id}_{key_hash}.mp3"

    if out_mp3.exists() and out_mp3.stat().st_size > 1000:
        return out_mp3

    async def _run():
        try:
            comm = edge_tts.Communicate(text, voice=voice_id, rate=rate_str, pitch=pitch_str)
        except TypeError:
            comm = edge_tts.Communicate(text, voice=voice_id, rate=rate_str)
        await comm.save(str(out_mp3))

    try:
        asyncio.run(_run())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(_run())
        loop.close()

    return out_mp3

def play_audio_on_windows(mp3_path: Path) -> None:
    try:
        subprocess.run(
            ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", str(mp3_path)],
            timeout=18,
            check=True
        )
    except Exception:
        try:
            import os
            os.startfile(str(mp3_path))
        except Exception:
            pass

def synthesize_bilingual_verse_preview(
    ref_str: str,
    en_text: str,
    hi_devanagari: str,
    hi_hinglish: str,
    listen_mode: str = "both",
) -> Path:
    """
    Guarantees that when listen_mode is 'hindi' or 'both', the Hindi verse is spoken
    in 100% pure Devanagari Hindi (never English!).
    """
    from bible_database import format_reference_for_speech, translate_verse_to_hindi, translate_any_text_to_hindi

    cfg = load_active_voice()
    en_voice = cfg.get("voice", "en-US-ChristopherNeural")
    if "hi-IN" in en_voice and listen_mode == "english":
        en_voice = "en-IN-PrabhatNeural"
    rate_str = cfg.get("rate", "-3%")
    pitch_str = cfg.get("pitch", "+0Hz")
    is_female = cfg.get("gender", "Male") == "Female"
    hi_voice = "hi-IN-SwaraNeural" if is_female else "hi-IN-MadhurNeural"

    # Ensure hi_devanagari is real Devanagari Hindi (never English!)
    if not hi_devanagari or not re.search(r"[\u0900-\u097F]", hi_devanagari):
        hi_devanagari, _ = translate_verse_to_hindi(ref_str, en_text)
    if not re.search(r"[\u0900-\u097F]", hi_devanagari):
        hi_devanagari = translate_any_text_to_hindi(en_text)

    en_spoken_ref = format_reference_for_speech(ref_str, is_hindi_speech=False)
    hi_spoken_ref = format_reference_for_speech(ref_str, is_hindi_speech=True)

    key_hash = hashlib.md5(f"v3_{listen_mode}_{en_voice}_{hi_voice}_{rate_str}_{pitch_str}_{ref_str}_{hi_devanagari[:30]}".encode("utf-8")).hexdigest()[:12]
    out_mp3 = PREVIEWS_DIR / f"verse_{listen_mode}_{key_hash}.mp3"

    if out_mp3.exists() and out_mp3.stat().st_size > 1000:
        return out_mp3

    async def _build_mp3():
        with open(out_mp3, "wb") as f_out:
            if listen_mode in ("english", "both"):
                en_line = f"{en_spoken_ref}. {en_text}"
                try:
                    c_en = edge_tts.Communicate(en_line, voice=en_voice, rate=rate_str, pitch=pitch_str)
                except TypeError:
                    c_en = edge_tts.Communicate(en_line, voice=en_voice, rate=rate_str)
                async for chunk in c_en.stream():
                    if chunk["type"] == "audio":
                        f_out.write(chunk["data"])

            if listen_mode in ("hindi", "both"):
                hi_line = f"पवित्र बाइबिल, {hi_spoken_ref}। {hi_devanagari}"
                try:
                    c_hi = edge_tts.Communicate(hi_line, voice=hi_voice, rate="-4%", pitch=pitch_str)
                except TypeError:
                    c_hi = edge_tts.Communicate(hi_line, voice=hi_voice, rate="-4%")
                async for chunk in c_hi.stream():
                    if chunk["type"] == "audio":
                        f_out.write(chunk["data"])

    try:
        asyncio.run(_build_mp3())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(_build_mp3())
        loop.close()

    return out_mp3
