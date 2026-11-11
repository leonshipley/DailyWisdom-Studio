import description_engine
import os
import re
import json
import time
import shutil
import asyncio
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Any, Tuple
from dotenv import load_dotenv
import edge_tts

import main as backend
import flow_story_engine as fse
import sticker_studio

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

ARCHETYPE_STATE_FILE = BASE_DIR / "last_archetype.json"
AFFILIATE_CONFIG_FILE = BASE_DIR / "affiliate_links.json"

ARCHETYPES: Dict[str, str] = {
    "Auto-Rotate (Never Repeat Last Archetype)": "AUTO",
    "Archetype A: Biblical Backstory (Historical Moment)": (
        "ARCHETYPE A (Biblical Backstory): Open with the raw historical moment a biblical figure wrote the verse "
        "(e.g., David in the cave of Adullam, Paul in chains, Hezekiah weeping at the wall), explain the verse, and close with a short prayer."
    ),
    "Archetype B: Original Word Insight (Hebrew/Greek Meaning)": (
        "ARCHETYPE B (Original Word Insight): Reveal the deeper Hebrew or Greek meaning of a key word in the scripture "
        "(e.g., Shalom, Hesed, Merimnao) providing educational commentary, then apply it to the viewer's life in prayer."
    ),
    "Archetype C: 3 AM Heart-to-Heart (Empathetic Scenario)": (
        "ARCHETYPE C (3 AM Heart-to-Heart): Start with an empathetic, specific real-life emotional scenario "
        "(e.g., staring at the ceiling at 2 AM worried about tomorrow), anchor it in Scripture, and pray for peace."
    ),
    "Archetype D: Immediate First-Person Prayer (Starts at 0:00)": (
        "ARCHETYPE D (Immediate First-Person Prayer): Start at 0:00 directly inside an intimate, poetic prayer woven with Scripture, "
        "speaking in first-person ('Lord, right now my mind is racing...')."
    ),
    "Archetype E: Perspective Shift (Reframe + 1 Action Step)": (
        "ARCHETYPE E (Perspective Shift): Open with a bold spiritual truth that reframes a hardship, share the Bible verse, "
        "and give 1 practical spiritual action step for the day."
    ),
    "Archetype F: Psalm of Protection & Pastoral Blessing": (
        "ARCHETYPE F (Psalm of Protection/Blessing): Spoken as a rhythmic, comforting pastoral blessing over the viewer's family, home, and mind."
    ),
}

VOICE_TONE_MAP: Dict[str, Dict[str, str]] = {
    "warm_mentor_male": {"voice": "en-US-AndrewNeural", "label": "Andrew (Warm Mentor Male)"},
    "gentle_comfort_female": {"voice": "en-US-AvaNeural", "label": "Ava (Gentle Comfort Female)"},
    "deep_pastoral_male": {"voice": "en-US-ChristopherNeural", "label": "Christopher (Deep Pastoral Male)"},
}

BANNED_OPENINGS = [
    "dealing with", "if you are struggling with", "if you're struggling with",
    "hear god's promise", "hear gods promise", "stop scrolling"
]

BANNED_NON_CHRISTIAN_TAGS = {
    "#dua", "#islamicreminder", "#allah", "#quran", "#manifestation",
    "#lawofattraction", "#universe", "#karma", "#zodiac", "#tarot"
}

DEFAULT_AFFILIATES = [
    {"heading": "📖 Featured Study Bible (ESV):", "url": "https://amzn.to/your-study-bible-link"},
    {"heading": "🙏 Daily Prayer & Gratitude Journal:", "url": "https://amzn.to/your-prayer-journal-link"},
    {"heading": "🕊️ Christian Devotional for Peace:", "url": "https://amzn.to/your-devotional-link"},
]

def load_affiliate_links() -> List[Dict[str, str]]:
    if AFFILIATE_CONFIG_FILE.exists():
        try:
            data = json.loads(AFFILIATE_CONFIG_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list) and len(data) == 3:
                return data
        except Exception:
            pass
    return DEFAULT_AFFILIATES

