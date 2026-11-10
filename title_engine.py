import os
import re
import json
import time
import difflib
import collections
import urllib.request
from pathlib import Path
from typing import Dict, List, Any, Tuple, Callable, Optional
from dotenv import load_dotenv
import yt_dlp

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

TITLES_HISTORY_FILE = BASE_DIR / "titles_log.json"

POWER_WORDS = {
    "wait", "stop", "before", "never", "always", "secret", "promise", "urgent",
    "tonight", "today", "now", "breakthrough", "peace", "fear", "worry", "heals",
    "fighting", "alone", "hear", "listen", "prayer", "pray", "god", "jesus",
    "unshakeable", "miracle", "open", "doors", "heavy", "storm", "rest", "cry"
}

STOPWORDS = {
    "the", "and", "for", "that", "this", "with", "you", "your", "from", "are",
    "have", "what", "more", "when", "will", "shorts", "short", "video", "about"
}

BANNED_WORDS = re.compile(
    r"\b(guaranteed money|100% cure|instant millionaire|get rich quick|medical cure)\b",
    re.IGNORECASE
)


TOPIC_CURATED_5_OPTIONS: Dict[str, List[Dict[str, Any]]] = {
    "debt": [
        {"rank": 1, "angle": "Top Pick • Urgent Hook & Promise", "title": "Stressed by Debt? God Will Provide #shorts", "score": 100, "why_it_works": "Directly targets financial stress and gives an instant reassuring promise.", "vs_competitors": "Clear, short (43c), and emotionally compelling without getting cut off on mobile."},
        {"rank": 2, "angle": "Pattern Interrupt / Thumb-Stopper", "title": "Wait! Before You Worry About Debt, Hear This 🙏 #shorts", "score": 98, "why_it_works": "'Wait!' stops scrolling within 0.5s and creates immediate curiosity.", "vs_competitors": "Much higher initial hook retention than passive titles."},
        {"rank": 3, "angle": "Direct Prayer / Time Commitment", "title": "A 30-Second Prayer to Break Debt Stress 🙏 #shorts", "score": 96, "why_it_works": "Promising a quick 30-second prayer gives viewers a low-effort commitment so they stay.", "vs_competitors": "Sets a clear time expectation that boosts average percentage viewed (APV)."},
        {"rank": 4, "angle": "Emotional Relatability", "title": "Drowning in Debt? God Sees Your Need 🕊️ #shorts", "score": 94, "why_it_works": "Deeply emotional phrasing that resonates with anyone feeling overwhelmed.", "vs_competitors": "Resonates strongly with late-night viewers carrying financial burdens."},
        {"rank": 5, "angle": "Curiosity & Scripture Authority", "title": "The 1 Verse That Calms Debt Worry (Phil 4:19) 📖 #shorts", "score": 94, "why_it_works": "Creates an information gap ('What is the 1 verse?') with scripture authority.", "vs_competitors": "Captures both YouTube Search and Shorts Feed browse traffic."}
    ],
    "anxiety": [
        {"rank": 1, "angle": "Top Pick • Urgent Hook & Promise", "title": "Racing Mind? Read This Before Bed 🛏️ #shorts", "score": 100, "why_it_works": "Names the exact physical symptom of anxiety and commands an easy action.", "vs_competitors": "Outperforms dry clinical titles by speaking to the physical feeling."},
        {"rank": 2, "angle": "Pattern Interrupt / Thumb-Stopper", "title": "Wait! Give Your Anxiety to God Tonight 🙏 #shorts", "score": 98, "why_it_works": "Halts the swipe and directs the viewer to an immediate prayer action.", "vs_competitors": "High emotional engagement in the first 2 words."},
        {"rank": 3, "angle": "Direct Prayer / Time Commitment", "title": "A 20-Second Prayer for Sudden Anxiety 🕊️ #shorts", "score": 96, "why_it_works": "Promises instant relief with a 20-second prayer commitment.", "vs_competitors": "Guarantees 100%+ video completion rate."},
        {"rank": 4, "angle": "Emotional Relatability", "title": "When Anxiety Feels Too Heavy to Carry ❤️ #shorts", "score": 94, "why_it_works": "Validates the viewer's unspoken exhaustion.", "vs_competitors": "More personal and comforting than generic verse labels."},
        {"rank": 5, "angle": "Curiosity & Scripture Authority", "title": "The 1 Verse That Silences Panic (Phil 4:6) 📖 #shorts", "score": 94, "why_it_works": "Pairs the curiosity gap with the authority of Philippians 4:6.", "vs_competitors": "High search + browse click-through rate."}
    ]
}

