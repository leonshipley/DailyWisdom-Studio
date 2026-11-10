import os
import re
import json
import asyncio
import subprocess
import shutil
import textwrap
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from dotenv import load_dotenv
import edge_tts

import bible_database as bdb

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

LONGFORM_DIR = BASE_DIR / "longform_videos"
LONGFORM_DIR.mkdir(parents=True, exist_ok=True)
AMBIENCE_DIR = BASE_DIR / "assets" / "ambience"
AMBIENCE_DIR.mkdir(parents=True, exist_ok=True)

def clean_ascii(text: str) -> str:
    if not text:
        return ""
    t = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace("—", " - ").replace("…", "...")
    return re.sub(r"\s+", " ", re.sub(r"[^\x20-\x7E\u0900-\u097F]", "", t)).strip()

def _sec_to_srt_time(sec: float) -> str:
    sec = max(0.0, float(sec))
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    ms = int(round((sec - int(sec)) * 1000))
    if ms >= 1000:
        s += 1
        ms -= 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def detect_hardware_video_encoder() -> tuple:
    try:
        t = subprocess.run(["ffmpeg", "-f", "lavfi", "-i", "color=s=64x64:d=0.1", "-c:v", "h264_nvenc", "-f", "null", "-"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
        if t.returncode == 0: return "h264_nvenc", ["-preset", "p1", "-cq", "24"]
    except Exception: pass
    try:
        t = subprocess.run(["ffmpeg", "-f", "lavfi", "-i", "color=s=64x64:d=0.1", "-c:v", "h264_qsv", "-f", "null", "-"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
        if t.returncode == 0: return "h264_qsv", ["-preset", "veryfast", "-global_quality", "25"]
    except Exception: pass
    return "libx264", ["-preset", "ultrafast", "-tune", "fastdecode", "-crf", "24"]

DURATION_CONFIGS: Dict[str, Dict[str, Any]] = {
    "5 Minutes": {"target_seconds": 300, "scriptures_count": 3, "words_per_stage": 100, "pause_between_paras_sec": 2.5, "pause_between_stages_sec": 4.0},
    "10 Minutes": {"target_seconds": 600, "scriptures_count": 5, "words_per_stage": 200, "pause_between_paras_sec": 3.0, "pause_between_stages_sec": 4.5},
    "15 Minutes (Soaking Sweet Spot)": {"target_seconds": 900, "scriptures_count": 5, "words_per_stage": 240, "pause_between_paras_sec": 3.0, "pause_between_stages_sec": 5.0},
    "20 Minutes": {"target_seconds": 1200, "scriptures_count": 8, "words_per_stage": 380, "pause_between_paras_sec": 3.2, "pause_between_stages_sec": 5.5},
    "30 Minutes": {"target_seconds": 1800, "scriptures_count": 10, "words_per_stage": 550, "pause_between_paras_sec": 3.5, "pause_between_stages_sec": 6.0},
    "1 Hour (60 Min)": {"target_seconds": 3600, "scriptures_count": 12, "words_per_stage": 700, "pause_between_paras_sec": 4.0, "pause_between_stages_sec": 7.0},
}

def select_scriptures_for_journey(topic: str, count: int) -> List[Dict[str, str]]:
    t_low = topic.lower()
    chosen_pool = ["Philippians 4:6-7", "John 14:27", "Isaiah 41:10", "Psalm 46:1", "Matthew 11:28", "1 Peter 5:7"]
    for k, pool in bdb.CATEGORY_VERSE_POOLS.items():
        if k.lower() in t_low:
            chosen_pool = pool
            break
    results = []
    for ref in chosen_pool[:count]:
        norm_ref, en_txt, _, _ = bdb.lookup_reference_bilingual(ref)
        spoken_ref = bdb.format_reference_for_speech(norm_ref, is_hindi_speech=False)
        results.append({"ref": norm_ref, "spoken_ref": spoken_ref, "text": en_txt})
    return results

def generate_soul_prayer_journey(topic: str, duration_label: str = "15 Minutes (Soaking Sweet Spot)", lang: str = "en", **kwargs) -> Dict[str, Any]:
    cfg = DURATION_CONFIGS.get(duration_label, DURATION_CONFIGS["15 Minutes (Soaking Sweet Spot)"])
    scriptures = select_scriptures_for_journey(topic, max(5, cfg.get("scriptures_count", 5)))
    is_hi = "hi" in str(lang).lower() or "hindi" in str(lang).lower()
    dur_short = duration_label.split("(")[0].strip()

    verse_bank_str = "\n".join([f"- {v['ref']} ({v['spoken_ref']}): \"{v['text']}\"" for v in scriptures[:6]])
    lang_instruction = "Write all spoken_script chapters, chapter_title, youtube_title, and pinned_comment in pure, comforting Devanagari Hindi (पवित्र बाइबिल हिंदी)." if is_hi else "Write in deeply emotional, unhurried, pastoral English."

    prompt = f"""You are an elite Christian YouTube Scriptwriter and Pastoral Guide. Write a deeply emotional, unhurried, and comforting multi-chapter prayer script designed for a {dur_short} long-form "soaking prayer" video.
Topic: {topic}
Language Requirement: {lang_instruction}
Available Canonical Bible Verses to weave naturally into the spoken text:
{verse_bank_str}

RULES FOR LONG-FORM RETENTION:
1. Pacing: Break into 5 distinct chapters. Tone should be slow, rhythmic, and meditative.
2. Progress the journey from "Acknowledging the Pain" -> "Standing on Scripture" -> "Spiritual Warfare" -> "Prophetic Blessing" -> "Benediction".
3. Use 4-5 different Bible verses woven naturally into the spoken text.
4. Do NOT include narrator stage directions or [brackets] inside spoken_script.

OUTPUT FORMAT (Strict JSON ONLY):
{{
  "youtube_title": "Play This In Your Home For Deep Peace | {dur_short} Prayer & Scripture",
  "chapters": [
    {{ "chapter_number": 1, "chapter_title": "Entering God's Presence & Releasing the Burden", "spoken_script": "200 words..." }},
    {{ "chapter_number": 2, "chapter_title": "The Unshakeable Promises of God", "spoken_script": "200 words..." }},
    {{ "chapter_number": 3, "chapter_title": "Breaking the Chains (Spiritual Warfare)", "spoken_script": "200 words..." }},
    {{ "chapter_number": 4, "chapter_title": "A Prophetic Blessing Over Your Home", "spoken_script": "200 words..." }},
    {{ "chapter_number": 5, "chapter_title": "Resting in His Grace (Benediction)", "spoken_script": "150 words..." }}
  ],
  "pinned_comment": "A warm question for the community...",
  "youtube_tags": "15 highly searched SEO keywords for this topic separated by commas"
}}"""

    ai_json = None
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if key:
        import urllib.request
        for m_id in ["gemini-3.5-flash-lite", "gemini-3.7-flash", "gemini-3.6-flash", "gemini-2.5-flash"]:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{m_id}:generateContent?key={key}"
                payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json", "temperature": 0.78}}
                req = urllib.request.Request(url, headers={"Content-Type": "application/json"}, data=json.dumps(payload).encode("utf-8"))
                with urllib.request.urlopen(req, timeout=18) as resp:
                    r_data = json.loads(resp.read().decode("utf-8"))
                    raw_t = r_data["candidates"][0]["content"]["parts"][0]["text"]
                    m = re.search(r"\{[\s\S]*\}", raw_t)
                    if m:
                        cand = json.loads(m.group(0))
                        if isinstance(cand.get("chapters"), list) and len(cand["chapters"]) >= 5:
                            ai_json = cand
                            break
            except Exception:
                continue

    v0 = scriptures[0] if len(scriptures) > 0 else {"ref": "Psalm 34:18", "spoken_ref": "Psalm 34, verse 18", "text": "The Lord is near to the brokenhearted."}
    v1 = scriptures[1] if len(scriptures) > 1 else v0
    v2 = scriptures[2] if len(scriptures) > 2 else v0
    v3 = scriptures[3] if len(scriptures) > 3 else v0
    v4 = scriptures[4] if len(scriptures) > 4 else v0

    if not ai_json:
        if is_hi:
            ai_json = {
                "youtube_title": f"अपने घर में यह प्रार्थना चलाएं | {dur_short} गहरी शांति और आशीष #prayer",
                "chapters": [
                    {"chapter_number": 1, "chapter_title": "परमेश्वर की उपस्थिति में प्रवेश और बोझ को छोड़ना", "spoken_script": f"इस समय एक गहरी सांस लें... अपने कंधों को ढीला छोड़ें, और अपने हृदय को प्रभु के सामने शांत होने दें। यदि आप {topic} के भारी बोझ को लेकर इस स्थान पर आए हैं, तो जान लें कि आप यहाँ अचानक नहीं पहुंचे हैं। सृष्टिकर्ता परमेश्वर आपके हर छिपे हुए आंसू को देखते हैं। पवित्र बाइबिल कहती है: {v0['text']} प्रभु यीशु के चरणों में अपनी सारी चिंताओं को सौंप दें और उनकी शांति को महसूस करें।"},
                    {"chapter_number": 2, "chapter_title": "परमेश्वर के अटल और जीवित वादे", "spoken_script": f"जब अनिश्चितता का डर आपके मन को घेरने लगे, तो हम परमेश्वर के जीवित वचन पर खड़े होते हैं। शास्त्र में लिखा है: {v1['text']} इस सत्य को अपने मन में बसने दें। परमेश्वर आपके हर एक पहलू की चिंता करते हैं।"},
                    {"chapter_number": 3, "chapter_title": "बंधनों को तोड़ना (आत्मिक युद्ध)", "spoken_script": f"स्वर्गीय पिता, हम प्रभु यीशु के सामर्थी नाम में प्रार्थना करते हैं। हम {topic} से जुड़ी हर निराशा, डर और अंधकार की शक्ति का विरोध करते हैं। वचन कहता है: {v3['text']} यीशु के नाम में हर भारीपन और डर का बादल दूर हो जाए।"},
                    {"chapter_number": 4, "chapter_title": "आपके घर और परिवार पर स्वर्गीय आशीष", "spoken_script": f"अब इस स्वर्गीय आशीष को अपने जीवन और परिवार पर ग्रहण करें। जैसा कि वचन में लिखा है: {v4['text']} प्रभु यीशु की अलौकिक शांति आपके घर के हर कमरे में भर जाए। स्वर्गदूत आपके घर की रक्षा करें।"},
                    {"chapter_number": 5, "chapter_title": "प्रभु के अनुग्रह में विश्राम (आशीर्वचन)", "spoken_script": f"अब इस विश्वास में विश्राम करें कि आपकी प्रार्थना स्वर्ग में सुनी गई है। यहोवा आपको आशीष दे और आपकी रक्षा करे। प्रभु अपना मुख आप पर चमकाए और आपको शांति दे, आमीन।"}
                ],
                "pinned_comment": f"क्या आप और आपका परिवार {topic} के लिए प्रार्थना चाहते हैं? कमेंट में AMEN ज़रूर लिखें! 🙏",
                "youtube_tags": f"{topic}, {topic} hindi prayer, christian soaking prayer, hindi bible verses, prarthana, jesus christ, psalm 91"
            }
        else:
            ai_json = {
                "youtube_title": f"Play This In Your Home For {topic[:32]} | {dur_short} Deep Soaking Prayer & Scripture",
                "chapters": [
                    {"chapter_number": 1, "chapter_title": "Entering God's Presence & Releasing the Burden", "spoken_script": f"Take a slow, deep breath right now... Let your shoulders drop, and allow your heart to become still before the Lord. If you have come to this quiet place carrying the silent, exhausting weight of {topic}, know that you have not arrived here by accident. The Creator of the universe sees every hidden tear you have wiped away when no one else was looking. He hears the unspoken cries of your heart late at night. Listen to the tender invitation of {v0['spoken_ref']}: {v0['text']} Right here, in His sanctuary, you do not have to pretend to be strong. Breathe in His grace... and exhale every anxious thought at the feet of Jesus."},
                    {"chapter_number": 2, "chapter_title": "The Unshakeable Promises of God", "spoken_script": f"When feelings of uncertainty try to overwhelm your mind, we anchor our souls in the unshakeable Word of God. Hear the eternal promise written in {v1['spoken_ref']}: {v1['text']} Let that truth echo through your spirit today. Circumstances may shift like sand, but the Word of the Lord stands forever."},
                    {"chapter_number": 3, "chapter_title": "Breaking the Chains (Spiritual Warfare)", "spoken_script": f"Heavenly Father, we stand right now in the mighty authority of the name of Jesus Christ. We come against every heavy cloud of fear, torment, delay, and discouragement surrounding {topic}. Your word declares in {v3['spoken_ref']}: {v3['text']} By the blood of Jesus, we command every storm of anxiety and every lying whisper of hopelessness to be silenced right now."},
                    {"chapter_number": 4, "chapter_title": "A Prophetic Blessing Over Your Home", "spoken_script": f"Now, receive this pastoral blessing over your life, your mind, and your household. As it is written in {v4['spoken_ref']}: {v4['text']} I speak supernatural peace over every room of your home tonight. May the angels of the Lord encamp around your family and guard your coming in and your going out."},
                    {"chapter_number": 5, "chapter_title": "Resting in His Grace (Benediction)", "spoken_script": f"Now, rest in the quiet assurance that your prayer has been heard in the courts of heaven. You can close your eyes in peace, knowing that while you rest, God is working behind the scenes on your behalf. May the Lord bless you and keep you. In Jesus' name, Amen."}
                ],
                "pinned_comment": f"How can we pray for you and your family today regarding {topic}? Leave your prayer request or type AMEN below so we can agree in faith together! 🙏",
                "youtube_tags": f"{topic}, {topic} prayer, soaking prayer, {dur_short} prayer, christian meditation, sleep prayer, bible verses for peace, spiritual warfare prayer, prophetic blessing, daily devotional, jesus christ, psalm 91, peace of god, morning prayer, night prayer"
            }

    compiled_stages = []
    raw_chapters = ai_json.get("chapters", [])
    for idx, ch_obj in enumerate(raw_chapters[:5]):
        sp_text = str(ch_obj.get("spoken_script", "")).strip()
        sp_text = re.sub(r"(\d+):(\d+)", r"chapter \1, verse \2", sp_text)
        sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", sp_text) if s.strip()]
        paras = [" ".join(sents[i:i+3]) for i in range(0, len(sents), 3)] if len(sents) > 3 else [sp_text]
        v_slice = [scriptures[min(idx, len(scriptures)-1)]] if scriptures else [v0]

        compiled_stages.append({
            "stage_num": int(ch_obj.get("chapter_number", idx + 1)),
            "chapter_title": str(ch_obj.get("chapter_title", f"Chapter {idx + 1}")),
            "verses": v_slice,
            "paragraphs": paras,
            "full_text": "\n\n".join(paras),
            "spoken_script": sp_text,
        })

    raw_tags = ai_json.get("youtube_tags", "")
    if isinstance(raw_tags, list):
        tags_str = ", ".join([str(x).strip() for x in raw_tags if str(x).strip()])
    else:
        tags_str = str(raw_tags)
    tags_list = [x.strip() for x in tags_str.split(",") if x.strip()]

    strict_json_export = {
        "youtube_title": ai_json.get("youtube_title", f"Play This In Your Home For {topic} | {dur_short} Prayer & Scripture"),
        "chapters": [{"chapter_number": s["stage_num"], "chapter_title": s["chapter_title"], "spoken_script": s["spoken_script"]} for s in compiled_stages],
        "pinned_comment": ai_json.get("pinned_comment", "Type AMEN below to seal this prayer over your home and family! 🙏"),
        "youtube_tags": tags_str,
    }

    return {
        "topic": topic,
        "duration_label": duration_label,
        "config": cfg,
        "scriptures": scriptures,
        "stages": compiled_stages,
        "youtube_title": strict_json_export["youtube_title"],
        "chapters": strict_json_export["chapters"],
        "pinned_comment": strict_json_export["pinned_comment"],
        "youtube_tags": strict_json_export["youtube_tags"],
        "youtube_tags_list": tags_list,
        "strict_json": strict_json_export,
    }

def generate_full_chapter_reading_journey(book: str, chapter: int, lang: str = "en", **kwargs) -> Dict[str, Any]:
    """
    Acts as a Pastoral Teacher: Reads the Bible chapter AND explains its deep meaning, 
    relates it to modern real-life struggles, and prays over the viewer.
    """
    import bible_database as bdb
    import urllib.request
    
    is_hi = "hi" in str(lang).lower() or "hindi" in str(lang).lower()
    verses_dict = bdb.get_verses_for_chapter(book, chapter)
    book_hi = bdb.HINDI_BOOK_SPOKEN_MAP.get(book.lower(), book)
    
    # Build the full chapter text to feed to the AI for accurate context
    full_chapter_text = " ".join([f"v{v}: {txt}" for v, txt in verses_dict.items()])
    all_refs = [{"ref": f"{book} {chapter}:{v}", "text": txt} for v, txt in verses_dict.items()]

    lang_instruction = (
        "Write all spoken_script chapters, chapter_title, youtube_title, and pinned_comment in pure, comforting Devanagari Hindi (?????? ?????? ?????). Quote verses in Hindi."
        if is_hi else
        "Write in deeply emotional, relatable, unhurried, pastoral English."
    )

    prompt = f"""You are an elite Christian Pastor and Bible Teacher. Your goal is to write a deeply engaging, relatable, and comforting sermon/teaching script for a long-form video exploring the Book of {book}, Chapter {chapter}.

Instead of just reading the text blindly, you must EXPLAIN it, relate it to modern real-life struggles (like anxiety, debt, family issues, or heartbreak), and guide the listener spiritually.

Full Chapter Text for Reference:
{full_chapter_text}

Language Requirement: {lang_instruction}

RULES:
1. Pacing: Break into 5 distinct chapters. Tone should be warm, pastoral, relatable, and deeply encouraging.
2. Weave the actual Bible verses naturally into the explanation (e.g., "In verse 1, it says... This means that in your life today..."). You do not have to read every single verse, but you MUST read and explain the most powerful ones.
3. Do NOT include narrator stage directions or [brackets] inside spoken_script.

OUTPUT FORMAT (Strict JSON ONLY):
{{
  "youtube_title": "Highly clickable Long-Form Title (e.g., 'The Hidden Power of {book} {chapter} Explained | Deep Bible Study & Prayer')",
  "chapters": [
    {{ "chapter_number": 1, "chapter_title": "Introduction & The Context", "spoken_script": "250 words welcoming the viewer, setting the historical/spiritual context of {book} {chapter}, reading the opening verses, and explaining them." }},
    {{ "chapter_number": 2, "chapter_title": "The Spiritual Lesson", "spoken_script": "250 words reading the middle verses and explaining the deep theological meaning in simple, comforting terms." }},
    {{ "chapter_number": 3, "chapter_title": "Real-Life Application", "spoken_script": "250 words directly relating this chapter to the viewer's modern struggles (finances, fear, family, etc.). Make it very relatable!" }},
    {{ "chapter_number": 4, "chapter_title": "The Promise of Victory", "spoken_script": "250 words reading the final verses of the chapter and declaring God's promises over the listener." }},
    {{ "chapter_number": 5, "chapter_title": "Closing Pastoral Prayer", "spoken_script": "200 words praying over the viewer based on the lessons of this chapter. End with 'In Jesus' name, Amen.'" }}
  ],
  "pinned_comment": "A warm question asking how this chapter touched their heart today.",
  "youtube_tags": "15 highly searched SEO keywords related to {book} {chapter} bible study, sermon, explained separated by commas"
}}"""

    ai_json = None
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if key:
        for m_id in ["gemini-3.5-flash-lite", "gemini-3.7-flash", "gemini-3.6-flash", "gemini-2.5-flash"]:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{m_id}:generateContent?key={key}"
                payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json", "temperature": 0.75}}
                req = urllib.request.Request(url, headers={"Content-Type": "application/json"}, data=json.dumps(payload).encode("utf-8"))
                with urllib.request.urlopen(req, timeout=30) as resp:
                    r_data = json.loads(resp.read().decode("utf-8"))
                    raw_t = r_data["candidates"][0]["content"]["parts"][0]["text"]
                    m = re.search(r"\{[\s\S]*\}", raw_t)
                    if m:
                        cand = json.loads(m.group(0))
                        if isinstance(cand.get("chapters"), list) and len(cand["chapters"]) >= 5:
                            ai_json = cand
                            break
            except Exception:
                continue

    if not ai_json:
        # FALLBACK: If AI is offline, do a clean verbatim reading chunk by chunk
        stages = []
        intro_title = f"Introduction to {book} {chapter}" if not is_hi else f"{book_hi} {chapter} ?? ???"
        intro_text = f"Welcome to the reading of God's Holy Word. Today, we are reading from the book of {book}, chapter {chapter}. Let your heart be still and receive His truth."
        if is_hi:
            intro_text = f"???????? ?? ?????? ??? ?? ??? ??? ???? ?????? ??? ?? ?? {book_hi}, ?????? {chapter} ?? ??? ?? ??? ???? ???? ???? ?? ???? ???? ?? ????? ?? ??? ?? ????? ?????"
        stages.append({"stage_num": 1, "chapter_title": intro_title, "verses": [], "paragraphs": [intro_text], "full_text": intro_text, "spoken_script": intro_text})

        v_nums = sorted(verses_dict.keys())
        chunk_size = max(3, len(v_nums) // 3)
        stage_idx = 2
        for i in range(0, len(v_nums), chunk_size):
            chunk = v_nums[i:i+chunk_size]
            chunk_spoken = []
            for vn in chunk:
                ref_str = f"{book} {chapter}:{vn}"
                en_v = verses_dict[vn]
                if is_hi:
                    dev_hi, _ = bdb.translate_verse_to_hindi(ref_str, en_v)
                    chunk_spoken.append(f"??? {vn}? {dev_hi}")
                else:
                    chunk_spoken.append(f"Verse {vn}. {en_v}")
            stage_title = f"Verses {chunk[0]}-{chunk[-1]}" if not is_hi else f"??? {chunk[0]} ?? {chunk[-1]}"
            stage_text = " ".join(chunk_spoken)
            stages.append({"stage_num": stage_idx, "chapter_title": stage_title, "verses": [], "paragraphs": [stage_text], "full_text": stage_text, "spoken_script": stage_text})
            stage_idx += 1

        outro_title = "Blessing & Amen" if not is_hi else "????????"
        outro_text = "May the Lord bless the reading of His Holy Word, and may it bring peace and strength to your soul. In Jesus' name, Amen."
        if is_hi:
            outro_text = "???????? ???? ?? ?????? ??? ?? ??? ?? ???? ??, ?? ???? ???? ??? ????? ?? ???????? ???? ???? ?? ??? ???, ?????"
        stages.append({"stage_num": stage_idx, "chapter_title": outro_title, "verses": [], "paragraphs": [outro_text], "full_text": outro_text, "spoken_script": outro_text})

        ai_json = {
            "youtube_title": f"Holy Bible Reading: {book} {chapter} (KJV) | Deep Sleep & Peace" if not is_hi else f"?????? ?????? ???: {book_hi} ?????? {chapter} | ?????? ?????",
            "chapters": [{"chapter_number": s["stage_num"], "chapter_title": s["chapter_title"], "spoken_script": s["spoken_script"]} for s in stages],
            "pinned_comment": f"What is your favorite verse from {book} {chapter}? Let us know in the comments! ??" if not is_hi else f"{book_hi} {chapter} ?? ???? ???? ????? ??? ??? ?? ??? ????? ??? ?????! ??",
            "youtube_tags": f"{book} {chapter}, audio bible, bible reading"
        }

    compiled_stages = []
    raw_chapters = ai_json.get("chapters", [])
    for idx, ch_obj in enumerate(raw_chapters[:5]):
        sp_text = str(ch_obj.get("spoken_script", "")).strip()
        sp_text = re.sub(r"(\d+):(\d+)", r"chapter \1, verse \2", sp_text)
        sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", sp_text) if s.strip()]
        paras = [" ".join(sents[i:i+3]) for i in range(0, len(sents), 3)] if len(sents) > 3 else [sp_text]
        compiled_stages.append({
            "stage_num": int(ch_obj.get("chapter_number", idx + 1)),
            "chapter_title": str(ch_obj.get("chapter_title", f"Chapter {idx + 1}")),
            "verses": all_refs[:2],
            "paragraphs": paras,
            "full_text": "\n\n".join(paras),
            "spoken_script": sp_text,
        })

    topic = f"{book} {chapter} Explained"
    total_words = sum(len(s["spoken_script"].split()) for s in compiled_stages)
    est_dur_sec = int((total_words / 130) * 60) + (len(compiled_stages) * 3)
    tags_str = ai_json.get("youtube_tags", "")
    tags_list = [x.strip() for x in tags_str.split(",") if x.strip()]

    strict_json_export = {
        "youtube_title": ai_json.get("youtube_title", f"{book} {chapter} Explained & Prayer"),
        "chapters": [{"chapter_number": s["stage_num"], "chapter_title": s["chapter_title"], "spoken_script": s["spoken_script"]} for s in compiled_stages],
        "pinned_comment": ai_json.get("pinned_comment", "Type AMEN below! ??"),
        "youtube_tags": tags_str,
    }

    return {
        "topic": topic,
        "duration_label": f"Sermon & Reading (~{max(1, int(est_dur_sec/60))}m)",
        "config": {"target_seconds": est_dur_sec, "pause_between_paras_sec": 1.5, "pause_between_stages_sec": 3.0},
        "scriptures": all_refs,
        "stages": compiled_stages,
        "youtube_title": strict_json_export["youtube_title"],
        "chapters": strict_json_export["chapters"],
        "pinned_comment": strict_json_export["pinned_comment"],
        "youtube_tags": strict_json_export["youtube_tags"],
        "youtube_tags_list": tags_list,
        "strict_json": strict_json_export,
    }

def get_audio_duration(audio_path: Path) -> float:
    try:
        cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path.absolute())]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10, encoding="utf-8", errors="replace")
        return float(res.stdout.strip())
    except Exception:
        return 0.0

def _create_silence_mp3(out_path: Path, seconds: float):
    cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", f"{seconds:.2f}", "-c:a", "libmp3lame", "-q:a", "4", str(out_path.absolute())]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def format_mm_ss(seconds: float) -> str:
    sec = int(max(0, seconds))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h > 0: return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"

def _sec_to_ass_time_lf(sec: float) -> str:
    sec = max(0.0, float(sec))
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"

def synthesize_meditative_voiceover(journey_pkg: Dict[str, Any], out_voice_mp3: Path, voice_name: str = "en-US-ChristopherNeural", rate_str: str = "-10%", pitch_str: str = "-2Hz") -> Dict[str, Any]:
    work_dir = out_voice_mp3.parent / "temp_meditative_chunks"
    work_dir.mkdir(parents=True, exist_ok=True)

    cfg = journey_pkg["config"]
    para_pause = float(cfg.get("pause_between_paras_sec", 2.5))
    stage_pause = float(cfg.get("pause_between_stages_sec", 4.0))

    sil_para_mp3 = work_dir / "sil_para.mp3"
    sil_stage_mp3 = work_dir / "sil_stage.mp3"
    _create_silence_mp3(sil_para_mp3, para_pause)
    _create_silence_mp3(sil_stage_mp3, stage_pause)

    concat_files: List[Path] = []
    chapters_log: List[Dict[str, Any]] = []
    all_word_timings: List[Dict[str, Any]] = []
    current_time_sec = 0.0

    async def _tts_chunk_stream(txt: str, target_mp3: Path, t_offset: float):
        clean_txt = re.sub(r"(\d+):(\d+)", r"chapter \1 verse \2", txt)
        comm = edge_tts.Communicate(clean_txt, voice=voice_name, rate=rate_str, pitch=pitch_str, boundary="WordBoundary")
        with open(target_mp3, "wb") as f_out:
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    f_out.write(chunk["data"])
                elif chunk["type"] in ("WordBoundary", "SentenceBoundary"):
                    st_s = t_offset + (chunk["offset"] / 10_000_000.0)
                    du_s = chunk["duration"] / 10_000_000.0
                    w_txt = chunk["text"].strip()
                    if len(w_txt.split()) <= 1:
                        all_word_timings.append({"text": w_txt, "start": round(st_s, 3), "end": round(st_s + du_s, 3)})
                    else:
                        w_list = w_txt.split()
                        step_d = max(0.1, du_s) / len(w_list)
                        for w_i, w_tok in enumerate(w_list):
                            all_word_timings.append({"text": w_tok, "start": round(st_s + w_i * step_d, 3), "end": round(st_s + (w_i + 1) * step_d, 3)})

    for stg in journey_pkg["stages"]:
        stg_idx = stg["stage_num"]
        chapters_log.append({
            "timestamp": format_mm_ss(current_time_sec),
            "start_sec": round(current_time_sec, 2),
            "title": stg["chapter_title"],
            "verses": [v["ref"] for v in stg["verses"]]
        })
        for p_idx, para_text in enumerate(stg["paragraphs"]):
            chunk_mp3 = work_dir / f"s{stg_idx}_p{p_idx}.mp3"
            import preacher_audio_engine as pae
            p_timings = pae.synthesize_preacher_voiceover(para_text, chunk_mp3, voice_name=voice_name, base_rate=rate_str, base_pitch=pitch_str)
            for wt in p_timings:
                all_word_timings.append({"text": wt["text"], "start": round(current_time_sec + wt["start"], 3), "end": round(current_time_sec + wt["end"], 3)})
            if chunk_mp3.exists() and chunk_mp3.stat().st_size > 500:
                dur = get_audio_duration(chunk_mp3)
                concat_files.append(chunk_mp3)
                current_time_sec += dur
                concat_files.append(sil_para_mp3)
                current_time_sec += para_pause
        concat_files.append(sil_stage_mp3)
        current_time_sec += stage_pause

    list_txt = work_dir / "concat_list.txt"
    lines = [f"file '{f.absolute().as_posix()}'" for f in concat_files]
    list_txt.write_text("\n".join(lines), encoding="utf-8")
    cmd_merge = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_txt.absolute()), "-ar", "44100", "-ac", "2", "-c:a", "libmp3lame", "-b:a", "192k", str(out_voice_mp3.absolute())]
    subprocess.run(cmd_merge, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    total_voice_dur = get_audio_duration(out_voice_mp3)

    phrases = []
    cur_w = []
    c_st = 0.0
    for i, w_obj in enumerate(all_word_timings):
        if not cur_w: c_st = w_obj["start"]
        cur_w.append(w_obj["text"])
        t_str = " ".join(cur_w)
        nxt_len = len(t_str) + (len(all_word_timings[i + 1]["text"]) + 1 if i + 1 < len(all_word_timings) else 0)
        is_strong_punct = bool(re.search(r"[.;!?]", w_obj["text"])) or (len(cur_w) >= 4 and "," in w_obj["text"])
        if nxt_len > 44 or len(cur_w) >= 6 or is_strong_punct or i == len(all_word_timings) - 1:
            c_en = all_word_timings[i + 1]["start"] if i + 1 < len(all_word_timings) else (w_obj["end"] + 0.25)
            safe_t = re.sub(r"[^a-zA-Z0-9\s:\-',.!?\u0900-\u097F]", "", t_str).strip()
            if safe_t:
                phrases.append({"text": safe_t, "start": round(c_st, 3), "end": round(c_en, 3)})
            cur_w = []

    ass_path = out_voice_mp3.parent / "longform_subtitles.ass"
    ass_lines = [
        "[Script Info]", "ScriptType: v4.00+", "PlayResX: 1920", "PlayResY: 1080", "",
        "[V4+ Styles]", "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: LongFormSubs,Segoe UI,54,&H00FFFFFF,&H0000D4FF,&H90000000,&H90000000,-1,0,0,0,100,100,0,0,1,3.5,2,2,140,140,82,1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
    ]
    for p in phrases:
        t_s = p["text"]
        w_p = t_s.split()
        if len(t_s) > 28 and len(w_p) >= 4:
            mid_w = len(w_p) // 2
            l1, l2 = " ".join(w_p[:mid_w]), " ".join(w_p[mid_w:])
            disp = f"{l1}\\N{l2}"
        else:
            disp = t_s
        st_t = _sec_to_ass_time_lf(p["start"])
        en_t = _sec_to_ass_time_lf(max(p["start"] + 0.15, p["end"]))
        ass_lines.append(f"Dialogue: 0,{st_t},{en_t},LongFormSubs,,0,0,0,,{{\\fs54}}{disp}")
    ass_path.write_text("\n".join(ass_lines), encoding="utf-8")

    srt_path = out_voice_mp3.parent / "longform_subtitles.srt"
    srt_blocks = []
    for idx_s, p in enumerate(phrases, start=1):
        st_srt = _sec_to_srt_time(p["start"])
        en_srt = _sec_to_srt_time(max(p["start"] + 0.15, p["end"]))
        srt_blocks.append(f"{idx_s}\n{st_srt} --> {en_srt}\n{p['text']}\n")
    srt_path.write_text("\n".join(srt_blocks), encoding="utf-8")

    return {"voice_mp3": out_voice_mp3, "voice_duration_sec": round(total_voice_dur, 2), "chapters": chapters_log, "subtitles_ass": ass_path}

def ensure_soaking_worship_pad() -> Path:
    pad_file = AMBIENCE_DIR / "432hz_cathedral_soaking_pad.mp3"
    if not pad_file.exists() or pad_file.stat().st_size < 10000:
        cmd = [
            "ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=144:sample_rate=44100",
            "-f", "lavfi", "-i", "sine=frequency=216:sample_rate=44100",
            "-f", "lavfi", "-i", "sine=frequency=288:sample_rate=44100",
            "-filter_complex", "amix=inputs=3:normalize=0,lowpass=f=380,aecho=0.8:0.88:60:0.4,volume=0.22",
            "-t", "180", "-c:a", "libmp3lame", "-b:a", "192k", str(pad_file.absolute())
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return pad_file

def ensure_nature_ambience(style: str = "Gentle Night Rain") -> Path | None:
    if not style or "None" in style: return None
    if "Stream" in style:
        out_f = AMBIENCE_DIR / "gentle_mountain_stream.mp3"
        filter_str = "anoisesrc=d=120:c=brown:r=44100:a=0.12,bandpass=f=450:width_type=h:w=350,volume=0.35"
    else:
        out_f = AMBIENCE_DIR / "gentle_night_rain.mp3"
        filter_str = "anoisesrc=d=120:c=pink:r=44100:a=0.10,lowpass=f=1200,highpass=f=200,volume=0.30"
    if not out_f.exists() or out_f.stat().st_size < 10000:
        cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", filter_str, "-t", "120", "-ac", "2", "-c:a", "libmp3lame", "-b:a", "192k", str(out_f.absolute())]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return out_f

def mix_longform_master_audio(voice_mp3: Path, out_master_mp3: Path, target_duration_sec: int, bgm_file: Path | str | None = None, bgm_volume: float = 0.18, nature_style: str = "None (Pure Worship Music)") -> float:
    has_bgm = not (bgm_file is None or str(bgm_file).upper() == "NONE" or bgm_volume <= 0.001)
    bgm_path = Path(str(bgm_file)) if (has_bgm and bgm_file and Path(str(bgm_file)).exists()) else (ensure_soaking_worship_pad() if has_bgm else None)
    nature_file = ensure_nature_ambience(nature_style)
    has_nat = bool(nature_file and nature_file.exists())
    voice_dur = get_audio_duration(voice_mp3)
    final_dur = max(int(voice_dur) + 10, int(target_duration_sec))
    fade_out_start = max(1, final_dur - 6)

    padded_voice = voice_mp3.parent / "padded_voice_loop.mp3"
    interlude_sil = voice_mp3.parent / "soaking_interlude.mp3"
    _create_silence_mp3(interlude_sil, 45.0)

    list_v = voice_mp3.parent / "voice_cycle.txt"
    cycles_needed = max(1, int(final_dur // max(1.0, (voice_dur + 45.0))) + 1)
    v_lines = []
    for _ in range(cycles_needed):
        v_lines.append(f"file '{voice_mp3.absolute().as_posix()}'")
        v_lines.append(f"file '{interlude_sil.absolute().as_posix()}'")
    list_v.write_text("\n".join(v_lines), encoding="utf-8")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_v.absolute()), "-t", f"{final_dur}", "-c:a", "libmp3lame", "-b:a", "192k", str(padded_voice.absolute())], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if has_bgm and bgm_path and has_nat:
        cmd_mix = [
            "ffmpeg", "-y", "-i", str(padded_voice.absolute()),
            "-stream_loop", "-1", "-t", f"{final_dur}", "-i", str(bgm_path.absolute()),
            "-stream_loop", "-1", "-t", f"{final_dur}", "-i", str(nature_file.absolute()),
            "-filter_complex",
            f"[0:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,volume=1.0[v];"
            f"[1:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,volume={bgm_volume:.2f}[bgm];"
            f"[2:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,volume=0.06[nat];"
            f"[v][bgm][nat]amix=inputs=3:duration=longest:normalize=0,afade=t=in:st=0:d=3,afade=t=out:st={fade_out_start}:d=6[aout]",
            "-map", "[aout]", "-c:a", "libmp3lame", "-b:a", "128k", "-t", f"{final_dur}", str(out_master_mp3.absolute())
        ]
    elif has_bgm and bgm_path:
        cmd_mix = [
            "ffmpeg", "-y", "-i", str(padded_voice.absolute()),
            "-stream_loop", "-1", "-t", f"{final_dur}", "-i", str(bgm_path.absolute()),
            "-filter_complex",
            f"[0:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,volume=1.0[v];"
            f"[1:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,volume={bgm_volume:.2f}[bgm];"
            f"[v][bgm]amix=inputs=2:duration=longest:normalize=0,afade=t=in:st=0:d=3,afade=t=out:st={fade_out_start}:d=6[aout]",
            "-map", "[aout]", "-c:a", "libmp3lame", "-b:a", "128k", "-t", f"{final_dur}", str(out_master_mp3.absolute())
        ]
    elif has_nat:
        cmd_mix = [
            "ffmpeg", "-y", "-i", str(padded_voice.absolute()),
            "-stream_loop", "-1", "-t", f"{final_dur}", "-i", str(nature_file.absolute()),
            "-filter_complex",
            f"[0:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,volume=1.0[v];"
            f"[1:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,volume=0.06[nat];"
            f"[v][nat]amix=inputs=2:duration=longest:normalize=0,afade=t=in:st=0:d=3,afade=t=out:st={fade_out_start}:d=6[aout]",
            "-map", "[aout]", "-c:a", "libmp3lame", "-b:a", "128k", "-t", f"{final_dur}", str(out_master_mp3.absolute())
        ]
    else:
        cmd_mix = [
            "ffmpeg", "-y", "-i", str(padded_voice.absolute()),
            "-af", f"afade=t=in:st=0:d=2,afade=t=out:st={fade_out_start}:d=5",
            "-c:a", "libmp3lame", "-b:a", "128k", "-t", f"{final_dur}", str(out_master_mp3.absolute())
        ]
    subprocess.run(cmd_mix, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return get_audio_duration(out_master_mp3)

def get_next_longform_folder(label: str) -> Path:
    clean = re.sub(r"[^a-zA-Z0-9]+", "_", label or "").strip("_")[:35] or "longform_prayer"
    nums = []
    for d in LONGFORM_DIR.iterdir():
        if d.is_dir():
            m = re.match(r"^LF(\d{3})_", d.name)
            if m: nums.append(int(m.group(1)))
    next_n = (max(nums) + 1) if nums else 1
    folder = LONGFORM_DIR / f"LF{next_n:03d}_{clean}"
    folder.mkdir(parents=True, exist_ok=True)
    return folder

def create_16x9_stage_overlay_png(out_png: Path, topic: str, scriptures: List[Dict[str, str]], w: int = 1920, h: int = 1080):
    from PIL import Image, ImageDraw, ImageFont
    ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(ov)
    for y in range(200):
        alpha = int(210 * (1.0 - y / 200.0))
        draw.line([(0, y), (w, y)], fill=(5, 8, 16, alpha))
    for y in range(h - 260, h):
        alpha = int(220 * ((y - (h - 260)) / 260.0))
        draw.line([(0, y), (w, y)], fill=(5, 8, 16, alpha))
    gold = (225, 185, 65, 235)
    gold_soft = (225, 185, 65, 130)
    draw.rounded_rectangle([28, 28, w - 28, h - 28], radius=26, outline=gold, width=4)
    draw.rounded_rectangle([40, 40, w - 40, h - 40], radius=20, outline=gold_soft, width=2)

    def _fnt(sz: int, black: bool = False):
        cands = [Path("C:/Windows/Fonts/ariblk.ttf") if black else Path("C:/Windows/Fonts/segoeuib.ttf"), Path("C:/Windows/Fonts/arialbd.ttf"), Path("C:/Windows/Fonts/arial.ttf")]
        for p in cands:
            if p.exists():
                try: return ImageFont.truetype(str(p), sz)
                except Exception: pass
        return ImageFont.load_default()

    f_top = _fnt(28, black=True)
    top_txt = f"DEEP SOUL PRAYER  •  {topic.upper()[:42]}"
    tb = draw.textbbox((0, 0), top_txt, font=f_top)
    tw, th = tb[2] - tb[0] + 60, tb[3] - tb[1] + 24
    bx = (w - tw) // 2
    by = 54
    draw.rounded_rectangle([bx, by, bx + tw, by + th], radius=th // 2, fill=(8, 12, 24, 230), outline=gold, width=2)
    draw.text(((w - (tb[2] - tb[0])) // 2 - tb[0], by + 11 - tb[1]), top_txt, font=f_top, fill=(255, 242, 175, 255))
    ov.save(str(out_png), "PNG")

def _make_lf_thumb(bg_image_path, journey_pkg, out_thumb_jpg, palette_name):
    import pro_design_addon as pda
    from types import SimpleNamespace
    from PIL import Image
    try:
        first_ref = journey_pkg["scriptures"][0]["ref"] if journey_pkg.get("scriptures") else "PSALM 91:1"
        dummy_script = SimpleNamespace(
            topic=journey_pkg.get("topic", "DEEP PRAYER"),
            verse_citation=first_ref,
            thumbnail_hook=f"PRAY THIS OVER {journey_pkg.get('topic', 'PRAYER').upper()[:18]}",
            title=f"Deep Prayer for {journey_pkg.get('topic', 'Peace')}"
        )
        thumbs = pda.render_pro_thumbnails(bg_image_path, dummy_script, out_thumb_jpg, palette_name=palette_name)
        if "16x9" in thumbs and Path(thumbs["16x9"]).exists():
            im16 = Image.open(thumbs["16x9"]).convert("RGB")
            im16.save(str(out_thumb_jpg), "JPEG", quality=95)
    except Exception:
        pass

def render_longform_16x9_video(master_audio_mp3: Path, out_video_mp4: Path, out_thumb_jpg: Path, journey_pkg: Dict[str, Any], bg_image_path: Path, bg_video_path: Path | None = None, visual_mode: str = "Looping Video Background (Fastest)", palette_name: str = "Gold Classic", subtitle_mode: str = "Instant Render (YouTube CC / .SRT)", progress_cb=None, **kwargs) -> bool:
    from PIL import Image
    w, h = 1920, 1080
    total_dur = get_audio_duration(master_audio_mp3)
    if total_dur <= 1.0:
        total_dur = float(journey_pkg.get("config", {}).get("target_seconds", 300))

    work_dir = out_video_mp4.parent / "temp_lf_render"
    work_dir.mkdir(parents=True, exist_ok=True)
    overlay_png = work_dir / "lf_overlay_16x9.png"
    create_16x9_stage_overlay_png(overlay_png, journey_pkg.get("topic", "Prayer"), journey_pkg.get("scriptures", []), w=w, h=h)
    
    ass_path = out_video_mp4.parent / "longform_subtitles.ass"
    if not ass_path.exists():
        ass_path = master_audio_mp3.parent / "longform_subtitles.ass"

    prebaked_bg_jpg = work_dir / "prebaked_bg_1080p.jpg"
    try:
        raw_bg = Image.open(bg_image_path).convert("RGB")
        ir = raw_bg.width / max(1, raw_bg.height)
        tr = w / h
        nw, nh = (int(h * ir), h) if ir > tr else (w, int(w / max(0.01, ir)))
        raw_bg = raw_bg.resize((nw, nh), Image.Resampling.LANCZOS)
        raw_bg = raw_bg.crop(((nw - w) // 2, (nh - h) // 2, (nw - w) // 2 + w, (nh - h) // 2 + h)).convert("RGBA")
        ov_im = Image.open(overlay_png).convert("RGBA")
        prebaked = Image.alpha_composite(raw_bg, ov_im).convert("RGB")
        prebaked.save(str(prebaked_bg_jpg), "JPEG", quality=94)
    except Exception:
        shutil.copy(bg_image_path, prebaked_bg_jpg)

    is_instant_mode = ("Instant" in str(subtitle_mode) or "CC" in str(subtitle_mode) or "SRT" in str(subtitle_mode))

    if is_instant_mode:
        if progress_cb: progress_cb(85, "⚡ Pre-baking loop & stream-copying in ~3s...")
        loop_segment = work_dir / "instant_base_loop.mp4"
        if "Video" in visual_mode and bg_video_path and bg_video_path.exists():
            cmd_base = ["ffmpeg", "-y", "-threads", "0", "-stream_loop", "-1", "-t", "16", "-i", str(bg_video_path.absolute()), "-loop", "1", "-t", "16", "-i", str(overlay_png.absolute()), "-filter_complex", f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps=24,format=yuv420p,setsar=1,eq=brightness=-0.07:contrast=1.10[v0];[v0][1:v]overlay=0:0:format=auto,format=yuv420p[vout]", "-map", "[vout]", "-an", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "24", str(loop_segment.absolute())]
        else:
            cmd_base = ["ffmpeg", "-y", "-threads", "0", "-loop", "1", "-t", "16", "-i", str(prebaked_bg_jpg.absolute()), "-vf", f"scale={w}:{h},fps=24,format=yuv420p", "-an", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "24", str(loop_segment.absolute())]
        subprocess.run(cmd_base, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        if loop_segment.exists() and loop_segment.stat().st_size > 5000:
            if progress_cb: progress_cb(92, "⚡ Muxing master video & audio...")
            cmd_instant = ["ffmpeg", "-y", "-stream_loop", "-1", "-i", str(loop_segment.absolute()), "-i", str(master_audio_mp3.absolute()), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-t", f"{total_dur:.2f}", str(out_video_mp4.absolute())]
            r_inst = subprocess.run(cmd_instant, capture_output=True, text=True, encoding="utf-8", errors="replace")
            if r_inst.returncode == 0 and out_video_mp4.exists():
                _make_lf_thumb(bg_image_path, journey_pkg, out_thumb_jpg, palette_name)
                return True

    sub_filter_str = f"subtitles='{ass_path.absolute().as_posix()}'" if ass_path.exists() else "null"
    enc_name, enc_opts = detect_hardware_video_encoder()

    if "Video" in visual_mode and bg_video_path and bg_video_path.exists():
        filter_complex = f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps=24,format=yuv420p,setsar=1,eq=brightness=-0.07:contrast=1.10[v0];[v0][1:v]overlay=0:0:format=auto,{sub_filter_str}[vout]"
        inputs = ["-stream_loop", "-1", "-t", f"{total_dur:.2f}", "-i", str(bg_video_path.absolute()), "-loop", "1", "-t", f"{total_dur:.2f}", "-i", str(overlay_png.absolute()), "-i", str(master_audio_mp3.absolute()), "-filter_complex", filter_complex, "-map", "[vout]", "-map", "2:a:0"]
    else:
        filter_complex = f"[0:v]scale={w}:{h},fps=24,format=yuv420p,{sub_filter_str}[vout]"
        inputs = ["-loop", "1", "-t", f"{total_dur:.2f}", "-i", str(prebaked_bg_jpg.absolute()), "-i", str(master_audio_mp3.absolute()), "-filter_complex", filter_complex, "-map", "[vout]", "-map", "1:a:0"]

    cmd = ["ffmpeg", "-y", "-threads", "0", *inputs, "-c:v", enc_name, *enc_opts, "-c:a", "aac", "-b:a", "128k", "-t", f"{total_dur:.2f}", "-progress", "pipe:1", str(out_video_mp4.absolute())]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, universal_newlines=True, encoding="utf-8", errors="replace")
    last_ui_update = 0.0
    if proc.stdout:
        for line in proc.stdout:
            if "out_time_us=" in line:
                try:
                    us_val = int(line.strip().split("=")[1])
                    curr_sec = us_val / 1000000.0
                    now_t = time.time()
                    if (now_t - last_ui_update) >= 1.2:
                        last_ui_update = now_t
                        pct = min(99, int(80 + (curr_sec / max(1.0, total_dur)) * 19))
                        if progress_cb: progress_cb(pct, f"🎬 Rendering 1080p Video: {format_mm_ss(curr_sec)} / {format_mm_ss(total_dur)}")
                except Exception: pass
    proc.wait()
    _make_lf_thumb(bg_image_path, journey_pkg, out_thumb_jpg, palette_name)
    return proc.returncode == 0 and out_video_mp4.exists()

def build_longform_youtube_metadata(journey_pkg: Dict[str, Any], chapters: List[Dict[str, Any]]) -> Tuple[str, str, List[str]]:
    import grace_of_lord_engine as gle
    import viral_researcher as vr
    topic = clean_ascii(journey_pkg.get("topic", "Peace")).strip()
    dur_lbl = journey_pkg.get("duration_label", "10 Minutes")
    scriptures = journey_pkg.get("scriptures", [])
    first_ref = scriptures[0]["ref"] if scriptures else "Psalm 91"
    all_refs = [v["ref"] for v in scriptures]

    ai_title = journey_pkg.get("youtube_title", "").strip()
    if not ai_title:
        ai_title = f"When You Need God's Breakthrough | {dur_lbl} Deep Prayer & Scripture ({first_ref})"[:98]

    ch_lines = []
    has_zero = False
    for ch in chapters:
        ts = ch.get("timestamp", "00:00")
        if ts.startswith("00:00") or ts.startswith("0:00"): has_zero = True
        ch_lines.append(f"{ts} - {ch.get('title', 'Prayer Movement')}")
    if not has_zero:
        ch_lines.insert(0, "00:00 - Entering God's Sanctuary")

    v_lines = [f"• {v['ref']}: \"{v['text'][:115]}...\"" for v in scriptures[:8]]
    try:
        import description_engine as de
        aff_links = de.load_affiliates()
    except Exception:
        aff_links = gle.load_affiliate_links()
    aff_block = "\n\n".join([f"{item['heading']}\n{item['url']}" for item in aff_links if item['url']])

    t_clean_slug = re.sub(r'[^a-zA-Z0-9]', '', topic.title())[:18]
    hashtags = [f"#{t_clean_slug}", "#ChristianPrayer", "#DeepPrayer", "#SoakingPrayer", "#BibleVerses", "#JesusChrist", "#FaithOverFear", "#PeaceOfGod"]
    
    desc = f"""🙏 {topic.upper()} — {dur_lbl.upper()} DEEP SOUL PRAYER & SCRIPTURE SOAKING ({first_ref}) ❤️

Take a slow, deep breath and enter into God's quiet sanctuary. If your heart has been carrying the silent weight of {topic}, let this {dur_lbl.lower()} prayer and scripture soaking journey bring supernatural peace, divine strength, and unshakeable hope into your home.

⏱️ CHAPTER TIMESTAMPS:
{chr(10).join(ch_lines)}

📖 SCRIPTURES PRAYED IN THIS VIDEO:
{chr(10).join(v_lines)}

----------------------------------------
💬 Let us agree in prayer! Leave your prayer request in the comments below or comment "AMEN" to seal this prayer over your family.

----------------------------------------
{aff_block}

Disclaimer: As an Amazon Associate, I earn from qualifying purchases at no extra cost to you.

----------------------------------------
{' '.join(hashtags)}
""".strip()

    raw_tag_candidates = [f"{topic} Prayer", f"Prayer for {topic}", f"{dur_lbl} Christian Prayer", "Deep Soul Prayer", "Soaking Prayer", "Christian Meditation", "Bible Verses For Sleep", "Jesus Christ"] + [v.replace(":", " ") for v in all_refs[:6]] + hashtags
    packed_tags = vr.pack_tags_to_limit(topic, hashtags, raw_tag_candidates, max_chars=380)
    return ai_title, desc, packed_tags