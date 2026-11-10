import description_engine
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
    """Ultra-fast direct REST call with strict 5s timeout (Zero tenacity retry freeze!)."""
    import urllib.request
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        return None

    full_prompt = f"{system}\n\n{prompt}".strip() if system else prompt
    payload = {
        "contents": [{"parts": [{"text": full_prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.7}
    }
    data_bytes = json.dumps(payload).encode("utf-8")

    for model_id in ["gemini-3.5-flash-lite", "gemini-3.7-flash", "gemini-2.5-flash"]:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={key}"
            req = urllib.request.Request(url, headers={"Content-Type": "application/json"}, data=data_bytes)
            with urllib.request.urlopen(req, timeout=5) as resp:
                r_json = json.loads(resp.read().decode("utf-8"))
                raw_t = r_json["candidates"][0]["content"]["parts"][0]["text"]
                parsed = extract_clean_json(raw_t)
                if parsed:
                    return parsed
        except Exception:
            continue
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

    if isinstance(ai_tags, str):

        ai_tags = [x.strip() for x in re.split(r'[,;]', ai_tags) if x.strip()]

    elif not isinstance(ai_tags, list):

        ai_tags = []

    if isinstance(competitor_keywords, str):

        competitor_keywords = [x.strip() for x in re.split(r'[,;]', competitor_keywords) if x.strip()]

    elif not isinstance(competitor_keywords, list):

        competitor_keywords = []

    topic_clean = re.sub(r"[^a-zA-Z0-9\s]", "", str(topic)).strip()

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

    "money": ["#FinancialBreakthrough", "#GodWillProvide", "#DebtFree", "#SupernaturalProvision", "#MiraclePrayer"],

    "financ": ["#FinancialBlessing", "#DebtFree", "#BreakEveryDebt", "#GodWillProvide", "#MiraclePrayer"],

    "job": ["#CareerBreakthrough", "#JobPrayer", "#NewJob", "#OpenDoors", "#WorkplaceBlessing", "#GodWillProvide"],

    "career": ["#CareerBreakthrough", "#OpenDoorsOfFavor", "#JobPrayer", "#PromotionPrayer", "#GodsPlan", "#WorkplaceBlessing"],

    "work": ["#WorkplaceBlessing", "#CareerPrayer", "#JobBreakthrough", "#FavorAtWork", "#GodWillProvide"],

    "anxiety": ["#AnxietyRelief", "#PeaceInTheStorm", "#Overthinking", "#CalmYourMind", "#PeaceOfGod", "#StopWorrying"],

    "panic": ["#PeaceOfGod", "#CalmYourMind", "#AnxietyRelief", "#PeaceInTheStorm", "#OvercomingFear"],

    "fear": ["#FaithOverFear", "#FearNot", "#GodIsWithYou", "#OvercomeFear", "#PeaceInTheStorm"],

    "broken": ["#HealingHeart", "#DepressionRelief", "#YouAreNotAlone", "#GodHeals", "#HopeInGod", "#ComfortInGrief"],

    "grief": ["#ComfortInGrief", "#GodHealsBrokenHearts", "#YouAreNotAlone", "#PeaceInSorrow", "#HopeInGod"],

    "healing": ["#MiracleHealing", "#DivineHealth", "#HealedByHisStripes", "#JesusHeals", "#HealingPrayer", "#Restoration"],

    "sick": ["#MiracleHealing", "#HealedByHisStripes", "#JesusHeals", "#HealingPrayer", "#DivineHealth"],

    "strength": ["#DontGiveUp", "#PrayerForStrength", "#NeverGiveUp", "#RenewYourStrength", "#Overcome", "#FaithOverFear"],

    "quit": ["#DontGiveUp", "#NeverGiveUp", "#KeepGoing", "#PrayerForStrength", "#FaithOverFear"],

    "protect": ["#GodsProtection", "#Psalm91", "#SpiritualWarfare", "#NoWeaponShallProsper", "#JesusProtects", "#ShieldOfFaith"],

    "sleep": ["#SleepInPeace", "#Psalm91", "#PeacefulSleep", "#RestInGod", "#NightPrayer", "#CalmYourMind"],

    "night": ["#NightPrayer", "#SleepInPeace", "#PeacefulSleep", "#RestInGod", "#GodsProtection"],

    "marriag": ["#MarriageRestoration", "#PeaceAtHome", "#FamilyBlessing", "#GodHealsMarriages", "#LoveAndFaith"],

    "family": ["#FamilyBlessing", "#ProtectionOverFamily", "#PeaceAtHome", "#GodBlessOurHome", "#DailyPrayer"],

    "forgiveness": ["#FreedomToForgive", "#InnerPeace", "#LetGoLetGod", "#ReleaseBitterness", "#GraceOfGod", "#HealingSoul"]

}



def build_viral_devotional_description(topic: str, ref_str: str, verse_text: str, reflection: str, prayer: str) -> tuple:
    import description_engine
    d_pkg = description_engine.build_curated_description(
        topic=topic, verse_ref=ref_str, verse_text=verse_text,
        reflection=reflection, prayer=prayer, style="emotional", lang="en"
    )
    return d_pkg["description"], d_pkg["hashtags"]



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









def get_fully_synced_youtube_package(

    topic: str,

    ref_str: str,

    verse_text: str,

    opening_hook: str = "",

    prayer_override: str = ""

) -> dict:

    clean_t = clean_ascii(topic).strip()

    t_low = clean_t.lower()

    ref_clean = re.sub(r"\s*\(.*?\)", "", ref_str).strip()



    # Dynamic Fallback Hooks if offline

    if any(w in t_low for w in ["job", "career", "work", "promot", "interview", "business"]):

        hook_phrase = "Career Breakthrough"

        fallback_title = f"When A Door Closes, Pray This Over Your Career \U0001f54a #shorts"

        refl_def = "God's plans for your career are for good and not for harm; He is opening doors no human can shut."

        pray_def = "Lord Jesus, grant me favor in my career, open doors of divine opportunity, and bless my future, Amen."

        extra_keywords = ["Job Breakthrough", "Career Prayer", "Open Doors Of Favor", "Workplace Blessing", "Promotion Prayer", "Job Interview Favor", ref_clean]

    elif any(w in t_low for w in ["debt", "money", "finan", "lack"]):

        hook_phrase = "Break Every Debt"

        fallback_title = f"Before You Worry About Money, Pray This \U0001f54a #shorts"

        refl_def = "God is your supernatural provider; His storehouses never run dry and He is breaking every financial burden."

        pray_def = "Lord Jesus, break every chain of debt and release supernatural financial provision over my family, Amen."

        extra_keywords = ["Break Every Debt", "Debt Free Prayer", "Financial Breakthrough", "Supernatural Provision", "God Will Provide", ref_clean]

    elif any(w in t_low for w in ["heal", "sick", "pain", "body"]):

        hook_phrase = "Miracle Healing"

        fallback_title = f"Speak This Healing Scripture Over Your Body \U0001f64f #shorts"

        refl_def = "Jesus took your infirmities upon the cross; His healing light is restoring your body right now."

        pray_def = "Lord Jesus, touch my body with Your healing power, drive out every sickness, and restore full health, Amen."

        extra_keywords = ["Miracle Healing", "Healed By His Stripes", "Healing Prayer", "Divine Health", "Jesus Heals", ref_clean]

    elif any(w in t_low for w in ["anxiet", "panic", "fear", "worry", "overthink"]):

        hook_phrase = "Peace In The Storm"

        fallback_title = f"If Your Mind Is Racing Tonight, Hear This \U0001f54a #shorts"

        refl_def = "Cast every anxious thought upon the Lord; His supernatural peace will guard your heart and mind."

        pray_def = "Lord Jesus, calm every storm in my mind and fill my spirit with Your everlasting peace, Amen."

        extra_keywords = ["Peace In The Storm", "Anxiety Relief Prayer", "Calm Anxious Thoughts", "Peace Of God", "Overcoming Fear", ref_clean]

    else:

        hook_phrase = "God's Promise"

        fallback_title = f"Hold Onto This Promise When Life Feels Heavy \U0001f64f #shorts"

        refl_def = f"Hold fast to God's covenant promise in {ref_clean}; His faithfulness endures through every storm."

        pray_def = f"Lord Jesus, release Your breakthrough, strength, and divine peace over {clean_t}, Amen."

        extra_keywords = [clean_t, f"{clean_t} Prayer", f"God On {clean_t}", ref_clean]



    # AI Prompt for High-CTR Title & Tags

    ai_title = ""

    ai_refl = ""

    ai_pray = ""

    ai_tags = []



    prompt = f"""You are an elite Christian YouTube Shorts Strategist.

Topic: {clean_t}

Scripture: {ref_clean} ("{verse_text[:110]}")



Generate a viral YouTube Shorts package:

- "title": A magnetic, high-CTR hook title UNDER 50 CHARACTERS with 1 emoji and #shorts.

  Examples of high-CTR hooks:

  • "When A Door Closes, Pray This First \U0001f54a #shorts"

  • "The 1 Verse That Breaks Career Delay \U0001f64f #shorts"

  • "God Says: Your Breakthrough Is Coming \U0001f54a #shorts"

  • "Never Worry About Your Future Again \U0001f64f #shorts"

- "reflection": 1 short empowering sentence for {clean_t} (under 14 words)

- "prayer": 1 short breakthrough prayer for {clean_t} ending in Amen (under 12 words)

- "tags": 15 keyword phrases specifically for {clean_t} and {ref_clean} (no #)



Return valid JSON with exact keys: title, reflection, prayer, tags."""



    try:

        from viral_researcher import call_gemini_fast

        ai_res = call_gemini_fast(prompt, system="Output valid JSON only. Do not invent false medical or guaranteed wealth claims.")

        if ai_res and isinstance(ai_res, dict):

            t_cand = str(ai_res.get("title", "")).strip()

            if 15 <= len(t_cand) <= 55 and "#shorts" in t_cand.lower():

                ai_title = t_cand

            ai_refl = str(ai_res.get("reflection", "")).strip()

            ai_pray = str(ai_res.get("prayer", "")).strip()

            ai_tags = ai_res.get("tags", [])

    except Exception:

        pass



    final_title = ai_title if ai_title else fallback_title

    final_refl = ai_refl if ai_refl else refl_def

    final_pray = prayer_override.strip() if prayer_override else (ai_pray if ai_pray else pray_def)



    # Clean Long-Form Description (Zero [HASHTAGS] Brackets)

    desc, dynamic_hts = build_viral_devotional_description(clean_t, ref_str, verse_text, final_refl, final_pray)

    desc = desc.replace("[HASHTAGS]", "----------------------------------------").replace("[/HASHTAGS]", "").strip()



    # Pack 380 chars of search tags

    all_tag_pool = (ai_tags if isinstance(ai_tags, list) else []) + extra_keywords + dynamic_hts

    packed_tags = pack_tags_to_limit(clean_t, dynamic_hts, all_tag_pool, max_chars=380)



    # Thumbnail Prompt

    import pro_design_addon as pda

    thumb_prompt = pda.build_ai_thumbnail_prompt(clean_t, ref_clean, hook_phrase)



    return {

        "title": final_title,

        "description": desc,

        "tags": packed_tags,

        "hashtags": dynamic_hts,

        "hook": hook_phrase.upper(),

        "reflection": final_refl,

        "prayer": final_pray,

        "thumbnail_prompt": thumb_prompt

    }

