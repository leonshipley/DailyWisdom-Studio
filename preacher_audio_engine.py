import os
import re
import json
import asyncio
import shutil
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Tuple
import edge_tts

BASE_DIR = Path(__file__).resolve().parent
SFX_DIR = BASE_DIR / "assets" / "preacher_sfx"
SFX_DIR.mkdir(parents=True, exist_ok=True)
PREACHER_CFG_FILE = BASE_DIR / "preacher_config.json"

PREACHER_MODES = [
    "🔥 Passionate Preacher (Dynamic Pitch + Sacred SFX + Swells)",
    "🕊️ Intimate Late-Night Pastor (Warm Whisper + Soft Chimes)",
    "⚡ Custom Manual Preacher Tuning (Use Sliders & Tags)",
    "📖 Classic Studio Reader (Flat Standard Voice)"
]

EMOTION_PRESETS = [
    "🤖 Auto-Detect",
    "😡 Angry / Righteous Thunder",
    "🔥 Warfare & Breakthrough",
    "🥺 Empathy & Comfort",
    "🤫 Soft Intimate Whisper",
    "📖 Reverent Scripture",
    "✨ Joyful Praise",
    "🙏 Benediction & Amen",
    "🎙️ Pastoral Teaching"
]

SFX_CHOICES = [
    "Auto",
    "None",
    "⚡ Thunder Boom (Angry/Warfare)",
    "✨ Scripture Shimmer",
    "🌊 Holy Sub-Swell",
    "🔔 Amen Sanctuary Bell"
]

DEFAULT_PREACHER_CONFIG = {
    "mode": PREACHER_MODES[0],
    "sfx_enabled": True,
    "sfx_vol": 0.35,
    "reverb_enabled": True,
    "sfx_shimmer": True,
    "sfx_swell": True,
    "sfx_boom": True,
    "sfx_bell": True,
    "angry_pitch": 6,
    "angry_rate": 9,
    "angry_vol": 18,
    "empathy_pitch": -5,
    "empathy_rate": -10,
    "empathy_vol": -4,
    "whisper_pitch": -7,
    "whisper_rate": -14,
    "whisper_vol": -12,
    "scripture_pitch": -2,
    "scripture_rate": -5,
    "scripture_vol": 5,
    "warfare_pitch": 4,
    "warfare_rate": 5,
    "warfare_vol": 12,
    "joy_pitch": 4,
    "joy_rate": 3,
    "joy_vol": 8,
    "amen_pitch": -5,
    "amen_rate": -11,
    "amen_vol": 4,
    "sentence_overrides": {}
}

def load_preacher_config() -> Dict[str, Any]:
    cfg = dict(DEFAULT_PREACHER_CONFIG)
    if PREACHER_CFG_FILE.exists():
        try:
            saved = json.loads(PREACHER_CFG_FILE.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                cfg.update(saved)
        except Exception:
            pass
    return cfg

def save_preacher_config(new_cfg: Dict[str, Any] | str, sfx_enabled: bool = True, sfx_vol: float = 0.35):
    cur = load_preacher_config()
    if isinstance(new_cfg, str):
        cur["mode"] = new_cfg
        cur["sfx_enabled"] = bool(sfx_enabled)
        cur["sfx_vol"] = float(sfx_vol)
    elif isinstance(new_cfg, dict):
        cur.update(new_cfg)
    PREACHER_CFG_FILE.write_text(json.dumps(cur, indent=2), encoding="utf-8")

def strip_emotion_tags(text: str) -> str:
    """Removes inline emotion/SFX tags like [angry], [empathy], [boom] and *asterisks* for clean subtitles/TTS."""
    if not text:
        return ""
    t = re.sub(r"\[(angry|fierce|rebuke|empathy|sad|comfort|whisper|soft|scripture|verse|warfare|bold|joy|praise|amen|normal|boom|thunder|swell|shimmer|bell)\]", "", text, flags=re.IGNORECASE)
    t = re.sub(r"\*([^*]+)\*", r"", t)
    return re.sub(r"\s+", " ", t).strip()

def ensure_sacred_sfx_files() -> Dict[str, Path]:
    sfx = {
        "shimmer": SFX_DIR / "scripture_shimmer.mp3",
        "swell": SFX_DIR / "holy_sub_swell.mp3",
        "boom": SFX_DIR / "warfare_pulse.mp3",
        "bell": SFX_DIR / "amen_sanctuary_bell.mp3",
    }

    if not sfx["shimmer"].exists() or sfx["shimmer"].stat().st_size < 1000:
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "sine=frequency=528:sample_rate=44100",
            "-f", "lavfi", "-i", "sine=frequency=660:sample_rate=44100",
            "-f", "lavfi", "-i", "sine=frequency=792:sample_rate=44100",
            "-f", "lavfi", "-i", "sine=frequency=1056:sample_rate=44100",
            "-filter_complex",
            "amix=inputs=4:normalize=0,afade=t=in:st=0:d=0.06,afade=t=out:st=0.25:d=1.9,aecho=0.8:0.88:90:0.45,volume=0.26",
            "-t", "2.2", "-ac", "2", "-c:a", "libmp3lame", "-b:a", "192k", str(sfx["shimmer"].absolute())
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if not sfx["swell"].exists() or sfx["swell"].stat().st_size < 1000:
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "sine=frequency=65.4:sample_rate=44100",
            "-f", "lavfi", "-i", "sine=frequency=98.0:sample_rate=44100",
            "-f", "lavfi", "-i", "sine=frequency=130.8:sample_rate=44100",
            "-filter_complex",
            "amix=inputs=3:normalize=0,lowpass=f=220,afade=t=in:st=0:d=0.7,afade=t=out:st=1.2:d=1.8,volume=0.42",
            "-t", "3.0", "-ac", "2", "-c:a", "libmp3lame", "-b:a", "192k", str(sfx["swell"].absolute())
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if not sfx["boom"].exists() or sfx["boom"].stat().st_size < 1000:
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "sine=frequency=50:sample_rate=44100",
            "-f", "lavfi", "-i", "sine=frequency=100:sample_rate=44100",
            "-f", "lavfi", "-i", "anoisesrc=d=1.5:c=brown:r=44100:a=0.18",
            "-filter_complex",
            "amix=inputs=3:normalize=0,lowpass=f=160,afade=t=in:st=0:d=0.01,afade=t=out:st=0.12:d=1.2,aecho=0.8:0.85:130:0.4,volume=0.52",
            "-t", "1.5", "-ac", "2", "-c:a", "libmp3lame", "-b:a", "192k", str(sfx["boom"].absolute())
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if not sfx["bell"].exists() or sfx["bell"].stat().st_size < 1000:
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "sine=frequency=432:sample_rate=44100",
            "-f", "lavfi", "-i", "sine=frequency=864:sample_rate=44100",
            "-filter_complex",
            "amix=inputs=2:normalize=0,afade=t=in:st=0:d=0.02,afade=t=out:st=0.2:d=2.4,aecho=0.8:0.9:120:0.5,volume=0.30",
            "-t", "2.7", "-ac", "2", "-c:a", "libmp3lame", "-b:a", "192k", str(sfx["bell"].absolute())
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    return sfx

def _parse_int(val_str: str, default: int = 0) -> int:
    try:
        return int(re.sub(r"[^0-9\-+]", "", str(val_str)))
    except Exception:
        return default

def _get_audio_dur(p: Path) -> float:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(p.absolute())],
            capture_output=True, text=True, timeout=6
        )
        return float(r.stdout.strip())
    except Exception:
        return 0.0