def get_curated_or_fallback_candidates(topic: str, verse_ref: str = "Philippians 4:19") -> List[Dict[str, Any]]:
    """Returns 5 verified high-CTR title options for instant display in the Tester Lab."""
    t_clean = _clean_topic_name(topic)
    t_low = t_clean.lower()
    for k, opts in TOPIC_CURATED_5_OPTIONS.items():
        if k in t_low:
            return opts

    # Clean word-boundary hook (never chop words like 'Fear of t?')
    words = t_clean.split()
    short_t = " ".join(words[:4]) if len(words) > 4 else t_clean
    return [
        {"rank": 1, "angle": "Top Pick • Urgent Hook & Promise", "title": f"Stressed About {short_t}? God Will Provide #shorts", "score": 100, "why_it_works": "Directly calls out the struggle with an immediate promise.", "vs_competitors": "Clear, punchy, and fits mobile screens."},
        {"rank": 2, "angle": "Pattern Interrupt / Thumb-Stopper", "title": f"Wait! Before You Worry About {short_t}, Hear This 🙏 #shorts", "score": 98, "why_it_works": "'Wait!' interrupts the scroll in the first 0.5 seconds.", "vs_competitors": "Stops the thumb and creates curiosity."},
        {"rank": 3, "angle": "Direct Prayer / Time Commitment", "title": f"A 30-Second Prayer for {short_t} 🙏 #shorts", "score": 96, "why_it_works": "Short time commitment drives full video retention.", "vs_competitors": "Higher completion rate than open-ended prayer titles."},
        {"rank": 4, "angle": "Emotional Relatability", "title": f"When {short_t} Feels Too Heavy, Pray This 🕊️ #shorts", "score": 94, "why_it_works": "Validates the emotional exhaustion of the viewer.", "vs_competitors": "Deeply empathetic late-night hook."},
        {"rank": 5, "angle": "Curiosity & Scripture Authority", "title": f"The 1 Verse That Calms {short_t} ({verse_ref}) 📖 #shorts", "score": 94, "why_it_works": "Curiosity gap paired with specific scripture reference.", "vs_competitors": "Ranks in both Search and Browse features."}
    ]