def save_affiliate_links(links: List[Dict[str, str]]):
    AFFILIATE_CONFIG_FILE.write_text(json.dumps(links, indent=2), encoding="utf-8")

def pick_next_archetype(selected_key: str) -> Tuple[str, str]:
    keys = [k for k in ARCHETYPES.keys() if k != "Auto-Rotate (Never Repeat Last Archetype)"]
    if selected_key in ARCHETYPES and ARCHETYPES[selected_key] != "AUTO":
        ARCHETYPE_STATE_FILE.write_text(json.dumps({"last": selected_key}), encoding="utf-8")
        return selected_key, ARCHETYPES[selected_key]

    last_used = ""
    if ARCHETYPE_STATE_FILE.exists():
        try:
            last_used = json.loads(ARCHETYPE_STATE_FILE.read_text(encoding="utf-8")).get("last", "")
        except Exception:
            pass

    idx = (keys.index(last_used) + 1) % len(keys) if last_used in keys else 0
    chosen_k = keys[idx]
    ARCHETYPE_STATE_FILE.write_text(json.dumps({"last": chosen_k}), encoding="utf-8")
    return chosen_k, ARCHETYPES[chosen_k]

def _sanitize_opening(text: str) -> str:
    t = text.strip()
    low = t.lower()
    for banned in BANNED_OPENINGS:
        if low.startswith(banned):
            # Strip the banned opening clause up to the first period or comma
            parts = re.split(r"[.,!?]", t, maxsplit=1)
            if len(parts) > 1 and len(parts[1].strip()) > 10:
                return parts[1].strip()
    return t

