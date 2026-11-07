import json
import re
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional

BASE_DIR = Path(__file__).resolve().parent
BIBLE_DATA_DIR = BASE_DIR / "assets" / "bible_data"
BIBLE_DATA_DIR.mkdir(parents=True, exist_ok=True)
KJV_JSON_FILE = BIBLE_DATA_DIR / "en_kjv.json"
HINDI_CACHE_FILE = BIBLE_DATA_DIR / "hindi_verse_cache.json"

# All 66 Books of the Bible: (English Name, Hindi/Romanized Name, Total Chapters)
BIBLE_66_BOOKS: List[Tuple[str, str, int]] = [
    ("Genesis", "Utpatti (उत्पत्ति)", 50),
    ("Exodus", "Nirgaman (निर्गमन)", 40),
    ("Leviticus", "Lavyavyavastha (लैव्यव्यवस्था)", 27),
    ("Numbers", "Ginti (गिनती)", 36),
    ("Deuteronomy", "Vyavasthavivaran (व्यवस्थाविवरण)", 34),
    ("Joshua", "Yahoshu (यहोशू)", 24),
    ("Judges", "Nyayiyon (न्यायियों)", 21),
    ("Ruth", "Ruth (रूत)", 4),
    ("1 Samuel", "1 Samuel (1 शमूएल)", 31),
    ("2 Samuel", "2 Samuel (2 शमूएल)", 24),
    ("1 Kings", "1 Rajaon (1 राजाओं)", 22),
    ("2 Kings", "2 Rajaon (2 राजाओं)", 25),
    ("1 Chronicles", "1 Itihas (1 इतिहास)", 29),
    ("2 Chronicles", "2 Itihas (2 इतिहास)", 36),
    ("Ezra", "Ezra (एज्रा)", 10),
    ("Nehemiah", "Nehemyah (नहेमायाह)", 13),
    ("Esther", "Esther (एस्तेर)", 10),
    ("Job", "Ayyub (अय्यूब)", 42),
    ("Psalms", "Bhajan Sanhita (भजन संहिता)", 150),
    ("Proverbs", "Nitiyachana (नीतिवचन)", 31),
    ("Ecclesiastes", "Sabhaupdeshak (सभोपदेशक)", 12),
    ("Song of Solomon", "Shreshthageet (श्रेष्ठगीत)", 8),
    ("Isaiah", "Yashahyah (यशायाह)", 66),
    ("Jeremiah", "Yirmeyah (यिर्मयाह)", 52),
    (" Lamentations", "Vilapgeet (विलापगीत)", 5),
    ("Ezekiel", "Yehezkel (यहेजकेल)", 48),
    ("Daniel", "Daniyel (दानिय्येल)", 12),
    ("Hosea", "Hoshe (होशे)", 14),
    ("Joel", "Yoel (योएल)", 3),
    ("Amos", "Amos (आमोस)", 9),
    ("Obadiah", "Obadyah (ओबद्याह)", 1),
    ("Jonah", "Yona (योना)", 4),
    ("Micah", "Mika (मीका)", 7),
    ("Nahum", "Nahum (नहूम)", 3),
    ("Habakkuk", "Habakkuk (हबक्कूक)", 3),
    ("Zephaniah", "Sefanyah (सपन्याह)", 3),
    ("Haggai", "Haggai (हाग्गै)", 2),
    ("Zechariah", "Zakharyah (जकर्याह)", 14),
    ("Malachi", "Malaki (मलाकी)", 4),
    ("Matthew", "Matti (मत्ती)", 28),
    ("Mark", "Markus (मरकुस)", 16),
    ("Luke", "Luka (लूका)", 24),
    ("John", "Yuhanna (यूहन्ना)", 21),
    ("Acts", "Preriton Ke Kam (प्रेरितों के काम)", 28),
    ("Romans", "Romiyon (रोमियों)", 16),
    ("1 Corinthians", "1 Kurinthiyon (1 कुरिन्थियों)", 16),
    ("2 Corinthians", "2 Kurinthiyon (2 कुरिन्थियों)", 13),
    ("Galatians", "Galatiyon (गलातियों)", 6),
    ("Ephesians", "Ifisiyon (इफिसियों)", 6),
    ("Philippians", "Filippion (फिलिप्पियों)", 4),
    ("Colossians", "Kulussiyon (कुलुस्सियों)", 4),
    ("1 Thessalonians", "1 Thissalunikiyon (1 थिस्सलुनीकियों)", 5),
    ("2 Thessalonians", "2 Thissalunikiyon (2 थिस्सलुनीकियों)", 3),
    ("1 Timothy", "1 Timothiyus (1 तीमुथियुस)", 6),
    ("2 Timothy", "2 Timothiyus (2 तीमुथियुस)", 4),
    ("Titus", "Titus (तीतुस)", 3),
    ("Philemon", "Filemon (फिलेमोन)", 1),
    ("Hebrews", "Ibraniyon (इब्रानियों)", 13),
    ("James", "Yakub (याकूब)", 5),
    ("1 Peter", "1 Patras (1 पतरस)", 5),
    ("2 Peter", "2 Patras (2 पतरस)", 3),
    ("1 John", "1 Yuhanna (1 यूहन्ना)", 5),
    ("2 John", "2 Yuhanna (2 यूहन्ना)", 1),
    ("3 John", "3 Yuhanna (3 यूहन्ना)", 1),
    ("Jude", "Yahuda (यहूदा)", 1),
    ("Revelation", "Prakashithvakya (प्रकाशितवाक्य)", 22),
]

