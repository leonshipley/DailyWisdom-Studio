import os
import sys
import time
import json
import subprocess
import re
import urllib.request
import pickle
from pathlib import Path
from dotenv import load_dotenv
import yt_dlp
from yt_dlp.utils import download_range_func
from youtube_transcript_api import YouTubeTranscriptApi
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

# Google API client for YouTube Upload
try:
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    YOUTUBE_API_AVAILABLE = True
except ImportError:
    YOUTUBE_API_AVAILABLE = False

# ==========================================
# CONFIGURATION
# ==========================================
AUTO_UPLOAD_TO_YOUTUBE = True
UPLOAD_PRIVACY = "public"            # "public", "private", or "unlisted"
MIN_VIEW_COUNT = 1_000_000           # Only process videos with 1M+ views
# ==========================================

BASE_DIR = Path(__file__).resolve().parent
CLIPS_DIR = BASE_DIR / "clips"
CLIPS_DIR.mkdir(exist_ok=True)
HISTORY_FILE = BASE_DIR / "processed_history.json"
BGM_FILE = BASE_DIR / "bg_music.mp3"
CLIENT_SECRET_FILE = BASE_DIR / "client_secret.json"
TOKEN_PICKLE = BASE_DIR / "youtube_token.pickle"

load_dotenv(BASE_DIR / ".env")
API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    print("\n[ERROR] GEMINI_API_KEY missing in .env file!")
    sys.exit(1)

client = genai.Client(api_key=API_KEY)

# --- 1. SCHEMAS ---
class BookClip(BaseModel):
    title: str = Field(description="Catchy YouTube Short title under 60 chars")
    start_time: str = Field(description="Start timestamp HH:MM:SS or MM:SS")
    end_time: str = Field(description="End timestamp HH:MM:SS or MM:SS")
    book_title: str = Field(description="Exact book title discussed")
    book_author: str = Field(description="Author of the book")
    hook_caption: str = Field(description="1 punchy sentence summarizing the insight")
    hashtags: list[str] = Field(description="5 viral tags, e.g. ['#Wisdom', '#Books', '#Shorts']")

class AnalysisResponse(BaseModel):
    clips: list[BookClip]

# --- 2. UTILITIES ---
def clean_filename(text: str) -> str:
    clean = re.sub(r'[\/*?:"<>|]', "", text)
    return re.sub(r"\s+", "_", clean).strip("_")[:35]

def timestamp_to_seconds(ts: str) -> float:
    parts = [float(p) for p in ts.strip().split(":")]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    elif len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return parts[0]

def ensure_bgm():
    if not BGM_FILE.exists():
        print("\n[Audio] Downloading ambient track...")
        url = "https://ia801503.us.archive.org/15/items/ambient-relaxing-music/ambient-calm.mp3"
        try:
            urllib.request.urlretrieve(url, BGM_FILE)
        except Exception:
            cmd = [
                "ffmpeg", "-y", "-f", "lavfi",
                "-i", "sine=frequency=110:sample_rate=44100",
                "-t", "120", "-af", "volume=0.03,lowpass=f=300",
                str(BGM_FILE)
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# --- 3. SCOUT WITH 1,000,000+ VIEWS ---
SEARCH_QUERIES = [
    "ytsearch15:books that changed my life podcast",
    "ytsearch15:Ryan Holiday favorite books",
    "ytsearch15:Chris Williamson best books ever",
    "ytsearch15:Alex Hormozi reading list recommended",
    "ytsearch15:Steven Bartlett best books diary of a ceo",
]

def load_history() -> set:
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, "r") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def save_to_history(video_id: str):
    history = load_history()
    history.add(video_id)
    with open(HISTORY_FILE, "w") as f:
        json.dump(list(history), f, indent=2)

def find_viral_video() -> dict | None:
    history = load_history()
    ydl_opts = {"quiet": True, "extract_flat": True, "skip_download": True}

    print(f"\n🔍 [Scout] Scanning top influencer channels for 1M+ view videos...")
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        for query in SEARCH_QUERIES:
            try:
                res = ydl.extract_info(query, download=False)
                for entry in res.get("entries", []):
                    if not entry:
                        continue
                    v_id = entry.get("id")
                    duration = entry.get("duration", 0)
                    view_count = entry.get("view_count") or 0

                    if v_id in history or duration < 180 or duration > 3600:
                        continue

                    if view_count == 0:
                        try:
                            info = ydl.extract_info(f"https://www.youtube.com/watch?v={v_id}", download=False)
                            view_count = info.get("view_count") or 0
                        except Exception:
                            continue

                    if view_count >= MIN_VIEW_COUNT:
                        print(f"🎯 VIRAL TARGET FOUND: '{entry.get('title')}' ({view_count:,} views)")
                        return {
                            "id": v_id,
                            "url": f"https://www.youtube.com/watch?v={v_id}",
                            "title": entry.get("title")
                        }
            except Exception:
                continue
    print("⚠️ No new videos found.")
    return None