def _clean_christian_hashtags(desc: str) -> str:
    # Remove any [HASHTAGS] or [/HASHTAGS] or HTML comments
    cleaned = re.sub(r"\[/?HASHTAGS\]", "", desc)
    cleaned = re.sub(r"<!--[\s\S]*?-->", "", cleaned)
    for bad_tag in BANNED_NON_CHRISTIAN_TAGS:
        cleaned = re.sub(re.escape(bad_tag), "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()

def generate_grace_3scene_script(
    topic: str,
    archetype_choice: str = "Auto-Rotate (Never Repeat Last Archetype)",
    target_pacing: str = "Viral 18-24s (High Retention)"
) -> Dict[str, Any]:
    """
    Generates a deeply authentic, non-repetitive 28-to-38s 3-Scene YouTube Short script
    following the exact 'Grace of the Lord' (@GraceAndDailyPrayer) specification.
    """
    arch_name, arch_instruction = pick_next_archetype(archetype_choice)
    aff_links = load_affiliate_links()
    aff_block = "\n\n".join([f"{item['heading']}\n{item['url']}" for item in aff_links])

    sys_prompt = """You are the Creative Director and Theological Scriptwriter for "Grace of the Lord" (@GraceAndDailyPrayer), a Christian devotional and prayer channel.
Your goal is to generate deeply authentic, non-repetitive, high-retention 28-to-38-second YouTube Shorts scripts that pass YouTube's human review for Original & Authentic Content.

STRICT ANTI-REPETITION RULES (CRITICAL FOR MONETIZATION):
1. BANNED PHRASES: NEVER start a script with "Dealing with...", "If you are struggling with...", "Hear God's promise", or "Stop scrolling".
2. ARCHETYPE TO USE FOR THIS SCRIPT:
""" + arch_instruction + """

3. COMPLIANCE & BRAND SAFETY:
- Never make literal medical cure claims or literal financial advice guarantees. Frame financial topics around "wisdom, stewardship, and freedom from money anxiety" and health topics around "spiritual comfort, strength, and peace."
- Use ONLY Christian/Biblical hashtags. NEVER include tags from other religions (no #dua, #islamicreminder, #manifestation).

4. 3-SCENE VISUAL STORYBOARD (Total spoken words across all 3 scenes: 44 to 55 words so total audio is 18 to 24 seconds (maximum Shorts retention)):
- Break the video into 3 distinct visual scenes (Scene 1: 0-10s Hook & Context, Scene 2: 10-22s Scripture & Editorial Commentary, Scene 3: 22-35s Anointed Prayer & Natural CTA) that visually progress from "The Human Struggle/Setting" -> "The Spiritual Turning Point" -> "Peace & Breakthrough".
- Do not just prompt for a static portrait of Jesus in every scene; include cinematic biblical landscapes, symbolic imagery (e.g., a warm oil lamp in a storm, olive groves at dawn, open ancient parchment scrolls), and warm biblical scenes."""

    user_prompt = f"""Topic / Life Theme: {topic}
Required Archetype: {arch_name}

Include these 3 affiliate items inside 'clean_youtube_description':
{aff_block}

Respond ONLY with a valid JSON object matching this exact schema (no markdown fences):
{{
  "archetype_used": "{arch_name}",
  "recommended_voice_tone": "deep_pastoral_male",
  "youtube_title": "Max 55 chars, high curiosity/emotion, 1 emoji and #shorts",
  "spoken_script_segments": [
    {{
      "scene_number": 1,
      "Role": "Hook & Context (0-10s)",
      "spoken_text": "13-17 words for TTS to read (short, punchy hook). Natural pauses (...) and punctuation. NO banned openings.",
      "on_screen_header": "SHORT 3-4 WORD UPPERCASE THEME",
      "image_prompt": "Detailed cinematic prompt for AI image generator, warm golden hour lighting, vertical 9:16 aspect ratio, no text in image.",
      "camera_motion": "zoom_in_slow"
    }},
    {{
      "scene_number": 2,
      "Role": "Scripture & Editorial Commentary (10-22s)",
      "spoken_text": "16-20 words for TTS reading the verse and 1-sentence core meaning.",
      "bible_verse_reference": "e.g., Psalm 34:18 (ESV)",
      "bible_verse_quote_short": "Short 1-sentence quote for on-screen display (Max 90 chars).",
      "image_prompt": "Detailed cinematic prompt showing transformation/hope, vertical 9:16, no text.",
      "camera_motion": "pan_up_slow"
    }},
    {{
      "scene_number": 3,
      "Role": "Anointed Prayer & Natural CTA (22-35s)",
      "spoken_text": "14-18 words heartfelt prayer ending in Amen + short call to action.",
      "image_prompt": "Detailed cinematic prompt of peace, sanctuary, or light breaking through clouds, vertical 9:16, no text.",
      "camera_motion": "zoom_out_slow"
    }}
  ],
  "clean_youtube_description": "Full ready-to-publish description including a 2-sentence devotional summary, the Bible verse, the 3 Amazon affiliate links with headings, the Amazon Associate disclaimer, and 8 strictly Christian hashtags at the very bottom. NO bracket tags like [HASHTAGS].",
  "pinned_comment_text": "A warm, engaging question + prayer agreement prompt to post as the pinned comment."
}}"""

    ai_json = None
    key = fse.get_active_gemini_key()
    if key:
        try:
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=key)
            for m_id in ["gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-3.7-flash", "gemini-2.5-flash", "gemini-2.0-flash"]:
                try:
                    res = client.models.generate_content(
                        model=m_id,
                        contents=f"{sys_prompt}\n\n{user_prompt}",
                        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.8)
                    )
                    if res and res.text:
                        s = res.text.find("{")
                        e = res.text.rfind("}")
                        if s != -1 and e != -1:
                            cand = json.loads(res.text[s:e+1])
                            if cand.get("spoken_script_segments") and len(cand["spoken_script_segments"]) >= 3:
                                ai_json = cand
                                break
                except Exception:
                    continue
        except Exception:
            pass

    if not ai_json:
        # Authentic Archetype Fallback so it is never repetitive even offline
        ai_json = {
            "archetype_used": arch_name,
            "recommended_voice_tone": "deep_pastoral_male",
            "youtube_title": f"When Night Feels Heavy, Remember This 🙏 #shorts",
            "spoken_script_segments": [
                {
                    "scene_number": 1,
                    "Role": "Hook & Context (0-10s)",
                    "spoken_text": f"Long before King David wore a crown, he sat alone in the cold shadows of a cave... wondering if his story was over.",
                    "on_screen_header": "LIGHT IN THE VALLEY",
                    "image_prompt": "Cinematic vertical 9:16 photograph of a flickering clay oil lamp resting on a stone table inside a quiet ancient cavern at dusk, warm golden rim light, shallow depth of field, Arri Alexa 65, no text.",
                    "camera_motion": "zoom_in_slow"
                },
                {
                    "scene_number": 2,
                    "Role": "Scripture & Editorial Commentary (10-22s)",
                    "spoken_text": "In that quiet place, he wrote Psalm 34, verse 18... The Lord is near to the brokenhearted. In Hebrew, the word 'near' means leaning in close to listen.",
                    "bible_verse_reference": "Psalm 34:18 (ESV)",
                    "bible_verse_quote_short": "The Lord is near to the brokenhearted and saves the crushed in spirit.",
                    "image_prompt": "Cinematic vertical 9:16 photograph of an ancient open Hebrew scroll beside an olive branch on weathered wood as warm morning sunbeams break through a window, golden dust motes, no text.",
                    "camera_motion": "pan_up_slow"
                },
                {
                    "scene_number": 3,
                    "Role": "Anointed Prayer & Natural CTA (22-35s)",
                    "spoken_text": "Father, wrap Your peace around every weary mind tonight and renew their strength for tomorrow. In Jesus' name, Amen. Share a prayer request below so we can pray with you.",
                    "image_prompt": "Cinematic vertical 9:16 photograph of ancient olive groves on a peaceful hillside overlooking a calm sea at sunrise, volumetric golden light rays parting soft clouds, no text.",
                    "camera_motion": "zoom_out_slow"
                }
            ],
            "clean_youtube_description": (
                f"Even in the quietest, heaviest seasons of life, God is leaning in close to hear your heart. "
                f"May this reflection on Psalm 34:18 bring deep spiritual comfort and unshakeable peace to your home tonight.\n\n"
                f"📖 Scripture: Psalm 34:18 (ESV)\n"
                f"\"The Lord is near to the brokenhearted and saves the crushed in spirit.\"\n\n"
                f"{aff_block}\n\n"
                f"Disclaimer: As an Amazon Associate, I earn from qualifying purchases at no extra cost to you.\n\n"
                f"#ChristianShorts #DailyPrayer #BibleVerse #Psalm34 #JesusChrist #FaithOverFear #GodsPeace #BiblicalWisdom"
            ),
            "pinned_comment_text": "How can our community pray for you or your family this week? Leave a word below and let's stand in faith together! 🙏"
        }

    # Sanitize openings & description
    segs = ai_json.get("spoken_script_segments", [])
    if segs:
        segs[0]["spoken_text"] = _sanitize_opening(segs[0].get("spoken_text", ""))
        for s_item in segs:
            if "bible_verse_quote_short" in s_item and s_item["bible_verse_quote_short"]:
                s_item["bible_verse_quote_short"] = s_item["bible_verse_quote_short"][:90]

    ai_json["clean_youtube_description"] = _clean_christian_hashtags(ai_json.get("clean_youtube_description", ""))
    return ai_json

