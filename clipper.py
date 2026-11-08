import os
import sys
import time
import json
import subprocess
import re
import urllib.request
from pathlib import Path
from datetime import date
from dotenv import load_dotenv
import yt_dlp
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

# Base directories
BASE_DIR = Path(__file__).resolve().parent
CLIPS_DIR = BASE_DIR / "clips"
QUOTA_FILE = BASE_DIR / ".gemini_quota.json"
BGM_FILE = BASE_DIR / "bg_music.mp3"
NICHE_FOLDER_NAME = "TheDailyWisdom"

load_dotenv(BASE_DIR / ".env")
API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    print("\n[ERROR] GEMINI_API_KEY is missing! Add it inside your .env file.")
    sys.exit(1)

client = genai.Client(api_key=API_KEY)


class VideoClip(BaseModel):
    title: str = Field(description="Short, punchy title for this clip")
    start_time: str = Field(description="Start timestamp (e.g. 00:01:23 or 01:23)")
    end_time: str = Field(description="End timestamp (e.g. 00:01:55 or 01:55)")
    reason: str = Field(description="Why this segment is viral")


class ClipsResponse(BaseModel):
    clips: list[VideoClip]


def clean_name(name: str) -> str:
    clean = re.sub(r'[\/*?:"<>|]', "", name)
    clean = re.sub(r"\s+", "_", clean).strip("_")
    return clean[:50] if clean else "Video_Short"


def timestamp_to_seconds(ts: str) -> float:
    parts = [float(p) for p in ts.strip().split(":")]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    elif len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return parts[0]


def ensure_background_music():
    """Checks for bg_music.mp3; downloads or generates a fallback track."""
    if not BGM_FILE.exists():
        print("\n[Audio] 'bg_music.mp3' not found. Downloading soft ambient track...")
        url = "https://ia801503.us.archive.org/15/items/ambient-relaxing-music/ambient-calm.mp3"
        try:
            urllib.request.urlretrieve(url, BGM_FILE)
            print(" Downloaded background music successfully!")
        except Exception:
            print(" Generating soft ambient pad audio fallback...")
            cmd = [
                "ffmpeg", "-y", "-f", "lavfi",
                "-i", "sine=frequency=110:sample_rate=44100",
                "-t", "120", "-af", "volume=0.03,lowpass=f=300",
                str(BGM_FILE)
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def track_quota():
    today_str = date.today().isoformat()
    quota_data = {"date": today_str, "used": 0}

    if QUOTA_FILE.exists():
        try:
            with open(QUOTA_FILE, "r") as f:
                saved = json.load(f)
            if saved.get("date") == today_str:
                quota_data = saved
        except Exception:
            pass

    quota_data["used"] += 1
    remaining = max(0, 1500 - quota_data["used"])

    with open(QUOTA_FILE, "w") as f:
        json.dump(quota_data, f, indent=2)

    return quota_data["used"], remaining


def download_youtube_video(url: str, output_path: Path) -> str:
    print(f"\n[1/4] Downloading 1080p HD master video...")
    ydl_opts = {
        "format": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]/best",
        "outtmpl": str(output_path),
        "merge_output_format": "mp4",
        "overwrites": True,
        "quiet": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        video_title = info.get("title", "Untitled_Video")

    print(f" Video Title: '{video_title}'")
    return video_title


def analyze_video_with_gemini(video_path: Path, max_clips: int = 3) -> tuple[list[VideoClip], dict]:
    print("\n[2/4] Uploading video to Gemini...")
    video_file = client.files.upload(file=str(video_path))
    print(" Upload complete. Waiting for processing...")

    while video_file.state.name == "PROCESSING":
        time.sleep(3)
        video_file = client.files.get(name=video_file.name)

    if video_file.state.name == "FAILED":
        raise ValueError("Gemini processing failed on this video.")

    print("\n[3/4] Finding high-retention viral moments...")
    prompt = f"""
    You are an expert short-form editor for TikTok, YouTube Shorts, and Reels in the wisdom/habits/podcast niche.
    Select the top {max_clips} viral, high-retention segments.

    Rules:
    - Clip length: 20 to 60 seconds each.
    - Start right when the hook begins; stop after conclusion.
    - Provide exact timestamps (HH:MM:SS or MM:SS format).
    """

    # Use 'gemini-2.0-flash' or 'gemini-1.5-flash'
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=[video_file, prompt],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ClipsResponse,
            temperature=0.3,
        ),
    )

    try:
        client.files.delete(name=video_file.name)
    except Exception:
        pass

    usage = {
        "prompt_tokens": getattr(response.usage_metadata, "prompt_token_count", 0),
        "output_tokens": getattr(response.usage_metadata, "candidates_token_count", 0),
        "total_tokens": getattr(response.usage_metadata, "total_token_count", 0),
    }

    data = json.loads(response.text)
    return [VideoClip(**clip) for clip in data.get("clips", [])], usage


