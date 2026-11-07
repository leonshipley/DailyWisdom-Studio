import random
import os
import sys
import time
import json
import shutil
import asyncio
import subprocess
import re
import urllib.request
import pickle
import textwrap
from pathlib import Path
from dotenv import load_dotenv

import yt_dlp
from yt_dlp.utils import download_range_func
from youtube_transcript_api import YouTubeTranscriptApi
import edge_tts
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

# Google API client for YouTube
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# --- BASE SETUP & DIRECTORIES ---
BASE_DIR = Path(__file__).resolve().parent
CLIPS_DIR = BASE_DIR / "clips"
CLIPS_DIR.mkdir(exist_ok=True)
DOWNLOADS_DIR = BASE_DIR / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)
CHANNELS_DIR = BASE_DIR / "channels"
CHANNELS_DIR.mkdir(exist_ok=True)
CHANNELS_CONFIG = BASE_DIR / "channels.json"
HISTORY_FILE = BASE_DIR / "processed_history.json"
BGM_PODCAST_FILE = BASE_DIR / "bg_music.mp3"
CLIENT_SECRET_FILE = BASE_DIR / "client_secret.json"

load_dotenv(BASE_DIR / ".env")
API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=API_KEY) if API_KEY else None

YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly"
]

# --- CUSTOM MEDIA FOLDERS & AUTO-MUTER ---
MEDIA_DIR = BASE_DIR / "custom_media"
INTRO_DIR = MEDIA_DIR / "intro_videos"
BG_DIR = MEDIA_DIR / "backgrounds"
THUMB_DIR = MEDIA_DIR / "thumbnails"
for _d in [INTRO_DIR, BG_DIR, THUMB_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

TOPIC_VISUAL_SUGGESTIONS = {
    "Debt": ("Golden heavenly clouds parting or light rays", "Jesus with outstretched hands offering peace", "Close-up of Jesus with bold 'BREAK EVERY DEBT' hook"),
    "Anxiety": ("Calm ocean waves at sunset or gentle rain", "Jesus calming the storm on the water", "Radiant white Jesus in storm with 'PEACE BE STILL'"),
    "Broken Heart": ("Soft glowing candle or warm sunrise through clouds", "Jesus embracing or wiping away tears", "Compassionate face of Christ with golden halo"),
    "Healing": ("Heavenly golden light beams descending", "Jesus reaching out His healing hand", "Glowing cross and healing hands of Christ"),
    "Protection": ("Mighty eagles soaring or dramatic sky clouds", "Warrior angels or Jesus standing guard in light", "Glowing shield of faith / Psalm 91 visual"),
    "Strength": ("Mountain peak above the clouds at dawn", "Jesus walking with footprints in the sand", "Radiant Christ with 'RENEW YOUR STRENGTH'"),
    "Forgiveness": ("Doves flying into bright golden sky", "The Cross at sunset or Jesus with open arms", "Merciful Christ in white robes")
}

def mute_any_video(input_vid: Path) -> Path:
    """Strips audio and normalizes video stream so FFmpeg concat never fails with -22."""
    if not input_vid or not input_vid.exists():
        return input_vid
    muted_dir = INTRO_DIR / "muted_cache"
    muted_dir.mkdir(parents=True, exist_ok=True)
    safe_stem = re.sub(r"[^a-zA-Z0-9_]+", "_", input_vid.stem).strip("_")[:30]
    muted_out = muted_dir / f"muted_{safe_stem}.mp4"
    if not muted_out.exists() or muted_out.stat().st_size < 1000:
        cmd = [
            "ffmpeg", "-y", "-i", str(input_vid),
            "-t", "12", "-an",
            "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=24,format=yuv420p,setsar=1",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
            str(muted_out)
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return muted_out if muted_out.exists() else input_vid

def choose_media_in_cli(topic: str) -> tuple[Path | None, Path | None, Path | None]:
    """Shows AI suggestions, exact save/rename instructions, and lets user pick files in CLI."""
    sug_intro, sug_bg, sug_thumb = ("Heavenly golden clouds moving", "Jesus in white robes with open arms", "High-contrast portrait of Jesus with golden glow")
    for k, val in TOPIC_VISUAL_SUGGESTIONS.items():
        if k.lower() in topic.lower():
            sug_intro, sug_bg, sug_thumb = val
            break

    safe_tag = re.sub(r"[^a-zA-Z0-9]", "", topic.title())[:12] or "Miracle"

    print("\n" + "=" * 68)
    print(f"🎨 AI VISUAL SUGGESTIONS & FILE GUIDE FOR: '{topic}'")
    print("=" * 68)
    print("💡 WHAT VISUALS TO USE FOR MAXIMUM VIEWS:")
    print(f"   • 10s Intro Video : {sug_intro}")
    print(f"   • Main Background : {sug_bg}")
    print(f"   • Thumbnail Image : {sug_thumb}")
    print("-" * 68)
    print("📂 WHERE TO SAVE & WHAT TO RENAME YOUR FILES (CLEAR INSTRUCTIONS):")
    print(f"   1. INTRO VIDEO (0-10s):")
    print(f"      👉 Save inside : {INTRO_DIR.resolve()}")
    print(f"      👉 Rename to   : Intro_{safe_tag}.mp4   (Audio will be muted automatically!)")
    print(f"   2. MAIN BACKGROUND IMAGE (10s-End):")
    print(f"      👉 Save inside : {BG_DIR.resolve()}")
    print(f"      👉 Rename to   : BG_{safe_tag}.jpg")
    print(f"   3. THUMBNAIL BACKGROUND IMAGE:")
    print(f"      👉 Save inside : {THUMB_DIR.resolve()}")
    print(f"      👉 Rename to   : Thumb_{safe_tag}.jpg")
    print("=" * 68)

    input("👉 (Optional) Drop your files into the folders above now, then press [ENTER] to select...")

    def _pick_from_folder(folder: Path, label: str, exts: tuple, fallback: Path | None) -> Path | None:
        files = sorted([f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in exts], key=lambda x: x.stat().st_mtime, reverse=True)
        if not files:
            print(f"   • No custom {label} in folder yet -> Using default.")
            return fallback
        print(f"\n📁 Select {label}:")
        print(f"   [Enter] Auto-use newest: {files[0].name}")
        for idx, f in enumerate(files):
            print(f"   [{idx + 1}] {f.name}")
        ch = input(f"Choose (1-{len(files)}) or press Enter: ").strip()
        if ch.isdigit() and 1 <= int(ch) <= len(files):
            return files[int(ch) - 1]
        return files[0]

    chosen_intro = _pick_from_folder(INTRO_DIR, "10s Intro Video", (".mp4", ".mov", ".mkv", ".webm"), get_short_main_video())
    chosen_bg = _pick_from_folder(BG_DIR, "Main Background Image", (".jpg", ".jpeg", ".png", ".webp"), get_jesus_image())
    chosen_thumb = _pick_from_folder(THUMB_DIR, "Thumbnail Image", (".jpg", ".jpeg", ".png", ".webp"), chosen_bg)

    if chosen_intro:
        chosen_intro = mute_any_video(chosen_intro)

    return chosen_intro, chosen_bg, chosen_thumb


# --- DYNAMIC ASSET LOCATORS ---
def get_file_by_name(base_name: str, extensions: list[str]) -> Path | None:
    for ext in extensions:
        p = BASE_DIR / f"{base_name}{ext}"
        if p.exists():
            return p
    matches = list(BASE_DIR.glob(f"{base_name}*"))
    return matches[0] if matches else None

def get_worship_bgm() -> Path:
    sample = get_file_by_name("worship_sample", [".mp3", ".wav", ".m4a", ".mp4", ""])
    if sample and sample.exists():
        return sample
    return BASE_DIR / "soft_worship_piano.mp3"

def get_jesus_image() -> Path:
    img = get_file_by_name("Jesus_Lord", [".jpg", ".png", ".jpeg", ".webp", ""])
    if img and img.exists():
        return img
    fb = BASE_DIR / "jesus_white_robes.jpg"
    return fb

def get_short_main_video() -> Path | None:
    vid = get_file_by_name("Short_Main", [".mp4", ".mov", ".mkv", ".webm", ""])
    return vid

# --- CATEGORIES FOR PODCAST CLIPPER ---
CATEGORIES = {
    "1": {
        "name": "Habits & Productivity",
        "badge_tag": "HABITS & PRODUCTIVITY",
        "queries": ["ytsearch15:books on habits and productivity podcast", "ytsearch15:Ali Abdaal productivity books"],
        "hashtags": ["#Habits", "#Productivity", "#AtomicHabits", "#Focus", "#Shorts"]
    },
    "2": {
        "name": "Stoicism & Philosophy",
        "badge_tag": "STOIC PHILOSOPHY",
        "queries": ["ytsearch15:Ryan Holiday stoic books podcast", "ytsearch15:Marcus Aurelius meditations life lessons"],
        "hashtags": ["#Stoicism", "#Philosophy", "#MarcusAurelius", "#Wisdom", "#Shorts"]
    },
    "3": {
        "name": "Wealth & Business",
        "badge_tag": "WEALTH & BUSINESS",
        "queries": ["ytsearch15:Alex Hormozi business books recommended", "ytsearch15:The psychology of money Morgan Housel"],
        "hashtags": ["#Wealth", "#Money", "#Business", "#Investing", "#Shorts"]
    },
    "4": {
        "name": "Discipline & Mental Toughness",
        "badge_tag": "MENTAL TOUGHNESS",
        "queries": ["ytsearch15:David Goggins discipline mindset podcast", "ytsearch15:Chris Williamson mental toughness books"],
        "hashtags": ["#Discipline", "#Mindset", "#MentalToughness", "#Motivation", "#Shorts"]
    },
    "5": {
        "name": "Health, Brain & Science",
        "badge_tag": "HEALTH & BIOHACKING",
        "queries": ["ytsearch15:Andrew Huberman best science books podcast", "ytsearch15:Matthew Walker Why We Sleep podcast"],
        "hashtags": ["#Health", "#Biohacking", "#Neuroscience", "#Longevity", "#Shorts"]
    },
    "6": {
        "name": "Human Nature & Power",
        "badge_tag": "PSYCHOLOGY & POWER",
        "queries": ["ytsearch15:Robert Greene 48 laws of power podcast", "ytsearch15:dark psychology and human behavior books"],
        "hashtags": ["#Psychology", "#Power", "#HumanNature", "#DarkPsychology", "#Shorts"]
    }
}

# --- CURATED BIBLE SCRIPTS ---
CURATED_BIBLE_VAULT = {
    "1": {
        "topic": "Debt & Financial Freedom",
        "title": "A 30-Second Prayer to Break Debt",
        "verse_citation": "Philippians 4:19",
        "verse_text": "And my God will supply every need of yours according to his riches in glory in Christ Jesus.",
        "meaning": "God calls you to live free from the burden of debt. Trust in His divine timing, for His storehouses of provision never run dry.",
        "prayer": "Lord, break every chain of debt over my family and release Your supernatural financial overflow today, Amen.",
        "thumbnail_hook": "BREAK EVERY DEBT",
        "hashtags": ["#DebtFree", "#FinancialBlessing", "#JesusProvides", "#Shorts"]
    },
    "2": {
        "topic": "Anxiety & Stress Relief",
        "title": "Peace in the Storm: Pray This Now",
        "verse_citation": "Philippians 4:6-7",
        "verse_text": "Do not be anxious about anything, but in everything by prayer present your requests to God, and peace will guard your heart.",
        "meaning": "You do not have to carry this burden alone. When you place your worries into Christ's hands, His peace guards your mind.",
        "prayer": "Lord, take away this heavy anxiety and fill my spirit with Your everlasting supernatural peace, Amen.",
        "thumbnail_hook": "PEACE IN THE STORM",
        "hashtags": ["#AnxietyRelief", "#PeaceOfGod", "#JesusHeals", "#Shorts"]
    },
    "3": {
        "topic": "Broken Heart & Depression",
        "title": "God Is Healing Your Broken Heart",
        "verse_citation": "Psalm 34:18",
        "verse_text": "The Lord is near to the brokenhearted and saves the crushed in spirit.",
        "meaning": "You are never alone in your tears. The Lord is holding your heart right now and turning your sorrow into divine strength.",
        "prayer": "Lord, heal every wound inside my soul and restore joy and hope into my life today, Amen.",
        "thumbnail_hook": "HEAL BROKEN HEARTS",
        "hashtags": ["#HealingHeart", "#DepressionRelief", "#HopeInGod", "#Shorts"]
    },
    "4": {
        "topic": "Healing & Sickness",
        "title": "A Miracle Healing Prayer Over Your Body",
        "verse_citation": "Jeremiah 17:14",
        "verse_text": "Heal me, O Lord, and I shall be healed; save me, and I shall be saved, for you are my praise.",
        "meaning": "Jesus is your divine physician. By His sacred stripes, restoration and divine life are flowing into your cells right now.",
        "prayer": "Lord, touch my body with Your healing light and drive out all sickness and pain, Amen.",
        "thumbnail_hook": "DIVINE HEALING NOW",
        "hashtags": ["#HealingPrayer", "#MiracleHealing", "#JesusRestores", "#Shorts"]
    },
    "5": {
        "topic": "Protection from Evil",
        "title": "No Weapon Formed Shall Prosper",
        "verse_citation": "Isaiah 54:17",
        "verse_text": "No weapon formed against you shall prosper, and you shall refute every tongue that accuses you.",
        "meaning": "God has assigned mighty angels to encamp around you. Every spiritual attack against your peace is defeated in Jesus' name.",
        "prayer": "Lord, shield me with Your presence and deliver my family from all darkness and evil, Amen.",
        "thumbnail_hook": "NO WEAPON PROSPERS",
        "hashtags": ["#GodsProtection", "#SpiritualWarfare", "#JesusProtects", "#Shorts"]
    },
    "6": {
        "topic": "Strength in Hard Times",
        "title": "Strength When You Feel Like Quitting",
        "verse_citation": "Isaiah 40:31",
        "verse_text": "Those who hope in the Lord will renew their strength. They will soar on wings like eagles; they will run and not grow weary.",
        "meaning": "When human strength fails, God's supernatural power takes over. Rise up in faith, for your victory is already sealed.",
        "prayer": "Lord, renew my strength today and give me the endurance to conquer every giant before me, Amen.",
        "thumbnail_hook": "RENEW YOUR STRENGTH",
        "hashtags": ["#GodIsMyStrength", "#Overcome", "#FaithOverFear", "#Shorts"]
    },
    "7": {
        "topic": "Forgiveness & Letting Go",
        "title": "Release the Pain: Freedom in Forgiveness",
        "verse_citation": "Colossians 3:13",
        "verse_text": "Bear with each other and forgive one another if any of you has a grievance against someone. Forgive as the Lord forgave you.",
        "meaning": "Forgiveness does not excuse their actions; it unchains your heart from their poison. Give your pain to God and walk in peace.",
        "prayer": "Lord, give me the strength to forgive those who hurt me and release all bitterness from my soul, Amen.",
        "thumbnail_hook": "FREEDOM TO FORGIVE",
        "hashtags": ["#Forgiveness", "#InnerPeace", "#LetGoLetGod", "#Shorts"]
    }
}

# --- 1. ASSET PREPARATION & MUTING ---
def prepare_muted_short_main() -> Path | None:
    """Mutes Short_Main video and saves it as Short_Main_muted.mp4."""
    raw_video = get_short_main_video()
    if not raw_video or not raw_video.exists():
        return None

    muted_file = BASE_DIR / "Short_Main_muted.mp4"
    if not muted_file.exists() or muted_file.stat().st_size < 1000:
        print("  • Muting 'Short_Main' and saving as 'Short_Main_muted.mp4'...")
        cmd = ["ffmpeg", "-y", "-i", str(raw_video), "-an", "-c:v", "copy", str(muted_file)]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    return muted_file if muted_file.exists() else raw_video

def ensure_sacred_assets():
    """Ensures fallback assets exist if user media is not placed."""
    jesus_file = get_jesus_image()
    if not jesus_file.exists() or jesus_file.stat().st_size < 10000:
        headers = {"User-Agent": "Mozilla/5.0"}
        try:
            req = urllib.request.Request("https://images.unsplash.com/photo-1544830237-7d5d28b12f66?auto=format&fit=crop&w=1080&q=80", headers=headers)
            with urllib.request.urlopen(req, timeout=6) as resp, open(jesus_file, "wb") as f:
                f.write(resp.read())
        except Exception:
            cmd_gen = ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=0x070B14:s=1080x1920:d=1", "-vf", "drawbox=x=80:y=200:w=920:h=1520:color=0xD4AF37@0.25:t=fill", "-vframes", "1", str(jesus_file)]
            subprocess.run(cmd_gen, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    bgm_file = get_worship_bgm()
    if not bgm_file.exists() or bgm_file.stat().st_size < 10000:
        cmd_audio = ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=130.81:sample_rate=44100", "-f", "lavfi", "-i", "sine=frequency=164.81:sample_rate=44100", "-filter_complex", "amix=inputs=2:normalize=0,volume=0.25,lowpass=f=450", "-t", "120", str(bgm_file)]
        subprocess.run(cmd_audio, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# --- 2. MULTI-CHANNEL SYSTEM ---
def load_channels() -> dict:
    channels = {}
    if CHANNELS_CONFIG.exists():
        try:
            with open(CHANNELS_CONFIG, "r") as f:
                channels = json.load(f)
        except Exception:
            channels = {}

    legacy_token = BASE_DIR / "youtube_token.pickle"
    if legacy_token.exists():
        ch_name = "TheDailyWisdom_Hub"
        token_path = CHANNELS_DIR / f"{ch_name}.pickle"
        if not token_path.exists():
            shutil.copy(legacy_token, token_path)
        if ch_name not in channels:
            channels[ch_name] = str(token_path)
            save_channels(channels)

    for p in CHANNELS_DIR.glob("*.pickle"):
        name = p.stem.replace("_", " ")
        if name not in channels:
            channels[name] = str(p)
            save_channels(channels)

    return channels

def save_channels(data: dict):
    with open(CHANNELS_CONFIG, "w") as f:
        json.dump(data, f, indent=2)

def connect_new_channel():
    if not CLIENT_SECRET_FILE.exists():
        print("❌ Missing client_secret.json in project root directory!")
        return None

    print("\n🌐 Opening Google login in your web browser...")
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_FILE), YOUTUBE_SCOPES)
    credentials = flow.run_local_server(port=0, prompt="select_account")
    youtube = build("youtube", "v3", credentials=credentials)
    res = youtube.channels().list(mine=True, part="snippet").execute()

    if not res.get("items"):
        return None

    channel_name = res["items"][0]["snippet"]["title"]
    safe_name = re.sub(r'[\/*?:"<>| ]', "_", channel_name)
    token_file = CHANNELS_DIR / f"{safe_name}.pickle"

    with open(token_file, "wb") as f:
        pickle.dump(credentials, f)

    channels = load_channels()
    channels[channel_name] = str(token_file)
    save_channels(channels)
    print(f"✅ Successfully connected: '{channel_name}'!")
    return channel_name

def get_authenticated_youtube(channel_name: str):
    channels = load_channels()
    token_path = channels.get(channel_name)
    if not token_path or not Path(token_path).exists():
        return None

    with open(token_path, "rb") as f:
        credentials = pickle.load(f)

    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            with open(token_path, "wb") as f:
                pickle.dump(credentials, f)
        else:
            return None

    return build("youtube", "v3", credentials=credentials)

# --- 3. METADATA & UPLOADER ---
def clean_filename(text: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9]+", "_", text or "")
    return clean.strip("_")[:35] or "media_item"

def timestamp_to_seconds(ts: str) -> float:
    parts = [float(p) for p in ts.strip().split(":")]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    elif len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return parts[0]

def get_next_sequence_folder(label: str) -> Path:
    nums = []
    for d in CLIPS_DIR.iterdir():
        if d.is_dir():
            m = re.match(r"^(\d{3})_", d.name)
            if m:
                nums.append(int(m.group(1)))
    next_n = (max(nums) + 1) if nums else 1
    folder = CLIPS_DIR / f"{next_n:03d}_{clean_filename(label)}"
    folder.mkdir(parents=True, exist_ok=True)
    return folder

def get_next_sequence_folder(label: str) -> Path:
    nums = []
    for d in CLIPS_DIR.iterdir():
        if d.is_dir():
            m = re.match(r"^(\d{3})_", d.name)
            if m:
                nums.append(int(m.group(1)))
    next_n = (max(nums) + 1) if nums else 1
    folder = CLIPS_DIR / f"{next_n:03d}_{clean_filename(label)}"
    folder.mkdir(parents=True, exist_ok=True)
    return folder

# --- VIRALITY & COMPETITOR INTELLIGENCE ENGINE ---
_CHANNEL_STATS_CACHE = {}

def get_my_top_shorts(channel_name: str, max_results: int = 8) -> list[dict]:
    """Fetches the user's own uploaded videos from YouTube API and sorts by most viewed."""
    if channel_name in _CHANNEL_STATS_CACHE:
        return _CHANNEL_STATS_CACHE[channel_name]

    youtube = get_authenticated_youtube(channel_name)
    if not youtube:
        return []

    try:
        ch_res = youtube.channels().list(mine=True, part="contentDetails").execute()
        if not ch_res.get("items"):
            return []
        uploads_id = ch_res["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

        pl_res = youtube.playlistItems().list(
            playlistId=uploads_id, part="contentDetails", maxResults=max_results
        ).execute()
        vid_ids = [item["contentDetails"]["videoId"] for item in pl_res.get("items", [])]
        if not vid_ids:
            return []

        v_res = youtube.videos().list(
            id=",".join(vid_ids), part="snippet,statistics"
        ).execute()

        my_videos = []
        for v in v_res.get("items", []):
            stats = v.get("statistics", {})
            snip = v.get("snippet", {})
            my_videos.append({
                "id": v["id"],
                "title": snip.get("title", ""),
                "views": int(stats.get("viewCount", 0)),
                "likes": int(stats.get("likeCount", 0)),
                "comments": int(stats.get("commentCount", 0)),
                "tags": snip.get("tags", [])
            })

        my_videos.sort(key=lambda x: x["views"], reverse=True)
        _CHANNEL_STATS_CACHE[channel_name] = my_videos
        return my_videos
    except Exception:
        return []


def scan_competitor_shorts(topic: str, limit: int = 6) -> list[dict]:
    """Scans YouTube for top-viewed competitor Shorts on this exact topic."""
    ydl_opts = {"quiet": True, "extract_flat": True, "skip_download": True}
    competitors = []
    query = f"ytsearch10:{topic} #shorts"
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            res = ydl.extract_info(query, download=False)
            for entry in res.get("entries", []):
                if not entry:
                    continue
                views = entry.get("view_count") or 0
                title = entry.get("title") or ""
                if title:
                    competitors.append({
                        "title": title,
                        "views": int(views),
                        "url": f"https://www.youtube.com/watch?v={entry.get('id', '')}"
                    })
    except Exception:
        pass

    competitors.sort(key=lambda x: x["views"], reverse=True)
    return competitors[:limit]


def optimize_with_virality_engine(topic: str, draft_title: str, draft_desc: str, draft_tags: list[str], channel_name: str) -> tuple[str, str, list[str]]:
    """Compares draft with user's #1 most-viewed Short and top competitors, then upgrades title, desc & tags."""
    print("\n" + "-" * 62)
    print(f"\U0001f525 [VIRALITY ENGINE] Analyzing Title & Tag Competition for: '{topic}'...")

    my_top = get_my_top_shorts(channel_name)
    competitors = scan_competitor_shorts(topic)

    my_best_summary = "No previous uploads yet (New Channel)"
    if my_top:
        best = my_top[0]
        my_best_summary = f"'{best['title']}' ({best['views']:,} views, {best['likes']} likes)"
        print(f"   \U0001f3c6 Your #1 Most Viewed Short: {my_best_summary}")
    else:
        print("   \U0001f4ca Channel Status: Building baseline data from initial uploads")

    comp_lines = []
    if competitors:
        print("   \U0001f50d Top Competitor Titles on YouTube Right Now:")
        for idx, c in enumerate(competitors[:4]):
            v_str = f"{c['views']:,} views" if c["views"] > 0 else "Trending"
            print(f"      {idx + 1}. \"{c['title'][:58]}\" ({v_str})")
            comp_lines.append(f"- {c['title']} ({v_str})")

    comp_block = "\n".join(comp_lines) if comp_lines else "None found"

    prompt = f"""You are a YouTube Shorts Virality & SEO Strategist.
Topic: {topic}
My Draft Title: {draft_title}
My Channel's #1 Most Viewed Short: {my_best_summary}
Top Competitor Titles on YouTube:
{comp_block}

Respond ONLY in valid JSON with these exact keys:
- "virality_score": integer (1-100) rating how clickable the new title is
- "winning_title": string (under 58 chars, high-CTR hook that beats competitors, include 1 power word)
- "competitor_insight": 1 short sentence on why this title beats the competitors
- "pinned_comment": 1 engaging question/call-to-action to pin in comments
- "hashtags": list of 6 viral hashtags starting with #
- "seo_tags": list of 12 high-search-volume YouTube backend keyword tags (no # symbol)"""

    ai_result = None
    if API_KEY:
        for m_name in ["gemini-3.5-flash-lite", "gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.8-flash"]:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{m_name}:generateContent?key={API_KEY}"
                payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"responseMimeType": "application/json", "temperature": 0.85}
                }
                req = urllib.request.Request(url, headers={"Content-Type": "application/json"}, data=json.dumps(payload).encode("utf-8"))
                with urllib.request.urlopen(req, timeout=7) as resp:
                    resp_json = json.loads(resp.read().decode("utf-8"))
                    raw_text = resp_json["candidates"][0]["content"]["parts"][0]["text"]
                    m = re.search(r"\{.*\}", raw_text, re.DOTALL)
                    if m:
                        raw_text = m.group(0)
                    ai_result = json.loads(raw_text)
                    break
            except Exception:
                continue

    or_key = os.getenv("OPENROUTER_API_KEY")
    if not ai_result and or_key:
        for model in ["openrouter/free", "google/gemma-4-31b-it:free"]:
            try:
                req = urllib.request.Request(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {or_key}", "Content-Type": "application/json"},
                    data=json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}]}).encode("utf-8")
                )
                with urllib.request.urlopen(req, timeout=8) as response:
                    data = json.loads(response.read().decode("utf-8"))
                    raw_text = data["choices"][0]["message"]["content"]
                    m = re.search(r"\{.*\}", raw_text, re.DOTALL)
                    if m:
                        raw_text = m.group(0)
                    ai_result = json.loads(raw_text)
                    break
            except Exception:
                continue

    if ai_result and isinstance(ai_result, dict):
        new_title = ai_result.get("winning_title") or draft_title
        score = ai_result.get("virality_score", 92)
        insight = ai_result.get("competitor_insight", "Optimized for high mobile CTR and retention.")
        pinned = ai_result.get("pinned_comment", "Type AMEN if you claim this today! \U0001f64f")
        new_hashtags = [h if h.startswith("#") else f"#{h}" for h in ai_result.get("hashtags", [])][:6]
        seo_tags = [str(t).replace("#", "").strip() for t in ai_result.get("seo_tags", []) if t]

        merged_tags = list(dict.fromkeys(seo_tags + [t.replace("#", "") for t in draft_tags]))[:18]
        hashtag_line = " ".join(new_hashtags) if new_hashtags else ""

        upgraded_desc = f"{draft_desc}\n\n{hashtag_line}\n\n\U0001f4cc PINNED COMMENT IDEA:\n{pinned}".strip()

        print(f"   \U0001f4c8 Virality Score:     {score}/100")
        print(f"   \U0001f3af Old Draft Title:    {draft_title}")
        print(f"   \U0001f680 NEW WINNING TITLE:  {new_title}")
        print(f"   \U0001f4a1 Strategy Insight:   {insight}")
        print(f"   \U0001f3f7\ufe0f  Injected SEO Tags:  {', '.join(merged_tags[:8])}...")
        print("-" * 62)
        return new_title, upgraded_desc, merged_tags

    print("   \u2705 Applied baseline high-retention tags.")
    print("-" * 62)
    return draft_title, draft_desc, draft_tags