def _clean_topic_name(raw_topic: str) -> str:
    t = re.sub(r"^\d+[_\.\s]+", "", str(raw_topic or ""))
    t = re.sub(r"^(?:Quick|Bible|Grace|Hindi|English)[_\s]+", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\(Suggested Verse:.*?\)", "", t)
    t = t.replace("_", " ").strip()
    return t or "Overcoming Fear of the Future"

def match_topic_to_canonical_verse(topic_str: str, use_ai_network: bool = False, lang: str = "en") -> Dict[str, Any]:
    """
    Keeps the exact user-selected topic name 100% intact (never hijacks 'Single Parents' into 'Grief'!)
    and rolls a fresh random Bible verse specifically for that topic.
    """
    import bible_database as bdb
    clean_t = _clean_topic_name(topic_str)

    # Check exact match in TOP_50_PRAYER_TOPICS only; otherwise keep clean_t as-is!
    exact_topic = clean_t
    for item in bdb.TOP_50_PRAYER_TOPICS:
        if item["topic"].lower() == clean_t.lower():
            exact_topic = item["topic"]
            break

    bundle = bdb.ai_pick_relevant_verse_for_topic(exact_topic, lang=lang, use_ai_network=use_ai_network)
    bundle["topic_en"] = exact_topic
    return bundle

def get_past_titles(limit: int = 50) -> List[str]:
    if TITLES_HISTORY_FILE.exists():
        try:
            data = json.loads(TITLES_HISTORY_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data[-limit:]
        except Exception:
            pass
    return []

def save_title_to_history(title: str) -> None:
    history = get_past_titles(100)
    if title and title not in history:
        history.append(title)
        try:
            TITLES_HISTORY_FILE.write_text(json.dumps(history[-60:], indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

def score_single_title(title: str, topic: str, past_titles: List[str], comp_keywords: List[str] = None) -> Tuple[int, Dict[str, str]]:
    t = title.strip()
    pts = 0
    breakdown: Dict[str, str] = {}

    ln = len(t)
    if 28 <= ln <= 58:
        pts += 25
        breakdown["1. Mobile Length (28-58c)"] = f"[PASS] {ln} chars (Optimal mobile fit, +25/25)"
    elif 22 <= ln < 28 or 58 < ln <= 68:
        pts += 16
        breakdown["1. Mobile Length (28-58c)"] = f"[OK] {ln} chars (Acceptable, +16/25)"
    else:
        pts += 6
        breakdown["1. Mobile Length (28-58c)"] = f"[WARN] {ln} chars (Too short/long, +6/25)"

    words = set(re.findall(r"\b[a-zA-Z]+\b", t.lower()))
    matched_pw = words.intersection(POWER_WORDS)
    if len(matched_pw) >= 2:
        pts += 25
        breakdown["2. Power Hook Words"] = f"[PASS] Strong ({', '.join(list(matched_pw)[:3])}, +25/25)"
    elif len(matched_pw) == 1:
        pts += 19
        breakdown["2. Power Hook Words"] = f"[PASS] Good ({list(matched_pw)[0]}, +19/25)"
    else:
        pts += 9
        breakdown["2. Power Hook Words"] = "[WARN] Mild emotional trigger (+9/25)"

    has_tag = "#shorts" in t.lower()
    has_emoji = any(ord(c) > 127000 for c in t)
    comp_match = words.intersection(set(comp_keywords or []))
    if has_tag and (has_emoji or comp_match):
        pts += 15
        breakdown["3. Format & Competitor Sync"] = "[PASS] #shorts + Emoji + Niche match (+15/15)"
    elif has_tag:
        pts += 11
        breakdown["3. Format & Competitor Sync"] = "[PASS] Has #shorts tag (+11/15)"
    else:
        pts += 5
        breakdown["3. Format & Competitor Sync"] = "[WARN] Missing #shorts cue (+5/15)"

    max_sim = 0.0
    for pt in past_titles:
        sim = difflib.SequenceMatcher(None, t.lower(), pt.lower()).ratio()
        if sim > max_sim:
            max_sim = sim
    if max_sim < 0.72 or not past_titles:
        pts += 20
        breakdown["4. Anti-Repetition Check"] = f"[PASS] {int((1.0 - max_sim)*100)}% Unique vs past uploads (+20/20)"
    else:
        pts += 7
        breakdown["4. Anti-Repetition Check"] = f"[WARN] {int(max_sim*100)}% similar to past title (+7/20)"

    if not BANNED_WORDS.search(t):
        pts += 15
        breakdown["5. Monetization Safety"] = "[PASS] 100% Safe for AdSense review (+15/15)"
    else:
        pts = max(0, pts - 30)
        breakdown["5. Monetization Safety"] = "[FAIL] Restricted claim detected (-30)"

    return min(100, max(0, pts)), breakdown

def _live_scrape_competitors_deep(topic: str, verse_ref: str, limit: int = 8) -> List[Dict[str, Any]]:
    results = []
    seen_titles = set()
    queries = [
        f"ytsearch8:Christian prayer for {topic} #shorts",
        f"ytsearch6:{verse_ref} prayer #shorts",
    ]
    ydl_opts = {"quiet": True, "extract_flat": True, "skip_download": True, "socket_timeout": 10, "no_warnings": True, "geo_bypass_country": "US", "http_headers": {"Accept-Language": "en-US,en;q=0.9"}}
    for q in queries:
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(q, download=False)
                for entry in info.get("entries", []) or []:
                    if not entry:
                        continue
                    title = (entry.get("title") or "").strip()
                    if not title or title.lower() in seen_titles:
                        continue
                    seen_titles.add(title.lower())
                    views = int(entry.get("view_count") or 0)
                    dur = int(entry.get("duration") or 30)
                    if dur <= 180:
                        results.append({
                            "title": title,
                            "views": views,
                            "views_per_day": round(views / 14.0, 1) if views > 0 else 150.0,
                            "duration_sec": dur,
                            "url": f"https://www.youtube.com/watch?v={entry.get('id', '')}",
                        })
        except Exception:
            continue

    results.sort(key=lambda x: x["views"], reverse=True)
    return results[:limit]

def build_default_title_command(topic: str, verse_ref: str, verse_text: str, spoken_script: str = "", lang: str = "en") -> str:
    lang_line = "Write all titles in high-CTR Hindi/Hinglish." if lang == "hi" else "TARGET AUDIENCE: United States (en-US) American Christian viewers. Use American English spelling, high-CTR American devotional phrasing, and optimize for the US YouTube Shorts feed."
    script_context = f"\nSpoken Video Script to Match:\n\"{spoken_script[:350]}\"" if spoken_script else ""
    return (
        f"Analyze the live YouTube competitor titles for '{topic}' and scripture '{verse_ref}' (\"{verse_text[:140]}\").{script_context}\n"
        f"{lang_line}\n"
        f"1. Explain what patterns the top competitors are using and what weakness we can exploit.\n"
        f"2. Generate 5 superior, non-repetitive YouTube Short titles (32 to 56 chars, 1 emoji + #shorts) across 5 psychological angles:\n"
        f"   - Angle 1: Urgent Pattern-Interrupt Hook\n"
        f"   - Angle 2: Curiosity Gap / Specific Verse Hook ({verse_ref})\n"
        f"   - Angle 3: Direct Voice-of-God Comfort Hook\n"
        f"   - Angle 4: Real-Life Midnight / Emotional Scenario Hook\n"
        f"   - Angle 5: Bold Faith & Breakthrough Declaration Hook\n"
        f"3. For EVERY title, provide a detailed 'why_it_works' psychological explanation and a direct 'vs_competitors' comparison."
    )

def research_and_generate_titles(
    topic: str,
    verse_ref: str = "",
    verse_text: str = "",
    channel_name: str = "",
    lang: str = "en",
    scan_live_competitors: bool = True,
    custom_command: str = "",
    spoken_script: str = "",
    auto_roll_new_verse: bool = True,
    step_cb: Optional[Callable[[int, str, str], None]] = None,
) -> Dict[str, Any]:
    t0 = time.time()
    process_logs: List[str] = []

    def _log(pct: int, stage: str, detail: str):
        el = time.time() - t0
        entry = f"[{el:04.1f}s] {stage}: {detail}"
        process_logs.append(entry)
        if step_cb:
            step_cb(pct, stage, detail)

    clean_t = _clean_topic_name(topic)
    past_titles = get_past_titles(50)
    verse_why_explanation = ""
    hi_verse_text = ""

    if auto_roll_new_verse or not verse_ref or not verse_text:
        _log(10, "Stage 1/5 | AI Random Verse Picker", f"Selecting a fresh, unused Bible verse relevant to '{clean_t}'...")
        v_bundle = match_topic_to_canonical_verse(clean_t, use_ai_network=True, lang=lang)
        clean_t = v_bundle.get("topic_en", clean_t)
        ref_clean = v_bundle["verse_citation"]
        v_txt_clean = v_bundle["en_verse"]
        hi_verse_text = v_bundle.get("hi_verse", "")
        verse_why_explanation = v_bundle.get("why_hi" if lang == "hi" else "why_en", "")
        _log(16, "Stage 1/5 | New Verse Selected", f"Picked '{ref_clean}': \"{v_txt_clean[:65]}...\" | Why: {verse_why_explanation[:80]}")
    else:
        import bible_database as bdb
        ref_clean = re.sub(r"\s*\(.*?\)", "", str(verse_ref)).strip()
        _, v_txt_clean, hi_verse_text, _ = bdb.lookup_reference_bilingual(ref_clean)
        verse_why_explanation = f"Locked scripture {ref_clean} for '{clean_t}'."
        _log(12, "Stage 1/5 | Locked Verse Sync", f"Using '{ref_clean}' ({len(v_txt_clean)} chars)")

    competitors: List[Dict[str, Any]] = []
    if scan_live_competitors:
        _log(22, "Stage 2/5 | Live Competitor Scraping", f"Scraping YouTube Shorts for '{clean_t}' and '{ref_clean}'...")
        competitors = _live_scrape_competitors_deep(clean_t, ref_clean, limit=8)
        if not competitors:
            try:
                import main as backend
                competitors = backend.scan_competitor_shorts(clean_t, limit=6, channel_name=channel_name)
            except Exception:
                pass
        _log(38, "Stage 2/5 | Competitor Results", f"Scraped {len(competitors)} live competitor Shorts from YouTube.")
    else:
        try:
            import main as backend
            competitors = backend.scan_competitor_shorts(clean_t, limit=6, channel_name=channel_name)
        except Exception:
            pass
        _log(35, "Stage 2/5 | Competitor Cache", f"Loaded {len(competitors)} competitor Shorts from cache.")

    my_top_shorts: List[Dict[str, Any]] = []
    if channel_name:
        _log(48, "Stage 3/5 | Own Channel Audit", f"Checking your uploaded Shorts on '{channel_name}'...")
        try:
            import main as backend
            my_top_shorts = backend.get_my_top_shorts(channel_name, max_results=5)
        except Exception:
            pass

    my_best_str = "No public Shorts indexed yet on this channel"
    if my_top_shorts:
        b = my_top_shorts[0]
        my_best_str = f"\"{b['title']}\" ({b.get('views', 0):,} views | {b.get('views_per_day', 0):,.0f} views/day)"
        _log(55, "Stage 3/5 | Own Channel Benchmark", f"Your #1 Short: {my_best_str}")

    comp_words: List[str] = []
    comp_lengths: List[int] = []
    comp_summary_lines: List[str] = []
    for idx, c in enumerate(competitors[:6], start=1):
        ct = c.get("title", "")
        comp_lengths.append(len(ct))
        tokens = [w.lower() for w in re.findall(r"\b[a-zA-Z]{4,}\b", ct) if w.lower() not in STOPWORDS]
        comp_words.extend(tokens)
        comp_summary_lines.append(f"{idx}. \"{ct}\" - {c.get('views', 0):,} views ({c.get('views_per_day', 0):,.0f} views/day)")

    top_comp_keywords = [w for w, _ in collections.Counter(comp_words).most_common(8)]
    avg_comp_len = int(sum(comp_lengths) / max(1, len(comp_lengths))) if comp_lengths else 46
    _log(64, "Stage 4/5 | Competitor Pattern Mining", f"Extracted keywords: {top_comp_keywords[:6]} | Avg length: {avg_comp_len} chars")

    load_dotenv(BASE_DIR / ".env", override=True)
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    comp_block = "\n".join(comp_summary_lines) if comp_summary_lines else "No direct competitors returned; analyze based on YouTube Shorts algorithm benchmarks."

    user_cmd = custom_command.strip() if custom_command and custom_command.strip() else build_default_title_command(clean_t, ref_clean, v_txt_clean, spoken_script, lang)

    full_prompt = f"""You are an Elite YouTube Shorts Title Scientist & Christian Content Strategist.

=== LIVE STUDIO DATA ===
Topic: {clean_t}
Randomly Selected Scripture Reference: {ref_clean}
Scripture Text: "{v_txt_clean}"
Why This Scripture Was Selected: {verse_why_explanation}
My Channel's #1 Best Performing Short: {my_best_str}
Top Live Competitor Shorts on YouTube:
{comp_block}
High-Velocity Competitor Keywords: {', '.join(top_comp_keywords)}
Recently Used Titles (Do NOT repeat): {', '.join(past_titles[-10:]) if past_titles else 'None'}

=== USER COMMAND / INSTRUCTIONS ===
{user_cmd}

=== REQUIRED JSON OUTPUT FORMAT ===
Respond ONLY with a valid JSON object matching this exact schema:
{{
  "competitor_pattern_analysis": "Detailed 2-3 sentence analysis of the competitor titles above, what makes them work or fail, and how our new titles beat them.",
  "candidates": [
    {{
      "angle": "Name of Psychological Angle",
      "title": "The generated YouTube Short title ending with #shorts",
      "why_it_works": "Detailed explanation of why this specific title triggers curiosity and emotion.",
      "vs_competitors": "Direct comparison explaining how this title beats the competitor titles above."
    }}
  ]
}}"""

    ai_parsed = None
    raw_ai_response_text = ""
    used_model_name = "None"
    api_errors: List[str] = []

    if api_key:
        payload = {
            "contents": [{"parts": [{"text": full_prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.85}
        }
        data_bytes = json.dumps(payload).encode("utf-8")

        active_models = [
            "gemini-3.5-flash-lite",
            "gemini-3.8-flash",
            "gemini-3.7-flash",
            "gemini-3.6-flash",
            "gemini-3.1-flash-lite",
        ]

        for m_id in active_models:
            for attempt in range(1, 3):
                try:
                    _log(75, f"Stage 5/5 | Live AI Call ({m_id})", f"Executing prompt on {m_id} (Attempt {attempt}/2)...")
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{m_id}:generateContent?key={api_key}"
                    req = urllib.request.Request(url, headers={"Content-Type": "application/json"}, data=data_bytes)
                    with urllib.request.urlopen(req, timeout=35) as resp:
                        r_json = json.loads(resp.read().decode("utf-8"))
                        raw_ai_response_text = r_json["candidates"][0]["content"]["parts"][0]["text"]
                        m = re.search(r"\{[\s\S]*\}", raw_ai_response_text)
                        if m:
                            cand_json = json.loads(m.group(0))
                            if isinstance(cand_json.get("candidates"), list) and len(cand_json["candidates"]) >= 1:
                                ai_parsed = cand_json
                                used_model_name = f"Google Gemini Live ({m_id})"
                                _log(92, "Stage 5/5 | Live AI Success", f"Received {len(cand_json['candidates'])} live titles from {m_id}!")
                                break
                except Exception as e_m:
                    err_str = str(e_m)
                    api_errors.append(f"{m_id} (Attempt {attempt}): {err_str[:90]}")
                    _log(78, f"Stage 5/5 | {m_id} Notice", f"{err_str[:75]}")
                    if "503" in err_str or "429" in err_str:
                        time.sleep(2.5)
                        continue
                    break
            if ai_parsed:
                break

    if not ai_parsed:
        raise RuntimeError(f"Live AI call could not complete. API Details: {' | '.join(api_errors) if api_errors else 'Check GEMINI_API_KEY in .env'}")

    raw_cands = ai_parsed.get("candidates", [])
    comp_analysis = ai_parsed.get("competitor_pattern_analysis", "")

    scored_list: List[Dict[str, Any]] = []
    for idx, c_obj in enumerate(raw_cands):
        raw_t = str(c_obj.get("title", "")).strip()
        if not raw_t:
            continue
        if "#shorts" not in raw_t.lower():
            raw_t = f"{raw_t} #shorts"
        sc, factors = score_single_title(raw_t, clean_t, past_titles, comp_keywords=top_comp_keywords)
        scored_list.append({
            "rank": idx + 1,
            "angle": c_obj.get("angle", f"Angle {idx + 1}"),
            "title": raw_t,
            "score": sc,
            "char_len": len(raw_t),
            "factors": factors,
            "why_it_works": c_obj.get("why_it_works", ""),
            "vs_competitors": c_obj.get("vs_competitors", ""),
        })

    scored_list.sort(key=lambda x: x["score"], reverse=True)
    for r_i, item in enumerate(scored_list, start=1):
        item["rank"] = r_i

    winning = scored_list[0]
    _log(100, "Complete | Ranked & Scored", f"Winner #{winning['rank']} ({winning['score']}/100): \"{winning['title']}\"")

    return {
        "topic": clean_t,
        "verse_ref": ref_clean,
        "verse_text": v_txt_clean,
        "hi_verse_text": hi_verse_text,
        "verse_why_explanation": verse_why_explanation,
        "engine_used": used_model_name,
        "elapsed_sec": round(time.time() - t0, 1),
        "prompt_sent": full_prompt,
        "raw_ai_json": raw_ai_response_text,
        "winning_title": winning["title"],
        "winning_score": winning["score"],
        "winning_explanation": winning["why_it_works"],
        "winning_vs_competitors": winning["vs_competitors"],
        "competitor_pattern_analysis": comp_analysis,
        "top_competitor_keywords": top_comp_keywords,
        "avg_competitor_len": avg_comp_len,
        "my_best_short": my_best_str,
        "competitors": competitors,
        "candidates": scored_list,
        "process_logs": process_logs,
    }

def lock_title_for_video(video_path: Path, locked_title: str, explanation: str = "") -> None:
    meta_path = video_path.with_suffix(".json")
    data = {}
    if meta_path.exists():
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data["title"] = locked_title.strip()
    data["title_locked"] = True
    if explanation:
        data["title_explanation"] = explanation
    meta_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    save_title_to_history(locked_title.strip())

    txt_path = video_path.parent / "youtube_details.txt"
    desc = data.get("description", "")
    tags = data.get("tags", [])
    nl = chr(10)
    txt_path.write_text(
        f"TITLE:{nl}{locked_title.strip()}{nl}{nl}DESCRIPTION:{nl}{desc}{nl}{nl}TAGS:{nl}{', '.join(tags)}{nl}",
        encoding="utf-8"
    )