# 50 Most-Searched Life Struggles & Prayer Topics with Recommended Scripture
TOP_50_PRAYER_TOPICS: List[Dict[str, str]] = [
    {"id": "01", "topic": "Debt & Financial Freedom", "ref": "Philippians 4:19", "cat": "Finance"},
    {"id": "02", "topic": "Anxiety & Panic Attacks", "ref": "Philippians 4:6-7", "cat": "Peace"},
    {"id": "03", "topic": "Broken Heart & Depression", "ref": "Psalm 34:18", "cat": "Emotional"},
    {"id": "04", "topic": "Miracle Healing from Sickness", "ref": "Jeremiah 17:14", "cat": "Health"},
    {"id": "05", "topic": "Protection from Evil & Jealousy", "ref": "Isaiah 54:17", "cat": "Protection"},
    {"id": "06", "topic": "Strength When You Feel Like Quitting", "ref": "Isaiah 40:31", "cat": "Strength"},
    {"id": "07", "topic": "Forgiving Someone Who Hurt You", "ref": "Colossians 3:13", "cat": "Relationships"},
    {"id": "08", "topic": "Job & Career Breakthrough", "ref": "Jeremiah 29:11", "cat": "Finance"},
    {"id": "09", "topic": "Exam & Study Success", "ref": "James 1:5", "cat": "Success"},
    {"id": "10", "topic": "Peaceful Sleep & Overcoming Insomnia", "ref": "Psalm 4:8", "cat": "Peace"},
    {"id": "11", "topic": "Marriage Restoration & Peace at Home", "ref": "1 Corinthians 13:4-7", "cat": "Family"},
    {"id": "12", "topic": "Children's Protection & Future", "ref": "Isaiah 54:13", "cat": "Family"},
    {"id": "13", "topic": "Overcoming Fear of the Future", "ref": "Isaiah 41:10", "cat": "Peace"},
    {"id": "14", "topic": "Loneliness & Feeling Forgotten", "ref": "Deuteronomy 31:8", "cat": "Emotional"},
    {"id": "15", "topic": "Breaking Bad Habits & Addictions", "ref": "1 Corinthians 10:13", "cat": "Freedom"},
    {"id": "16", "topic": "Waiting on God's Timing with Patience", "ref": "Ecclesiastes 3:11", "cat": "Faith"},
    {"id": "17", "topic": "Business Growth & Workplace Favor", "ref": "Deuteronomy 28:12", "cat": "Finance"},
    {"id": "18", "topic": "Comfort in Grief & Loss of a Loved One", "ref": "Matthew 5:4", "cat": "Emotional"},
    {"id": "19", "topic": "Clarity & Wisdom for Hard Decisions", "ref": "Proverbs 3:5-6", "cat": "Wisdom"},
    {"id": "20", "topic": "Protection While Traveling (Psalm 121)", "ref": "Psalm 121:7-8", "cat": "Protection"},
    {"id": "21", "topic": "Nightmares & Spiritual Warfare", "ref": "Psalm 91:1-2", "cat": "Protection"},
    {"id": "22", "topic": "Overcoming Shame & Past Mistakes", "ref": "Romans 8:1", "cat": "Freedom"},
    {"id": "23", "topic": "Finding a Godly Life Partner", "ref": "Proverbs 18:22", "cat": "Relationships"},
    {"id": "24", "topic": "Healing from Betrayal by Friends", "ref": "Psalm 55:22", "cat": "Relationships"},
    {"id": "25", "topic": "Deliverance from Overthinking", "ref": "2 Timothy 1:7", "cat": "Peace"},
    {"id": "26", "topic": "Blessing Over New Home & Family", "ref": "Joshua 24:15", "cat": "Family"},
    {"id": "27", "topic": "Victory in Court Cases & Injustice", "ref": "Exodus 14:14", "cat": "Protection"},
    {"id": "28", "topic": "Overcoming Anger & Short Temper", "ref": "James 1:19-20", "cat": "Emotional"},
    {"id": "29", "topic": "Pregnancy & Safe Childbirth Blessing", "ref": "Psalm 139:13-14", "cat": "Health"},
    {"id": "30", "topic": "Restoration of Stolen Years & Losses", "ref": "Joel 2:25", "cat": "Finance"},
    {"id": "31", "topic": "Courage to Face Impossible Giants", "ref": "Joshua 1:9", "cat": "Strength"},
    {"id": "32", "topic": "Morning Gratitude & Fresh Mercy", "ref": "Lamentations 3:22-23", "cat": "Faith"},
    {"id": "33", "topic": "Healing Chronic Pain & Weakness", "ref": "2 Corinthians 12:9", "cat": "Health"},
    {"id": "34", "topic": "Favor in Interviews & Promotions", "ref": "Psalm 5:12", "cat": "Success"},
    {"id": "35", "topic": "Peace During Family Financial Crisis", "ref": "Psalm 37:25", "cat": "Finance"},
    {"id": "36", "topic": "Protection from Toxic People & Gossip", "ref": "Psalm 31:20", "cat": "Protection"},
    {"id": "37", "topic": "Renewing Faith When Prayers Feel Delayed", "ref": "Habakkuk 2:3", "cat": "Faith"},
    {"id": "38", "topic": "Comfort for Single Parents & Providers", "ref": "Psalm 68:5", "cat": "Family"},
    {"id": "39", "topic": "Freedom from Jealousy & Comparison", "ref": "Galatians 6:4", "cat": "Emotional"},
    {"id": "40", "topic": "Guidance for Youth & Purpose in Life", "ref": "Psalm 119:105", "cat": "Wisdom"},
    {"id": "41", "topic": "Miracle Doors Opening Where None Existed", "ref": "Revelation 3:8", "cat": "Success"},
    {"id": "42", "topic": "Peace Before Surgery or Medical Tests", "ref": "Psalm 46:1", "cat": "Health"},
    {"id": "43", "topic": "Breaking Generational Struggles", "ref": "Galatians 3:13", "cat": "Freedom"},
    {"id": "44", "topic": "Humility & Grace Under Pressure", "ref": "1 Peter 5:6-7", "cat": "Wisdom"},
    {"id": "45", "topic": "Joy After a Season of Weeping", "ref": "Psalm 30:5", "cat": "Emotional"},
    {"id": "46", "topic": "Unshakeable Trust in Dark Valleys", "ref": "Psalm 23:4", "cat": "Faith"},
    {"id": "47", "topic": "Blessing the Work of Your Hands", "ref": "Psalm 90:17", "cat": "Success"},
    {"id": "48", "topic": "Salvation & Softening of Loved Ones' Hearts", "ref": "Ezekiel 36:26", "cat": "Family"},
    {"id": "49", "topic": "Supernatural Rest for Exhausted Souls", "ref": "Matthew 11:28", "cat": "Peace"},
    {"id": "50", "topic": "Nothing Is Impossible With God", "ref": "Luke 1:37", "cat": "Faith"},
]

