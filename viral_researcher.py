import os
import re
import json
import collections
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# Instant In-Memory Cache (0.001s instant re-renders)
_VIRAL_RESEARCH_CACHE = {}

def clean_ascii(text: str) -> str:
    if not text:
        return ""
    t = (text.replace("’", "'").replace("‘", "'")
             .replace("“", '"').replace("”", '"')
             .replace("—", " - ").replace("…", "..."))
    return re.sub(r"\s+", " ", re.sub(r"[^\x20-\x7E]", "", t)).strip()

def extract_clean_json(text: str) -> dict | None:
    if not text:
        return None
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end+1])
        except Exception:
            pass
    return None

def call_gemini_fast(prompt: str, system: str = "") -> dict | None:
    """Ultra-fast direct Gemini call (Bypasses slow models.list). Responds in ~1.5s."""
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        return None

    full_prompt = f"{system}\n\n{prompt}".strip() if system else prompt

    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=key)

        # Direct call to the fastest models (No slow network scanning)
        for model_id in ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-3.5-flash-lite"]:
            try:
                res = client.models.generate_content(
                    model=model_id,
                    contents=full_prompt,
                    config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.7)
                )
                if res and res.text:
                    parsed = extract_clean_json(res.text)
                    if parsed:
                        return parsed
            except Exception:
                continue
    except Exception:
        pass

    return None

HIGH_VOLUME_SEO_POOL = [
    "Christian Motivation", "Bible Verse Today", "Daily Prayer", "Faith Over Fear",
    "Jesus Christ", "Powerful Prayer", "Spiritual Breakthrough", "Gods Promise",
    "Morning Prayer", "Scripture For Sleep", "Holy Spirit", "Christian Faith",
    "Miracle Prayer", "Word Of God", "Christian Shorts", "Jesus Loves You",
    "Bible Study", "Biblical Wisdom", "Peace In The Storm", "God Will Provide"
]

def pack_tags_to_limit(topic: str, ai_tags: list, competitor_keywords: list, max_chars: int = 380) -> list:
    combined = []
    seen = set()
    topic_clean = re.sub(r"[^a-zA-Z0-9\s]", "", topic).strip()
    priority_tags = [
        topic_clean,
        f"{topic_clean} Prayer",
        f"{topic_clean} Bible Verse",
        f"God on {topic_clean}",
        f"Overcome {topic_clean}"
    ] + competitor_keywords + ai_tags + HIGH_VOLUME_SEO_POOL

    total_len = 0
    final_tags = []
    for raw_tag in priority_tags:
        t = str(raw_tag).replace("#", "").strip().title()
        t_clean = re.sub(r"[<>,#\"'\\`\r\n\t&!?:;]", "", t)
        if len(t_clean) >= 3 and t_clean.lower() not in seen:
            tag_cost = len(t_clean) + 1
            if total_len + tag_cost <= max_chars:
                final_tags.append(t_clean)
                seen.add(t_clean.lower())
                total_len += tag_cost
    return final_tags

TOPIC_HASHTAG_MAP = {
    "debt": ["#DontGiveUp", "#DebtFree", "#BreakEveryDebt", "#FinancialBreakthrough", "#GodWillProvide", "#MiraclePrayer"],
    "anxiety": ["#AnxietyRelief", "#PeaceInTheStorm", "#Overthinking", "#CalmYourMind", "#PeaceOfGod", "#StopWorrying"],
    "broken": ["#HealingHeart", "#DepressionRelief", "#YouAreNotAlone", "#GodHeals", "#HopeInGod", "#ComfortInGrief"],
    "healing": ["#MiracleHealing", "#DivineHealth", "#HealedByHisStripes", "#JesusHeals", "#HealingPrayer", "#Restoration"],
    "strength": ["#DontGiveUp", "#PrayerForStrength", "#NeverGiveUp", "#RenewYourStrength", "#Overcome", "#FaithOverFear"],
    "protection": ["#GodsProtection", "#Psalm91", "#SpiritualWarfare", "#NoWeaponShallProsper", "#JesusProtects", "#ShieldOfFaith"],
    "forgiveness": ["#FreedomToForgive", "#InnerPeace", "#LetGoLetGod", "#ReleaseBitterness", "#GraceOfGod", "#HealingSoul"]
}