# --- 4. LIGHTNING TRANSCRIPT FETCH (MULTI-VERSION COMPATIBLE) ---
def get_video_transcript(video_id: str) -> str | None:
    print("⚡ [Fast-Track] Pulling timestamped transcript (0 MB video download)...")
    data = None

    # 1. Try modern API (v1.0+: .fetch())
    try:
        api = YouTubeTranscriptApi()
        if hasattr(api, "fetch"):
            fetched = api.fetch(video_id, languages=["en", "en-US", "en-GB"])
            if hasattr(fetched, "to_raw_data"):
                data = fetched.to_raw_data()
            elif isinstance(fetched, list):
                data = fetched
            else:
                data = list(fetched)
    except Exception:
        pass

    # 2. Try legacy API (get_transcript)
    if not data:
        try:
            if hasattr(YouTubeTranscriptApi, "get_transcript"):
                data = YouTubeTranscriptApi.get_transcript(video_id, languages=["en", "en-US", "en-GB"])
        except Exception:
            pass

    if not data:
        print("⚠️ Could not extract captions for this video.")
        return None

    formatted = []
    for line in data:
        text = line.get("text", "") if isinstance(line, dict) else getattr(line, "text", "")
        start = line.get("start", 0) if isinstance(line, dict) else getattr(line, "start", 0)
        sec = int(start)
        m, s = divmod(sec, 60)
        h, m = divmod(m, 60)
        ts = f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"
        formatted.append(f"[{ts}] {text}")

    print("✅ Transcript loaded in under 1 second!")
    return "\n".join(formatted)

# --- 5. GEMINI TEXT BRAIN (2 SECONDS) ---
def analyze_transcript_for_books(transcript_text: str, max_clips: int = 2) -> list[BookClip]:
    print("🧠 [Brain] Gemini analyzing text transcript in 2 seconds...")

    prompt = f"""
    You are an elite short-form video editor for a wisdom/book channel.
    Here is the exact timestamped transcript of a podcast.
    Analyze this transcript and extract up to {max_clips} viral moments where a specific book, philosophy, or mental model is explained.

    Rules:
    - Clip length: strictly between 30 and 55 seconds.
    - Identify the exact BOOK TITLE and AUTHOR being discussed.
    - Use the timestamps from the transcript (HH:MM:SS or MM:SS format).
    - Start right at the punchy hook; stop cleanly after the lesson is complete.

    TRANSCRIPT:
    {transcript_text[:120000]}
    """

    candidate_models = ["gemini-3.8-flash", "gemini-2.5-flash", "gemini-2.5-flash-lite"]
    response = None

    for model_name in candidate_models:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=AnalysisResponse,
                ),
            )
            break
        except Exception:
            continue

    if not response:
        return []

    data = json.loads(response.text)
    return [BookClip(**item) for item in data.get("clips", [])]

# --- 6. TARGETED 45-SECOND SLICE DOWNLOAD (3 SECONDS) ---
def download_clip_slice(url: str, start_sec: float, end_sec: float, output_path: Path):
    pad_start = max(0.0, start_sec - 1.5)
    pad_end = end_sec + 1.5
    duration = pad_end - pad_start

    print(f"⚡ [Fast-Track] Downloading ONLY the {round(duration)}s slice (~20 MB)...")

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

# --- 7. DESIGNER RENDER ENGINE ---
def render_designer_short(raw_slice: Path, clip: BookClip, output_path: Path) -> bool:
    w, h = 1080, 1920
    start_sec = timestamp_to_seconds(clip.start_time)
    end_sec = timestamp_to_seconds(clip.end_time)
    duration = max(1.0, end_sec - start_sec)

    clean_book = re.sub(r'[\':,"]', '', clip.book_title).upper()[:28]

    font_file = "C\\:/Windows/Fonts/arialbd.ttf"
    if not Path("C:/Windows/Fonts/arialbd.ttf").exists():
        font_file = "C\\:/Windows/Fonts/arial.ttf"

    print(f"⚡ [Render] Stamping Designer Gold Badge on: '{clip.title}'...")

    # Fast relative seek inside the pre-trimmed 45-second slice
    offset_start = 1.5 if start_sec >= 1.5 else start_sec

    filter_complex = (
        f"[0:v]setpts=PTS-STARTPTS,scale=-2:{h}:flags=lanczos,crop={w}:{h}:(in_w-{w})/2:0,"
        f"unsharp=5:5:0.85:5:5:0.0,eq=contrast=1.06:saturation=1.10[v_base];"
        f"[v_base]drawbox=x=110:y=220:w=860:h=140:color=0x0D0D12@0.88:t=fill[card1];"
        f"[card1]drawbox=x=110:y=220:w=860:h=140:color=0xD4AF37@0.85:t=3[card2];"
        f"[card2]drawbox=x=110:y=220:w=12:h=140:color=0xD4AF37@1:t=fill[card3];"
        f"[card3]drawtext=fontfile='{font_file}':text='FEATURED BOOK':fontcolor=0xD4AF37:fontsize=22:x=145:y=240[txt1];"
        f"[txt1]drawtext=fontfile='{font_file}':text='{clean_book}':fontcolor=white:fontsize=34:x=145:y=274[txt2];"
        f"[txt2]drawtext=fontfile='{font_file}':text='Link in Channel Bio ↗':fontcolor=0xBBBBCC:fontsize=22:x=145:y=322[txt3];"
        f"[txt3]drawbox=x=0:y=1902:w='min({w}, {w}*t/{duration})':h=16:color=0xD4AF37@1:t=fill[vout];"
        f"[0:a]asetpts=PTS-STARTPTS,aformat=sample_fmts=fltp:sample_rates=44100[speech];"
        f"[1:a]volume=0.05,aformat=sample_fmts=fltp:sample_rates=44100[bgm];"
        f"[speech][bgm]amix=inputs=2:duration=first[aout]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(offset_start),
        "-t", str(duration),
        "-i", str(raw_slice),
        "-stream_loop", "-1",
        "-i", str(BGM_FILE),
        "-filter_complex", filter_complex,
        "-map", "[vout]",
        "-map", "[aout]",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "18",
        "-c:a", "aac",
        "-b:a", "192k",
        str(output_path)
    ]

    res = subprocess.run(cmd, capture_output=True, text=True)
    return res.returncode == 0

