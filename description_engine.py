import os
import re
import json
import urllib.request
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=True)

AFFILIATE_FILE = BASE_DIR / "affiliate_links.json"

DUMMY_KEYWORDS = [
    "your-study-bible-link",
    "your-prayer-journal-link",
    "your-devotional-link",
    "example.com",
    "placeholder"
]

def load_affiliates() -> List[Dict[str, str]]:
    if AFFILIATE_FILE.exists():
        try:
            data = json.loads(AFFILIATE_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                slots = []
                for item in data[:5]:
                    slots.append({
                        "heading": str(item.get("heading", "")).strip(),
                        "url": str(item.get("url", "")).strip()
                    })
                while len(slots) < 5:
                    slots.append({"heading": "", "url": ""})
                return slots
        except Exception:
            pass
    return [{"heading": "", "url": ""} for _ in range(5)]

def save_affiliates(links: List[Dict[str, str]]) -> None:
    clean_data = []
    for item in links[:5]:
        clean_data.append({
            "heading": str(item.get("heading", "")).strip(),
            "url": str(item.get("url", "")).strip()
        })
    AFFILIATE_FILE.write_text(json.dumps(clean_data, indent=2, ensure_ascii=False), encoding="utf-8")

save_affiliate_links = save_affiliates
load_affiliate_links = load_affiliates

def clean_ascii(text: str) -> str:
    if not text:
        return ""
    t = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace("—", " - ").replace("…", "...")
    return re.sub(r"\s+", " ", re.sub(r"[^\x20-\x7E\u0900-\u097F]", "", t)).strip()

def build_affiliate_block() -> str:
    affs = load_affiliates()
    active_links = []
    for item in affs:
        heading = item.get("heading", "").strip()
        url = item.get("url", "").strip()
        if not url or any(dummy in url.lower() for dummy in DUMMY_KEYWORDS):
            continue
        if not heading:
            heading = "🔗 Recommended Resource:"
        if not heading.endswith(":"):
            heading += ":"
        active_links.append(f"{heading}\n{url}")
    if not active_links:
        return ""
    links_text = "\n\n".join(active_links)
    disclaimer = "Disclaimer: As an Amazon Associate, I earn from qualifying purchases at no extra cost to you."
    return f"{links_text}\n\n{disclaimer}"

def build_curated_description(
    topic: str,
    verse_ref: str,
    verse_text: str,
    reflection: str = "",
    prayer: str = "",
    style: str = "emotional",
    lang: str = "en"
) -> Dict[str, Any]:
    is_hi = (lang == "hi")
    aff_block = build_affiliate_block()
    sep = "----------------------------------------"

    if not reflection:
        if is_hi:
            reflection = "परमेश्वर का यह वचन हमें स्मरण कराता है कि वह हर परिस्थिति में हमारे साथ हैं और हमें अपनी शांति और सामर्थ्य देते हैं।"
        else:
            reflection = f"When you face {topic}, let the unshakeable truth of {verse_ref} bring comfort to your spirit today. God is with you through every storm."

    if not prayer:
        if is_hi:
            prayer = "प्रभु यीशु, मेरे जीवन में अपनी अलौकिक शांति, सामर्थ्य और छुटकारा दें, आमीन।"
        else:
            prayer = f"Lord Jesus, I surrender all worries concerning {topic} into Your hands. Fill my home with Your peace and divine breakthrough, Amen."

    aff_separator = f"\n\n{sep}\n{aff_block}\n\n{sep}" if aff_block else f"\n\n{sep}"

    if is_hi:
        hashtags = ["#HindiBible", "#YeshuMasih", "#Prarthana", "#Shorts", "#DailyPrayer"]
        pinned = f"क्या आप और आपका परिवार '{topic}' के लिए प्रार्थना चाहते हैं? कमेंट में AMEN ज़रूर लिखें! 🙏"

        if "teaching" in style.lower():
            parts = [
                f"📖 पवित्र बाइबिल वचन: {verse_ref}",
                f"\"{verse_text}\"",
                f"💡 वचन का आत्मिक अर्थ:\n{reflection}",
                f"🙏 आज की प्रार्थना:\n{prayer}",
                "कमेंट में \"AMEN\" लिखकर इस वचन की आशीष को अपने जीवन में ग्रहण करें! 🙏"
            ]
        else:
            parts = [
                f"🙏 रुकिए! यदि आप {topic} से परेशान हैं, तो प्रभु यीशु के इस वचन को सुनें ❤️",
                "परमेश्वर आपके हर आंसू को देखते हैं और आपके दिल के दर्द को जानते हैं। आप अकेले नहीं हैं।",
                f"📖 पवित्र बाइबिल वचन: {verse_ref}",
                f"\"{verse_text}\"",
                f"💡 आत्मिक शांति:\n{reflection}",
                f"🙏 समर्पण प्रार्थना:\n{prayer}",
                "👇 कमेंट में \"AMEN\" लिखें और विश्वास करें कि प्रभु आपके जीवन में नया मार्ग खोल रहे हैं! 🙏"
            ]

        body = "\n\n".join(parts)
        desc = f"{body}{aff_separator}\n{' '.join(hashtags)}"
    else:
        topic_tag = re.sub(r"[^a-zA-Z0-9]", "", topic.title())[:18]
        hashtags = [f"#{topic_tag}" if topic_tag else "#Faith", "#ChristianShorts", "#DailyPrayer", "#BibleVerse", "#JesusChrist"]
        pinned = f"How can our community pray for you regarding {topic}? Drop an 'AMEN' below so we can agree in faith! 🙏"

        if "compact" in style.lower():
            parts = [
                f"🙏 A 20-Second Prayer for {topic} ({verse_ref}) ❤️",
                f"📖 Scripture: {verse_ref}\n\"{verse_text}\"",
                f"🙏 Prayer: {prayer}",
                "Comment \"AMEN\" to receive this blessing today! 🙏"
            ]
        elif "teaching" in style.lower():
            parts = [
                f"📖 {topic.upper()} | God's Promise in {verse_ref} ❤️",
                f"📖 Scripture: {verse_ref}\n\"{verse_text}\"",
                f"💡 Spiritual Reflection:\n{reflection}",
                f"🙏 Prayer of Faith:\n{prayer}",
                "Type \"AMEN\" in the comments to anchor this truth in your heart! 🙏"
            ]
        else:
            parts = [
                f"🙏 DON'T GIVE UP! PRAY THIS OVER {topic.upper()}! ❤️",
                "Before you let fear or exhaustion overwhelm your heart, take a deep breath and pray with me.\nGod sees every tear you hide, hears every prayer you whisper, and knows every burden you carry.",
                f"📖 Scripture: {verse_ref}\n\"{verse_text}\"",
                f"💡 Comforting Truth:\n{reflection}",
                f"🙏 Surrender Prayer:\n{prayer}",
                "👇 If you are trusting God through this season, comment \"AMEN\"!",
                "❤️ Share this prayer with someone who is silently fighting and needs peace today."
            ]

        body = "\n\n".join(parts)
        desc = f"{body}{aff_separator}\n{' '.join(hashtags)}"

    return {
        "description": desc.strip(),
        "pinned_comment": pinned,
        "hashtags": hashtags,
        "style": style,
        "char_count": len(desc.strip())
    }

def research_and_generate_description_ai(
    topic: str,
    verse_ref: str,
    verse_text: str,
    reflection: str = "",
    prayer: str = "",
    style: str = "emotional",
    lang: str = "en",
    custom_instructions: str = ""
) -> Dict[str, Any]:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    or_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    
    aff_block = build_affiliate_block()
    sep = "----------------------------------------"
    aff_separator = f"\n\n{sep}\n{aff_block}\n\n{sep}" if aff_block else f"\n\n{sep}"

    prompt = f"""You are an elite YouTube Shorts Strategist for a Christian devotional channel.
Topic: {topic}
Scripture: {verse_ref} (\"{verse_text[:140]}\")
Reflection: {reflection[:180]}
Prayer: {prayer[:140]}
Style: {style}
Language: {'Hindi/Hinglish' if lang == 'hi' else 'English'}
Custom Instructions: {custom_instructions or 'None'}

Generate a clean, high-retention YouTube Short description:
1. Opening line with emojis and hook.
2. 2-sentence emotional connection explaining that God hears their prayer.
3. Scripture citation and exact verse text.
4. Reflection and Prayer.
5. High-engagement Call-To-Action asking viewers to comment 'AMEN'.
6. Do NOT include bracket tags like [HASHTAGS] or [/HASHTAGS].
7. Include 5 viral hashtags at the very bottom.
8. Include 1 engaging question for the pinned comment.

Respond ONLY with valid JSON:
{{
  "body_text": "The complete description text without affiliate links or hashtags",
  "pinned_comment": "1 engaging community question/prompt",
  "hashtags": ["#Tag1", "#Tag2", "#Tag3", "#Tag4", "#Tag5"]
}}"""

    def _parse_ai(raw_text: str) -> Dict[str, Any]:
        m = re.search(r"\{[\s\S]*\}", raw_text)
        if m:
            parsed = json.loads(m.group(0))
            body = parsed.get("body_text", "").strip()
            hts = parsed.get("hashtags", ["#DailyPrayer", "#BibleVerse", "#Shorts"])
            pinned = parsed.get("pinned_comment", "Comment AMEN to receive this prayer! 🙏")
            ht_str = " ".join([h if h.startswith("#") else f"#{h}" for h in hts[:5]])
            full_desc = f"{body}{aff_separator}\n{ht_str}".strip()
            return {
                "description": full_desc,
                "pinned_comment": pinned,
                "hashtags": hts[:5],
                "style": "AI-Generated",
                "char_count": len(full_desc)
            }
        return {}

    if api_key:
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.8}
        }
        data_bytes = json.dumps(payload).encode("utf-8")
        for m_id in ["gemini-3.5-flash-lite", "gemini-3.7-flash", "gemini-2.5-flash", "gemini-3.8-flash"]:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{m_id}:generateContent?key={api_key}"
                req = urllib.request.Request(url, headers={"Content-Type": "application/json"}, data=data_bytes)
                with urllib.request.urlopen(req, timeout=12) as resp:
                    r_json = json.loads(resp.read().decode("utf-8"))
                    raw_t = r_json["candidates"][0]["content"]["parts"][0]["text"]
                    res_pkg = _parse_ai(raw_t)
                    if res_pkg:
                        res_pkg["style"] = f"AI-Generated ({m_id})"
                        return res_pkg
            except Exception:
                continue

    if or_key:
        for model in ["openrouter/free", "google/gemma-4-26b-a4b-it:free"]:
            try:
                req = urllib.request.Request(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {or_key}", "Content-Type": "application/json"},
                    data=json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}]}).encode("utf-8")
                )
                with urllib.request.urlopen(req, timeout=12) as response:
                    data = json.loads(response.read().decode("utf-8"))
                    raw_t = data["choices"][0]["message"]["content"]
                    res_pkg = _parse_ai(raw_t)
                    if res_pkg:
                        res_pkg["style"] = f"AI-Generated ({model})"
                        return res_pkg
            except Exception:
                continue

    # 100% Fail-safe local generator if AI is totally offline
    return build_curated_description(topic, verse_ref, verse_text, reflection, prayer, style=style, lang=lang)

def lock_description_for_video(video_path: Path, description: str, pinned_comment: str = "") -> None:
    meta_path = video_path.with_suffix(".json")
    data = {}
    if meta_path.exists():
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data["description"] = description.strip()
    data["description_locked"] = True
    if pinned_comment:
        data["pinned_comment"] = pinned_comment.strip()
    meta_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    txt_path = video_path.parent / "youtube_details.txt"
    title = data.get("title", "")
    tags = data.get("tags", [])
    nl = chr(10)
    txt_path.write_text(
        f"TITLE:{nl}{title}{nl}{nl}DESCRIPTION:{nl}{description.strip()}{nl}{nl}TAGS:{nl}{', '.join(tags)}{nl}",
        encoding="utf-8"
    )

    if pinned_comment:
        pin_file = video_path.parent / "pinned_comment.txt"
        pin_file.write_text(pinned_comment.strip(), encoding="utf-8")