_BIBLE_MEM_CACHE: Optional[List[Dict[str, Any]]] = None

def ensure_full_bible_downloaded() -> List[Dict[str, Any]]:
    """Downloads and caches the complete 66-book, 31,102-verse English KJV Bible JSON."""
    global _BIBLE_MEM_CACHE
    if _BIBLE_MEM_CACHE is not None:
        return _BIBLE_MEM_CACHE

    if not KJV_JSON_FILE.exists() or KJV_JSON_FILE.stat().st_size < 1_000_000:
        url = "https://raw.githubusercontent.com/thiagobodruk/bible/master/json/en_kjv.json"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw_bytes = resp.read()
                # Strip UTF-8 BOM if present
                text_data = raw_bytes.decode("utf-8-sig")
                KJV_JSON_FILE.write_text(text_data, encoding="utf-8")
        except Exception:
            pass

    if KJV_JSON_FILE.exists() and KJV_JSON_FILE.stat().st_size > 100_000:
        try:
            _BIBLE_MEM_CACHE = json.loads(KJV_JSON_FILE.read_text(encoding="utf-8-sig"))
            return _BIBLE_MEM_CACHE
        except Exception:
            pass
    return []

def get_book_chapters_count(book_eng_name: str) -> int:
    for b_en, _, ch_cnt in BIBLE_66_BOOKS:
        if b_en.strip().lower() == book_eng_name.strip().lower():
            return ch_cnt
    return 1