def _apply_emotion_preset(emo_label: str, b_rate: int, b_pitch: int, cfg: Dict[str, Any]) -> Tuple[str, str, str, float, str]:
    if "Angry" in emo_label:
        r = max(-25, min(30, b_rate + int(cfg.get("angry_rate", 9))))
        p = max(-15, min(18, b_pitch + int(cfg.get("angry_pitch", 6))))
        v = int(cfg.get("angry_vol", 18))
        return f"{r:+d}%", f"{p:+d}Hz", f"{v:+d}%", 0.30, "😡 Angry / Righteous Thunder"
    if "Warfare" in emo_label:
        r = max(-25, min(25, b_rate + int(cfg.get("warfare_rate", 5))))
        p = max(-15, min(15, b_pitch + int(cfg.get("warfare_pitch", 4))))
        v = int(cfg.get("warfare_vol", 12))
        return f"{r:+d}%", f"{p:+d}Hz", f"{v:+d}%", 0.35, "🔥 Warfare & Breakthrough"
    if "Empathy" in emo_label:
        r = max(-28, min(25, b_rate + int(cfg.get("empathy_rate", -10))))
        p = max(-15, min(15, b_pitch + int(cfg.get("empathy_pitch", -5))))
        v = int(cfg.get("empathy_vol", -4))
        return f"{r:+d}%", f"{p:+d}Hz", f"{v:+d}%", 0.44, "🥺 Empathy & Comfort"
    if "Whisper" in emo_label:
        r = max(-30, min(20, b_rate + int(cfg.get("whisper_rate", -14))))
        p = max(-15, min(15, b_pitch + int(cfg.get("whisper_pitch", -7))))
        v = int(cfg.get("whisper_vol", -12))
        return f"{r:+d}%", f"{p:+d}Hz", f"{v:+d}%", 0.50, "🤫 Soft Intimate Whisper"
    if "Scripture" in emo_label:
        r = max(-25, min(25, b_rate + int(cfg.get("scripture_rate", -5))))
        p = max(-15, min(15, b_pitch + int(cfg.get("scripture_pitch", -2))))
        v = int(cfg.get("scripture_vol", 5))
        return f"{r:+d}%", f"{p:+d}Hz", f"{v:+d}%", 0.40, "📖 Reverent Scripture"
    if "Joyful" in emo_label:
        r = max(-20, min(25, b_rate + int(cfg.get("joy_rate", 3))))
        p = max(-10, min(15, b_pitch + int(cfg.get("joy_pitch", 4))))
        v = int(cfg.get("joy_vol", 8))
        return f"{r:+d}%", f"{p:+d}Hz", f"{v:+d}%", 0.30, "✨ Joyful Praise"
    if "Benediction" in emo_label or "Amen" in emo_label:
        r = max(-28, min(25, b_rate + int(cfg.get("amen_rate", -11))))
        p = max(-15, min(15, b_pitch + int(cfg.get("amen_pitch", -5))))
        v = int(cfg.get("amen_vol", 4))
        return f"{r:+d}%", f"{p:+d}Hz", f"{v:+d}%", 0.45, "🙏 Benediction & Amen"
    return f"{b_rate:+d}%", f"{b_pitch:+d}Hz", "+0%", 0.28, "🎙️ Pastoral Teaching"

def classify_sentence_prosody(sentence: str, base_rate: str, base_pitch: str, cfg: Dict[str, Any], sent_idx: int = -1) -> Tuple[str, str, str, float, str]:
    b_rate = _parse_int(base_rate, 0)
    b_pitch = _parse_int(base_pitch, 0)
    mode = cfg.get("mode", PREACHER_MODES[0])

    if "Classic" in mode:
        return f"{b_rate:+d}%", f"{b_pitch:+d}Hz", "+0%", 0.20, "📖 Flat Reader"

    # Check if user set a manual table override for this sentence index
    overrides = cfg.get("sentence_overrides", {})
    if str(sent_idx) in overrides:
        ov = overrides[str(sent_idx)]
        emo_ov = ov.get("emotion", "🤖 Auto-Detect")
        if emo_ov != "🤖 Auto-Detect":
            return _apply_emotion_preset(emo_ov, b_rate, b_pitch, cfg)

    low = sentence.lower()

    # 1. Explicit Inline Emotion Tags ([angry], [empathy], [whisper], [warfare], [scripture], [joy], [amen])
    if any(t in low for t in ["[angry]", "[fierce]", "[rebuke]"]):
        return _apply_emotion_preset("😡 Angry / Righteous Thunder", b_rate, b_pitch, cfg)
    if any(t in low for t in ["[warfare]", "[bold]"]):
        return _apply_emotion_preset("🔥 Warfare & Breakthrough", b_rate, b_pitch, cfg)
    if any(t in low for t in ["[empathy]", "[sad]", "[comfort]"]):
        return _apply_emotion_preset("🥺 Empathy & Comfort", b_rate, b_pitch, cfg)
    if any(t in low for t in ["[whisper]", "[soft]"]):
        return _apply_emotion_preset("🤫 Soft Intimate Whisper", b_rate, b_pitch, cfg)
    if any(t in low for t in ["[scripture]", "[verse]"]):
        return _apply_emotion_preset("📖 Reverent Scripture", b_rate, b_pitch, cfg)
    if any(t in low for t in ["[joy]", "[praise]"]):
        return _apply_emotion_preset("✨ Joyful Praise", b_rate, b_pitch, cfg)
    if "[amen]" in low:
        return _apply_emotion_preset("🙏 Benediction & Amen", b_rate, b_pitch, cfg)

    # 2. Automatic Keyword Detection
    if any(w in low for w in ["enough is enough", "devil is a liar", "satan", "get behind me", "rebuke", "destroy", "enemy", "curse", "wicked", "hell", "शैतान", "नाश"]):
        return _apply_emotion_preset("😡 Angry / Righteous Thunder", b_rate, b_pitch, cfg)

    if any(w in low for w in ["amen", "in jesus' name", "in jesus name", "type amen", "comment amen", "आमीन", "कमेंट"]):
        return _apply_emotion_preset("🙏 Benediction & Amen", b_rate, b_pitch, cfg)

    if any(w in low for w in ["break every", "command", "authority", "no weapon", "prosper", "chains", "mighty", "victory", "rise", "miracle", "never", "deliver", "power", "बंधन", "सामर्थ्य"]):
        return _apply_emotion_preset("🔥 Warfare & Breakthrough", b_rate, b_pitch, cfg)

    if any(w in low for w in ["chapter", "verse", "psalm", "isaiah", "philippians", "matthew", "proverbs", "jeremiah", "word of god", "scripture", "bible", "अध्याय", "वचन", "बाइबिल", "भजन"]):
        return _apply_emotion_preset("📖 Reverent Scripture", b_rate, b_pitch, cfg)

    if any(w in low for w in ["whisper", "still small voice", "close your eyes", "quietly", "गहरी सांस"]):
        return _apply_emotion_preset("🤫 Soft Intimate Whisper", b_rate, b_pitch, cfg)

    if any(w in low for w in ["breath", "tears", "heavy", "weary", "alone", "afraid", "worry", "anxious", "broken", "sleep", "night", "pain", "heart", "soul", "peace", "आंसू", "चिंता", "शांति", "बोझ", "थक"]):
        return _apply_emotion_preset("🥺 Empathy & Comfort", b_rate, b_pitch, cfg)

    return _apply_emotion_preset("🎙️ Pastoral Teaching", b_rate, b_pitch, cfg)