def run_cli_virality_engine(active_channel: str):
    """Interactive Menu [9] to audit channel performance, spy on competitors, or upgrade saved Shorts."""
    print("\n" + "=" * 62)
    print(f"\U0001f525 VIRALITY ENGINE & COMPETITOR SPY (Channel: {active_channel})")
    print("=" * 62)
    print("  [1] \U0001f3c6 View My Channel's Most Viewed Shorts & Performance")
    print("  [2] \U0001f50d Spy on Competitor Titles & Tags for Any Topic")
    print("  [3] \u26a1 Upgrade & Re-Optimize All Unuploaded Shorts in clips/")
    print("  [b] Back")

    choice = input("\nChoose option (1-3 or b): ").strip().lower()
    if choice == "1":
        _CHANNEL_STATS_CACHE.pop(active_channel, None)
        my_vids = get_my_top_shorts(active_channel, max_results=12)
        if not my_vids:
            print("\n\u26a0\ufe0f No public videos found or channel stats are still processing.")
            return
        print(f"\n\U0001f4ca TOP PERFORMING SHORTS ON [{active_channel}]:")
        for i, v in enumerate(my_vids):
            print(f"  #{i + 1}: \"{v['title']}\" \u2014 \U0001f441\ufe0f {v['views']:,} views | \U0001f44d {v['likes']} likes | \U0001f4ac {v['comments']} comments")
    elif choice == "2":
        topic = input("\nEnter Topic / Niche to Spy On (e.g. 'Bible Verse for Debt' or 'Stoicism'): ").strip()
        if topic:
            optimize_with_virality_engine(topic, f"Powerful Lesson on {topic}", "Sample description", ["Shorts"], active_channel)
    elif choice == "3":
        mp4s = sorted(list(CLIPS_DIR.rglob("*.mp4")), key=os.path.getmtime, reverse=True)
        unuploaded = [v for v in mp4s if not load_clip_metadata(v).get("youtube_id")]
        if not unuploaded:
            print("\n\U0001f389 All videos in clips/ are already uploaded!")
            return
        for v in unuploaded:
            meta = load_clip_metadata(v)
            new_t, new_d, new_tags = optimize_with_virality_engine(meta["title"], meta["title"], meta["description"], meta["tags"], active_channel)
            save_clip_metadata(v, new_t, new_d, new_tags)
            print(f"\u2705 Upgraded metadata for: {v.parent.name}/{v.name}")