def render_full_screen(input_file: Path, clips: list[VideoClip], video_title: str):
    w, h = 1080, 1920
    target_folder = CLIPS_DIR / NICHE_FOLDER_NAME / clean_name(video_title)
    target_folder.mkdir(parents=True, exist_ok=True)

    print(f"\n[4/4] Output Directory: {target_folder.resolve()}")
    print(f" Rendering {len(clips)} Full-Screen Ultra-HD Shorts...")

    for i, clip in enumerate(clips):
        clip_name = clean_name(clip.title)
        out_file = target_folder / f"short_{i+1}_{clip_name}.mp4"

        start_sec = timestamp_to_seconds(clip.start_time)
        end_sec = timestamp_to_seconds(clip.end_time)
        duration = max(1.0, end_sec - start_sec)

        print(f"\n⚡ Rendering Full-Screen Short #{i+1}: '{clip.title}' ({round(duration)}s)")

        # Filter Breakdown with PTS reset so progress bar starts accurately at t=0
        filter_complex = (
            f"[0:v]setpts=PTS-STARTPTS,scale=-2:{h}:flags=lanczos,crop={w}:{h}:(in_w-{w})/2:0,"
            f"unsharp=5:5:0.85:5:5:0.0,eq=contrast=1.05:saturation=1.08[v_base];"
            f"[v_base]drawbox=x=0:y=1902:w='min({w}, {w}*t/{duration})':h=14:color=0xFFCC00@1:t=fill[vout];"
            f"[0:a]asetpts=PTS-STARTPTS,aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[speech];"
            f"[1:a]volume=0.06,aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[bgm];"
            f"[speech][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]"
        )

        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start_sec),
            "-t", str(duration),
            "-i", str(input_file),
            "-stream_loop", "-1",
            "-i", str(BGM_FILE),
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-map", "[aout]",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "19",
            "-c:a", "aac",
            "-b:a", "192k",
            str(out_file)
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"[FFmpeg Error on clip {i+1}]: {result.stderr[-400:]}")
            continue

        print(f" Saved: {out_file.name}")

    return target_folder


if __name__ == "__main__":
    ensure_background_music()

    url = input("Paste your YouTube Video URL: ").strip()
    if not url:
        print("URL cannot be empty.")
        sys.exit(1)

    master_file = BASE_DIR / "temp_master.mp4"

    try:
        start_time = time.time()

        video_title = download_youtube_video(url, master_file)
        clips, usage = analyze_video_with_gemini(master_file, max_clips=3)
        output_folder = render_full_screen(master_file, clips, video_title=video_title)

        if master_file.exists():
            master_file.unlink()

        used_today, remaining_today = track_quota()
        total_duration = round(time.time() - start_time, 1)

        print("\n" + "=" * 60)
        print(f" COMPLETED IN JUST {total_duration} SECONDS!")
        print(f" Saved in: {output_folder.resolve()}")
        print("=" * 60)
        print("\n📊 GEMINI USAGE & REMAINING LIMITS:")
        print(f"  • Video Tokens Analyzed:   {usage['prompt_tokens']:,}")
        print(f"  • Output Tokens:           {usage['output_tokens']:,}")
        print("  --------------------------------------------------")
        print(f"  • Requests Made Today:     {used_today} / 1,500")
        print(f"  • REQUESTS REMAINING TODAY: {remaining_today} requests left")
        print("=" * 60)

    except Exception as e:
        print(f"\n[Execution Error]: {e}")