# --- 8. YOUTUBE UPLOADER ---
def upload_to_youtube(video_path: Path, title: str, description: str, tags: list[str]) -> str | None:
    if not YOUTUBE_API_AVAILABLE or not CLIENT_SECRET_FILE.exists():
        return None

    scopes = ["https://www.googleapis.com/auth/youtube.upload"]
    credentials = None

    if TOKEN_PICKLE.exists():
        with open(TOKEN_PICKLE, "rb") as token:
            credentials = pickle.load(token)

    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_FILE), scopes)
            credentials = flow.run_local_server(port=0)
        with open(TOKEN_PICKLE, "wb") as token:
            pickle.dump(credentials, token)

    youtube = build("youtube", "v3", credentials=credentials)

    body = {
        "snippet": {
            "title": title[:100],
            "description": description,
            "tags": tags,
            "categoryId": "27"
        },
        "status": {
            "privacyStatus": UPLOAD_PRIVACY,
            "selfDeclaredMadeForKids": False
        }
    }

    media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True, mimetype="video/mp4")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    print(f"\n🚀 [YouTube] Publishing '{title}' to @TheDailyWisdom_Hub...")
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"   Upload progress: {int(status.progress() * 100)}%")

    video_id = response.get("id")
    url = f"https://youtube.com/shorts/{video_id}"
    print(f"🎉 Live on YouTube! URL: {url}")
    return url

# --- 9. ULTRA-FAST PIPELINE ---
def main():
    start_total_time = time.time()
    ensure_bgm()

    target = find_viral_video()
    if not target:
        return

    # Step 1: Pull transcript without downloading video
    transcript = get_video_transcript(target["id"])
    if not transcript:
        save_to_history(target["id"])
        return

    # Step 2: Gemini analyzes text in 2 seconds
    clips = analyze_transcript_for_books(transcript, max_clips=2)
    if not clips:
        print("⚠️ No clear book recommendations found in transcript.")
        save_to_history(target["id"])
        return

    # Step 3: Download ONLY the 45-second chunk & render immediately
    for clip in clips:
        start_s = timestamp_to_seconds(clip.start_time)
        end_s = timestamp_to_seconds(clip.end_time)

        temp_slice = BASE_DIR / "temp_slice.mp4"
        try:
            download_clip_slice(target["url"], start_s, end_s, temp_slice)

            filename = f"{clean_filename(clip.book_title)}_{clean_filename(clip.title)}.mp4"
            out_file = CLIPS_DIR / filename

            success = render_designer_short(temp_slice, clip, out_file)
            if success:
                desc = f"""{clip.hook_caption}

📖 Featured Book: {clip.book_title} ({clip.book_author})
👉 Grab your copy via the link in our channel bio!

{' '.join(clip.hashtags)} #Shorts

---
Disclaimer: As an Amazon Associate, I earn from qualifying purchases at no extra cost to you."""

                print("\n" + "=" * 55)
                print(f"✅ SHORT COMPLETED IN RECORD TIME: {out_file.name}")
                print(f"📌 TITLE: {clip.title}")
                print(f"📖 BOOK: {clip.book_title} ({clip.book_author})")
                print("=" * 55)

                if AUTO_UPLOAD_TO_YOUTUBE:
                    upload_to_youtube(out_file, clip.title, desc, clip.hashtags)
        finally:
            if temp_slice.exists():
                temp_slice.unlink()

    save_to_history(target["id"])
    total_time = round(time.time() - start_total_time, 1)
    print(f"\n⚡ ENTIRE RUN FINISHED IN JUST {total_time} SECONDS!")

if __name__ == "__main__":
    main()