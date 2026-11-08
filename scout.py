# scout.py
import json
from pathlib import Path
import yt_dlp

HISTORY_FILE = Path(__file__).resolve().parent / "processed_history.json"

# Top channels & keywords known for viral book discussions
SEARCH_QUERIES = [
    "ytsearch5:Ryan Holiday favorite life changing books",
    "ytsearch5:Ali Abdaal books that changed my life",
    "ytsearch5:Chris Williamson best books modern wisdom",
    "ytsearch5:Alex Hormozi books you must read",
    "ytsearch5:Steven Bartlett diary of a ceo best books",
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

def find_next_video() -> dict | None:
    """Searches for the first high-quality, unprocessed video."""
    history = load_history()

    ydl_opts = {
        "quiet": True,
        "extract_flat": True,
        "skip_download": True,
    }

    print("\n🔍 [Scout] Scanning top influencer channels for book videos...")

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        for query in SEARCH_QUERIES:
            try:
                res = ydl.extract_info(query, download=False)
                entries = res.get("entries", [])
                for entry in entries:
                    if not entry:
                        continue
                    v_id = entry.get("id")
                    title = entry.get("title", "")
                    duration = entry.get("duration", 0)

                    # Criteria: Not already processed & between 4 to 45 mins
                    if v_id not in history and 240 <= duration <= 2700:
                        print(f" Target Found: '{title}' ({entry.get('url')})")
                        return {
                            "id": v_id,
                            "url": f"https://www.youtube.com/watch?v={v_id}",
                            "title": title
                        }
            except Exception as e:
                print(f" Warning on query '{query}': {e}")
                continue

    print("⚠️ No new candidate videos found. Try updating search queries.")
    return None

def download_candidate_video(url: str, output_path: Path) -> str:
    print(f"\n📥 [Downloader] Downloading master video...")
    ydl_opts = {
        "format": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]/best",
        "outtmpl": str(output_path),
        "merge_output_format": "mp4",
        "overwrites": True,
        "quiet": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return info.get("title", "Master_Video")