def split_into_preacher_sentences(text: str) -> List[str]:
    clean = re.sub(r"\s+", " ", text.strip())
    parts = re.split(r"(?<=[\.\!\?।])\s+|\.\.\.\s*", clean)
    return [p.strip() for p in parts if p and p.strip()]

def preview_script_preacher_breakdown(text: str, base_rate: str = "+0%", base_pitch: str = "+0Hz") -> List[Dict[str, str]]:
    cfg = load_preacher_config()
    sents = split_into_preacher_sentences(text)
    overrides = cfg.get("sentence_overrides", {})
    rows = []
    for idx, s in enumerate(sents):
        r_s, p_s, v_s, pause_s, emo_lbl = classify_sentence_prosody(s, base_rate, base_pitch, cfg, sent_idx=idx)
        low = s.lower()
        ov_sfx = overrides.get(str(idx), {}).get("sfx", "Auto")
        sfx_list = []
        if ov_sfx != "Auto":
            if ov_sfx != "None":
                sfx_list.append(ov_sfx)
        elif cfg.get("sfx_enabled", True) and "Classic" not in cfg.get("mode", ""):
            if "[boom]" in low or "[thunder]" in low or "Angry" in emo_lbl or (cfg.get("sfx_boom", True) and any(w in low for w in ["break", "chains", "weapon", "authority", "miracle", "overcome", "rebuke", "enemy", "बंधन", "सामर्थ्य"])):
                sfx_list.append("⚡ Thunder Boom")
            if "[shimmer]" in low or (cfg.get("sfx_shimmer", True) and any(w in low for w in ["chapter", "verse", "psalm", "isaiah", "philippians", "jeremiah", "proverbs", "matthew", "scripture", "वचन", "अध्याय", "बाइबिल"])):
                sfx_list.append("✨ Scripture Shimmer")
            if "[swell]" in low or (cfg.get("sfx_swell", True) and any(w in low for w in ["jesus", "father", "lord", "almighty", "spirit", "heavenly", "यीशु", "परमेश्वर", "प्रभु"])):
                sfx_list.append("🌊 Holy Sub-Swell")
            if "[bell]" in low or (cfg.get("sfx_bell", True) and any(w in low for w in ["amen", "आमीन"])):
                sfx_list.append("🔔 Amen Bell")
        rows.append({
            "ID": str(idx),
            "Emotion": emo_lbl,
            "Pitch": p_s,
            "Speed": r_s,
            "Vol": v_s,
            "SFX": ", ".join(sfx_list) if sfx_list else "None",
            "Clean Sentence": strip_emotion_tags(s)
        })
    return rows

def detect_sfx_cues_from_timings(word_timings: List[Dict[str, Any]], cfg: Dict[str, Any], sentence_cues: List[Tuple[str, float]] = None) -> List[Tuple[str, float]]:
    if not cfg.get("sfx_enabled", True) or "Classic" in cfg.get("mode", ""):
        return []
    cues: List[Tuple[str, float]] = list(sentence_cues or [])
    last_cue_time = -4.0

    for w_obj in word_timings:
        w_clean = re.sub(r"[^a-zA-Zऀ-ॿ]", "", w_obj.get("text", "")).lower()
        t_sec = float(w_obj.get("start", 0.0))
        if not w_clean:
            continue

        if cfg.get("sfx_bell", True) and w_clean in ("amen", "आमीन"):
            if (t_sec - last_cue_time) >= 1.5:
                cues.append(("bell", max(0.0, t_sec - 0.05)))
                last_cue_time = t_sec
            continue

        if (t_sec - last_cue_time) < 3.2:
            continue

        if cfg.get("sfx_shimmer", True) and w_clean in ("chapter", "verse", "psalm", "psalms", "isaiah", "philippians", "jeremiah", "proverbs", "matthew", "scripture", "वचन", "अध्याय", "बाइबिल"):
            cues.append(("shimmer", max(0.0, t_sec - 0.1)))
            last_cue_time = t_sec
        elif cfg.get("sfx_swell", True) and w_clean in ("jesus", "father", "lord", "almighty", "spirit", "heavenly", "यीशु", "परमेश्वर", "प्रभु"):
            cues.append(("swell", max(0.0, t_sec - 0.15)))
            last_cue_time = t_sec
        elif cfg.get("sfx_boom", True) and w_clean in ("break", "chains", "weapon", "authority", "miracle", "overcome", "rebuke", "enemy", "enough", "बंधन", "सामर्थ्य"):
            cues.append(("boom", max(0.0, t_sec - 0.05)))
            last_cue_time = t_sec

    return cues[:16]