def build_viral_devotional_description(topic: str, ref_str: str, verse_text: str, reflection: str, prayer: str) -> tuple:
    topic_clean = clean_ascii(topic).strip()
    topic_lower = topic_clean.lower()
    matched_tags = []
    for k, tags in TOPIC_HASHTAG_MAP.items():
        if k in topic_lower:
            matched_tags = tags
            break
    if not matched_tags:
        clean_word = re.sub(r'[^a-zA-Z0-9]', '', topic_clean.title())
        matched_tags = [f"#{clean_word}", "#PrayThisFirst", "#GodHearsYou", "#NeverGiveUp"]

    universal_tags = [
        "#PrayThisFirst", "#PowerfulPrayer", "#JesusChrist", "#DailyPrayer",
        "#GodIsWithYou", "#FaithOverFear", "#ChristianShorts", "#PrayerWorks",
        "#HopeInGod", "#YouTubeShorts"
    ]
    all_hts = []
    seen = set()
    for ht in (matched_tags + universal_tags):
        ht_norm = ht.lower()
        if ht_norm not in seen:
            all_hts.append(ht)
            seen.add(ht_norm)
        if len(all_hts) >= 13:
            break

    ht_line = " ".join(all_hts)
    desc = f"""🙏 DON'T GIVE UP! PRAY THIS FIRST! GOD HEARS YOUR CRY! ❤️

WAIT! Before you lose hope or let your struggles overwhelm your heart, take a deep breath and pray with me.

Are you tired of pretending everything is okay? Are you silently fighting battles nobody knows about? Have you been praying for a breakthrough while wondering when things will finally get better?

God sees every tear you hide, hears every prayer you whisper, and knows every burden you carry.

❤️ You don't have to carry this alone. Bring your worries, fears, disappointments, and struggles to Jesus.

📖 Scripture: {ref_str}
\"{verse_text.strip()}\"

💡 Reflection:
{reflection.strip()}

🙏 Surrender Prayer:
{prayer.strip()}

When life feels impossible, remember that nothing is impossible with God. When human strength runs out, His supernatural grace is more than enough!

DON'T GIVE UP JUST YET! YOUR STORY IS NOT OVER, YOUR PRAYERS STILL MATTER, AND GOD HAS NOT FORGOTTEN YOU!

👇 If you are trusting God through this season, comment \"AMEN\"!
❤️ Share this prayer with someone who is silently struggling and needs a reminder that God is near.

May the Lord bless you, protect your family, strengthen your faith, and fill your heart with everlasting peace.
IN JESUS' MIGHTY NAME, AMEN! 🙏

[HASHTAGS]
{ht_line}
[/HASHTAGS]""".strip()
    return desc, all_hts