def save_clip_metadata(video_path: Path, title: str, description: str, tags: list[str]):
    meta_path = video_path.with_suffix(".json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({"title": title, "description": description, "tags": tags, "youtube_id": None}, f, indent=2)
    txt_path = video_path.parent / "youtube_details.txt"
    txt_path.write_text(f"TITLE:\n{title}\n\nDESCRIPTION:\n{description}\n", encoding="utf-8")
    txt_path = video_path.parent / "youtube_details.txt"
    txt_path.write_text(f"TITLE:\n{title}\n\nDESCRIPTION:\n{description}\n", encoding="utf-8")

def load_clip_metadata(video_path: Path) -> dict:
    meta_path = video_path.with_suffix(".json")
    if meta_path.exists():
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"title": video_path.stem.replace("_", " "), "description": "Watch this message.\n\n#Shorts #Faith", "tags": ["Shorts", "Faith"], "youtube_id": None}

def choose_upload_channel(default_channel: str) -> str | None:
    channels = list(load_channels().keys())
    if not channels:
        print("⚠️ No YouTube channels connected yet!")
        return None
    print("\n📺 Which YouTube channel do you want to post to?")
    for idx, ch in enumerate(channels):
        print(f"  [{idx + 1}] {ch}")
    print("  [n] Skip (Do not upload now)")
    choice = input(f"Select channel (1-{len(channels)}) or 'n' to skip: ").strip().lower()
    if choice in ("n", "no", ""):
        return None
    if choice.isdigit() and 1 <= int(choice) <= len(channels):
        return channels[int(choice) - 1]
    if choice in ("y", "yes"):
        return default_channel
    return None

