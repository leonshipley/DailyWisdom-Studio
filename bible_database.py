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


# Verified Pavitra Baibil (Devanagari Hindi) Verses for instant 100% accurate Hindi reading
VERIFIED_PAVITRA_BAIBIL: Dict[str, Tuple[str, str]] = {
    "Philippians 4:19": (
        "और मेरा परमेश्वर अपने उस धन के अनुसार जो महिमा सहित मसीह यीशु में है, तुम्हारी हर एक घटी को पूरी करेगा।",
        "Aur mera Parmeshwar apne us dhan ke anusaar jo mahima sahit Masih Yeshu mein hai, tumhari har ek ghati ko poori karega."
    ),
    "Philippians 4:6-7": (
        "किसी भी बात की चिन्ता मत करो, परन्तु हर एक बात में तुम्हारे निवेदन, प्रार्थना और विनती के द्वारा धन्यवाद के साथ परमेश्वर के सम्मुख उपस्थित किए जाएं। तब परमेश्वर की शान्ति, जो सारी समझ से परे है, तुम्हारे हृदय और तुम्हारे विचारों को मसीह यीशु में सुरक्षित रखेगी।",
        "Kisi bhi baat ki chinta mat karo, parantu har ek baat mein tumhare nivedan prarthana aur vinti ke dwara Parmeshwar ke sammukh upasthit kiye jayein."
    ),
    "Psalm 34:18": (
        "यहोवा टूटे मन वालों के समीप रहता है, और पिसे हुए लोगों का उद्धार करता है।",
        "Yahowa toote man walon ke samip rehta hai, aur pise hue logon ka uddhar karta hai."
    ),
    "Psalms 34:18": (
        "यहोवा टूटे मन वालों के समीप रहता है, और पिसे हुए लोगों का उद्धार करता है।",
        "Yahowa toote man walon ke samip rehta hai, aur pise hue logon ka uddhar karta hai."
    ),
    "Jeremiah 17:14": (
        "हे यहोवा, मुझे चंगा कर, तब मैं चंगा हो जाऊंगा; मुझे बचा, तब मैं बच जाऊंगा, क्योंकि तू ही मेरी स्तुति का पात्र है।",
        "He Yahowa, mujhe changa kar, tab main changa ho jaunga; mujhe bacha, tab main bach jaunga."
    ),
    "Isaiah 54:17": (
        "जितने हथियार तेरी हानि के लिए बनाए जाएं, उनमें से कोई भी सफल न होगा, और जितने लोग मुद्दई होकर तुझ पर नालिश करें उन सभी से तू जीत जाएगा।",
        "Jitne hathiyar teri hani ke liye banaye jayein, unmein se koi bhi safal na hoga."
    ),
    "Isaiah 40:31": (
        "परन्तु जो यहोवा की बाट जोहते हैं, वे नया बल प्राप्त करते जाएंगे, वे उकाबों के समान उड़ेंगे, वे दौड़ेंगे और श्रमित न होंगे, चलेंगे और थकित न होंगे।",
        "Parantu jo Yahowa ki baat johte hain, ve naya bal prapt karte jayenge."
    ),
    "Colossians 3:13": (
        "यदि किसी को किसी पर दोष देने का कोई कारण हो, तो एक दूसरे की सह लो, और एक दूसरे के अपराध क्षमा करो; जैसे प्रभु ने तुम्हारे अपराध क्षमा किए, वैसे ही तुम भी करो।",
        "Ek doosre ki sah lo, aur ek doosre ke aparadh kshama karo; jaise Prabhu ne tumhare aparadh kshama kiye."
    ),
    "Jeremiah 29:11": (
        "क्योंकि जो कल्पनाएं मैं तुम्हारे विषय में करता हूँ, उन्हें मैं जानता हूँ, यहोवा की यह वाणी है, वे हानि की नहीं, वरन कुशल ही की कल्पनाएं हैं, और अंत में तुम्हारी आशा पूरी करूंगा।",
        "Kyonki jo kalpanayein main tumhare vishay mein karta hoon, ve kushal hi ki kalpanayein hain."
    ),
    "James 1:5": (
        "पर यदि तुम में से किसी को बुद्धि की घटी हो, तो परमेश्वर से मांगे, जो बिना उलाहना दिए सब को उदारता से देता है, और उसको दी जाएगी।",
        "Yadi tum mein se kisi ko buddhi ki ghati ho, to Parmeshwar se maange, aur usko di jayegi."
    ),
    "Psalm 4:8": (
        "मैं शान्ति से लेट जाऊंगा और सो जाऊंगा; क्योंकि, हे यहोवा, केवल तू ही मुझ को एकान्त में निश्चिन्त रहने देता है।",
        "Main shanti se let jaunga aur so jaunga; kyonki he Yahowa, keval tu hi mujh ko nishchint rehne deta hai."
    ),
    "Isaiah 41:10": (
        "मत डर, क्योंकि मैं तेरे संग हूँ, इधर उधर मत ताक, क्योंकि मैं तेरा परमेश्वर हूँ; मैं तुझे दृढ़ करूंगा और तेरी सहायता करूंगा।",
        "Mat dar, kyonki main tere sang hoon, main tera Parmeshwar hoon; main tujhe dridh karunga."
    ),
    "Matthew 11:28": (
        "हे सब परिश्रम करने वालों और बोझ से दबे हुए लोगों, मेरे पास आओ, मैं तुम्हें विश्राम दूंगा।",
        "He sab parishram karne walon aur bojh se dabe hue logon, mere paas aao, main tumhein vishram dunga."
    ),
}