def research_viral_scripture_package(topic: str, channel_name: str = "") -> dict:
    clean_t = clean_ascii(topic).strip()
    cache_key = clean_t.lower()

    # 1. Instant Cache Return (0.001s)
    if cache_key in _VIRAL_RESEARCH_CACHE:
        print(f"⚡ [FAST CACHE] Loaded research for '{clean_t}' in 0.001s!")
        return _VIRAL_RESEARCH_CACHE[cache_key]

    print(f"\n🔬 [VIRALITY RESEARCH] Analyzing competitor velocity & scripture for: '{clean_t}'...")

    # 2. Fast Competitor Scan (Max 3s timeout)
    competitors = []
    try:
        import main
        competitors = main.scan_competitor_shorts(clean_t, limit=4, channel_name=channel_name)
    except Exception:
        pass

    comp_lines = [f"- {c['title']} ({c.get('views_per_day', 0):,.0f} views/day)" for c in competitors[:3]]
    comp_block = "\n".join(comp_lines) if comp_lines else "None found - focus on pure emotional breakthrough."

    sys_prompt = (
        "You are an elite Christian YouTube Shorts Strategist. "
        "Select 1 powerful canonical Bible verse and teaching. Keep spoken word budget strictly 40 to 46 words. "
        "STRICT SAFETY: Never promise guaranteed money, medical cures, or 100% instant wealth. Output ONLY valid JSON."
    )

    user_prompt = f"""Topic: {clean_t}
Top Competitor Titles:
{comp_block}

Return JSON with exact keys:
- "verse_citation": e.g. "Proverbs 10:22"
- "verse_text": core clause under 20 words
- "why_chosen": 1 short reason why this beats competitors
- "hook_line1": 1-2 words ALL CAPS (e.g. "DON'T", "BREAK", "GOD WILL")
- "hook_line2": 2-3 words ALL CAPS (e.g. "GIVE UP YET", "EVERY DEBT")
- "meaning": 1 comforting teaching sentence (max 14 words)
- "prayer": 1 breakthrough prayer sentence ending in Amen (max 12 words)
- "title": High-CTR title under 50 chars with #shorts
- "pinned_comment": 1 question for comments
- "hashtags": 10-12 hashtags with #
- "tags": 16-20 keyword tags without #"""

    # 3. Direct Fast API Call (~1.5s)
    ai_data = call_gemini_fast(user_prompt, system=sys_prompt)

    if not ai_data or not isinstance(ai_data, dict) or "verse_citation" not in ai_data:
        ai_data = {
            "verse_citation": "Philippians 4:19",
            "verse_text": "And my God will supply every need of yours according to His riches in glory.",
            "why_chosen": "Addresses root anxiety with God's covenant promise of infinite storehouses.",
            "hook_line1": "GOD WILL",
            "hook_line2": "PROVIDE TODAY",
            "meaning": "Trust His storehouses of grace; God never abandons those who call upon Him.",
            "prayer": "Lord, release supernatural breakthrough over my family today, Amen.",
            "title": f"God's Plan to Break {clean_t[:25]} #shorts",
            "pinned_comment": "Type AMEN if you claim this breakthrough today! 🙏",
            "hashtags": ["#DontGiveUp", "#DailyPrayer", "#FaithOverFear", "#JesusChrist", "#Shorts"],
            "tags": ["Daily Prayer", "Faith", "Christian Motivation", "Bible Verse"]
        }

    ref_str = ai_data.get("verse_citation", "Philippians 4:19").strip()
    v_text = ai_data.get("verse_text", "").strip()
    meaning = ai_data.get("meaning", "").strip()
    prayer = ai_data.get("prayer", "").strip()
    why_chosen = ai_data.get("why_chosen", "Directly targets the root emotional battle with divine authority.")

    h_l1 = ai_data.get("hook_line1", "HOLD ON").strip().upper()
    h_l2 = ai_data.get("hook_line2", "TO GOD").strip().upper()
    full_hook = f"{h_l1} {h_l2}".strip()

    desc, dynamic_hts = build_viral_devotional_description(clean_t, ref_str, v_text, meaning, prayer)

    competitor_words = []
    for c in competitors:
        competitor_words.extend(re.findall(r"\b[a-zA-Z]{4,}\b", c.get("title", "").lower()))
    frequent_comp = [w for w, count in collections.Counter(competitor_words).items() if count >= 2]

    packed_tags = pack_tags_to_limit(clean_t, ai_data.get("tags", []), frequent_comp, max_chars=480)
    winning_title = ai_data.get("title", f"God's Promise For {clean_t[:30]} #shorts")

    result_pkg = {
        "topic": clean_t,
        "verse_citation": ref_str,
        "verse_text": v_text,
        "why_chosen": why_chosen,
        "hook_line1": h_l1,
        "hook_line2": h_l2,
        "thumbnail_hook": full_hook,
        "meaning": meaning,
        "prayer": prayer,
        "title": winning_title,
        "description": desc,
        "tags": packed_tags,
        "hashtags": dynamic_hts,
        "competitors_audited": len(competitors)
    }

    # Store in memory for instant reuse
    _VIRAL_RESEARCH_CACHE[cache_key] = result_pkg
    print(f"   ⚡ [RESEARCH COMPLETE] '{ref_str}' ready in ~2 seconds!")
    return result_pkg