def upload_video_to_youtube(channel_name: str, video_path: Path) -> str | None:
    youtube = get_authenticated_youtube(channel_name)
    if not youtube:
        print(f"❌ Could not authenticate channel: {channel_name}")
        return None

    meta = load_clip_metadata(video_path)
    print(f"\n🚀 [YouTube] Publishing '{meta['title']}' to '{channel_name}'...")

    body = {
        "snippet": {"title": meta["title"][:100], "description": meta["description"], "tags": meta["tags"], "categoryId": "27"},
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}
    }
    media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True, mimetype="video/mp4")
    req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    res = None
    try:
        while res is None:
            status, res = req.next_chunk()
            if status:
                print(f"   Upload progress: {int(status.progress() * 100)}%")
        yt_id = res.get("id")

        meta["youtube_id"] = yt_id
        meta_path = video_path.with_suffix(".json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

        print(f"🎉 Live on YouTube! https://youtube.com/shorts/{yt_id}")
        return yt_id
    except Exception as e:
        if "uploadLimitExceeded" in str(e):
            print("⚠️ YouTube daily upload limit reached for today. Video is safely stored in 'clips/' folder.")
        else:
            print(f"❌ Upload error: {e}")
        return None

# --- 4. BIBLE SCRIPT ENGINE (FIXED SYNTAX & VOICEOVER) ---
class BibleShortScript(BaseModel):
    topic: str
    title: str
    verse_citation: str
    verse_text: str
    meaning: str
    prayer: str
    thumbnail_hook: str
    hashtags: list[str]

def generate_bible_content(topic_query: str) -> BibleShortScript:
    used_verses_file = BASE_DIR / "used_bible_verses.json"
    try:
        used_verses = json.loads(used_verses_file.read_text(encoding="utf-8")) if used_verses_file.exists() else []
    except Exception:
        used_verses = []

    avoid_list = ", ".join(used_verses[-50:]) if used_verses else "None"
    seed = random.randint(100000, 9999999)

    from voice_studio import load_active_voice, HINDI_BIBLE_VAULT
    active_v_cfg = load_active_voice()
    is_hindi_script = ("Hindi" in active_v_cfg.get("script_mode", "") or "hi-IN" in active_v_cfg.get("voice", ""))
    if is_hindi_script:
        for hk, hval in HINDI_BIBLE_VAULT.items():
            if hk.lower() in topic_query.lower():
                return BibleShortScript(**hval)
    lang_rule = (
        "Write verse_text, meaning, prayer, and thumbnail_hook in Romanized Hindi (Hinglish using English alphabet, e.g. 'Mera Parmeshwar aapki har zaroorat poora karega') so Indian viewers understand easily."
        if is_hindi_script else
        "Write in clear, comforting English."
    )
    sys_prompt = (
        f"You are a Christian content creator. {lang_rule} Respond ONLY in valid JSON with exact keys: "
        "topic, title, verse_citation, verse_text, meaning, prayer, thumbnail_hook, hashtags (list of strings)."
    )
    user_prompt = f"""Seed: {seed}
Topic: {topic_query}
CRITICAL: DO NOT use these verses: [{avoid_list}].
Select a unique, powerful Bible verse specifically about '{topic_query}'. Provide a 2-sentence meaning and a 1-sentence prayer ending in Amen."""

    script_data = None

    print(f"?? [DEBUG] 1. Attempting Direct Fast Gemini API for '{topic_query}'...")
    if API_KEY:
        gemini_models = [
            "gemini-3.5-flash-lite",
            "gemini-3.7-flash",
            "gemini-3.6-flash",
            "gemini-3.1-flash-lite",
            "gemini-3.8-flash"
        ]
        for m_name in gemini_models:
            try:
                print(f"   - Trying Gemini model: {m_name} (7s max timeout)...")
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{m_name}:generateContent?key={API_KEY}"
                payload = {
                    "contents": [{"parts": [{"text": sys_prompt + " " + user_prompt}]}],
                    "generationConfig": {
                        "responseMimeType": "application/json",
                        "temperature": 1.0
                    }
                }
                req = urllib.request.Request(
                    url,
                    headers={"Content-Type": "application/json"},
                    data=json.dumps(payload).encode("utf-8")
                )
                with urllib.request.urlopen(req, timeout=7) as resp:
                    resp_json = json.loads(resp.read().decode("utf-8"))
                    raw_text = resp_json["candidates"][0]["content"]["parts"][0]["text"]
                    match = re.search(r"\{.*\}", raw_text, re.DOTALL)
                    if match:
                        raw_text = match.group(0)
                    parsed = json.loads(raw_text)
                    script_data = BibleShortScript(**parsed).model_dump()
                    print(f"   ?? [SUCCESS] Connected in 1s via Gemini ({m_name})!")
                    break
            except Exception as e:
                print(f"   ? [SKIP] {m_name}: {e}")
                continue
    else:
        print("   ?? GEMINI_API_KEY missing in .env file.")

    or_key = os.getenv("OPENROUTER_API_KEY")
    if not script_data and or_key:
        print("?? [DEBUG] 2. Switching to OpenRouter Free Models...")
        free_models = [
            "openrouter/free",
            "google/gemma-4-31b-it:free",
            "google/gemma-4-26b-a4b-it:free",
            "nvidia/nemotron-3-super-120b-a12b:free"
        ]

        for model in free_models:
            try:
                print(f"   - Trying OpenRouter model: {model} (8s max timeout)...")
                req = urllib.request.Request(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {or_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://localhost",
                        "X-Title": "DailyWisdomStudio"
                    },
                    data=json.dumps({
                        "model": model,
                        "messages": [
                            {"role": "system", "content": sys_prompt},
                            {"role": "user", "content": user_prompt}
                        ]
                    }).encode("utf-8")
                )
                with urllib.request.urlopen(req, timeout=8) as response:
                    data = json.loads(response.read().decode("utf-8"))
                    raw_text = data["choices"][0]["message"]["content"]
                    match = re.search(r"\{.*\}", raw_text, re.DOTALL)
                    if match:
                        raw_text = match.group(0)
                    parsed = json.loads(raw_text)
                    script_data = BibleShortScript(**parsed).model_dump()
                    print(f"   ?? [SUCCESS] Connected via OpenRouter ({model})!")
                    break
            except Exception as e:
                print(f"   ? [SKIP] {model}: {e}")
                continue

    if not script_data:
        print("?? [DEBUG] 3. Falling back to local curated vault...")
        matching = [
            v for v in CURATED_BIBLE_VAULT.values()
            if v["topic"].lower() in topic_query.lower() or topic_query.lower() in v["topic"].lower()
        ]
        if not matching:
            matching = list(CURATED_BIBLE_VAULT.values())
        available = [m for m in matching if m["verse_citation"] not in used_verses]
        script_data = random.choice(available) if available else random.choice(matching)

    script = BibleShortScript(**script_data)
    if is_hindi_script:
        from bible_database import lookup_reference_bilingual, translate_any_text_to_hindi
        _, _, dev_v, _ = lookup_reference_bilingual(script.verse_citation)
        if dev_v:
            script.verse_text = dev_v
        else:
            script.verse_text = translate_any_text_to_hindi(script.verse_text)
        script.meaning = translate_any_text_to_hindi(script.meaning)
        script.prayer = translate_any_text_to_hindi(script.prayer)
    if script.verse_citation not in used_verses:
        used_verses.append(script.verse_citation)
        used_verses_file.write_text(json.dumps(used_verses, indent=2), encoding="utf-8")

    return script


def generate_bible_content_from_exact_verse(book_name: str, chapter: int, verse_num: int, custom_topic: str = "") -> BibleShortScript:
    """Generates a complete devotional Short script around an exact user-selected Book, Chapter, and Verse."""
    from bible_database import get_verses_for_chapter, translate_verse_to_hindi
    from voice_studio import load_active_voice

    verses_map = get_verses_for_chapter(book_name, chapter)
    en_text = verses_map.get(verse_num, "The Lord is near to all who call upon Him.")
    ref_str = f"{book_name.strip()} {chapter}:{verse_num}"
    topic_label = custom_topic.strip() or f"{book_name.strip()} {chapter}:{verse_num} Promise"

    active_v = load_active_voice()
    is_hindi_mode = "Hindi / Hinglish" in active_v.get("script_mode", "")

    if is_hindi_mode:
        _, hinglish_v = translate_verse_to_hindi(ref_str, en_text)
        v_text_final = hinglish_v if hinglish_v else en_text
    else:
        v_text_final = en_text

    # Ask Gemini to craft the reflection, prayer, and hook specifically for this exact verse
    prompt = f"""Create a Christian YouTube Short script for this EXACT Bible verse:
Reference: {ref_str}
Verse Text: {v_text_final}
Topic: {topic_label}
Language Mode: {'Romanized Hindi (Hinglish)' if is_hindi_mode else 'English'}

Respond ONLY in valid JSON with exact keys:
topic, title, verse_citation, verse_text, meaning, prayer, thumbnail_hook, hashtags (list of strings).
IMPORTANT: Keep verse_citation as '{ref_str}' and verse_text as '{v_text_final}'."""

    if API_KEY:
        for m_name in ["gemini-3.5-flash-lite", "gemini-3.7-flash", "gemini-3.6-flash"]:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{m_name}:generateContent?key={API_KEY}"
                payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"responseMimeType": "application/json", "temperature": 0.7}
                }
                req = urllib.request.Request(url, headers={"Content-Type": "application/json"}, data=json.dumps(payload).encode("utf-8"))
                with urllib.request.urlopen(req, timeout=7) as resp:
                    resp_json = json.loads(resp.read().decode("utf-8"))
                    raw_t = resp_json["candidates"][0]["content"]["parts"][0]["text"]
                    m = re.search(r"\{.*\}", raw_t, re.DOTALL)
                    if m:
                        raw_t = m.group(0)
                    parsed = json.loads(raw_t)
                    parsed["verse_citation"] = ref_str
                    parsed["verse_text"] = v_text_final
                    return BibleShortScript(**parsed)
            except Exception:
                continue

    if is_hindi_mode:
        return BibleShortScript(
            topic=topic_label,
            title=f"{ref_str} Parmeshwar Ka Vachan #shorts",
            verse_citation=ref_str,
            verse_text=v_text_final,
            meaning="Prabhu ka yeh pavitra vachan aapke jeevan mein nayi shanti aur aasha lata hai. Unpar poora bharosa rakhein.",
            prayer="Prabhu Yeshu, is vachan ko mere jeevan mein poora karein aur mujhe apni shanti dein, Amen.",
            thumbnail_hook=f"{ref_str.upper()} PROMISE",
            hashtags=["#HindiBible", "#YeshuMasih", "#BibleVerse", "#Shorts"]
        )

    return BibleShortScript(
        topic=topic_label,
        title=f"God's Promise in {ref_str} #shorts",
        verse_citation=ref_str,
        verse_text=v_text_final,
        meaning="Let this timeless promise anchor your soul today. God's word never returns void and His grace surrounds you right now.",
        prayer="Lord, thank You for the promise of Your Word; let its truth bring peace and strength to my heart today, Amen.",
        thumbnail_hook=f"{ref_str.upper()} PROMISE",
        hashtags=["#BibleVerse", "#DailyPrayer", "#Faith", "#Shorts"]
    )


def generate_voiceover(text: str, output_voice_path: Path):
    """Generates audio AND millisecond-synced word timings using the selected Voice Studio profile (Hindi/Indian/UK/US)."""
    from voice_studio import load_active_voice
    active_v = load_active_voice()
    v_name = active_v.get("voice", "hi-IN-MadhurNeural")
    v_rate = active_v.get("rate", "-4%")
    v_pitch = active_v.get("pitch", "+0Hz")
    print(f"   🎙️ Speaking with Voice: {active_v.get('name')} [{v_name} | Rate: {v_rate} | Pitch: {v_pitch}]")

    # Ensure no raw number:number colons reach TTS as clock time
    if "hi-IN" in v_name and "Hindi" in active_v.get("script_mode", ""):
        text = re.sub(r"(\d+):(\d+)", r"अध्याय \1 वचन \2", text)
    else:
        text = re.sub(r"(\d+):(\d+)", r"chapter \1 verse \2", text)
    json_path = Path(str(output_voice_path).replace(".mp3", ".json"))

    async def _make():
        try:
            communicate = edge_tts.Communicate(text, voice=v_name, rate=v_rate, pitch=v_pitch, boundary="WordBoundary")
        except TypeError:
            try:
                communicate = edge_tts.Communicate(text, voice=v_name, rate=v_rate, boundary="WordBoundary")
            except TypeError:
                communicate = edge_tts.Communicate(text, voice=v_name, rate=v_rate)

        raw_events = []
        with open(output_voice_path, "wb") as f_voice:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    f_voice.write(chunk["data"])
                elif chunk["type"] in ("WordBoundary", "SentenceBoundary"):
                    start_s = chunk["offset"] / 10_000_000.0
                    dur_s = chunk["duration"] / 10_000_000.0
                    raw_events.append({
                        "type": chunk["type"],
                        "text": chunk["text"],
                        "start": start_s,
                        "end": start_s + dur_s
                    })

        word_timings = []
        for ev in raw_events:
            if ev["type"] == "WordBoundary" or len(ev["text"].split()) == 1:
                word_timings.append({
                    "text": ev["text"].strip(),
                    "start": round(ev["start"], 3),
                    "end": round(ev["end"], 3)
                })
            else:
                words = ev["text"].split()
                if not words:
                    continue
                weights = []
                for w in words:
                    w_weight = max(2, len(w))
                    if re.search(r"[.,;!?]", w):
                        w_weight += 4
                    weights.append(w_weight)
                total_w = sum(weights) or 1
                cur_t = ev["start"]
                ev_dur = max(0.1, ev["end"] - ev["start"])
                for w, wt in zip(words, weights):
                    w_dur = ev_dur * (wt / total_w)
                    word_timings.append({
                        "text": w,
                        "start": round(cur_t, 3),
                        "end": round(cur_t + w_dur, 3)
                    })
                    cur_t += w_dur

        merged_timings = []
        i = 0
        while i < len(word_timings):
            cur = word_timings[i]
            c_clean = re.sub(r"[^0-9]", "", cur["text"])
            if i + 1 < len(word_timings):
                nxt = word_timings[i + 1]
                n_clean = re.sub(r"[^0-9\-]", "", nxt["text"])
                if cur["text"].isdigit() and n_clean and nxt["text"][0].isdigit():
                    merged_timings.append({
                        "text": f"{c_clean}:{n_clean}",
                        "start": cur["start"],
                        "end": nxt["end"]
                    })
                    i += 2
                    continue
            merged_timings.append(cur)
            i += 1

        if merged_timings:
            json_path.write_text(json.dumps(merged_timings, indent=2), encoding="utf-8")

    try:
        asyncio.run(_make())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_make())
        loop.close()