def get_verses_for_chapter(book_eng_name: str, chapter_num: int) -> Dict[int, str]:
    """Returns {verse_number: verse_text} for any of the 66 books and any chapter."""
    data = ensure_full_bible_downloaded()
    book_idx = next((i for i, (b_en, _, _) in enumerate(BIBLE_66_BOOKS) if b_en.strip().lower() == book_eng_name.strip().lower()), -1)

    if data and 0 <= book_idx < len(data):
        chapters = data[book_idx].get("chapters", [])
        if 1 <= chapter_num <= len(chapters):
            v_list = chapters[chapter_num - 1]
            return {i + 1: re.sub(r"\{([^}]*)\}", r"\1", v_str) for i, v_str in enumerate(v_list)}

    # Online single-chapter fallback if JSON hasn't downloaded yet
    try:
        q = urllib.parse.quote(f"{book_eng_name} {chapter_num}")
        req = urllib.request.Request(f"https://bible-api.com/{q}?translation=kjv", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            j = json.loads(resp.read().decode("utf-8"))
            return {int(v["verse"]): v["text"].strip() for v in j.get("verses", [])}
    except Exception:
        return {1: "The Lord is near to all who call upon Him in truth."}

def translate_verse_to_hindi(ref: str, english_verse: str) -> Tuple[str, str]:
    """
    Returns (hindi_devanagari, romanized_hinglish) for any Bible verse in the 66 books,
    caching results locally so repeated lookups are instant.
    """
    cache: Dict[str, Dict[str, str]] = {}
    if HINDI_CACHE_FILE.exists():
        try:
            cache = json.loads(HINDI_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            cache = {}

    if ref in cache:
        return cache[ref].get("devanagari", ""), cache[ref].get("hinglish", "")

    devanagari = ""
    hinglish = ""
    try:
        q = urllib.parse.quote(english_verse)
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=hi&dt=t&dt=rm&q={q}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            arr = json.loads(resp.read().decode("utf-8"))
            if arr and arr[0]:
                devanagari = "".join(seg[0] for seg in arr[0] if seg and seg[0])
                # Extract transliteration if provided in last segment
                for seg in arr[0]:
                    if len(seg) > 2 and seg[2]:
                        hinglish += seg[2] + " "
                hinglish = hinglish.strip()
    except Exception:
        pass

    if not hinglish:
        hinglish = english_verse

    cache[ref] = {"devanagari": devanagari, "hinglish": hinglish}
    try:
        HINDI_CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

    return devanagari, hinglish