def _sec_to_ass(sec: float) -> str:
    sec = max(0.0, float(sec))
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"

def render_grace_3scene_short(
    grace_pkg: Dict[str, Any],
    voice_id: str = "en-US-ChristopherNeural",
    voice_rate: str = "-4%",
    lyrics_words_per_card: int = 4,
    bgm_file: Path | None = None,
    bgm_vol: float = 0.18,
    palette_name: str = "Gold Classic",
    sticker_path: Path | None = None,
    sticker_position: str = "Bottom Dock (Centered)",
    sticker_timing: str = "Throughout Entire Video",
    progress_cb=None
) -> Tuple[bool, Path, Path]:
    """
    1. Synthesizes each of the 3 scenes' spoken_text and measures exact scene transition timestamps.
    2. Generates the 3 distinct 9:16 HD scene images in parallel from their image_prompts.
    3. Applies Scene 1 (zoom_in_slow), Scene 2 (pan_up_slow), and Scene 3 (zoom_out_slow),
       overlays the on_screen_header, bible_verse_reference, short verse quote, calm 2-line ASS lyrics,
       and renders the 28-to-38s Short + 3D Gold Thumbnail + clean metadata + pinned_comment.txt!
    """
    from types import SimpleNamespace
    import pro_design_addon as pda

    segs = grace_pkg["spoken_script_segments"]
    s1, s2, s3 = segs[0], segs[1], segs[2]

    header_str = re.sub(r"[^a-zA-Z0-9\s&\-]", "", s1.get("on_screen_header", "GRACE OF THE LORD")).upper().strip()[:28]
    verse_ref = re.sub(r"[^a-zA-Z0-9\s:\-()]", "", s2.get("bible_verse_reference", "Psalm 34:18")).strip()[:28]
    verse_short = s2.get("bible_verse_quote_short", "")[:90]

    clean_label = backend.clean_filename(f"Grace_{header_str}_{verse_ref}")
    seq_dir = backend.get_next_sequence_folder(clean_label)
    scenes_dir = seq_dir / "grace_scenes"
    scenes_dir.mkdir(parents=True, exist_ok=True)

    out_video = seq_dir / f"{clean_label}.mp4"
    out_thumb = seq_dir / f"{clean_label}_thumb.jpg"

    if progress_cb:
        progress_cb(15, "🎨 Generating 3 Distinct 9:16 HD Scene Images in Parallel (Struggle ➔ Turning Point ➔ Peace)...")

    img_paths = [scenes_dir / f"scene_{i}.jpg" for i in range(1, 4)]

    def _gen_img(idx_zero: int):
        p_txt = segs[idx_zero].get("image_prompt", "Cinematic biblical golden hour landscape, vertical 9:16")
        fse.generate_scene_image(p_txt, img_paths[idx_zero], aspect_ratio="9:16 Vertical", seed=700 + idx_zero)

    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(_gen_img, [0, 1, 2]))

    if progress_cb:
        progress_cb(45, f"🎙️ Synthesizing 3-Scene Anointed Voiceover ({voice_rate} speed)...")

    # Synthesize each scene's audio so we know exact scene durations, and capture word timings
    scene_mp3s = [scenes_dir / f"sc_{i}.mp3" for i in range(1, 4)]
    sil_mp3 = scenes_dir / "pause_0_5s.mp3"
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-t", "0.55", "-c:a", "libmp3lame", "-q:a", "2", str(sil_mp3.absolute())
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    all_word_timings = []
    scene_durs = []
    time_offset = 0.0

    for idx_s, seg in enumerate(segs):
        raw_t = seg.get("spoken_text", "").strip()
        clean_tts = re.sub(r"(\d+):(\d+)", r"chapter \1 verse \2", raw_t)
        target_mp3 = scene_mp3s[idx_s]

        async def _make_sc(txt_in: str, mp3_out: Path, t_off: float):
            comm = edge_tts.Communicate(txt_in, voice=voice_id, rate=voice_rate, boundary="WordBoundary")
            with open(mp3_out, "wb") as f_v:
                async for ch in comm.stream():
                    if ch["type"] == "audio":
                        f_v.write(ch["data"])
                    elif ch["type"] in ("WordBoundary", "SentenceBoundary"):
                        st_s = t_off + (ch["offset"] / 10_000_000.0)
                        du_s = ch["duration"] / 10_000_000.0
                        w_txt = ch["text"].strip()
                        if len(w_txt.split()) <= 1:
                            all_word_timings.append({"text": w_txt, "start": round(st_s, 3), "end": round(st_s + du_s, 3)})
                        else:
                            w_list = w_txt.split()
                            step_d = max(0.1, du_s) / len(w_list)
                            for w_i, w_tok in enumerate(w_list):
                                all_word_timings.append({
                                    "text": w_tok,
                                    "start": round(st_s + w_i * step_d, 3),
                                    "end": round(st_s + (w_i + 1) * step_d, 3)
                                })

        import preacher_audio_engine as pae
        sc_timings = pae.synthesize_preacher_voiceover(clean_tts, target_mp3, voice_name=voice_id, base_rate=voice_rate, base_pitch="+0Hz")
        for wt in sc_timings:
            all_word_timings.append({"text": wt["text"], "start": round(time_offset + wt["start"], 3), "end": round(time_offset + wt["end"], 3)})

        sc_d = max(3.0, backend.get_video_duration(target_mp3))
        scene_durs.append(sc_d + 0.55)
        time_offset += sc_d + 0.55

    # Concatenate the 3 scene voiceovers with 0.55s natural pauses
    aud_concat_txt = scenes_dir / "voice_concat.txt"
    aud_lines = []
    for smp3 in scene_mp3s:
        aud_lines.append(f"file '{smp3.absolute().as_posix()}'")
        aud_lines.append(f"file '{sil_mp3.absolute().as_posix()}'")
    aud_concat_txt.write_text("\n".join(aud_lines), encoding="utf-8")

    full_voice_mp3 = scenes_dir / "full_voice.mp3"
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(aud_concat_txt.absolute()),
        "-c:a", "libmp3lame", "-b:a", "192k", str(full_voice_mp3.absolute())
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    total_dur = max(12.0, sum(scene_durs))
    d1, d2, d3 = scene_durs[0], scene_durs[1], scene_durs[2]

    if progress_cb:
        progress_cb(70, f"🎬 Rendering 3-Scene Storyboard ({total_dur:.1f}s: zoom_in_slow ➔ pan_up_slow ➔ zoom_out_slow)...")

    # Build calm 2-line ASS subtitles
    max_w_card = max(1, int(lyrics_words_per_card))
    max_c_card = max_w_card * 7 + 4
    phrases = []
    cur_w = []
    c_st = 0.0
    for i, w_obj in enumerate(all_word_timings):
        if not cur_w:
            c_st = w_obj["start"]
        cur_w.append(w_obj["text"])
        t_str = " ".join(cur_w)
        nxt_len = len(t_str) + (len(all_word_timings[i + 1]["text"]) + 1 if i + 1 < len(all_word_timings) else 0)
        is_punct = bool(re.search(r"[.;!?]", w_obj["text"])) or (len(cur_w) >= 3 and "," in w_obj["text"])
        if nxt_len > max_c_card or len(cur_w) >= max_w_card or is_punct or i == len(all_word_timings) - 1:
            c_en = all_word_timings[i + 1]["start"] if i + 1 < len(all_word_timings) else (w_obj["end"] + 0.2)
            safe_t = re.sub(r"[^a-zA-Z0-9\s:\-',.!?]", "", t_str).strip()
            if safe_t:
                phrases.append({"text": safe_t, "start": round(c_st, 3), "end": round(c_en, 3)})
            cur_w = []

    ass_path = BASE_DIR / "temp_grace_subs.ass"
    ass_lines = [
        "[Script Info]", "ScriptType: v4.00+", "PlayResX: 1080", "PlayResY: 1920", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: SubPop,Nirmala UI,90,&H20FFFFFF,&H0000FFFF,&H90000000,&H90000000,-1,0,0,0,100,100,0,0,1,5,4,5,70,70,0,1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
    ]
    for p in phrases:
        t_s = p["text"]
        w_p = t_s.split()
        if len(t_s) > 16 and len(w_p) >= 3:
            m_w = len(w_p) // 2
            l1, l2 = " ".join(w_p[:m_w]), " ".join(w_p[m_w:])
            f_sz = 86 if max(len(l1), len(l2)) <= 13 else max(60, int(960 / (max(len(l1), len(l2)) * 0.58)))
            disp = f"{l1}\\N{l2}"
        else:
            f_sz = 92 if len(t_s) <= 11 else max(62, int(960 / (len(t_s) * 0.58)))
            disp = t_s
        ass_lines.append(f"Dialogue: 0,{_sec_to_ass(p['start'])},{_sec_to_ass(max(p['start']+0.12, p['end']))},SubPop,,0,0,0,,{{\\fs{f_sz}}}{disp}")

    ass_path.write_text("\n".join(ass_lines), encoding="utf-8")

    # Build top header + Scene 2 Verse Quote Overlay PNG with Pillow (zero drawtext escaping bugs!)
    hdr_png = scenes_dir / "header_overlay.png"
    from PIL import Image, ImageDraw, ImageFont
    ov = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
    dr = ImageDraw.Draw(ov)
    for y in range(340):
        dr.line([(0, y), (1080, y)], fill=(5, 8, 16, int(210 * (1.0 - y / 340.0))))
    for y in range(1580, 1920):
        dr.line([(0, y), (1080, y)], fill=(5, 8, 16, int(220 * ((y - 1580) / 340.0))))

    f_hdr = pda.get_black_font(38)
    f_ref = pda.get_black_font(44)
    f_ch = pda.get_bold_font(26)

    # Channel Brand Pill
    ch_txt = "GRACE OF THE LORD"
    cb = dr.textbbox((0, 0), ch_txt, font=f_ch)
    dr.text(((1080 - (cb[2] - cb[0])) // 2, 130), ch_txt, font=f_ch, fill=(235, 185, 55, 230), stroke_width=2, stroke_fill=(0, 0, 0, 240))

    # Theme Header
    hb = dr.textbbox((0, 0), header_str, font=f_hdr)
    dr.text(((1080 - (hb[2] - hb[0])) // 2, 175), header_str, font=f_hdr, fill=(255, 245, 185, 255), stroke_width=4, stroke_fill=(0, 0, 0, 250))

    # Verse Reference
    rb = dr.textbbox((0, 0), verse_ref.upper(), font=f_ref)
    dr.text(((1080 - (rb[2] - rb[0])) // 2, 232), verse_ref.upper(), font=f_ref, fill=(255, 255, 255, 255), stroke_width=4, stroke_fill=(0, 0, 0, 250))

    ov.save(str(hdr_png), "PNG")

    has_bgm = not (bgm_file == "NONE" or str(bgm_file).upper() == "NONE" or bgm_vol <= 0.001)
    bgm_audio = bgm_file if (has_bgm and bgm_file and Path(str(bgm_file)).exists()) else (backend.get_worship_bgm() if has_bgm else None)

    # 3-Scene Distinct Camera Motions:
    # Scene 1: zoom_in_slow
    # Scene 2: pan_up_slow
    # Scene 3: zoom_out_slow
    filter_complex = (
        f"[0:v]scale=1260:2240:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop=1080:1920:'(in_w-out_w)/2':'(in_h-out_h)*(0.5-0.35*t/{d1:.2f})',fps=24,format=yuv420p,setsar=1,setpts=PTS-STARTPTS[v1];"
        f"[1:v]scale=1260:2240:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop=1080:1920:'(in_w-out_w)/2':'(in_h-out_h)*(0.85-0.70*t/{d2:.2f})',fps=24,format=yuv420p,setsar=1,setpts=PTS-STARTPTS[v2];"
        f"[2:v]scale=1260:2240:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop=1080:1920:'(in_w-out_w)*(0.2+0.6*t/{d3:.2f})':'(in_h-out_h)/2',fps=24,format=yuv420p,setsar=1,setpts=PTS-STARTPTS[v3];"
        f"[v1][v2][v3]concat=n=3:v=1:a=0,unsharp=5:5:0.85:5:5:0.0,eq=brightness=-0.05:contrast=1.12:saturation=1.10[bg];"
        f"[bg][3:v]overlay=0:0:format=auto,subtitles='temp_grace_subs.ass'[vout];"
        (
            f"[4:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,volume=1.0[voice];"
            f"[5:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,volume={bgm_vol:.2f}[bgm];"
            f"[voice][bgm]amix=inputs=2:duration=first:normalize=0[aout]"
            if has_bgm else
            f"[4:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,volume=1.0[aout]"
        )
    )

    inputs = [
        "-loop", "1", "-t", f"{d1:.2f}", "-i", str(img_paths[0].absolute()),
        "-loop", "1", "-t", f"{d2:.2f}", "-i", str(img_paths[1].absolute()),
        "-loop", "1", "-t", f"{d3:.2f}", "-i", str(img_paths[2].absolute()),
        "-loop", "1", "-t", f"{total_dur:.2f}", "-i", str(hdr_png.absolute()),
        "-i", str(full_voice_mp3.absolute())
    ]

    stk_inputs, stk_filter = sticker_studio.build_ffmpeg_sticker_filter(
        sticker_path, total_dur, position=sticker_position, timing=sticker_timing
    )
    if has_bgm and bgm_audio:
        inputs.extend(["-stream_loop", "-1", "-i", str(Path(bgm_audio).absolute())])
    if stk_inputs:
        inputs.extend(stk_inputs)
        filter_complex = filter_complex.replace("[vout];", f"[vout];[6:v]{stk_filter};")
        final_v_map = "[vout_stk]"
    else:
        final_v_map = "[vout]"

    cmd = [
        "ffmpeg", "-y", "-threads", "0",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", final_v_map, "-map", "[aout]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-t", f"{total_dur:.2f}",
        str(out_video.absolute())
    ]

    subprocess.run(cmd, cwd=str(BASE_DIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if ass_path.exists():
        ass_path.unlink(missing_ok=True)

    # Render 3D Gold Thumbnail + 3 Variants using Scene 2 (Turning Point) or Scene 3 image
    thumb_bg = img_paths[2] if img_paths[2].exists() else img_paths[0]
    dummy_script = SimpleNamespace(
        topic=header_str,
        verse_citation=re.sub(r"\s*\(.*?\)", "", verse_ref),
        thumbnail_hook=header_str,
        title=grace_pkg.get("youtube_title", header_str)
    )
    pda.render_pro_thumbnails(thumb_bg, dummy_script, out_thumb, palette_name=palette_name)

    # Save metadata, clean description & pinned_comment.txt
    win_title = grace_pkg.get("youtube_title", f"{header_str.title()} 🙏 #shorts")[:95]
    clean_desc = _clean_christian_hashtags(grace_pkg.get("clean_youtube_description", ""))
    pinned_txt = grace_pkg.get("pinned_comment_text", "How can we pray for you today? Comment AMEN below! 🙏")
    (seq_dir / "pinned_comment.txt").write_text(pinned_txt, encoding="utf-8")
    (seq_dir / "grace_script_spec.json").write_text(json.dumps(grace_pkg, indent=2), encoding="utf-8")

    tags = backend.sanitize_youtube_tags([
        header_str.title(), re.sub(r"\s*\(.*?\)", "", verse_ref),
        "Grace Of The Lord", "Christian Shorts", "Daily Prayer", "Bible Verse",
        "Jesus Christ", "Faith Over Fear", "Spiritual Comfort", "Biblical Wisdom"
    ])
    backend.save_clip_metadata(out_video, win_title, clean_desc, tags, topic=header_str)

    if progress_cb:
        progress_cb(100, f"🎉 3-Scene 'Grace of the Lord' Short Ready ({total_dur:.1f}s)!")

    return out_video.exists(), out_video, out_thumb

def post_pinned_comment_if_possible(channel_name: str, video_id: str, video_path: Path):
    """Posts the saved pinned_comment.txt as the top comment on the uploaded YouTube Short."""
    pin_f = video_path.parent / "pinned_comment.txt"
    if not pin_f.exists() or not video_id:
        return False
    comment_txt = pin_f.read_text(encoding="utf-8").strip()
    if not comment_txt:
        return False
    try:
        yt = backend.get_authenticated_youtube(channel_name)
        if not yt:
            return False
        body = {
            "snippet": {
                "videoId": video_id,
                "topLevelComment": {
                    "snippet": {
                        "textOriginal": comment_txt
                    }
                }
            }
        }
        yt.commentThreads().insert(part="snippet", body=body).execute()
        print(f"   💬 Posted top prayer comment on video {video_id}!")
        return True
    except Exception as e:
        print(f"   [Comment Note] {e}")
        return False