def create_designer_thumbnail(bg_image_path: Path, script: BibleShortScript, font_path: Path, thumb_path: Path, palette_name: str = "Gold Classic"):
    from pro_design_addon import render_pro_thumbnails
    render_pro_thumbnails(bg_image_path, script, thumb_path, palette_name=palette_name)


# --- 5. RENDER FACELESS BIBLE VIDEO ---
def _sec_to_ass_time(sec: float) -> str:
    sec = max(0.0, float(sec))
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"

def render_faceless_bible_video(script: BibleShortScript, voice_path: Path, output_path: Path, thumb_path: Path, custom_intro: Path | None = None, custom_bg: Path | None = None, custom_thumb: Path | None = None, raw_thumb_only: bool = False) -> bool:
    w, h = 1080, 1920
    ensure_sacred_assets()

    duration = 30.0
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(voice_path.absolute())],
            cwd=str(BASE_DIR), capture_output=True, text=True
        )
        if probe.stdout.strip():
            duration = float(probe.stdout.strip()) + 1.0
    except Exception:
        pass

    from voice_studio import load_active_voice
    _cur_v = load_active_voice()
    _is_hi = ("Hindi" in _cur_v.get("script_mode", "") or "hi-IN" in _cur_v.get("voice", ""))
    local_font = BASE_DIR / ("hindi_bold_font.ttf" if _is_hi else "bold_font.ttf")
    if _is_hi and not local_font.exists():
        for hf in ["C:/Windows/Fonts/NirmalaB.ttf", "C:/Windows/Fonts/Nirmala.ttf", "C:/Windows/Fonts/mangal.ttf"]:
            if Path(hf).exists():
                shutil.copy(hf, local_font)
                break
    if not local_font.exists():
        for f in ["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/georgiab.ttf", "C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/arial.ttf"]:
            if Path(f).exists():
                shutil.copy(f, local_font)
                break
    font_bold = local_font.name

    muted_video = mute_any_video(custom_intro) if (custom_intro and custom_intro.exists()) else prepare_muted_short_main()
    jesus_img = custom_bg if (custom_bg and custom_bg.exists()) else get_jesus_image()
    bgm_audio = get_worship_bgm()

    raw_citation = re.sub(r"[^a-zA-Z0-9\s:\-]", "", script.verse_citation).upper().strip()[:28]
    ff_citation = raw_citation.replace(":", r"\:")
    clean_topic = re.sub(r"\s+", " ", re.sub(r"[^a-zA-Z0-9\s&\-]", "", script.topic)).upper().strip()
    topic_fsize = 36 if len(clean_topic) <= 22 else max(24, int(820 / max(1, len(clean_topic) * 0.62)))

    intro_dur = min(10.0, max(5.0, duration * 0.35))
    image_dur = max(1.0, duration - intro_dur)

    print("  ⚡ Fast-Rendering 1080p Video (SAR-Normalized + Single-Pass 102pt Subtitles)...")

    inputs = []
    if muted_video and muted_video.exists():
        inputs = [
            "-stream_loop", "-1", "-t", f"{intro_dur:.2f}", "-i", str(muted_video.absolute()),
            "-loop", "1", "-t", f"{image_dur:.2f}", "-i", str(jesus_img.absolute()),
            "-i", str(voice_path.absolute()),
            "-stream_loop", "-1", "-t", f"{duration:.2f}", "-i", str(bgm_audio.absolute())
        ]
        # Force format=yuv420p,setsar=1,fps=24 on BOTH streams so concat never throws -22
        bg_filter = (
            f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps=24,format=yuv420p,setsar=1,setpts=PTS-STARTPTS[v_intro];"
            f"[1:v]scale=1240:2204:force_original_aspect_ratio=increase,crop={w}:{h}:(in_w-out_w)/2:'(in_h-out_h)*(0.15+0.75*t/{image_dur:.2f})',fps=24,format=yuv420p,setsar=1,setpts=PTS-STARTPTS[v_jesus];"
            f"[v_intro][v_jesus]concat=n=2:v=1:a=0,eq=brightness=-0.06:contrast=1.16:saturation=1.12[bg];"
        )
        voice_idx, bgm_idx = "2:a", "3:a"
    else:
        inputs = [
            "-loop", "1", "-t", f"{duration:.2f}", "-i", str(jesus_img.absolute()),
            "-i", str(voice_path.absolute()),
            "-stream_loop", "-1", "-t", f"{duration:.2f}", "-i", str(bgm_audio.absolute())
        ]
        bg_filter = (
            f"[0:v]scale=1240:2204:force_original_aspect_ratio=increase,crop={w}:{h}:(in_w-out_w)/2:'(in_h-out_h)*(0.15+0.75*t/{duration:.2f})',"
            f"fps=24,format=yuv420p,setsar=1,eq=brightness=-0.06:contrast=1.16:saturation=1.12[bg];"
        )
        voice_idx, bgm_idx = "1:a", "2:a"

    json_path = str(voice_path).replace(".mp3", ".json")
    timings = []
    if Path(json_path).exists():
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                timings = json.load(f)
        except Exception:
            timings = []

    if not timings:
        full_spoken = f"If you are struggling with {script.topic}, hold onto this verse. {script.verse_citation}. {script.verse_text}. {script.meaning}. Let us pray. {script.prayer} Type Amen in the comments to receive this blessing."
        words = full_spoken.split()
        weights = [max(2, len(w_s)) + (4 if re.search(r"[.,;!?]", w_s) else 0) for w_s in words]
        total_w = sum(weights) or 1
        cur_t = 0.0
        usable_dur = max(1.0, duration - 1.0)
        for w_str, wt in zip(words, weights):
            w_d = usable_dur * (wt / total_w)
            timings.append({"text": w_str, "start": round(cur_t, 3), "end": round(cur_t + w_d, 3)})
            cur_t += w_d

    phrases = []
    current = []
    c_start = 0.0
    for i, w_obj in enumerate(timings):
        if not current:
            c_start = w_obj["start"]
        current.append(w_obj["text"])
        text_str = " ".join(current)

        next_len = len(text_str) + (len(timings[i + 1]["text"]) + 1 if i + 1 < len(timings) else 0)
        if next_len > 10 or len(current) >= 2 or re.search(r"[.,;!?]", w_obj["text"]) or i == len(timings) - 1:
            c_end = timings[i + 1]["start"] if i + 1 < len(timings) else (w_obj["end"] + 0.12)
            safe_text = re.sub(r"[^a-zA-Z0-9\u0900-\u097F\s:\-]", "", text_str).strip()
            if safe_text:
                phrases.append({"text": safe_text, "start": round(c_start, 3), "end": round(c_end, 3)})
            current = []

    # Build a single ultra-fast ASS subtitle file (1 filter pass instead of 60 drawtext filters!)
    ass_path = BASE_DIR / "temp_fast_subs.ass"
    ass_lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {w}",
        f"PlayResY: {h}",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        # &H59FFFFFF = 65% opaque white (35% transparent), &H70000000 = soft shadow
        "Style: SubPop,Nirmala UI,96,&H45FFFFFF,&H0000FFFF,&H80000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,4,5,60,60,0,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for p in phrases:
        t_str = p["text"]
        f_sz = 102 if len(t_str) <= 10 else max(64, int(1020 / (len(t_str) * 0.58)))
        st_time = _sec_to_ass_time(p["start"])
        en_time = _sec_to_ass_time(max(p["start"] + 0.08, p["end"]))
        ass_lines.append(f"Dialogue: 0,{st_time},{en_time},SubPop,,0,0,0,,{{\\fs{f_sz}}}{t_str}")

    ass_path.write_text("\n".join(ass_lines), encoding="utf-8")

    # Single-pass filtergraph: renders in ~4 seconds!
    filter_complex = (
        f"{bg_filter}"
        f"[bg]drawtext=fontfile='{font_bold}':text='THE WORD OF GOD':fontcolor=0xFFD700@0.75:fontsize=26:shadowcolor=black@0.7:shadowx=2:shadowy=2:x=(w-text_w)/2:y=150[hdr0];"
        f"[hdr0]drawtext=fontfile='{font_bold}':text='{clean_topic}':fontcolor=0xFFD700@0.95:fontsize={topic_fsize}:shadowcolor=black@0.8:shadowx=3:shadowy=3:x=(w-text_w)/2:y=190[hdr1];"
        f"[hdr1]drawtext=fontfile='{font_bold}':text='{ff_citation}':fontcolor=white@0.95:fontsize=46:shadowcolor=black@0.85:shadowx=3:shadowy=3:x=(w-text_w)/2:y=250[hdr2];"
        f"[hdr2]subtitles='temp_fast_subs.ass'[sub_out];"
        f"[sub_out]drawtext=fontfile='{font_bold}':text='Type AMEN to receive this blessing':fontcolor=0xFFD700@0.85:fontsize=38:shadowcolor=black@0.7:shadowx=3:shadowy=3:x=(w-text_w)/2:y=1700[vout];"
        f"[{voice_idx}]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,volume=1.0[voice];"
        f"[{bgm_idx}]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,volume=0.20[bgm];"
        f"[voice][bgm]amix=inputs=2:duration=first:normalize=0,aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[aout]"
    )

    cmd = [
        "ffmpeg", "-y", "-threads", "0",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "19", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-t", f"{duration:.2f}",
        str(output_path.absolute())
    ]

    try:
        subprocess.run(cmd, cwd=str(BASE_DIR), capture_output=True, text=True, timeout=60, check=True)
    except subprocess.CalledProcessError as e:
        print(" ❌ FFMPEG ERROR DETAILS:")
        print(e.stderr[-600:])
        return False
    finally:
        for tf in [ass_path, Path(json_path)]:
            if tf.exists():
                tf.unlink(missing_ok=True)

    thumb_bg = custom_thumb if (custom_thumb and custom_thumb.exists()) else (jesus_img if (jesus_img and jesus_img.exists()) else (BASE_DIR / "jesus_white_robes.jpg"))
    try:
        if raw_thumb_only and custom_thumb and custom_thumb.exists():
            from PIL import Image
            im = Image.open(custom_thumb).convert("RGB").resize((w, h))
            im.save(str(thumb_path), "JPEG", quality=95)
        else:
            print("  • Designing graphical thumbnail (glows, glass badges, 3D strokes)...")
            create_designer_thumbnail(thumb_bg, script, local_font, thumb_path)
    except Exception as e:
        print(f"  ⚠️ Thumbnail fallback: {e}")
    return True

# --- 6. PODCAST CLIPPER ENGINE ---
class BookClip(BaseModel):
    title: str = Field(description="Short title")
    start_time: str
    end_time: str
    book_title: str
    book_author: str
    hook_caption: str
    hashtags: list[str]

class AnalysisResponse(BaseModel):
    clips: list[BookClip]