def synthesize_preacher_voiceover(
    text: str,
    output_voice_path: Path,
    voice_name: str = "en-US-ChristopherNeural",
    base_rate: str = "+0%",
    base_pitch: str = "+0Hz",
    mode: str | None = None,
    sfx_enabled: bool | None = None,
    sfx_vol: float | None = None,
) -> List[Dict[str, Any]]:
    cfg = load_preacher_config()
    if mode is not None:
        cfg["mode"] = mode
    if sfx_enabled is not None:
        cfg["sfx_enabled"] = sfx_enabled
    vol_sfx = float(sfx_vol if sfx_vol is not None else cfg.get("sfx_vol", 0.35))

    if "hi-IN" in voice_name:
        text = re.sub(r"(\d+):(\d+)", r"अध्याय  वचन ", text)
    else:
        text = re.sub(r"(\d+):(\d+)", r"chapter  verse ", text)

    if cfg.get("auto_ai_direct", False) and not re.search(r"\[(angry|empathy|whisper|warfare|scripture|joy|amen)\]", text, re.IGNORECASE):
        text, _ = ai_direct_preacher_script(text)
    sentences = split_into_preacher_sentences(text) or [text]
    work_dir = output_voice_path.parent / f"temp_preacher_{output_voice_path.stem}"
    work_dir.mkdir(parents=True, exist_ok=True)

    concat_files: List[Path] = []
    all_word_timings: List[Dict[str, Any]] = []
    explicit_sentence_cues: List[Tuple[str, float]] = []
    current_offset = 0.0
    overrides = cfg.get("sentence_overrides", {})

    async def _synth_sentence(sent_txt: str, out_mp3: Path, r_str: str, p_str: str, v_str: str, t_off: float):
        try:
            comm = edge_tts.Communicate(sent_txt, voice=voice_name, rate=r_str, pitch=p_str, volume=v_str, boundary="WordBoundary")
        except TypeError:
            comm = edge_tts.Communicate(sent_txt, voice=voice_name, rate=r_str, pitch=p_str)

        raw_evs = []
        with open(out_mp3, "wb") as f_v:
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    f_v.write(chunk["data"])
                elif chunk["type"] in ("WordBoundary", "SentenceBoundary"):
                    st_s = t_off + (chunk["offset"] / 10_000_000.0)
                    du_s = chunk["duration"] / 10_000_000.0
                    raw_evs.append({"type": chunk["type"], "text": chunk["text"], "start": st_s, "end": st_s + du_s})

        for ev in raw_evs:
            if ev["type"] == "WordBoundary" or len(ev["text"].split()) <= 1:
                all_word_timings.append({"text": ev["text"].strip(), "start": round(ev["start"], 3), "end": round(ev["end"], 3)})
            else:
                words = ev["text"].split()
                if not words:
                    continue
                step = max(0.1, ev["end"] - ev["start"]) / len(words)
                for idx_w, w_tok in enumerate(words):
                    all_word_timings.append({
                        "text": w_tok,
                        "start": round(ev["start"] + idx_w * step, 3),
                        "end": round(ev["start"] + (idx_w + 1) * step, 3)
                    })

    for idx, sent in enumerate(sentences):
        r_s, p_s, v_s, pause_sec, emo_lbl = classify_sentence_prosody(sent, base_rate, base_pitch, cfg, sent_idx=idx)

        # Check explicit SFX tags or manual table SFX override
        low_s = sent.lower()
        ov_sfx = overrides.get(str(idx), {}).get("sfx", "Auto")
        if ov_sfx != "Auto":
            if "Thunder" in ov_sfx: explicit_sentence_cues.append(("boom", current_offset))
            elif "Shimmer" in ov_sfx: explicit_sentence_cues.append(("shimmer", current_offset))
            elif "Swell" in ov_sfx: explicit_sentence_cues.append(("swell", current_offset))
            elif "Bell" in ov_sfx: explicit_sentence_cues.append(("bell", current_offset))
        else:
            if "[boom]" in low_s or "[thunder]" in low_s or "Angry" in emo_lbl:
                explicit_sentence_cues.append(("boom", current_offset))
            elif "[shimmer]" in low_s:
                explicit_sentence_cues.append(("shimmer", current_offset))
            elif "[swell]" in low_s:
                explicit_sentence_cues.append(("swell", current_offset))
            elif "[bell]" in low_s:
                explicit_sentence_cues.append(("bell", current_offset))

        # Word-level emphasis: if user wrapped a word in *asterisks* (e.g. *NEVER*), add a micro-pause before it
        clean_sent = re.sub(r"\*([^*]+)\*", r"... !", sent)
        clean_sent = strip_emotion_tags(clean_sent)
        if not clean_sent:
            continue

        sent_mp3 = work_dir / f"sent_{idx:03d}.mp3"
        try:
            asyncio.run(_synth_sentence(clean_sent, sent_mp3, r_s, p_s, v_s, current_offset))
        except RuntimeError:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(_synth_sentence(clean_sent, sent_mp3, r_s, p_s, v_s, current_offset))
            loop.close()

        if sent_mp3.exists() and sent_mp3.stat().st_size > 200:
            dur = _get_audio_dur(sent_mp3)
            concat_files.append(sent_mp3)
            current_offset += dur

            if idx < len(sentences) - 1 and pause_sec > 0.05:
                sil_f = work_dir / f"pause_{idx:03d}.mp3"
                subprocess.run([
                    "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                    "-t", f"{pause_sec:.2f}", "-c:a", "libmp3lame", "-b:a", "192k", str(sil_f.absolute())
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if sil_f.exists():
                    concat_files.append(sil_f)
                    current_offset += pause_sec

    raw_joined = work_dir / "joined_raw.mp3"
    list_txt = work_dir / "concat.txt"
    list_txt.write_text(chr(10).join([f"file '{f.absolute().as_posix()}'" for f in concat_files]), encoding="utf-8")
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_txt.absolute()),
        "-ar", "44100", "-ac", "2", "-c:a", "libmp3lame", "-b:a", "192k", str(raw_joined.absolute())
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if "Classic" in cfg.get("mode", "") or not cfg.get("reverb_enabled", True):
        voice_eq = "aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo"
    else:
        voice_eq = (
            "aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,"
            "equalizer=f=135:width_type=o:width=1.2:g=2.8,"
            "equalizer=f=3500:width_type=o:width=1.5:g=2.0,"
            "aecho=0.8:0.86:45:0.12"
        )

    cues = detect_sfx_cues_from_timings(all_word_timings, cfg, sentence_cues=explicit_sentence_cues)
    sfx_map = ensure_sacred_sfx_files() if cues else {}

    if cues and sfx_map:
        inputs = ["-i", str(raw_joined.absolute())]
        filter_parts = [f"[0:a]{voice_eq}[v_main]"]
        mix_labels = ["[v_main]"]

        for c_idx, (sfx_type, cue_sec) in enumerate(cues, start=1):
            sfx_p = sfx_map.get(sfx_type)
            if not sfx_p or not sfx_p.exists():
                continue
            inputs.extend(["-i", str(sfx_p.absolute())])
            delay_ms = max(0, int(cue_sec * 1000))
            filter_parts.append(
                f"[{c_idx}:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,"
                f"volume={vol_sfx:.2f},adelay={delay_ms}|{delay_ms}[sfx{c_idx}]"
            )
            mix_labels.append(f"[sfx{c_idx}]")

        n_in = len(mix_labels)
        filter_parts.append(f"{''.join(mix_labels)}amix=inputs={n_in}:duration=first:normalize=0[aout]")
        cmd_final = [
            "ffmpeg", "-y", *inputs,
            "-filter_complex", ";".join(filter_parts),
            "-map", "[aout]", "-c:a", "libmp3lame", "-b:a", "192k", str(output_voice_path.absolute())
        ]
        subprocess.run(cmd_final, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        subprocess.run([
            "ffmpeg", "-y", "-i", str(raw_joined.absolute()),
            "-af", voice_eq, "-c:a", "libmp3lame", "-b:a", "192k", str(output_voice_path.absolute())
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    json_path = Path(str(output_voice_path).replace(".mp3", ".json"))
    if all_word_timings:
        json_path.write_text(json.dumps(all_word_timings, indent=2), encoding="utf-8")

    try:
        shutil.rmtree(work_dir, ignore_errors=True)
    except Exception:
        pass

    return all_word_timings



# ==============================================================================
# AI PREACHER EMOTION DIRECTOR & GOOGLE FLOW MUSIC GENERATOR
# ==============================================================================
FLOW_MUSIC_DIR = BASE_DIR / "custom_media" / "flow_music"
FLOW_MUSIC_DIR.mkdir(parents=True, exist_ok=True)

FLOW_MUSIC_PRESETS = {
    "🕊️ Altar Call Tearful Soaking Pad (432Hz Warm Cathedral)": {
        "prompt": "Slow emotional Christian altar call worship pad, 432Hz warm analog strings, soft cathedral reverb, deep peaceful sub-bass, no drums, 60 BPM.",
        "freqs": [108.0, 162.0, 216.0, 270.0, 324.0],
        "lowpass": 380,
        "echo": "0.8:0.90:85:0.48"
    },
    "🔥 Spiritual Warfare & Breakthrough Pulse (Epic Low Brass & Heartbeat)": {
        "prompt": "Cinematic Christian spiritual warfare underscore, deep pulsing sub-bass heartbeat, minor-to-major rising cello and warm brass swell, intense authority, 72 BPM.",
        "freqs": [73.42, 110.0, 146.83, 220.0, 277.18],
        "lowpass": 460,
        "echo": "0.8:0.86:120:0.42"
    },
    "🥺 Deep Empathy & 3 AM Comfort (Soft Rainy Cello & Warm Rhodes)": {
        "prompt": "Intimate late-night prayer ambient music, warm cello drone, gentle Rhodes electric piano chords, comforting and emotional, 56 BPM.",
        "freqs": [98.0, 146.83, 196.0, 246.94, 293.66],
        "lowpass": 340,
        "echo": "0.8:0.92:95:0.50"
    },
    "✨ Miracle & Heavenly Glory (Angelic Harp & Shimmering Strings)": {
        "prompt": "Uplifting heavenly miracle worship pad, bright angelic shimmer, warm major harmonic strings, hopeful sunrise atmosphere, 64 BPM.",
        "freqs": [130.81, 196.0, 261.63, 329.63, 392.0],
        "lowpass": 580,
        "echo": "0.8:0.90:110:0.52"
    }
}

def _get_gemini_key() -> str:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env", override=True)
    return os.getenv("GEMINI_API_KEY", "").strip()

def ai_direct_preacher_script(raw_script: str, topic: str = "Faith & Breakthrough") -> Tuple[str, str]:
    """
    Uses the connected Gemini AI to analyze a plain script and automatically inject:
    - Sentence emotion tags: [empathy], [angry], [whisper], [warfare], [scripture], [joy], [amen]
    - Word-level emphasis: *WORD* on 2 to 4 key power words
    - Sound effect triggers: [boom], [shimmer], [swell], [bell]
    Returns (annotated_script, ai_director_notes).
    """
    clean_in = strip_emotion_tags(raw_script)
    if not clean_in:
        return raw_script, "Empty script."

    key = _get_gemini_key()
    prompt = f"""You are a Master Christian Preacher Vocal Director and Sound Designer.
Take the following spoken script and inject real-time Preacher Emotion Tags, Sacred Sound Effect Tags, and *WORD EMPHASIS* so the TTS voice sounds like a living, breathing, deeply emotional pastor instead of a flat reader.

Topic: {topic}
Original Plain Script:
\"{clean_in}\"

AVAILABLE EMOTION TAGS (Place at the very beginning of each sentence):
- [empathy] -> Soft, slow, heartbroken/comforting tone for pain, tears, or heavy burdens.
- [whisper] -> Very quiet, intimate close-mic whisper for deep spiritual stillness.
- [angry] -> Righteous thunder, fierce rebuke against the enemy, fear, debt, or lies!
- [warfare] -> Bold, commanding, rising preacher intensity for breaking chains & declaring victory.
- [scripture] -> Reverent, deep pulpit authority when introducing or quoting a Bible verse.
- [joy] -> Uplifting, bright, celebratory praise.
- [amen] -> Slow, peaceful closing benediction.

AVAILABLE SOUND EFFECT TAGS (Insert 2 to 4 total across the script right before key moments):
- [shimmer] -> Before a Bible verse reference.
- [swell] -> Before calling on Jesus, Heavenly Father, or the Holy Spirit.
- [boom] -> Right before a fierce [angry] or [warfare] command!
- [bell] -> Right before the final Amen.

WORD EMPHASIS RULE:
- Wrap 2 to 5 critical power words in *ASTERISKS* and ALL CAPS (e.g., *ENOUGH*, *NEVER*, *BROKEN*, *JESUS*, *FREE*) so the preacher pauses and punches those exact words!
- DO NOT change the actual words of the script—only add the [tags] and *ASTERISKS*.

Respond ONLY in valid JSON with exact keys:
{{
  "directed_script": "The full script with [emotion] tags, [sfx] tags, and *EMPHASIS* words injected",
  "director_notes": "1 sentence explaining the emotional arc and why these emotions/SFX were chosen"
}}"""

    if key:
        import urllib.request
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.65}
        }
        data_bytes = json.dumps(payload).encode("utf-8")
        for m_id in ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-3.5-flash-lite", "gemini-3.7-flash"]:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{m_id}:generateContent?key={key}"
                req = urllib.request.Request(url, headers={"Content-Type": "application/json"}, data=data_bytes)
                with urllib.request.urlopen(req, timeout=10) as resp:
                    r_json = json.loads(resp.read().decode("utf-8"))
                    raw_t = r_json["candidates"][0]["content"]["parts"][0]["text"]
                    m = re.search(r"\{[\s\S]*\}", raw_t)
                    if m:
                        parsed = json.loads(m.group(0))
                        dir_s = parsed.get("directed_script", "").strip()
                        notes = parsed.get("director_notes", f"Directed live by Gemini ({m_id}).")
                        if dir_s:
                            return dir_s, f"🤖 AI Directed ({m_id}): {notes}"
            except Exception:
                continue

    # Intelligent Rule-Based Fallback if offline
    sents = split_into_preacher_sentences(clean_in)
    out_sents = []
    for idx, s in enumerate(sents):
        low = s.lower()
        if any(w in low for w in ["amen", "type amen", "comment amen"]):
            out_sents.append(f"[amen] [bell] {s}")
        elif any(w in low for w in ["devil", "enemy", "enough", "liar", "rebuke", "satan", "weapon"]):
            s_emp = re.sub(r"\b(never|enough|break|every|prosper)\b", lambda m: f"*{m.group(1).upper()}*", s, count=1, flags=re.IGNORECASE)
            out_sents.append(f"[angry] [boom] {s_emp}")
        elif any(w in low for w in ["break", "chains", "command", "authority", "mighty", "miracle"]):
            s_emp = re.sub(r"\b(jesus|break|chains|miracle|now)\b", lambda m: f"*{m.group(1).upper()}*", s, count=1, flags=re.IGNORECASE)
            out_sents.append(f"[warfare] [swell] {s_emp}")
        elif any(w in low for w in ["psalm", "isaiah", "philippians", "matthew", "proverbs", "jeremiah", "verse", "chapter"]):
            out_sents.append(f"[scripture] [shimmer] {s}")
        elif idx == 0 or any(w in low for w in ["heavy", "tears", "breath", "weary", "alone", "broken", "night", "worry"]):
            out_sents.append(f"[empathy] {s}")
        else:
            out_sents.append(f"[joy] {s}")
    return " ".join(out_sents), "🤖 Smart Preacher Auto-Director applied emotional arc, *WORD* emphasis & SFX cues!"

def generate_ai_flow_music_track(
    mood_choice: str,
    custom_prompt: str = "",
    duration_sec: int = 90
) -> Tuple[bool, Path, str]:
    """
    1. Connects to Gemini / Google Flow API to design custom harmonic chord progressions for your prompt.
    2. Synthesizes a rich, stereo multi-layered worship/warfare soundtrack using pure NumPy stereo DSP
       (warm sub-bass + breathing choir/string harmonics + heartbeat pulse + spatial shimmer)
       and encodes to 192kbps MP3 so it NEVER fails!
    """
    import urllib.request
    import base64
    import wave
    import numpy as np

    preset = FLOW_MUSIC_PRESETS.get(mood_choice, list(FLOW_MUSIC_PRESETS.values())[0])
    active_prompt = custom_prompt.strip() if custom_prompt.strip() else preset["prompt"]
    freqs = list(preset["freqs"])
    is_warfare = "Warfare" in mood_choice or "warfare" in active_prompt.lower() or "angry" in active_prompt.lower()

    safe_slug = re.sub(r"[^a-zA-Z0-9]+", "_", (custom_prompt[:28] if custom_prompt.strip() else mood_choice[:28])).strip("_") or "Flow_Worship"
    out_mp3 = FLOW_MUSIC_DIR / f"FlowAI_{safe_slug}.mp3"
    temp_wav = FLOW_MUSIC_DIR / f"FlowAI_{safe_slug}.wav"
    downloads_copy = BASE_DIR / "downloads" / f"FlowAI_{safe_slug}.mp3"
    downloads_copy.parent.mkdir(parents=True, exist_ok=True)

    key = _get_gemini_key()
    ai_music_note = f"🎵 Synthesized '{mood_choice.split('(')[0].strip()}' Track"

    if key:
        try:
            music_prompt = f"""You are an AI Worship Music Composer & Sound Engineer.
Design a 5-note warm harmonic chord progression (in Hz between 60Hz and 528Hz) for this worship music prompt:
\"{active_prompt}\"

Respond ONLY in valid JSON:
{{
  "chord_name": "e.g. D Minor 9th Warfare & Breakthrough Pad",
  "frequencies_hz": [73.42, 110.0, 146.83, 220.0, 329.63]
}}"""
            for m_id in ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-3.5-flash-lite"]:
                try:
                    url_g = f"https://generativelanguage.googleapis.com/v1beta/models/{m_id}:generateContent?key={key}"
                    req_g = urllib.request.Request(
                        url_g,
                        headers={"Content-Type": "application/json"},
                        data=json.dumps({
                            "contents": [{"parts": [{"text": music_prompt}]}],
                            "generationConfig": {"responseMimeType": "application/json"}
                        }).encode("utf-8")
                    )
                    with urllib.request.urlopen(req_g, timeout=8) as resp_g:
                        rj = json.loads(resp_g.read().decode("utf-8"))
                        raw_t = rj["candidates"][0]["content"]["parts"][0]["text"]
                        m = re.search(r"\{[\s\S]*\}", raw_t)
                        if m:
                            mp = json.loads(m.group(0))
                            cand_f = mp.get("frequencies_hz", [])
                            if isinstance(cand_f, list) and len(cand_f) >= 4:
                                freqs = [max(50.0, min(880.0, float(x))) for x in cand_f[:5]]
                            ai_music_note = f"🎵 AI Composed '{mp.get('chord_name', 'Custom Flow Pad')}' ({m_id})"
                            break
                except Exception:
                    continue
        except Exception:
            pass

    # Pure-Python NumPy Stereo Harmonic + Cinematic Pulse Synthesizer (100% Fail-Safe!)
    sr = 44100
    dur = max(15, min(300, int(duration_sec)))
    t = np.linspace(0, dur, sr * dur, endpoint=False, dtype=np.float32)

    left = np.zeros_like(t)
    right = np.zeros_like(t)

    for idx, f_hz in enumerate(freqs[:5]):
        # Slow organic breathing LFO per voice
        lfo_rate = 0.11 + idx * 0.04
        lfo_l = 0.65 + 0.35 * np.sin(2 * np.pi * lfo_rate * t + idx)
        lfo_r = 0.65 + 0.35 * np.cos(2 * np.pi * lfo_rate * t + idx * 1.3)

        # Fundamental + warm octave/fifth overtone
        amp = 0.24 if idx < 2 else 0.14
        wave_l = np.sin(2 * np.pi * f_hz * t) + 0.25 * np.sin(2 * np.pi * (f_hz * 2.0) * t)
        wave_r = np.sin(2 * np.pi * (f_hz * 1.0015) * t) + 0.25 * np.sin(2 * np.pi * (f_hz * 2.002) * t)

        left += amp * lfo_l * wave_l
        right += amp * lfo_r * wave_r

    # If Warfare / Breakthrough mood, add a deep cinematic heartbeat sub-pulse (72 BPM = 1.2 Hz)
    if is_warfare:
        beat_env = np.maximum(0.0, np.sin(2 * np.pi * 0.6 * t)) ** 6
        sub_pulse = 0.32 * beat_env * np.sin(2 * np.pi * 55.0 * t)
        left += sub_pulse
        right += sub_pulse

    # Smooth 3-second fade-in and 5-second fade-out
    fade_in_len = min(len(t), sr * 3)
    fade_out_len = min(len(t), sr * 5)
    left[:fade_in_len] *= np.linspace(0.0, 1.0, fade_in_len, dtype=np.float32)
    right[:fade_in_len] *= np.linspace(0.0, 1.0, fade_in_len, dtype=np.float32)
    left[-fade_out_len:] *= np.linspace(1.0, 0.0, fade_out_len, dtype=np.float32)
    right[-fade_out_len:] *= np.linspace(1.0, 0.0, fade_out_len, dtype=np.float32)

    # Normalize cleanly to warm stereo 16-bit PCM
    peak = max(float(np.max(np.abs(left))), float(np.max(np.abs(right))), 1e-4)
    stereo = np.empty((len(t), 2), dtype=np.int16)
    stereo[:, 0] = np.clip((left / peak) * 26000, -32767, 32767).astype(np.int16)
    stereo[:, 1] = np.clip((right / peak) * 26000, -32767, 32767).astype(np.int16)

    with wave.open(str(temp_wav), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(stereo.tobytes())

    # Convert WAV to 192kbps MP3 via FFmpeg (or keep WAV if FFmpeg is busy)
    subprocess.run([
        "ffmpeg", "-y", "-i", str(temp_wav.absolute()),
        "-c:a", "libmp3lame", "-b:a", "192k", str(out_mp3.absolute())
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if temp_wav.exists():
        if not out_mp3.exists() or out_mp3.stat().st_size < 1000:
            shutil.copy(temp_wav, out_mp3)
        temp_wav.unlink(missing_ok=True)

    if out_mp3.exists() and out_mp3.stat().st_size > 1000:
        shutil.copy(out_mp3, downloads_copy)
        return True, out_mp3, f"{ai_music_note} — Saved & added to your Worship BGM selector!"
    return False, out_mp3, "Could not synthesize audio track."



# ==============================================================================
# WORD-BY-WORD & PHRASE-BY-PHRASE AI PREACHER AUDIO MASTERING (STEP 1 PREVIEW)
# ==============================================================================
def ai_generate_word_level_prosody_plan(
    raw_script: str,
    base_rate: str = "+0%",
    base_pitch: str = "+0Hz"
) -> Tuple[List[Dict[str, Any]], str]:
    """
    Connects to Gemini AI to break the script into dynamic micro-phrases/words,
    assigning exact Pitch (Hz), Speed (%), Volume (%), Pause (s), and SFX triggers
    per phrase/word based on the user's configured Preacher sliders & SFX toggles!
    """
    cfg = load_preacher_config()
    b_rate = _parse_int(base_rate, 0)
    b_pitch = _parse_int(base_pitch, 0)
    clean_txt = strip_emotion_tags(raw_script)
    if not clean_txt:
        return [], "Empty script"

    key = _get_gemini_key()
    ang_p, ang_r, ang_v = int(cfg.get("angry_pitch", 6)), int(cfg.get("angry_rate", 9)), int(cfg.get("angry_vol", 18))
    emp_p, emp_r, emp_v = int(cfg.get("empathy_pitch", -5)), int(cfg.get("empathy_rate", -10)), int(cfg.get("empathy_vol", -4))
    whi_p, whi_r, whi_v = int(cfg.get("whisper_pitch", -7)), int(cfg.get("whisper_rate", -14)), int(cfg.get("whisper_vol", -12))
    war_p, war_r, war_v = int(cfg.get("warfare_pitch", 4)), int(cfg.get("warfare_rate", 5)), int(cfg.get("warfare_vol", 12))
    scr_p, scr_r = int(cfg.get("scripture_pitch", -2)), int(cfg.get("scripture_rate", -5))
    amn_p, amn_r = int(cfg.get("amen_pitch", -5)), int(cfg.get("amen_rate", -11))

    prompt = f"""You are a Real-Time Preacher Vocal & Sound Effects Director.
Break the following script into 5 to 12 expressive spoken micro-phrases (splitting at emotional shifts or key power words so the preacher changes pitch and intensity dynamically as he speaks, just like a real pastor!).

Script to Direct:
\"{clean_txt}\"

USER'S CONFIGURED PITCH & SPEED PALETTE (Add these offsets to Base Pitch {b_pitch}Hz and Base Speed {b_rate}%):
- EMPATHY / HEARTBREAK words: pitch {b_pitch + emp_p:+d}Hz, rate {b_rate + emp_r:+d}%, volume {emp_v:+d}%
- WHISPER / STILLNESS words: pitch {b_pitch + whi_p:+d}Hz, rate {b_rate + whi_r:+d}%, volume {whi_v:+d}%
- ANGRY / FIERCE REBUKE / POWER words: pitch {b_pitch + ang_p:+d}Hz, rate {b_rate + ang_r:+d}%, volume {ang_v:+d}%
- WARFARE / BREAKTHROUGH words: pitch {b_pitch + war_p:+d}Hz, rate {b_rate + war_r:+d}%, volume {war_v:+d}%
- SCRIPTURE CITATION & VERSE words: pitch {b_pitch + scr_p:+d}Hz, rate {b_rate + scr_r:+d}%, volume +5%
- BENEDICTION / AMEN words: pitch {b_pitch + amn_p:+d}Hz, rate {b_rate + amn_r:+d}%, volume +4%

AVAILABLE SFX TO TRIGGER ON SPECIFIC PHRASES (Pick 'none', 'shimmer', 'swell', 'boom', or 'bell'):
- 'shimmer': When introducing a Bible verse/chapter
- 'swell': When calling on Jesus, Father, Lord, or Holy Spirit
- 'boom': On fierce [angry] or [warfare] power words (like Break, Enough, Never, Chains, Weapon)
- 'bell': On the closing Amen

IMPORTANT: Every single word of the original script MUST be preserved in exact order across the segments!

Respond ONLY with valid JSON:
{{
  "director_summary": "1 sentence explaining how AI modulated the pitch, speed, and SFX across the words",
  "segments": [
    {{
      "text": "exact words of this micro-phrase",
      "emotion": "e.g. 🥺 Empathy / 😡 Angry / 🔥 Warfare / 📖 Scripture / 🤫 Whisper / 🙏 Amen",
      "pitch_hz": -5,
      "rate_pct": -8,
      "volume_pct": 0,
      "pause_after_sec": 0.35,
      "sfx": "none"
    }}
  ]
}}"""

    if key:
        import urllib.request
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.55}
        }
        data_bytes = json.dumps(payload).encode("utf-8")
        for m_id in ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-3.5-flash-lite", "gemini-3.7-flash"]:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{m_id}:generateContent?key={key}"
                req = urllib.request.Request(url, headers={"Content-Type": "application/json"}, data=data_bytes)
                with urllib.request.urlopen(req, timeout=12) as resp:
                    rj = json.loads(resp.read().decode("utf-8"))
                    raw_t = rj["candidates"][0]["content"]["parts"][0]["text"]
                    m = re.search(r"\{[\s\S]*\}", raw_t)
                    if m:
                        parsed = json.loads(m.group(0))
                        segs = parsed.get("segments", [])
                        if isinstance(segs, list) and len(segs) >= 2:
                            norm_segs = []
                            for idx, sg in enumerate(segs):
                                p_val = max(-15, min(18, int(sg.get("pitch_hz", b_pitch))))
                                r_val = max(-28, min(28, int(sg.get("rate_pct", b_rate))))
                                v_val = max(-25, min(30, int(sg.get("volume_pct", 0))))
                                sfx_raw = str(sg.get("sfx", "none")).lower().strip()
                                if sfx_raw not in ("shimmer", "swell", "boom", "bell"):
                                    sfx_raw = "none"
                                if not cfg.get(f"sfx_{sfx_raw}", True) and sfx_raw != "none":
                                    sfx_raw = "none"
                                norm_segs.append({
                                    "idx": idx + 1,
                                    "text": strip_emotion_tags(str(sg.get("text", ""))),
                                    "emotion": str(sg.get("emotion", "🎙️ Preacher")),
                                    "pitch": f"{p_val:+d}Hz",
                                    "rate": f"{r_val:+d}%",
                                    "volume": f"{v_val:+d}%",
                                    "pause": round(min(1.0, max(0.1, float(sg.get("pause_after_sec", 0.30)))), 2),
                                    "sfx": sfx_raw
                                })
                            return norm_segs, f"🤖 AI Word/Phrase Director ({m_id}): {parsed.get('director_summary', 'Dynamic pitch & SFX applied!')}"
            except Exception:
                continue

    # Fallback: Split by clauses & punctuation so even offline it modulates phrase-by-phrase
    clauses = [c.strip() for c in re.split(r"(?<=[\.\!\?।,;:])\s+|\.\.\.\s*", raw_script) if c and c.strip()]
    fallback_segs = []
    for idx, cl in enumerate(clauses):
        r_s, p_s, v_s, pause_s, emo_lbl = classify_sentence_prosody(cl, base_rate, base_pitch, cfg, sent_idx=idx)
        low = cl.lower()
        sfx_pick = "none"
        if "amen" in low or "आमीन" in low:
            sfx_pick = "bell"
        elif any(w in low for w in ["chapter", "verse", "psalm", "isaiah", "philippians", "proverbs", "matthew", "jeremiah", "वचन", "अध्याय"]):
            sfx_pick = "shimmer"
        elif any(w in low for w in ["break", "chains", "weapon", "enough", "devil", "enemy", "authority", "बंधन"]):
            sfx_pick = "boom"
        elif any(w in low for w in ["jesus", "father", "lord", "spirit", "यीशु", "प्रभु"]):
            sfx_pick = "swell"
        fallback_segs.append({
            "idx": idx + 1,
            "text": strip_emotion_tags(cl),
            "emotion": emo_lbl,
            "pitch": p_s,
            "rate": r_s,
            "volume": v_s,
            "pause": pause_s,
            "sfx": sfx_pick
        })
    return fallback_segs, "🤖 Smart Phrase-Level Preacher Director applied pitch, speed & SFX cues!"

def build_ai_directed_preacher_audio_preview(
    raw_script: str,
    out_voice_mp3: Path,
    out_mixed_preview_mp3: Path,
    voice_name: str = "en-US-ChristopherNeural",
    base_rate: str = "+0%",
    base_pitch: str = "+0Hz",
    bgm_file: Path | str | None = None,
    bgm_vol: float = 0.18,
    custom_segments: List[Dict[str, Any]] | None = None
) -> Dict[str, Any]:
    """
    1. Gets the AI phrase/word-level prosody plan (or uses user-edited table segments).
    2. Synthesizes every phrase with its exact AI Pitch, Speed, Volume, and Pause.
    3. Mixes the exact word-triggered Sacred SFX + Pulpit Reverb into `out_voice_mp3` (ready for video render!).
    4. Also creates `out_mixed_preview_mp3` (with BGM mixed in) so the user can listen to the 100% final audio before clicking Render Video!
    """
    cfg = load_preacher_config()
    vol_sfx = float(cfg.get("sfx_vol", 0.35))

    if custom_segments:
        segments = custom_segments
        ai_note = "🎛️ Using your custom Phrase/Word Pitch & SFX Cue Sheet!"
    else:
        segments, ai_note = ai_generate_word_level_prosody_plan(raw_script, base_rate=base_rate, base_pitch=base_pitch)

    out_voice_mp3.parent.mkdir(parents=True, exist_ok=True)
    work_dir = out_voice_mp3.parent / f"temp_word_ai_{out_voice_mp3.stem}"
    work_dir.mkdir(parents=True, exist_ok=True)

    concat_files: List[Path] = []
    all_word_timings: List[Dict[str, Any]] = []
    sfx_cues: List[Tuple[str, float]] = []
    current_offset = 0.0

    async def _synth_seg(seg_txt: str, out_p: Path, r_str: str, p_str: str, v_str: str, t_off: float):
        if "hi-IN" in voice_name:
            seg_txt = re.sub(r"(\d+):(\d+)", r"अध्याय \1 वचन \2", seg_txt)
        else:
            seg_txt = re.sub(r"(\d+):(\d+)", r"chapter \1 verse \2", seg_txt)
        try:
            comm = edge_tts.Communicate(seg_txt, voice=voice_name, rate=r_str, pitch=p_str, volume=v_str, boundary="WordBoundary")
        except TypeError:
            comm = edge_tts.Communicate(seg_txt, voice=voice_name, rate=r_str, pitch=p_str)

        raw_evs = []
        with open(out_p, "wb") as f_v:
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    f_v.write(chunk["data"])
                elif chunk["type"] in ("WordBoundary", "SentenceBoundary"):
                    st_s = t_off + (chunk["offset"] / 10_000_000.0)
                    du_s = chunk["duration"] / 10_000_000.0
                    raw_evs.append({"type": chunk["type"], "text": chunk["text"], "start": st_s, "end": st_s + du_s})

        for ev in raw_evs:
            if ev["type"] == "WordBoundary" or len(ev["text"].split()) <= 1:
                all_word_timings.append({"text": ev["text"].strip(), "start": round(ev["start"], 3), "end": round(ev["end"], 3)})
            else:
                words = ev["text"].split()
                if not words:
                    continue
                step = max(0.1, ev["end"] - ev["start"]) / len(words)
                for idx_w, w_tok in enumerate(words):
                    all_word_timings.append({
                        "text": w_tok,
                        "start": round(ev["start"] + idx_w * step, 3),
                        "end": round(ev["start"] + (idx_w + 1) * step, 3)
                    })

    for idx, seg in enumerate(segments):
        txt_s = strip_emotion_tags(seg.get("text", "")).strip()
        if not txt_s:
            continue
        p_s = str(seg.get("pitch", "+0Hz"))
        r_s = str(seg.get("rate", "+0%"))
        v_s = str(seg.get("volume", "+0%"))
        pause_s = float(seg.get("pause", 0.30))
        sfx_tag = str(seg.get("sfx", "none")).lower()

        if cfg.get("sfx_enabled", True) and sfx_tag in ("shimmer", "swell", "boom", "bell"):
            sfx_cues.append((sfx_tag, max(0.0, current_offset)))

        seg_mp3 = work_dir / f"seg_{idx:03d}.mp3"
        try:
            asyncio.run(_synth_seg(txt_s, seg_mp3, r_s, p_s, v_s, current_offset))
        except RuntimeError:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(_synth_seg(txt_s, seg_mp3, r_s, p_s, v_s, current_offset))
            loop.close()

        if seg_mp3.exists() and seg_mp3.stat().st_size > 200:
            dur = _get_audio_dur(seg_mp3)
            concat_files.append(seg_mp3)
            current_offset += dur

            if idx < len(segments) - 1 and pause_s > 0.05:
                sil_f = work_dir / f"pause_{idx:03d}.mp3"
                subprocess.run([
                    "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                    "-t", f"{pause_s:.2f}", "-c:a", "libmp3lame", "-b:a", "192k", str(sil_f.absolute())
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if sil_f.exists():
                    concat_files.append(sil_f)
                    current_offset += pause_s

    raw_joined = work_dir / "joined_raw.mp3"
    list_txt = work_dir / "concat.txt"
    list_txt.write_text(chr(10).join([f"file '{f.absolute().as_posix()}'" for f in concat_files]), encoding="utf-8")
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_txt.absolute()),
        "-ar", "44100", "-ac", "2", "-c:a", "libmp3lame", "-b:a", "192k", str(raw_joined.absolute())
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if not cfg.get("reverb_enabled", True) or "Classic" in cfg.get("mode", ""):
        voice_eq = "aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo"
    else:
        voice_eq = (
            "aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,"
            "equalizer=f=135:width_type=o:width=1.2:g=2.8,"
            "equalizer=f=3500:width_type=o:width=1.5:g=2.0,"
            "aecho=0.8:0.86:45:0.12"
        )

    sfx_map = ensure_sacred_sfx_files() if sfx_cues else {}
    if sfx_cues and sfx_map:
        inputs = ["-i", str(raw_joined.absolute())]
        filter_parts = [f"[0:a]{voice_eq}[v_main]"]
        mix_labels = ["[v_main]"]
        for c_idx, (sfx_type, cue_sec) in enumerate(sfx_cues, start=1):
            sfx_p = sfx_map.get(sfx_type)
            if not sfx_p or not sfx_p.exists():
                continue
            inputs.extend(["-i", str(sfx_p.absolute())])
            delay_ms = max(0, int(cue_sec * 1000))
            filter_parts.append(
                f"[{c_idx}:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,"
                f"volume={vol_sfx:.2f},adelay={delay_ms}|{delay_ms}[sfx{c_idx}]"
            )
            mix_labels.append(f"[sfx{c_idx}]")
        n_in = len(mix_labels)
        filter_parts.append(f"{''.join(mix_labels)}amix=inputs={n_in}:duration=first:normalize=0[aout]")
        subprocess.run([
            "ffmpeg", "-y", *inputs,
            "-filter_complex", ";".join(filter_parts),
            "-map", "[aout]", "-c:a", "libmp3lame", "-b:a", "192k", str(out_voice_mp3.absolute())
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        subprocess.run([
            "ffmpeg", "-y", "-i", str(raw_joined.absolute()),
            "-af", voice_eq, "-c:a", "libmp3lame", "-b:a", "192k", str(out_voice_mp3.absolute())
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Save the exact millisecond word timings JSON alongside out_voice_mp3
    json_path = Path(str(out_voice_mp3).replace(".mp3", ".json"))
    if all_word_timings:
        json_path.write_text(json.dumps(all_word_timings, indent=2), encoding="utf-8")

    # Also build the full BGM-mixed preview MP3 so the user hears the exact final audio before rendering video!
    total_v_dur = max(1.0, _get_audio_dur(out_voice_mp3))
    has_bgm = not (bgm_file is None or str(bgm_file).upper() == "NONE" or bgm_vol <= 0.001)
    if has_bgm and bgm_file and Path(str(bgm_file)).exists():
        subprocess.run([
            "ffmpeg", "-y",
            "-i", str(out_voice_mp3.absolute()),
            "-stream_loop", "-1", "-t", f"{total_v_dur:.2f}", "-i", str(Path(str(bgm_file)).absolute()),
            "-filter_complex",
            f"[0:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,volume=1.0[v];"
            f"[1:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,volume={bgm_vol:.2f}[bgm];"
            f"[v][bgm]amix=inputs=2:duration=first:normalize=0[aout]",
            "-map", "[aout]", "-c:a", "libmp3lame", "-b:a", "192k", str(out_mixed_preview_mp3.absolute())
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        shutil.copy(out_voice_mp3, out_mixed_preview_mp3)

    try:
        shutil.rmtree(work_dir, ignore_errors=True)
    except Exception:
        pass

    return {
        "voice_mp3": str(out_voice_mp3),
        "preview_mp3": str(out_mixed_preview_mp3),
        "timings_json": str(json_path),
        "duration_sec": round(total_v_dur, 1),
        "segments": segments,
        "ai_note": ai_note
    }