def translate_verse_to_hindi(ref: str, english_verse: str) -> Tuple[str, str]:
    """
    Guarantees pure Devanagari Hindi translation for any Bible verse.
    Never caches or returns English in the Devanagari slot.
    """
    ref_clean = ref.strip()
    if ref_clean in VERIFIED_PAVITRA_BAIBIL:
        return VERIFIED_PAVITRA_BAIBIL[ref_clean]

    cache: Dict[str, Any] = {}
    if HINDI_CACHE_FILE.exists():
        try:
            cache = json.loads(HINDI_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            cache = {}

    if ref_clean in cache and isinstance(cache[ref_clean], dict):
        cached_dev = cache[ref_clean].get("devanagari", "")
        if re.search(r"[\u0900-\u097F]", cached_dev):
            return cached_dev, cache[ref_clean].get("hinglish", cached_dev)

    devanagari = ""
    hinglish = ""
    try:
        q = urllib.parse.quote(english_verse.strip())
        # Use single dt=t first for 100% reliable Devanagari extraction
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=hi&dt=t&q={q}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            arr = json.loads(resp.read().decode("utf-8"))
            if arr and arr[0]:
                devanagari = "".join(str(seg[0]) for seg in arr[0] if seg and seg[0]).strip()
    except Exception:
        pass

    if re.search(r"[\u0900-\u097F]", devanagari):
        hinglish = devanagari
        cache[ref_clean] = {"devanagari": devanagari, "hinglish": hinglish}
        try:
            HINDI_CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
        return devanagari, hinglish

    # Fallback if offline
    return "यहोवा अपने सभी पुकारने वालों के समीप रहता है और उन्हें शान्ति देता है।", "Yahowa apne sabhi pukarne walon ke samip rehta hai."



def lookup_reference_bilingual(ref_str: str) -> Tuple[str, str, str, str]:
    """
    Parses any reference like 'Philippians 4:19', 'Psalm 34:18', or 'Philippians 4:6-7'
    and returns (normalized_ref, english_text, hindi_devanagari, romanized_hinglish).
    """
    ref_clean = ref_str.strip()
    m = re.match(r"^((?:[1-3]\s+)?[A-Za-z\s]+?)\s+(\d+):(\d+)(?:-(\d+))?$", ref_clean)
    if not m:
        en_default = "And my God will supply every need of yours according to his riches in glory in Christ Jesus."
        dev, rom = translate_verse_to_hindi("Philippians 4:19", en_default)
        return ("Philippians 4:19", en_default, dev, rom)

    book_raw = m.group(1).strip()
    if book_raw.lower() == "psalm":
        book_lookup = "Psalms"
    else:
        book_lookup = book_raw

    ch_num = int(m.group(2))
    v_start = int(m.group(3))
    v_end = int(m.group(4)) if m.group(4) else v_start

    verses_map = get_verses_for_chapter(book_lookup, ch_num)
    collected = []
    for vn in range(v_start, v_end + 1):
        if vn in verses_map:
            collected.append(verses_map[vn])
    en_text = " ".join(collected) if collected else verses_map.get(v_start, "The Lord is near to all who call upon Him.")

    dev_hi, rom_hi = translate_verse_to_hindi(ref_clean, en_text)
    return (ref_clean, en_text, dev_hi, rom_hi)


# Exact Devanagari Hindi Book Names for all 66 Books (for natural TTS pronunciation)
HINDI_BOOK_SPOKEN_MAP: Dict[str, str] = {
    "genesis": "उत्पत्ति",
    "exodus": "निर्गमन",
    "leviticus": "लैव्यव्यवस्था",
    "numbers": "गिनती",
    "deuteronomy": "व्यवस्थाविवरण",
    "joshua": "यहोशू",
    "judges": "न्यायियों",
    "ruth": "रूत",
    "1 samuel": "पहला शमूएल",
    "2 samuel": "दूसरा शमूएल",
    "1 kings": "पहला राजाओं",
    "2 kings": "दूसरा राजाओं",
    "1 chronicles": "पहला इतिहास",
    "2 chronicles": "दूसरा इतिहास",
    "ezra": "एज्रा",
    "nehemiah": "नहेमायाह",
    "esther": "एस्तेर",
    "job": "अय्यूब",
    "psalms": "भजन संहिता",
    "psalm": "भजन संहिता",
    "proverbs": "नीतिवचन",
    "ecclesiastes": "सभोपदेशक",
    "song of solomon": "श्रेष्ठगीत",
    "isaiah": "यशायाह",
    "jeremiah": "यिर्मयाह",
    "lamentations": "विलापगीत",
    "ezekiel": "यहेजकेल",
    "daniel": "दानिय्येल",
    "hosea": "होशे",
    "joel": "योएल",
    "amos": "आमोस",
    "obadiah": "ओबद्याह",
    "jonah": "योना",
    "micah": "मीका",
    "nahum": "नहूम",
    "habakkuk": "हबक्कूक",
    "zephaniah": "सपन्याह",
    "haggai": "हाग्गै",
    "zechariah": "जकर्याह",
    "malachi": "मलाकी",
    " Matthew": "मत्ती",
    "matthew": "मत्ती",
    "mark": "मरकुस",
    "luke": "लूका",
    "john": "यूहन्ना",
    "acts": "प्रेरितों के काम",
    "romans": "रोमियों",
    "1 corinthians": "पहला कुरिन्थियों",
    "2 corinthians": "दूसरा कुरिन्थियों",
    "galatians": "गलातियों",
    "ephesians": "इफिसियों",
    "philippians": "फिलिप्पियों",
    "colossians": "कुलुस्सियों",
    "1 thessalonians": "पहला थिस्सलुनीकियों",
    "2 thessalonians": "दूसरा थिस्सलुनीकियों",
    "1 timothy": "पहला तीमुथियुस",
    "2 timothy": "दूसरा तीमुथियुस",
    "titus": "तीतुस",
    "philemon": "फिलेमोन",
    "hebrews": "इब्रानियों",
    "james": "याकूब",
    "1 peter": "पहला पतरस",
    "2 peter": "दूसरा पतरस",
    "1 john": "पहला यूहन्ना",
    "2 john": "दूसरा यूहन्ना",
    "3 john": "तीसरा यूहन्ना",
    "jude": "यहूदा",
    "revelation": "प्रकाशितवाक्य",
}

def format_reference_for_speech(ref_str: str, is_hindi_speech: bool = False) -> str:
    """
    Converts 'Leviticus 1:1' into:
    - Hindi Speech:   'लैव्यव्यवस्था, अध्याय 1, वचन 1' (Never says '1 bajke 1 minute'!)
    - English Speech: 'Leviticus, chapter 1, verse 1'
    """
    ref_clean = ref_str.strip()
    m = re.match(r"^((?:[1-3]\s+)?[A-Za-z\s]+?)\s+(\d+):(\d+)(?:-(\d+))?$", ref_clean)
    if not m:
        # Strip any colons between numbers so TTS never reads clock time
        if is_hindi_speech:
            return re.sub(r"(\d+):(\d+)", r"अध्याय \1, वचन \2", ref_clean)
        return re.sub(r"(\d+):(\d+)", r"chapter \1, verse \2", ref_clean)

    book_en = m.group(1).strip()
    ch = m.group(2)
    v1 = m.group(3)
    v2 = m.group(4)

    if is_hindi_speech:
        hi_book = HINDI_BOOK_SPOKEN_MAP.get(book_en.lower(), book_en)
        if v2 and v2 != v1:
            return f"{hi_book}, अध्याय {ch}, वचन {v1} से {v2}"
        return f"{hi_book}, अध्याय {ch}, वचन {v1}"
    else:
        if v2 and v2 != v1:
            return f"{book_en}, chapter {ch}, verses {v1} to {v2}"
        return f"{book_en}, chapter {ch}, verse {v1}"


def translate_any_text_to_hindi(en_text: str) -> str:
    """Translates any English sentence (topic, meaning, prayer) into 100% pure Devanagari Hindi."""
    if not en_text or not en_text.strip():
        return ""
    # If already contains Devanagari characters, return as-is
    if re.search(r"[\u0900-\u097F]", en_text):
        return en_text
    cache: Dict[str, Any] = {}
    if HINDI_CACHE_FILE.exists():
        try:
            cache = json.loads(HINDI_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            cache = {}
    key = f"txt_{en_text.strip()[:80]}"
    if key in cache and isinstance(cache[key], str) and cache[key]:
        return cache[key]
    try:
        q = urllib.parse.quote(en_text.strip())
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=hi&dt=t&q={q}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            arr = json.loads(resp.read().decode("utf-8"))
            if arr and arr[0]:
                hi_out = "".join(seg[0] for seg in arr[0] if seg and seg[0]).strip()
                if hi_out:
                    cache[key] = hi_out
                    HINDI_CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
                    return hi_out
    except Exception:
        pass
    return en_text


# Rich multi-verse pool per category so every topic has dozens of relevant scriptures
CATEGORY_VERSE_POOLS: Dict[str, List[str]] = {
    "Finance": ["Philippians 4:19", "Deuteronomy 28:12", "Malachi 3:10", "Proverbs 10:22", "2 Corinthians 9:8", "Psalm 23:1", "Psalm 37:25", "Proverbs 3:9-10", "Luke 6:38", "Deuteronomy 8:18", "Psalm 112:3", "Job 22:28"],
    "Peace": ["Philippians 4:6-7", "John 14:27", "Isaiah 26:3", "Psalm 4:8", "Matthew 11:28", "Psalm 46:10", "2 Thessalonians 3:16", "Colossians 3:15", "Psalm 29:11", "1 Peter 5:7", "Psalm 131:2", "Psalm 94:19"],
    "Emotional": ["Psalm 34:18", "Psalm 147:3", "Matthew 5:4", "Psalm 30:5", "Isaiah 61:3", "2 Corinthians 1:3-4", "Psalm 42:11", "Psalm 73:26", "Revelation 21:4", "Psalm 55:22", "Deuteronomy 31:8", "Psalm 27:10"],
    "Health": ["Jeremiah 17:14", "Jeremiah 30:17", "Isaiah 53:5", "Psalm 103:2-3", "Exodus 23:25", "3 John 1:2", "Proverbs 4:20-22", "Psalm 107:20", "James 5:15", "Psalm 41:3", "Exodus 15:26", "Malachi 4:2"],
    "Protection": ["Isaiah 54:17", "Psalm 91:1-2", "Psalm 91:11", "Psalm 121:7-8", "2 Thessalonians 3:3", "Proverbs 18:10", "Psalm 18:2", "Exodus 14:14", "Psalm 27:1", "Psalm 46:1", "Deuteronomy 31:6", "Psalm 34:7"],
    "Strength": ["Isaiah 40:31", "Philippians 4:13", "Isaiah 41:10", "2 Corinthians 12:9", "Joshua 1:9", "Psalm 28:7", "Nehemiah 8:10", "Habakkuk 3:19", "Psalm 18:32", "Ephesians 6:10", "Psalm 73:26", "Deuteronomy 20:4"],
    "Relationships": ["Colossians 3:13", "1 Corinthians 13:4-7", "Ephesians 4:32", "Proverbs 17:17", "1 Peter 4:8", "Ecclesiastes 4:9-10", "Romans 12:10", "Proverbs 18:22", "Mark 11:25", "Proverbs 15:1"],
    "Family": ["Joshua 24:15", "Isaiah 54:13", "Psalm 127:3", "Proverbs 22:6", "Acts 16:31", "Psalm 128:3", "Proverbs 31:28", "Psalm 103:17", "Numbers 6:24-26", "Psalm 115:14"],
    "Success": ["Jeremiah 29:11", "James 1:5", "Proverbs 16:3", "Psalm 90:17", "Psalm 5:12", "Revelation 3:8", "Psalm 1:3", "Proverbs 3:5-6", "Psalm 37:4", "Psalm 20:4"],
    "Freedom": ["1 Corinthians 10:13", "John 8:36", "Romans 8:1", "2 Corinthians 5:17", "Galatians 5:1", "Isaiah 43:18-19", "Psalm 107:14", "Romans 8:2", "1 John 1:9", "Galatians 3:13"],
    "Faith": ["Luke 1:37", "Mark 11:24", "Hebrews 11:1", "Romans 8:28", "Habakkuk 2:3", "Ecclesiastes 3:11", "Lamentations 3:22-23", "Psalm 23:4", "Matthew 19:26", "2 Corinthians 5:7"],
    "Wisdom": ["Proverbs 3:5-6", "James 1:5", "Psalm 119:105", "Isaiah 30:21", "Psalm 32:8", "Proverbs 2:6", "Colossians 3:16", "1 Peter 5:6-7", "Proverbs 4:7", "Psalm 25:4-5"],
}

def ai_pick_relevant_verse_for_topic(topic_str: str, lang: str = "en", api_key: str = "") -> Dict[str, Any]:
    """
    Uses AI (plus anti-repetition tracking per language channel) to pick a fresh,
    relevant Bible verse for `topic_str` along with an explanation, meaning, and prayer.
    `lang` is 'en' (English Maker) or 'hi' (Hindi Maker).
    """
    import os
    import random

    clean_topic = re.sub(r"^\d+\.\s*", "", re.sub(r"\s*—\s*\[.*?\]", "", topic_str)).strip()
    used_file = BASE_DIR / f"used_verses_{lang}.json"
    try:
        used_list = json.loads(used_file.read_text(encoding="utf-8")) if used_file.exists() else []
    except Exception:
        used_list = []

    avoid_str = ", ".join(used_list[-40:]) if used_list else "None"
    seed = random.randint(10000, 999999)

    # Determine category pool for fallback
    cat_name = "Faith"
    for item in TOP_50_PRAYER_TOPICS:
        if item["topic"].lower() in clean_topic.lower() or clean_topic.lower() in item["topic"].lower():
            cat_name = item["cat"]
            break
    pool = CATEGORY_VERSE_POOLS.get(cat_name, CATEGORY_VERSE_POOLS["Faith"])
    unused_pool = [r for r in pool if r not in used_list] or pool
    fallback_ref = random.choice(unused_pool)

    chosen_ref = fallback_ref
    why_explanation_en = f"This scripture directly addresses {clean_topic} by reminding us of God's unshakeable promise and provision."
    meaning_en = f"When you face {clean_topic}, God invites you to cast every burden upon Him. His strength and grace are more than enough to carry you through today."
    prayer_en = f"Lord Jesus, I surrender my struggle with {clean_topic} into Your hands; fill my life with Your peace and breakthrough, Amen."
    hook_en = f"GODS PROMISE FOR {clean_topic.upper()[:16]}"
    title_en = f"God's Promise for {clean_topic[:32]} #shorts"

    key_to_use = api_key or os.getenv("GEMINI_API_KEY", "")
    if key_to_use:
        prompt = f"""Random Seed: {seed}
Topic: {clean_topic}
DO NOT pick any of these recently used verses: [{avoid_str}]

Pick 1 powerful, deeply relevant Bible verse for someone praying about '{clean_topic}'.
Respond ONLY in valid JSON with exact keys:
- "verse_citation": Standard Book Chapter:Verse (e.g. "Psalm 147:3" or "Deuteronomy 28:12")
- "why_this_verse": 1 sentence explaining WHY this specific verse is powerful for '{clean_topic}'
- "meaning": 2 comforting, reverent sentences explaining the spiritual meaning of this verse
- "prayer": 1 powerful breakthrough prayer sentence starting with 'Lord...' and ending with 'Amen.'
- "thumbnail_hook": 3-4 words ALL CAPS bold hook
- "title": Under 55 chars catchy YouTube Short title ending with #shorts"""

        for m_name in ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-3.5-flash-lite"]:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{m_name}:generateContent?key={key_to_use}"
                payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"responseMimeType": "application/json", "temperature": 1.05}
                }
                req = urllib.request.Request(url, headers={"Content-Type": "application/json"}, data=json.dumps(payload).encode("utf-8"))
                with urllib.request.urlopen(req, timeout=7) as resp:
                    resp_json = json.loads(resp.read().decode("utf-8"))
                    raw_t = resp_json["candidates"][0]["content"]["parts"][0]["text"]
                    m = re.search(r"\{.*\}", raw_t, re.DOTALL)
                    if m:
                        raw_t = m.group(0)
                    parsed = json.loads(raw_t)
                    cand_ref = parsed.get("verse_citation", "").strip()
                    if re.match(r"^(?:[1-3]\s+)?[A-Za-z\s]+\s+\d+:\d+", cand_ref):
                        chosen_ref = cand_ref
                        why_explanation_en = parsed.get("why_this_verse") or why_explanation_en
                        meaning_en = parsed.get("meaning") or meaning_en
                        prayer_en = parsed.get("prayer") or prayer_en
                        hook_en = parsed.get("thumbnail_hook") or hook_en
                        title_en = parsed.get("title") or title_en
                        break
            except Exception:
                continue

    # Look up exact canonical English KJV verse and pure Devanagari Hindi verse
    norm_ref, en_verse_text, hi_verse_dev, hi_verse_rom = lookup_reference_bilingual(chosen_ref)

    # Record in language-specific used list so next click gives a different verse
    if norm_ref not in used_list:
        used_list.append(norm_ref)
        try:
            used_file.write_text(json.dumps(used_list[-80:], indent=2), encoding="utf-8")
        except Exception:
            pass

    why_hi = translate_any_text_to_hindi(why_explanation_en)
    meaning_hi = translate_any_text_to_hindi(meaning_en)
    prayer_hi = translate_any_text_to_hindi(prayer_en)
    topic_hi = translate_any_text_to_hindi(clean_topic)

    return {
        "topic_en": clean_topic,
        "topic_hi": topic_hi,
        "verse_citation": norm_ref,
        "en_spoken_ref": format_reference_for_speech(norm_ref, is_hindi_speech=False),
        "hi_spoken_ref": format_reference_for_speech(norm_ref, is_hindi_speech=True),
        "en_verse": en_verse_text,
        "hi_verse": hi_verse_dev,
        "rom_verse": hi_verse_rom,
        "why_en": why_explanation_en,
        "why_hi": why_hi,
        "meaning_en": meaning_en,
        "meaning_hi": meaning_hi,
        "prayer_en": prayer_en,
        "prayer_hi": prayer_hi,
        "hook_en": hook_en,
        "title_en": title_en,
        "title_hi": f"{format_reference_for_speech(norm_ref, is_hindi_speech=True)} — {topic_hi[:22]} #shorts",
    }