def find_viral_video(min_views: int, queries: list[str]) -> dict | None:
    history = set()
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, "r") as f:
                history = set(json.load(f))
        except Exception:
            pass

    print(f"  • Scanning influencer channels for {min_views:,}+ view videos...")
    ydl_opts = {"quiet": True, "extract_flat": True, "skip_download": True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        for q in queries:
            try:
                res = ydl.extract_info(q, download=False)
                for entry in res.get("entries", []):
                    if not entry:
                        continue
                    v_id = entry.get("id")
                    dur = entry.get("duration", 0)
                    views = entry.get("view_count") or 0

                    if v_id in history or dur < 180 or dur > 3600:
                        continue

                    if views >= min_views:
                        return {"id": v_id, "url": f"https://www.youtube.com/watch?v={v_id}", "title": entry.get("title"), "views": views}
            except Exception:
                continue
    return None

def get_transcript(video_id: str) -> str | None:
    print("  • Checking for multi-language captions on YouTube...")
    try:
        api = YouTubeTranscriptApi()
        if hasattr(api, "fetch"):
            f = api.fetch(video_id, languages=["en", "en-US", "en-GB", "te", "hi", "es"])
            data = f.to_raw_data() if hasattr(f, "to_raw_data") else list(f)
        else:
            data = YouTubeTranscriptApi.get_transcript(video_id, languages=["en", "en-US", "en-GB", "te", "hi", "es"])

        formatted = []
        for line in data:
            sec = int(line.get("start", 0))
            m, s = divmod(sec, 60)
            h, m = divmod(m, 60)
            ts = f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"
            formatted.append(f"[{ts}] {line.get('text', '')}")
        return "\n".join(formatted)
    except Exception:
        return None

def analyze_audio_fallback(url: str, category_name: str) -> list[BookClip]:
    if not client:
        return []

    print("  • No text captions found. Downloading tiny audio stream (~3 MB) for AI listening...")
    temp_audio = BASE_DIR / "temp_listen.mp3"
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": str(temp_audio),
        "overwrites": True,
        "quiet": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    print("  • Gemini listening to audio & detecting viral hook moments...")
    audio_file = client.files.upload(file=str(temp_audio))
    while audio_file.state.name == "PROCESSING":
        time.sleep(2)
        audio_file = client.files.get(name=audio_file.name)

    prompt = f"""
    Listen to this audio track. Identify the top 2 most viral, inspiring, or emotional moments (strictly 30 to 50 seconds each).
    Return exact start_time and end_time (MM:SS), catchy title, hook_caption, and hashtags for {category_name}.
    """
    try:
        res = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=[audio_file, prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=AnalysisResponse,
                thinking_config=types.ThinkingConfig(thinking_level="low")
            )
        )
        clips = [BookClip(**item) for item in json.loads(res.text).get("clips", [])]
    except Exception as e:
        print(f"❌ Gemini audio listening error: {e}")
        clips = []
    finally:
        try:
            client.files.delete(name=audio_file.name)
            if temp_audio.exists():
                temp_audio.unlink()
        except Exception:
            pass

    return clips

def analyze_transcript(transcript_text: str, category_name: str) -> list[BookClip]:
    if not client:
        return []
    prompt = f"Extract top 2 viral moments from this transcript for {category_name}.\nTRANSCRIPT:\n{transcript_text[:120000]}"
    try:
        res = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=AnalysisResponse, thinking_config=types.ThinkingConfig(thinking_level="low")),
        )
        return [BookClip(**item) for item in json.loads(res.text).get("clips", [])]
    except Exception:
        return []

def download_slice(url: str, start_sec: float, end_sec: float, output_path: Path):
    pad_start = max(0.0, start_sec - 1.5)
    pad_end = end_sec + 1.5
    print(f"  • Downloading ONLY the {round(pad_end - pad_start)}s slice (~20 MB)...")

    ydl_opts = {
        "format": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]/best",
        "download_ranges": download_range_func(None, [(pad_start, pad_end)]),
        "force_keyframes_at_cuts": True,
        "outtmpl": str(output_path),
        "merge_output_format": "mp4",
        "overwrites": True,
        "quiet": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

def render_podcast_short(raw_slice: Path, clip: BookClip, output_path: Path, badge_tag: str) -> bool:
    w, h = 1080, 1920
    ensure_sacred_assets()

    start_sec = timestamp_to_seconds(clip.start_time)
    end_sec = timestamp_to_seconds(clip.end_time)
    duration = max(1.0, end_sec - start_sec)
    offset_start = 1.5 if start_sec >= 1.5 else start_sec

    clean_book = re.sub(r'[\':,"]', '', clip.book_title).upper()[:28]
    font_file = "C\\:/Windows/Fonts/arial.ttf"

    print(f"  • Rendering Designer Short with [{badge_tag}] badge...")

    filter_complex = (
        f"[0:v]setpts=PTS-STARTPTS,scale=-2:{h}:flags=lanczos,crop={w}:{h}:(in_w-{w})/2:0,"
        f"unsharp=5:5:0.85:5:5:0.0,eq=contrast=1.06:saturation=1.10[v_base];"
        f"[v_base]drawbox=x=110:y=220:w=860:h=140:color=0x0D0D12@0.88:t=fill[card1];"
        f"[card1]drawbox=x=110:y=220:w=860:h=140:color=0xD4AF37@0.85:t=3[card2];"
        f"[card2]drawbox=x=110:y=220:w=12:h=140:color=0xD4AF37@1:t=fill[card3];"
        f"[card3]drawtext=fontfile='{font_file}':text='FEATURED - {badge_tag}':fontcolor=0xD4AF37:fontsize=20:x=145:y=240[txt1];"
        f"[txt1]drawtext=fontfile='{font_file}':text='{clean_book}':fontcolor=white:fontsize=34:x=145:y=274[txt2];"
        f"[txt2]drawtext=fontfile='{font_file}':text='Link in Channel Bio ↗':fontcolor=0xBBBBCC:fontsize=22:x=145:y=322[txt3];"
        f"[txt3]drawbox=x=0:y=1902:w='min({w}, {w}*t/{duration})':h=16:color=0xD4AF37@1:t=fill[vout];"
        f"[0:a]asetpts=PTS-STARTPTS,aformat=sample_fmts=fltp:sample_rates=44100[speech];"
        f"[1:a]volume=0.08,aformat=sample_fmts=fltp:sample_rates=44100[bgm];"
        f"[speech][bgm]amix=inputs=2:duration=first[aout]"
    )

    cmd = [
        "ffmpeg", "-y", "-ss", str(offset_start), "-t", str(duration), "-i", str(raw_slice),
        "-stream_loop", "-1", "-i", str(BGM_PODCAST_FILE),
        "-filter_complex", filter_complex, "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "19", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        str(output_path)
    ]
    return subprocess.run(cmd, capture_output=True, text=True).returncode == 0

# --- 7. STANDALONE DOWNLOADERS ---
# --- PINTEREST IMAGE & VIDEO DOWNLOADER (AUTO-SORTED & AUTO-MUTED) ---
PINTEREST_DIR = BASE_DIR / "Pinterest"
PIN_IMG_DIR = PINTEREST_DIR / "Images"
PIN_VID_DIR = PINTEREST_DIR / "Videos"
for _pd in [PIN_IMG_DIR, PIN_VID_DIR]:
    _pd.mkdir(parents=True, exist_ok=True)

def _next_pin_seq(folder: Path) -> int:
    nums = []
    for f in folder.iterdir():
        m = re.match(r"^(\d{3})_", f.name)
        if m:
            nums.append(int(m.group(1)))
    return (max(nums) + 1) if nums else 1

