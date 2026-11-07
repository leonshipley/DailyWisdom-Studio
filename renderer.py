# renderer.py
import subprocess
import re
from pathlib import Path
from analyzer import BookClip

BGM_FILE = Path(__file__).resolve().parent / "bg_music.mp3"

def timestamp_to_seconds(ts: str) -> float:
    parts = [float(p) for p in ts.strip().split(":")]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    elif len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return parts[0]

def clean_filename(text: str) -> str:
    clean = re.sub(r'[\/*?:"<>|]', "", text)
    return re.sub(r"\s+", "_", clean).strip("_")[:45]

def render_short_with_badge(input_video: Path, clip: BookClip, output_path: Path):
    w, h = 1080, 1920
    start_sec = timestamp_to_seconds(clip.start_time)
    end_sec = timestamp_to_seconds(clip.end_time)
    duration = max(1.0, end_sec - start_sec)

    # Sanitize book title for FFmpeg drawtext
    clean_book = clip.book_title.replace(":", " -").replace("'", "")[:28]
    badge_text = f"Book: {clean_book} (Link in Bio)"

    print(f"\n⚡ [Renderer] Rendering: '{clip.title}' with badge [{badge_text}]...")

    filter_complex = (
        f"[0:v]setpts=PTS-STARTPTS,scale=-2:{h}:flags=lanczos,crop={w}:{h}:(in_w-{w})/2:0,"
        f"unsharp=5:5:0.85:5:5:0.0,eq=contrast=1.05:saturation=1.08[v_base];"
        # 1. Gold Progress Bar at bottom
        f"[v_base]drawbox=x=0:y=1902:w='min({w}, {w}*t/{duration})':h=14:color=0xFFCC00@1:t=fill[v_bar];"
        # 2. Sleek semi-transparent black pill box for the Book CTA
        f"[v_bar]drawbox=x=(in_w-850)/2:y=180:w=850:h=70:color=black@0.65:t=fill[v_box];"
        # 3. Dynamic Book Name Text inside the pill
        f"[v_box]drawtext=text='📖 {badge_text}':fontcolor=white:fontsize=32:x=(w-text_w)/2:y=198[vout];"
        # 4. Audio Ducking / Mixing
        f"[0:a]asetpts=PTS-STARTPTS,aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[speech];"
        f"[1:a]volume=0.05,aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[bgm];"
        f"[speech][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start_sec),
        "-t", str(duration),
        "-i", str(input_video),
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
        str(output_path)
    ]

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"❌ FFmpeg Error: {res.stderr[-300:]}")
        return False
    return True