def download_pinterest_media(url: str, sync_to_studio: bool = True) -> Path | None:
    """Reliably downloads any Pinterest Video (.mp4/.m3u8) or HD Image from pin.it / in.pinterest.com / pinterest.com."""
    url = url.strip()
    if not url:
        return None

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9"
    }

    print(f"\n📌 [Pinterest] Resolving link: {url}...")

    # 1. Resolve short links (pin.it) & regional domains (in.pinterest.com) to canonical Pin URL
    final_url = url
    html = ""
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=12) as resp:
            final_url = resp.geturl()
            html = resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"⚠️ Initial fetch note: {e}")

    pin_id_match = re.search(r"/pin/(?:[^/]+--)?(\d+)", final_url) or re.search(r"/pin/(?:[^/]+--)?(\d+)", url)
    if pin_id_match:
        pin_id = pin_id_match.group(1)
        canonical_url = f"https://www.pinterest.com/pin/{pin_id}/"
        if canonical_url != final_url or not html:
            try:
                req2 = urllib.request.Request(canonical_url, headers=headers)
                with urllib.request.urlopen(req2, timeout=12) as resp2:
                    html = resp2.read().decode("utf-8", errors="ignore")
                final_url = canonical_url
            except Exception:
                pass
    else:
        pin_id = str(int(time.time()))

    # Unescape Pinterest's JSON slashes (\u002F and \/) so all hidden video & image URLs are exposed
    html_clean = html.replace("\\u002F", "/").replace("\\/", "/").replace("&amp;", "&")

    title_m = re.search(r"<title>([^<]+)</title>", html_clean)
    raw_title = title_m.group(1).replace("Pinterest", "").replace("|", "").strip() if title_m else f"Pin_{pin_id}"
    pin_title = clean_filename(raw_title) or f"Pin_{pin_id}"

    # 2. Check for Direct Pinterest Video Streams (.mp4 or .m3u8) inside the Pin's JSON data
    mp4_urls = re.findall(r"https://v\d*\.pinimg\.com/videos/[^\"'\s\\<>]+\.mp4", html_clean)
    m3u8_urls = re.findall(r"https://v\d*\.pinimg\.com/videos/[^\"'\s\\<>]+\.m3u8", html_clean)

    if mp4_urls or m3u8_urls:
        vid_seq = _next_pin_seq(PIN_VID_DIR)
        final_vid = PIN_VID_DIR / f"{vid_seq:03d}_{pin_title}.mp4"

        # Prefer 720p / expmp4 direct MP4 if available
        if mp4_urls:
            best_mp4 = mp4_urls[0]
            for u in mp4_urls:
                if "720p" in u or "expmp4" in u:
                    best_mp4 = u
                    break
            print(f"🎬 Found Pinterest HD MP4 Video Stream! Downloading...")
            try:
                v_req = urllib.request.Request(best_mp4, headers=headers)
                with urllib.request.urlopen(v_req, timeout=20) as v_resp:
                    final_vid.write_bytes(v_resp.read())
            except Exception as e:
                print(f"⚠️ Direct MP4 download note: {e}")

        # If direct MP4 wasn't saved, convert HLS .m3u8 stream via FFmpeg
        if (not final_vid.exists() or final_vid.stat().st_size < 5000) and m3u8_urls:
            print("🎬 Downloading Pinterest HLS Video Stream via FFmpeg...")
            cmd_hls = [
                "ffmpeg", "-y", "-i", m3u8_urls[0],
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                "-an", str(final_vid)
            ]
            subprocess.run(cmd_hls, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        if final_vid.exists() and final_vid.stat().st_size > 5000:
            print(f"✅ [Pinterest Video] Saved to: Pinterest/Videos/{final_vid.name}")
            if sync_to_studio:
                studio_copy = INTRO_DIR / final_vid.name
                shutil.copy(final_vid, studio_copy)
                mute_any_video(studio_copy)
                print(f"🔇 Auto-muted & added to Studio Intro Videos: {studio_copy.name}")
            return final_vid

    # 3. Try yt-dlp on the canonical URL if regex didn't catch a video
    vid_seq = _next_pin_seq(PIN_VID_DIR)
    temp_pin = PINTEREST_DIR / f"temp_pin_{pin_id}"
    ydl_opts = {
        "outtmpl": str(temp_pin) + ".%(ext)s",
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.extract_info(final_url, download=True)
            downloaded_files = list(PINTEREST_DIR.glob(f"{temp_pin.name}*"))
            if downloaded_files and downloaded_files[0].stat().st_size > 5000:
                final_vid = PIN_VID_DIR / f"{vid_seq:03d}_{pin_title}.mp4"
                shutil.move(str(downloaded_files[0]), str(final_vid))
                print(f"✅ [Pinterest Video] Saved to: Pinterest/Videos/{final_vid.name}")
                if sync_to_studio:
                    studio_copy = INTRO_DIR / final_vid.name
                    shutil.copy(final_vid, studio_copy)
                    mute_any_video(studio_copy)
                    print(f"🔇 Auto-muted & added to Studio Intro Videos: {studio_copy.name}")
                return final_vid
    except Exception:
        for leftover in PINTEREST_DIR.glob(f"{temp_pin.name}*"):
            leftover.unlink(missing_ok=True)

    # 4. Extract Exact Pin High-Res Image (og:image & orig JSON field)
    print("🖼️ Extracting High-Res Pinterest Image...")
    img_candidates = []

    # Check og:image meta tag first (always points to the exact Pin's main image, never sidebar ads)
    og_m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\'](https://i\.pinimg\.com/[^"\']+)["\']', html_clean)
    if not og_m:
        og_m = re.search(r'<meta[^>]+content=["\'](https://i\.pinimg\.com/[^"\']+)["\'][^>]+property=["\']og:image["\']', html_clean)
    if og_m:
        og_url = og_m.group(1)
        orig_upgrade = re.sub(r"/\d+x/", "/originals/", og_url)
        img_candidates.extend([orig_upgrade, og_url])

    # Also check "orig":{"width":...,"url":"https://i.pinimg.com/originals/..."}
    orig_matches = re.findall(r'"orig"\s*:\s*\{[^{}]*"url"\s*:\s*"(https://i\.pinimg\.com/originals/[^"]+)"', html_clean)
    img_candidates.extend(orig_matches)

    # Fallback to 736x images
    if not img_candidates:
        img_candidates.extend(re.findall(r"https://i\.pinimg\.com/(?:originals|736x|564x)/[a-zA-Z0-9/_.-]+\.(?:jpg|jpeg|png|webp)", html_clean))

    if not img_candidates:
        print("❌ Could not find a valid image or video stream on this Pinterest link.")
        return None

    img_seq = _next_pin_seq(PIN_IMG_DIR)
    final_img = PIN_IMG_DIR / f"{img_seq:03d}_{pin_title}.jpg"

    for candidate_u in dict.fromkeys(img_candidates):
        try:
            img_req = urllib.request.Request(candidate_u, headers=headers)
            with urllib.request.urlopen(img_req, timeout=12) as i_resp:
                data = i_resp.read()
                if len(data) > 5000:
                    final_img.write_bytes(data)
                    break
        except Exception:
            continue

    if final_img.exists() and final_img.stat().st_size > 5000:
        print(f"✅ [Pinterest Image] Saved to: Pinterest/Images/{final_img.name}")
        if sync_to_studio:
            shutil.copy(final_img, BG_DIR / final_img.name)
            shutil.copy(final_img, THUMB_DIR / final_img.name)
            print(f"🎨 Added to Studio Backgrounds & Thumbnails: {final_img.name}")
        return final_img

    print("❌ Failed to download image bytes from Pinterest.")
    return None

def run_cli_pinterest_downloader():
    print("\n" + "=" * 65)
    print("📌 PINTEREST IMAGE & VIDEO DOWNLOADER (AUTO-SORTED)")
    print(f"📂 Images Folder: {PIN_IMG_DIR.resolve()}")
    print(f"📂 Videos Folder: {PIN_VID_DIR.resolve()}")
    print("=" * 65)
    pin_url = input("Paste Pinterest Pin URL (pin.it or pinterest.com/pin/...): ").strip()
    if pin_url:
        download_pinterest_media(pin_url, sync_to_studio=True)


def download_audio_from_url():
    print("\n" + "=" * 60)
    print("🎵 DOWNLOAD HIGH-QUALITY MP3 AUDIO FROM YOUTUBE")
    print("=" * 60)
    url = input("Paste YouTube Video URL: ").strip()
    if not url:
        return

    print("\n📥 Downloading and extracting audio (MP3 192kbps)...")
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': str(DOWNLOADS_DIR / '%(title)s.%(ext)s'),
        'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
        'overwrites': True,
        'quiet': False,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            print(f"\n✅ Audio Downloaded: '{info.get('title')}.mp3'")
            print(f"📁 Saved to: {DOWNLOADS_DIR.resolve()}")
    except Exception as e:
        print(f"❌ Download failed: {e}")

def download_video_from_url():
    print("\n" + "=" * 60)
    print("📹 DOWNLOAD FULL HD (1080P) MP4 VIDEO FROM YOUTUBE")
    print("=" * 60)
    url = input("Paste YouTube Video URL: ").strip()
    if not url:
        return

    print("\n📥 Downloading 1080p HD master video...")
    ydl_opts = {
        'format': 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]/best',
        'outtmpl': str(DOWNLOADS_DIR / '%(title)s.%(ext)s'),
        'merge_output_format': 'mp4',
        'overwrites': True,
        'quiet': False,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            print(f"\n✅ Video Downloaded: '{info.get('title')}.mp4'")
            print(f"📁 Saved to: {DOWNLOADS_DIR.resolve()}")
    except Exception as e:
        print(f"❌ Download failed: {e}")

# --- 8. CLI RUNNERS ---
def run_cli_bible(active_channel: str):
    print("\n" + "=" * 60)
    print("✝️ GENERATE FACELESS BIBLE VERSE & PRAYER SHORT")
    print("=" * 60)
    print("Select a Topic:")
    for k, v in CURATED_BIBLE_VAULT.items():
        print(f"  [{k}] {v['topic']}")
    print("  [8] Type a Custom Topic")

    choice = input("\nChoose (1-8): ").strip()
    if choice in CURATED_BIBLE_VAULT:
        topic = CURATED_BIBLE_VAULT[choice]["topic"]
    elif choice == "8":
        topic = input("Enter custom topic: ").strip()
    else:
        topic = "Debt & Financial Freedom"

    print(f"\n⚡ [1/3] Loading scripture & prayer for '{topic}'...")
    script = generate_bible_content(topic)
    print(f"   📖 Verse: {script.verse_citation} - \"{script.verse_text}\"")
    print(f"   🙏 Prayer: \"{script.prayer}\"")

    print("\n🎙️ [2/3] Generating solemn voiceover & word timings...")
    from voice_studio import build_spoken_voice_script
    voice_script = build_spoken_voice_script(script)
    temp_voice = BASE_DIR / "temp_voice.mp3"
    generate_voiceover(voice_script, temp_voice)

    print("\n⚡ [3/3] Rendering video (10s Short_Main video ➔ Jesus_Lord image)...")
    clean_name = clean_filename(f"Bible_{script.topic}_{script.verse_citation}")
    seq_dir = get_next_sequence_folder(clean_name)
    out_video = seq_dir / f"{clean_name}.mp4"
    out_thumb = seq_dir / f"{clean_name}_thumb.jpg"

    c_intro, c_bg, c_thumb = choose_media_in_cli(script.topic)
    success = render_faceless_bible_video(script, temp_voice, out_video, out_thumb, custom_intro=c_intro, custom_bg=c_bg, custom_thumb=c_thumb)
    if temp_voice.exists():
        temp_voice.unlink()

    if success:
        desc = f"""If you are dealing with {script.topic}, let this powerful scripture speak to your spirit.

📖 Scripture: {script.verse_citation}
"{script.verse_text}"

💡 Reflection:
{script.meaning}

🙏 Prayer:
{script.prayer}

Type "AMEN" in the comments if you receive this word today! 🙏

---
📖 Recommended Study Bible & Prayer Journal (Linked in channel bio):
Grab your copy to deepen your walk with God.

{' '.join(script.hashtags)} #Bible #Jesus #Prayer #Shorts #Faith

---
Disclaimer: As an Amazon Associate, I earn from qualifying purchases at no extra cost to you."""

        opt_title, opt_desc, opt_tags = optimize_with_virality_engine(script.topic, script.title, desc, script.hashtags + ["Bible", "Jesus", "Prayer"], active_channel)
        save_clip_metadata(out_video, opt_title, opt_desc, opt_tags)
        print("\n" + "=" * 60)
        print(f"✅ BIBLE SHORT READY: {out_video.name}")
        print(f"🖼️ THUMBNAIL READY:   {out_thumb.name}")
        print("=" * 60)

        target_ch = choose_upload_channel(active_channel)
        if target_ch:
            upload_video_to_youtube(target_ch, out_video)

def run_cli_podcast_scout(active_channel: str):
    print("\n" + "=" * 60)
    print("🎙️ AUTO-SCOUT VIRAL PODCAST (1M+ VIEWS)")
    print("=" * 60)
    print("Select Niche Category:")
    for k, v in CATEGORIES.items():
        print(f"  [{k}] {v['name']}")

    cat_choice = input("\nChoose Category (1-6): ").strip()
    cat_config = CATEGORIES.get(cat_choice, CATEGORIES["1"])

    target = find_viral_video(1_000_000, cat_config["queries"])
    if not target:
        print("⚠️ No new videos found with 1M+ views right now.")
        return

    print(f"\n🎯 Target Found: '{target['title']}' ({target['views']:,} views)")
    transcript = get_transcript(target["id"])
    if transcript:
        clips = analyze_transcript(transcript, cat_config["name"])
    else:
        clips = analyze_audio_fallback(target["url"], cat_config["name"])

    if not clips:
        print("⚠️ No suitable clip moments detected.")
        return

    for clip in clips:
        start_s = timestamp_to_seconds(clip.start_time)
        end_s = timestamp_to_seconds(clip.end_time)
        temp_slice = BASE_DIR / "temp_slice.mp4"

        try:
            download_slice(target["url"], start_s, end_s, temp_slice)
            seq_name = f"{clean_filename(clip.book_title)}_{clean_filename(clip.title)}"
            seq_dir = get_next_sequence_folder(seq_name)
            out_file = seq_dir / f"{seq_name}.mp4"
            if render_podcast_short(temp_slice, clip, out_file, cat_config["badge_tag"]):
                all_tags = list(set(clip.hashtags + cat_config["hashtags"]))
                desc = f"""{clip.hook_caption}\n\n📖 Featured Book: {clip.book_title} ({clip.book_author})\n👉 Grab your copy via the link in our channel bio!\n\n{' '.join(all_tags)}\n\n---\nDisclaimer: As an Amazon Associate, I earn from qualifying purchases at no extra cost to you."""
                opt_title, opt_desc, opt_tags = optimize_with_virality_engine(cat_config["name"], clip.title, desc, all_tags, active_channel)
                save_clip_metadata(out_file, opt_title, opt_desc, opt_tags)

                print(f"\n✅ SHORT CREATED: {out_file.name}")
                ask = input(f"🚀 Upload this short to '{active_channel}' now? (y/n): ").strip().lower()
                if ask == "y":
                    upload_video_to_youtube(active_channel, out_file)
        finally:
            if temp_slice.exists():
                temp_slice.unlink()

    history = set()
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, "r") as f:
                history = set(json.load(f))
        except Exception:
            pass
    history.add(target["id"])
    with open(HISTORY_FILE, "w") as f:
        json.dump(list(history), f, indent=2)

def run_cli_podcast_custom(active_channel: str):
    print("\n" + "=" * 60)
    print("🔗 CLIP A CUSTOM YOUTUBE VIDEO URL")
    print("=" * 60)
    url = input("Paste YouTube Video URL: ").strip()
    if not url:
        return

    m = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11})', url)
    if not m:
        print("❌ Invalid YouTube URL.")
        return

    v_id = m.group(1)

    print("\nHow would you like to clip this video?")
    print("  [1] Auto-detect best viral moment with AI (Even if subtitles are disabled!)")
    print("  [2] Enter my own exact timestamps (e.g. 00:05 to 00:45)")
    mode = input("Choose (1/2): ").strip()

    clips = []
    if mode == "2":
        start_t = input("Enter Start Time (e.g. 00:10): ").strip()
        end_t = input("Enter End Time   (e.g. 00:50): ").strip()
        title_t = input("Enter Title for this clip: ").strip() or "Inspiring Moment"
        clips.append(BookClip(
            title=title_t,
            start_time=start_t,
            end_time=end_t,
            book_title="Sacred Inspiration",
            book_author="Daily Wisdom",
            hook_caption="Watch this powerful moment.",
            hashtags=["#Shorts", "#Inspiration", "#Worship", "#Faith"]
        ))
    else:
        transcript = get_transcript(v_id)
        if transcript:
            clips = analyze_transcript(transcript, "Inspiration & Wisdom")
        else:
            clips = analyze_audio_fallback(url, "Inspiration & Wisdom")

    if not clips:
        print("⚠️ Could not detect clips automatically.")
        return

    for clip in clips:
        start_s = timestamp_to_seconds(clip.start_time)
        end_s = timestamp_to_seconds(clip.end_time)
        temp_slice = BASE_DIR / "temp_slice.mp4"

        try:
            download_slice(url, start_s, end_s, temp_slice)
            seq_name = f"{clean_filename(clip.book_title)}_{clean_filename(clip.title)}"
            seq_dir = get_next_sequence_folder(seq_name)
            out_file = seq_dir / f"{seq_name}.mp4"
            if render_podcast_short(temp_slice, clip, out_file, "SPECIAL HIGHLIGHT"):
                desc = f"""{clip.hook_caption}\n\n👉 Follow our channel for daily inspiration!\n\n{' '.join(clip.hashtags)}\n\n---\nDisclaimer: As an Amazon Associate, I earn from qualifying purchases at no extra cost to you."""
                opt_title, opt_desc, opt_tags = optimize_with_virality_engine(clip.title, clip.title, desc, clip.hashtags, active_channel)
                save_clip_metadata(out_file, opt_title, opt_desc, opt_tags)

                print(f"\n✅ SHORT CREATED: {out_file.name}")
                ask = input(f"🚀 Upload this short to '{active_channel}' now? (y/n): ").strip().lower()
                if ask == "y":
                    upload_video_to_youtube(active_channel, out_file)
        finally:
            if temp_slice.exists():
                temp_slice.unlink()

def run_cli_bulk_uploader(active_channel: str):
    print("\n" + "=" * 60)
    print("🚀 BATCH UPLOAD SAVED SHORTS TO YOUTUBE")
    print("=" * 60)

    mp4s = sorted(list(CLIPS_DIR.rglob("*.mp4")), key=os.path.getmtime, reverse=True)
    unuploaded = []

    for vid in mp4s:
        meta = load_clip_metadata(vid)
        if not meta.get("youtube_id"):
            unuploaded.append(vid)

    if not unuploaded:
        print("🎉 All shorts in 'clips/' folder are already uploaded!")
        return

    print(f"Found {len(unuploaded)} unuploaded Short(s):")
    for i, v in enumerate(unuploaded):
        print(f"  [{i+1}] {v.name}")

    target_ch = choose_upload_channel(active_channel)
    if target_ch:
        for v in unuploaded:
            upload_video_to_youtube(target_ch, v)
            time.sleep(2)

def run_cli_channel_switcher(current_active: str) -> str:
    print("\n" + "=" * 60)
    print("📺 YOUTUBE CHANNEL MANAGER")
    print("=" * 60)
    channels = load_channels()

    print("Connected Channels:")
    c_list = list(channels.keys())
    for i, ch in enumerate(c_list):
        mark = " (Active)" if ch == current_active else ""
        print(f"  [{i+1}] {ch}{mark}")

    print("  [+] Connect New YouTube Channel")
    print("  [b] Back")

    choice = input("\nChoose option: ").strip()
    if choice == "+":
        new_ch = connect_new_channel()
        return new_ch if new_ch else current_active
    elif choice.isdigit() and 1 <= int(choice) <= len(c_list):
        selected = c_list[int(choice) - 1]
        print(f"✅ Switched active channel to: '{selected}'")
        return selected

    return current_active

# --- 1-CLICK GIT & GITHUB AUTO-BACKUP ---
def save_everything_to_git() -> tuple[bool, str]:
    """Stages all safe project files, commits with a timestamp, and pushes to GitHub."""
    from datetime import datetime
    print("\n☁️ [Git Backup] Saving & pushing project to GitHub (leonshipley/DailyWisdom-Studio)...")
    try:
        # Ensure secrets stay untracked
        subprocess.run(
            ["git", "rm", "-r", "--cached", ".env", "client_secret*.json", "youtube_token.pickle", "channels/", "--ignore-unmatch"],
            cwd=str(BASE_DIR), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        subprocess.run(["git", "add", "."], cwd=str(BASE_DIR), check=True)

        status = subprocess.run(["git", "status", "--porcelain"], cwd=str(BASE_DIR), capture_output=True, text=True)
        if status.stdout.strip():
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            subprocess.run(["git", "commit", "-m", f"Studio Auto-Save: {ts}"], cwd=str(BASE_DIR), check=True)

        push_res = subprocess.run(["git", "push", "-u", "origin", "main"], cwd=str(BASE_DIR), capture_output=True, text=True)
        if push_res.returncode == 0:
            msg = "✅ Successfully saved & pushed everything to GitHub (leonshipley/DailyWisdom-Studio)!"
            print(msg)
            return True, msg
        else:
            err = push_res.stderr.strip() or push_res.stdout.strip()
            msg = f"⚠️ Committed locally, but push returned: {err}"
            print(msg)
            return False, msg
    except Exception as e:
        msg = f"❌ Git save error: {e}"
        print(msg)
        return False, msg


# --- 9. MAIN INTERACTIVE BACKEND MENU ---
def run_cli_voice_studio():
    """Interactive Terminal Voice Studio: Browse 4 accents, listen to any voice sample, and select."""
    from voice_studio import VOICE_CATALOG, DEFAULT_SAMPLE_TEXTS, load_active_voice, save_active_voice, synthesize_preview_sample, play_audio_on_windows
    cur = load_active_voice()
    accents = list(VOICE_CATALOG.keys())

    while True:
        print("\n" + "=" * 68)
        print("🎙️ PROFESSIONAL VOICE & ACCENT STUDIO (28 NEURAL VOICES)")
        print(f"🔊 Currently Active Voice: {cur.get('name')} ({cur.get('accent')})")
        print("=" * 68)
        for idx, acc in enumerate(accents, start=1):
            print(f"  [{idx}] {acc} ({len(VOICE_CATALOG[acc])} Voices)")
        print("  [b] Back to Main Menu")
        print("=" * 68)

        c_acc = input("Select Accent Category (1-4 or b): ").strip().lower()
        if c_acc in ("b", "back", "0", ""):
            break
        if not (c_acc.isdigit() and 1 <= int(c_acc) <= len(accents)):
            continue

        chosen_accent = accents[int(c_acc) - 1]
        v_list = VOICE_CATALOG[chosen_accent]
        sample_txt = DEFAULT_SAMPLE_TEXTS[chosen_accent]

        while True:
            print("\n" + "-" * 68)
            print(f"🎧 VOICES IN: {chosen_accent}")
            print("-" * 68)
            for v_i, v_obj in enumerate(v_list, start=1):
                mark = " ⭐ [ACTIVE]" if v_obj["id"] == cur.get("id") else ""
                print(f"  [{v_i}] {v_obj['name']} ({v_obj['gender']}){mark}")
                print(f"      Style: {v_obj['style']} | Rate: {v_obj['rate']} | Pitch: {v_obj['pitch']}")
            print("-" * 68)
            print("💡 Commands:")
            print(f"  • Type a number (1-{len(v_list)}) to SELECT that voice as Active")
            print(f"  • Type 'p1', 'p2', etc. to LISTEN / AUDITION that voice right now!")
            print("  • Type 'b' to go back to Accent Categories")

            cmd_in = input("\nYour choice (e.g. 'p1' to listen, '1' to select, 'b' back): ").strip().lower()
            if cmd_in in ("b", "back", ""):
                break
            if cmd_in.startswith("p") and cmd_in[1:].isdigit():
                p_idx = int(cmd_in[1:]) - 1
                if 0 <= p_idx < len(v_list):
                    target_v = v_list[p_idx]
                    print(f"🎧 Generating & playing sample for: {target_v['name']}...")
                    mp3_f = synthesize_preview_sample(target_v["voice"], target_v["rate"], target_v["pitch"], sample_txt)
                    play_audio_on_windows(mp3_f)
            elif cmd_in.isdigit() and 1 <= int(cmd_in) <= len(v_list):
                sel_v = dict(v_list[int(cmd_in) - 1])
                sel_v["accent"] = chosen_accent
                save_active_voice(sel_v)
                cur = sel_v
                print(f"\n✅ LOCKED IN ACTIVE VOICE: {sel_v['name']} ({chosen_accent})!")
                break


def main():
    channels = load_channels()
    if not channels:
        active_channel = "TheDailyWisdom_Hub"
    else:
        active_channel = list(channels.keys())[0]

    while True:
        print("\n" + "=" * 65)
        print("🎬 DAILYWISDOM ENGINE (PURE BACKEND - ZERO BROWSER)")
        print(f"📺 Active Target Channel: [{active_channel}]")
        print("=" * 65)
        print("  [1] 🎙️ Auto-Scout & Clip Viral Podcast (1M+ Views)")
        print("  [2] 🔗 Clip a Custom YouTube Video URL (With Audio AI Fallback)")
        print("  [3] ✝️ Generate Faceless Bible & Prayer Short (+ Thumbnail)")
        print("  [4] 🚀 Upload Unuploaded Shorts to YouTube")
        print("  [5] 📺 Switch / Add YouTube Channel")
        print("  [6] 🧹 Clear Cache & Redownload Master Assets")
        print("  [7] 🎵 Download Audio (MP3) from YouTube URL")
        print("  [8] 📹 Download Video (1080p MP4) from YouTube URL")
        print("  [9] 🔥 Virality Engine (Spy on Competitors & My Top Shorts)")
        print("  [10] 📌 Download Pinterest Image or Video (Auto-Sorted in Pinterest/)")
        print("  [11] ☁️ Save & Push Everything to GitHub")
        print("  [12] 🎙️ Voice & Accent Studio (Listen & Choose from 28 Voices)")
        print("  [0] ❌ Exit")
        print("=" * 65)

        opt = input("Select an option (0-12): ").strip()

        if opt == "1":
            run_cli_podcast_scout(active_channel)
        elif opt == "2":
            run_cli_podcast_custom(active_channel)
        elif opt == "3":
            run_cli_bible(active_channel)
        elif opt == "4":
            run_cli_bulk_uploader(active_channel)
        elif opt == "5":
            active_channel = run_cli_channel_switcher(active_channel)
        elif opt == "6":
            for f in [BGM_PODCAST_FILE, HISTORY_FILE]:
                if f.exists():
                    f.unlink()
            print("✅ Cache cleared!")
        elif opt == "7":
            download_audio_from_url()
        elif opt == "8":
            download_video_from_url()
        elif opt == "9":
            run_cli_virality_engine(active_channel)
        elif opt == "10":
            run_cli_pinterest_downloader()
        elif opt == "11":
            save_everything_to_git()
        elif opt == "12":
            run_cli_voice_studio()
        elif opt == "0":
            print("\n👋 Exiting DailyWisdom Engine. God bless!")
            break
        else:
            print("⚠️ Invalid choice. Enter 0 to 12.")

if __name__ == "__main__":
    main()