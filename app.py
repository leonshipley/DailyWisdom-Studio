import os
import re
import time
import json
import base64
import shutil
import warnings
import logging
import subprocess
from pathlib import Path
import pandas as pd
import streamlit as st
from PIL import Image

warnings.filterwarnings("ignore")
logging.getLogger("streamlit").setLevel(logging.ERROR)

import main as backend
import sticker_studio
import longform_prayer_engine as lpe
import flow_story_engine as fse
import channel_analytics_engine as cae
import grace_of_lord_engine as gle
import viral_researcher as vr

from voice_studio import (
    VOICE_CATALOG,
    SCRIPT_MODES,
    load_active_voice,
    save_active_voice,
    synthesize_preview_sample,
    build_spoken_voice_script,
)
from bible_database import (
    TOP_50_PRAYER_TOPICS,
    BIBLE_66_BOOKS,
    get_verses_for_chapter,
    lookup_reference_bilingual,
    format_reference_for_speech,
    translate_any_text_to_hindi,
)

st.set_page_config(
    page_title="DailyWisdom AI Studio",
    page_icon="\u271d\ufe0f",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ==============================================================================
# FAST ASSET SCANNERS & CACHED HELPERS
# ==============================================================================
def get_all_sequence_videos():
    return sorted(list(backend.CLIPS_DIR.rglob("*.mp4")), key=lambda p: p.parent.name, reverse=True)

def get_media_files(folder: Path, exts: tuple):
    if not folder.exists():
        return []
    return sorted([f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in exts], key=lambda x: x.stat().st_mtime, reverse=True)

def get_jesus_wallpapers() -> dict:
    backend.ensure_sacred_assets()
    walls = {}
    def_j = backend.get_jesus_image()
    if def_j and def_j.exists():
        walls["Sacred Jesus Default"] = def_j
    for folder in [backend.BG_DIR, getattr(backend, "PIN_IMG_DIR", backend.BG_DIR), backend.THUMB_DIR]:
        if folder and folder.exists():
            for f in get_media_files(folder, (".jpg", ".jpeg", ".png", ".webp"))[:15]:
                lbl = f"\U0001f5bc\ufe0f {f.name[:30]}"
                if lbl not in walls:
                    walls[lbl] = f
    return walls

@st.cache_data(show_spinner=False)
def _cached_bg_b64(path_str: str, mtime: float) -> str:
    try:
        cache_jpg = backend.BASE_DIR / "assets" / "studio_bg_cached.jpg"
        cache_jpg.parent.mkdir(parents=True, exist_ok=True)
        im = Image.open(path_str).convert("RGB")
        im.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
        im.save(str(cache_jpg), "JPEG", quality=80)
        return base64.b64encode(cache_jpg.read_bytes()).decode("utf-8")
    except Exception:
        return ""

def get_bg_base64(img_path: Path) -> str:
    if not img_path or not img_path.exists():
        return ""
    return _cached_bg_b64(str(img_path), img_path.stat().st_mtime)

@st.cache_data(show_spinner=False)
def cached_video_dur(path_str: str) -> float:
    return backend.get_video_duration(Path(path_str))

def get_available_bgm_tracks():
    tracks = {
        "Default Worship Piano": backend.get_worship_bgm(),
        "432Hz Cathedral Soaking Pad": lpe.ensure_soaking_worship_pad(),
        "Ambient Pad": backend.BGM_PODCAST_FILE
    }
    if backend.DOWNLOADS_DIR.exists():
        dl_files = sorted(
            [f for f in backend.DOWNLOADS_DIR.glob("*.*") if f.suffix.lower() in (".mp3", ".wav", ".m4a", ".aac")],
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )
        for f in dl_files:
            tracks[f"\U0001f4e5 {f.name[:36]}"] = f
    return tracks

class LiveTaskLoader:
    def __init__(self, title: str = "Studio Engine Running..."):
        self.title = title
        self.t0 = time.time()
        self.box = st.empty()
        self.prog = st.progress(0)
        self.update(5, "Initializing task...")

    def update(self, pct: int, step_msg: str):
        elapsed = time.time() - self.t0
        p_val = min(100, max(0, int(pct)))
        self.box.markdown(
            f'<div class="live-loader-card">'
            f'<div class="live-spinner-ring"></div>'
            f'<div style="flex:1;">'
            f'<div class="live-loader-title">\u26a1 {self.title} \u2014 <span style="color:#F87171;">{p_val}%</span></div>'
            f'<div class="live-loader-sub">{step_msg} &nbsp;\u2022&nbsp; \u23f1\ufe0f {elapsed:.1f}s elapsed</div>'
            f'</div></div>',
            unsafe_allow_html=True
        )
        self.prog.progress(p_val)

    def complete(self, final_msg: str):
        elapsed = time.time() - self.t0
        self.prog.progress(100)
        self.box.success(f"{final_msg} (Completed in {elapsed:.1f}s)")

CLASSIC_OPENING_HOOKS = [
    "Heavenly Father, I bring this prayer before You today...",
    "Before you close your eyes tonight, remember this truth...",
    "Take a deep breath and let this promise fill your heart...",
    "If your heart feels heavy right now, listen closely...",
    "Stop for 30 seconds and let God speak peace to your soul...",
    "You do not have to fight this battle alone today...",
    "God sees every tear and knows the weight you are carrying...",
    "No weapon formed against you shall prosper in this season...",
    "When everything around you feels uncertain, hold onto this...",
    "Lord Jesus, we surrender every worry into Your hands right now...",
    "Here is the divine truth God wants you to hear today...",
    "Never let fear convince you that God has forgotten you...",
    "This is your reminder that God is turning your trial into a testimony...",
    "Whatever door closed on you, God is opening a greater one...",
    "Speak this blessing over your life and your family right now...",
    "Dealing with this struggle? Here is God's unshakeable promise..."
]

channels = backend.load_channels()
channel_names = list(channels.keys()) if channels else ["Grace of the Lord (@GraceAndDailyPrayer)"]
all_videos = get_all_sequence_videos()
uploaded_count = sum(1 for v in all_videos if backend.load_clip_metadata(v).get("youtube_id"))
pending_count = len(all_videos) - uploaded_count
jesus_walls = get_jesus_wallpapers()

# ==============================================================================
# SIDEBAR COMMAND DECK
# ==============================================================================
with st.sidebar:
    st.markdown("### \U0001f39b\ufe0f Studio Quick Deck")
    if jesus_walls:
        sel_wall_lbl = st.selectbox("\u271d\ufe0f Studio Jesus Wallpaper:", list(jesus_walls.keys()), index=0, key="sb_wall_sel")
        active_wall_path = jesus_walls[sel_wall_lbl]
    else:
        active_wall_path = backend.get_jesus_image()

    sb_c1, sb_c2 = st.columns(2)
    with sb_c1:
        if st.button("\u2795 Add Channel", width="stretch"):
            new_c = backend.connect_new_channel()
            if new_c:
                st.rerun()
    with sb_c2:
        if st.button("\u2601\ufe0f Git Backup", width="stretch"):
            with st.spinner("Saving to GitHub..."):
                ok, msg = backend.save_everything_to_git()
                st.toast("Saved to GitHub!" if ok else msg)

    if st.button("\U0001f6d1 Stop Active Tasks", width="stretch"):
        subprocess.run(["taskkill", "/F", "/IM", "ffmpeg.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["taskkill", "/F", "/IM", "yt-dlp.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        st.warning("All active tasks stopped.")
        st.stop()

    st.divider()
    st.markdown("### \U0001f511 Gemini / Flow API Key")
    cur_k = fse.get_active_gemini_key()
    sb_key_in = st.text_input("API Key (.env):", value=cur_k, type="password", key="sb_api_key")
    if st.button("\U0001f4be Save API Key", width="stretch"):
        if fse.save_gemini_key_to_env(sb_key_in):
            st.success("\u2705 Saved to .env!")
            time.sleep(0.4)
            st.rerun()

    st.divider()
    st.markdown("### \U0001f4cc Pinterest Grabber")
    pin_in = st.text_input("Pin URL:", placeholder="https://pin.it/...", key="sb_pin_input")
    if st.button("\U0001f4e5 Download Pin", width="stretch") and pin_in.strip():
        with st.spinner("Downloading Pin..."):
            saved_p = backend.download_pinterest_media(pin_in.strip(), sync_to_studio=True)
            if saved_p and saved_p.exists() and saved_p.stat().st_size > 1000:
                st.success(f"\u2705 Saved: {saved_p.name}")
                time.sleep(0.8)
                st.rerun()
            else:
                st.error("\u274c Failed to extract media.")

    st.divider()
    st.markdown("### \U0001f3a5 YouTube Grabber")
    yt_in = st.text_input("YouTube URL:", placeholder="https://youtube.com/...", key="sb_yt_input")
    c_y1, c_y2 = st.columns(2)
    with c_y1:
        if st.button("\U0001f3b5 MP3", width="stretch") and yt_in.strip():
            with st.spinner("Downloading MP3..."):
                out_a = backend.download_youtube_audio_direct(yt_in.strip())
                if out_a and out_a.exists():
                    st.success(f"\u2705 {out_a.name[:22]}")
                else:
                    st.error("\u274c Failed")
    with c_y2:
        if st.button("\U0001f4f9 MP4", width="stretch") and yt_in.strip():
            with st.spinner("Downloading MP4..."):
                out_v = backend.download_youtube_video_direct(yt_in.strip())
                if out_v and out_v.exists():
                    st.success(f"\u2705 {out_v.name[:22]}")
                else:
                    st.error("\u274c Failed")

# ==============================================================================
# CSS STYLING & SACRED JESUS GLASSMORPHISM
# ==============================================================================
bg_b64 = get_bg_base64(active_wall_path)
bg_css_rule = (
    f'background-image: linear-gradient(135deg, rgba(4, 7, 15, 0.88) 0%, rgba(9, 17, 36, 0.82) 50%, rgba(16, 6, 12, 0.90) 100%), url("data:image/jpeg;base64,{bg_b64}") !important;'
    'background-size: cover !important; background-position: center center !important; background-attachment: fixed !important;'
) if bg_b64 else "background-color: #05070E !important;"

st.markdown(f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap');
    html, body, [class*="css"] {{ font-family: 'Plus Jakarta Sans', -apple-system, sans-serif; }}
    .stApp {{ {bg_css_rule} }}
    .block-container {{ padding-top: 3.5rem !important; padding-bottom: 2.5rem !important; padding-left: 1.5rem !important; padding-right: 1.5rem !important; max-width: 100% !important; }}
    header[data-testid="stHeader"] {{ background: transparent !important; z-index: 10 !important; }}
    section[data-testid="stSidebar"] {{ background: rgba(5, 7, 14, 0.92) !important; backdrop-filter: blur(14px) !important; border-right: 1px solid rgba(59, 130, 246, 0.35) !important; }}
    div[data-testid="stVerticalBlockBorderWrapper"] {{ background: rgba(8, 13, 25, 0.82) !important; backdrop-filter: blur(12px) !important; border: 1px solid rgba(59, 130, 246, 0.32) !important; border-radius: 14px !important; box-shadow: 0 8px 28px rgba(0, 0, 0, 0.45) !important; }}
    .top-nav {{
        background: linear-gradient(135deg, rgba(7, 11, 22, 0.94) 0%, rgba(15, 25, 48, 0.90) 50%, rgba(20, 8, 14, 0.94) 100%);
        backdrop-filter: blur(14px);
        border: 1px solid rgba(59, 130, 246, 0.45);
        border-left: 6px solid #DC2626;
        border-radius: 14px;
        padding: 14px 22px;
        margin-bottom: 12px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        flex-wrap: wrap;
        gap: 12px;
        box-shadow: 0 8px 26px rgba(0, 0, 0, 0.55);
    }}
    .nav-title {{ font-size: 24px; font-weight: 800; color: #60A5FA; margin: 0; }}
    .nav-sub {{ font-size: 13px; color: #CBD5E1; margin-top: 2px; font-weight: 500; }}
    .status-pill {{ background: rgba(15, 23, 42, 0.9); border: 1px solid #3B82F6; color: #F8FAFC; padding: 5px 13px; border-radius: 999px; font-size: 12px; font-weight: 700; white-space: nowrap; }}
    .status-pill-red {{ background: rgba(220, 38, 38, 0.22); border: 1px solid #EF4444; color: #FCA5A5; padding: 5px 13px; border-radius: 999px; font-size: 12px; font-weight: 700; white-space: nowrap; }}
    .verse-card {{ background: rgba(8, 13, 26, 0.88); border: 1px solid rgba(59, 130, 246, 0.4); border-left: 5px solid #DC2626; border-radius: 12px; padding: 14px 18px; margin: 10px 0; }}
    .verse-hdr {{ font-size: 15px; font-weight: 800; color: #60A5FA; margin-bottom: 5px; }}
    .verse-body {{ font-size: 14.5px; color: #F8FAFC; line-height: 1.5; }}
    .budget-badge {{ background: rgba(12, 21, 39, 0.9); border: 1px solid #2563EB; border-radius: 8px; padding: 8px 14px; font-size: 13px; color: #93C5FD; font-weight: 600; margin: 8px 0; display: inline-block; }}
    img {{ max-width: 100% !important; height: auto !important; object-fit: contain !important; border-radius: 10px; }}
    video {{ width: 100% !important; max-height: 620px !important; border-radius: 12px; background: #000; }}
    .stButton>button {{ background: linear-gradient(90deg, #DC2626 0%, #B91C1C 100%) !important; color: #FFFFFF !important; font-weight: 800 !important; border-radius: 9px !important; border: 1px solid rgba(255,255,255,0.18) !important; padding: 9px 18px !important; box-shadow: 0 4px 14px rgba(220, 38, 38, 0.35) !important; }}
    .stButton>button:hover {{ background: linear-gradient(90deg, #EF4444 0%, #DC2626 100%) !important; transform: translateY(-1px); }}
    div[data-testid="stHorizontalBlock"] .stButton>button {{ background: linear-gradient(90deg, #1E40AF 0%, #1D4ED8 100%) !important; box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3) !important; }}
    .stTabs [data-baseweb="tab"] {{ background-color: rgba(10, 15, 29, 0.85) !important; border: 1px solid rgba(59, 130, 246, 0.3) !important; border-radius: 8px 8px 0 0 !important; color: #CBD5E1 !important; font-weight: 700 !important; padding: 10px 16px !important; }}
    .stTabs [aria-selected="true"] {{ background-color: rgba(17, 28, 51, 0.95) !important; border-color: #3B82F6 !important; color: #60A5FA !important; border-bottom: 3px solid #DC2626 !important; }}
    div[data-testid="stStatusWidget"] {{ background: linear-gradient(90deg, #DC2626 0%, #1D4ED8 100%) !important; border: 2px solid #60A5FA !important; border-radius: 999px !important; padding: 6px 18px !important; }}
    @keyframes studio-spin {{ 0% {{ transform: rotate(0deg); }} 100% {{ transform: rotate(360deg); }} }}
    .live-loader-card {{ background: rgba(9, 14, 26, 0.95); border: 2px solid #3B82F6; border-left: 6px solid #DC2626; border-radius: 12px; padding: 14px 20px; margin: 10px 0; display: flex; align-items: center; gap: 16px; }}
    .live-spinner-ring {{ width: 32px; height: 32px; min-width: 32px; border: 4px solid rgba(96,165,250,0.2); border-top: 4px solid #EF4444; border-right: 4px solid #3B82F6; border-radius: 50%; animation: studio-spin 0.85s linear infinite; }}
    .live-loader-title {{ font-size: 15px; font-weight: 800; color: #FFFFFF; }}
    .live-loader-sub {{ font-size: 12.5px; color: #93C5FD; font-weight: 600; }}
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# TOP BANNER (FIXED: ZERO MARKDOWN INDENTATION / FULL CHANNEL HANDLE)
# ==============================================================================
ch_disp = channel_names[0] if channel_names else "Grace of the Lord (@GraceAndDailyPrayer)"

with st.container(border=True):
    tb_c1, tb_c2 = st.columns([1.5, 1.2], gap="medium")
    with tb_c1:
        st.markdown(
            f'<div style="display:flex;flex-direction:column;gap:2px;">'
            f'<span style="font-size:24px;font-weight:800;color:#60A5FA;letter-spacing:-0.5px;">✝️ DailyWisdom Sacred AI Studio</span>'
            f'<span style="font-size:13px;color:#CBD5E1;font-weight:500;">Active Channel: <b style="color:#FFFFFF;">{ch_disp}</b> &nbsp;•&nbsp; Clean Organized UI &nbsp;•&nbsp; Zero Clutter</span>'
            f'</div>',
            unsafe_allow_html=True
        )
    with tb_c2:
        st.markdown(
            f'<div style="display:flex;gap:8px;align-items:center;justify-content:flex-end;flex-wrap:wrap;padding-top:6px;">'
            f'<span class="status-pill">📺 {ch_disp}</span>'
            f'<span class="status-pill">🎬 {len(all_videos)} Shorts</span>'
            f'<span class="status-pill-red">⚡ Studio Ready</span>'
            f'</div>',
            unsafe_allow_html=True
        )

# ==============================================================================
# MASTER SETTINGS STRIP
# ==============================================================================
with st.container(border=True):
    st.markdown("##### \U0001f39a\ufe0f Master Adjuster Strip (Voice, Pacing & Background Music)")
    top_c1, top_c2, top_c3, top_c4 = st.columns([1.3, 1.25, 1.25, 1.2], gap="small")

    with top_c1:
        global_target_ch = channel_names[0]
        g_acc_choices = list(VOICE_CATALOG.keys())
        global_acc = st.selectbox("🌐 Accent:", g_acc_choices, index=2 if len(g_acc_choices) > 2 else 0, key="top_acc")
        g_v_list = VOICE_CATALOG[global_acc]
        g_v_names = [v["name"] for v in g_v_list]
        global_v_name = st.selectbox("🎙️ Voice:", g_v_names, index=0, key="top_voice")
        global_v_obj = g_v_list[g_v_names.index(global_v_name)]

    with top_c2:
        global_speed_pct = st.slider("🐢 Voice Speed (%):", min_value=-20, max_value=10, value=-4, step=2, key="top_speed")
        global_rate_str = f"{global_speed_pct:+d}%"
        lyrics_pace_options = {
            "Calm & Easy (4 Words / Screen)": 4,
            "Slow Worship (6 Words / Screen)": 6,
            "Smooth Balanced (3 Words / Screen)": 3,
            "Fast Pop-In (2 Words / Screen)": 2
        }
        global_lyrics_lbl = st.selectbox("📝 Lyrics Screen Pacing:", list(lyrics_pace_options.keys()), index=0, key="top_lyrics")
        global_lyrics_words = lyrics_pace_options[global_lyrics_lbl]

    with top_c3:
        all_bgm_map = get_available_bgm_tracks()
        global_bgm_lbl = st.selectbox("🎵 Worship BGM:", list(all_bgm_map.keys()), index=0, key="top_bgm")
        global_bgm_file = all_bgm_map[global_bgm_lbl]
        global_bgm_vol = st.slider("🔊 Music Volume:", min_value=0.05, max_value=0.45, value=0.18, step=0.01, key="top_bgm_vol")
        if global_bgm_file and Path(global_bgm_file).exists():
            st.caption("🎧 Preview BGM:")
            st.audio(str(global_bgm_file), format="audio/mp3")

    with top_c4:
        global_palette = st.selectbox("🎨 Thumbnail Palette:", ["Gold Classic", "Midnight Blue", "Sunrise", "Crimson Glory"], key="top_pal")
        if st.button(f"🎧 Audition Voice ({global_rate_str})", key="top_test_voice_btn", width="stretch"):
            with st.spinner("Generating sample..."):
                sample_txt = "The Lord is near to the brokenhearted, and His peace will guard your soul today. Type Amen."
                mp3_test = synthesize_preview_sample(global_v_obj["voice"], rate_str=global_rate_str, pitch_str=global_v_obj.get("pitch", "+0Hz"), sample_text=sample_txt)
                st.session_state["top_sample_mp3"] = str(mp3_test)
        if st.session_state.get("top_sample_mp3") and Path(st.session_state["top_sample_mp3"]).exists():
            st.caption("🎙️ Voice Audition:")
            st.audio(st.session_state["top_sample_mp3"], format="audio/mp3")

# ==============================================================================
# REUSABLE CUSTOM THUMBNAIL STUDIO WIDGET
# ==============================================================================
def render_custom_thumbnail_manager(video_path: Path, key_prefix: str) -> Path | None:
    v_dir = video_path.parent
    meta = backend.load_clip_metadata(video_path)
    tp_master = video_path.with_name(f"{video_path.stem}_thumb.jpg")
    custom_up_path = v_dir / "custom_uploaded_thumb.jpg"

    plain_candidates = []
    raw_bg = v_dir / "raw_clean_background.jpg"
    if raw_bg.exists():
        plain_candidates.append(("Plain Used Background (No Text)", raw_bg))
    grace_sc_dir = v_dir / "grace_scenes"
    if grace_sc_dir.exists():
        for s_i in range(1, 4):
            sp = grace_sc_dir / f"scene_{s_i}.jpg"
            if sp.exists():
                plain_candidates.append((f"Plain Scene {s_i} (No Text)", sp))
    if not plain_candidates:
        def_bg = backend.get_jesus_image()
        if def_bg and def_bg.exists():
            plain_candidates.append(("Plain Default Background", def_bg))

    prompt_file = v_dir / "ai_thumbnail_prompt.txt"
    if prompt_file.exists():
        ai_thumb_prompt = prompt_file.read_text(encoding="utf-8")
    else:
        import pro_design_addon as pda
        topic_str = meta.get("topic") or meta.get("title", "FAITH OVER FEAR")
        desc_str = meta.get("description", "")
        v_match = re.search(r"Scripture:\s*([^\n]+)", desc_str)
        v_ref_str = v_match.group(1).strip() if v_match else "PSALM 34:18"
        hook_str = re.sub(r"#\S+", "", meta.get("title", "DON'T GIVE UP YET")).strip()[:28]
        ai_thumb_prompt = pda.build_ai_thumbnail_prompt(topic_str, v_ref_str, hook_str)

    with st.expander("🎨 Custom Thumbnail Studio: Download Plain Image • Copy AI Prompt • Upload External", expanded=True):
        st.markdown("##### 1️⃣ Download Plain Background Image (Clean — Zero Text)")
        if plain_candidates:
            dl_cols = st.columns(min(4, len(plain_candidates)))
            for idx_p, (lbl_p, p_path) in enumerate(plain_candidates[:4]):
                with dl_cols[idx_p]:
                    st.image(str(p_path), caption=lbl_p, width="stretch")
                    st.download_button(
                        f"📥 Download {lbl_p[:18]}",
                        data=p_path.read_bytes(),
                        file_name=f"plain_{video_path.stem}_{p_path.name}",
                        mime="image/jpeg",
                        key=f"{key_prefix}_dl_plain_{idx_p}",
                        width="stretch"
                    )

        st.markdown("##### 2️⃣ AI-Analyzed Thumbnail Prompt (Copy for External AI Generators)")
        st.caption("Click the copy icon in the top-right corner to copy this prompt into Google AI Studio / Flow / Midjourney:")
        st.code(ai_thumb_prompt, language="text")

        st.markdown("##### 3️⃣ Upload Your Own Thumbnail (Made Outside)")
        up_ext_thumb = st.file_uploader(
            "Drop your custom thumbnail image (.jpg, .png, .webp) — automatically selected for YouTube upload:",
            type=["jpg", "jpeg", "png", "webp"],
            key=f"{key_prefix}_ext_thumb_up"
        )
        if up_ext_thumb is not None:
            im_ext = Image.open(up_ext_thumb).convert("RGB")
            im_ext.save(str(custom_up_path), "JPEG", quality=96, subsampling=0)
            st.success("✅ Custom thumbnail saved and selected for YouTube upload!")

    thumb_options = {}
    if custom_up_path.exists():
        thumb_options["🖼️ My Uploaded Custom Thumbnail"] = custom_up_path
    if tp_master.exists():
        thumb_options["⭐ Studio Master 9:16 (3D Gold)"] = tp_master
    for v_i in range(1, 4):
        vf_p = v_dir / f"thumbnail_9x16_variant_{v_i}.png"
        if vf_p.exists():
            thumb_options[f"✨ Variant #{v_i}"] = vf_p

    if thumb_options:
        sel_lbl = st.radio(
            "📺 Select Which Thumbnail Uploads to YouTube:",
            list(thumb_options.keys()),
            index=0,
            horizontal=True,
            key=f"{key_prefix}_final_thumb_radio"
        )
        chosen_file = thumb_options[sel_lbl]
        st.image(str(chosen_file), caption=f"Active Cover for YouTube: {sel_lbl}", width=240)
        return chosen_file

    return tp_master if tp_master.exists() else None

# ==============================================================================
# MAIN STUDIO TABS
# ==============================================================================
tab_en, tab_hi, tab_long, tab_story, tab_lib, tab_pod, tab_stats = st.tabs([
    "🎬 1. English Shorts Studio",
    "🇮🇳 2. Hindi Shorts",
    "🕊️ 3. Long-Form Prayers (5m-1Hr)",
    "🎬 4. 3-Min Flow Story Movies",
    "📂 5. Video Vault",
    "🎙️ 6. Podcast Clipper",
    "📊 7. Channel Analytics",
])

# ==============================================================================
# TAB 1: CONSOLIDATED & ORGANIZED ENGLISH SHORTS STUDIO
# ==============================================================================
with tab_en:
    short_style = st.radio(
        "Select Shorts Creation Style:",
        [
            "🌟 3-Scene Cinematic Short (Grace of the Lord, 28–38s — Recommended for High Retention)",
            "⚡ 1-Scene Quick Short (Fast Creation, 20–25s)"
        ],
        horizontal=True,
        key="en_short_style_choice"
    )

    col_workflow, col_monitor = st.columns([1.18, 1.0], gap="large")

    # --- STYLE A: 3-SCENE CINEMATIC SHORT ---
    if "3-Scene" in short_style:
        with col_workflow:
            with st.container(border=True):
                st.markdown("#### 📖 Step 1: Topic, Archetype & 3-Scene Storyboard")
                gr_c1, gr_c2 = st.columns(2)
                with gr_c1:
                    gr_arch = st.selectbox("🎭 Narrative Archetype (Anti-Repetition):", list(gle.ARCHETYPES.keys()), index=0, key="gr_arch_sel")
                with gr_c2:
                    gr_t_labels = [f"{item['id']}. {item['topic']}" for item in TOP_50_PRAYER_TOPICS]
                    gr_t_pick = st.selectbox("📖 Prayer Topic:", ["Custom Topic (Type Below)"] + gr_t_labels, index=1, key="gr_t_pick")

                if gr_t_pick == "Custom Topic (Type Below)":
                    gr_topic = st.text_input("Custom Topic:", value="Staring at the ceiling at 2 AM worried about tomorrow", key="gr_cust_t")
                else:
                    gr_topic = TOP_50_PRAYER_TOPICS[gr_t_labels.index(gr_t_pick)]["topic"]

                if st.button("📝 1. Write 3-Scene Script & Scene Prompts", key="gr_write_btn", width="stretch"):
                    with st.spinner(f"Writing authentic 3-Scene script for '{gr_topic}'..."):
                        st.session_state["active_grace_pkg"] = gle.generate_grace_3scene_script(gr_topic, gr_arch)

                if "active_grace_pkg" not in st.session_state:
                    st.info("💡 Click **'1. Write 3-Scene Script & Scene Prompts'** above to generate your script.")
                else:
                    gpkg = st.session_state["active_grace_pkg"]
                    g_segs = gpkg.get("spoken_script_segments", [])
                    rec_tone = gpkg.get("recommended_voice_tone", "deep_pastoral_male")
                    tone_info = gle.VOICE_TONE_MAP.get(rec_tone, gle.VOICE_TONE_MAP["deep_pastoral_male"])

                    st.markdown(
                        f'<div class="budget-badge">🎭 Archetype: <b>{gpkg.get("archetype_used")}</b> &nbsp;|&nbsp; '
                        f'🎙️ Tone: <b>{tone_info["label"]}</b></div>',
                        unsafe_allow_html=True
                    )
                    gpkg["youtube_title"] = st.text_input("🏆 YouTube Title:", value=gpkg.get("youtube_title", ""), key="gr_title_ed")

                    sc_cols = st.columns(3)
                    for idx_g, seg_g in enumerate(g_segs[:3]):
                        with sc_cols[idx_g]:
                            st.markdown(f"**Scene {seg_g['scene_number']}** (`{seg_g.get('camera_motion', 'zoom_in_slow')}`)")
                            seg_g["spoken_text"] = st.text_area(f"Spoken Text (Scene {idx_g+1}):", value=seg_g.get("spoken_text", ""), height=92, key=f"gr_sp_{idx_g}")
                            seg_g["image_prompt"] = st.text_area(f"9:16 Image Prompt (Scene {idx_g+1}):", value=seg_g.get("image_prompt", ""), height=78, key=f"gr_im_{idx_g}")

                    with st.expander("📝 View / Edit Clean Description & Pinned Comment", expanded=False):
                        gpkg["clean_youtube_description"] = st.text_area("Clean Description:", value=gpkg.get("clean_youtube_description", ""), height=150, key="gr_desc_ed")
                        gpkg["pinned_comment_text"] = st.text_input("Pinned Comment:", value=gpkg.get("pinned_comment_text", ""), key="gr_pin_ed")

            with st.container(border=True):
                st.markdown("#### 🎨 Step 2: Overlay Stickers & Render")
                gr_stk_inv = sticker_studio.get_sticker_inventory()
                gs1, gs2 = st.columns(2)
                with gs1:
                    use_rec_tone = st.checkbox(f"Use Recommended Voice ({tone_info['label']})", value=False, key="gr_use_rec_v") if "active_grace_pkg" in st.session_state else False
                with gs2:
                    gr_stk_lbl = st.selectbox("🏷️ Floating Sticker Overlay:", list(gr_stk_inv.keys()), index=1 if len(gr_stk_inv) > 1 else 0, key="gr_stk_sel")
                    gr_stk_path = gr_stk_inv[gr_stk_lbl]

                if st.button("⚡ 2. GENERATE 3-SCENE CINEMATIC SHORT (28–38s)", key="gr_render_3sc_btn", width="stretch"):
                    if "active_grace_pkg" not in st.session_state:
                        st.warning("Please click '1. Write 3-Scene Script' above first!")
                    else:
                        gr_loader = LiveTaskLoader("Producing 3-Scene Cinematic Short")
                        chosen_v_id = tone_info["voice"] if use_rec_tone else global_v_obj["voice"]
                        ok_gr, out_gr_v, out_gr_th = gle.render_grace_3scene_short(
                            st.session_state["active_grace_pkg"],
                            voice_id=chosen_v_id,
                            voice_rate=global_rate_str,
                            lyrics_words_per_card=global_lyrics_words,
                            bgm_file=global_bgm_file,
                            bgm_vol=global_bgm_vol,
                            palette_name=global_palette,
                            sticker_path=gr_stk_path,
                            progress_cb=lambda p, m: gr_loader.update(p, m)
                        )
                        if ok_gr:
                            st.session_state["last_created_video"] = str(out_gr_v)
                            st.session_state["last_grace_video"] = str(out_gr_v)
                            gr_loader.complete(f"🎉 Rendered Short: `{out_gr_v.name}`!")
                            time.sleep(0.4)
                            st.rerun()

    # --- STYLE B: 1-SCENE QUICK SHORT ---
    else:
        with col_workflow:
            with st.container(border=True):
                st.markdown("#### 📖 Step 1: Topic, 16 Openers & Full Spoken Script")
                qs_mode = st.radio("Choose By:", ["🎲 50 Topics", "📖 66-Book Bible", "✍️ Custom Situation"], horizontal=True, key="qs_mode")

                if "50 Topics" in qs_mode:
                    qs_t_labels = [f"{item['id']}. {item['topic']}" for item in TOP_50_PRAYER_TOPICS]
                    qs_chosen_lbl = st.selectbox("Select Topic:", qs_t_labels, key="qs_topic_dd")
                    qs_topic = TOP_50_PRAYER_TOPICS[qs_t_labels.index(qs_chosen_lbl)]["topic"]
                    qs_ref = TOP_50_PRAYER_TOPICS[qs_t_labels.index(qs_chosen_lbl)].get("ref", "Philippians 4:19")
                elif "66-Book" in qs_mode:
                    b_labels = [f"{i+1:02d}. {b_en.strip()}" for i, (b_en, _, _) in enumerate(BIBLE_66_BOOKS)]
                    qs_b = st.selectbox("Book:", b_labels, index=18, key="qs_bk").split(". ")[-1]
                    qs_c = st.selectbox("Chapter:", [1, 2, 3, 4, 5, 23, 91], index=0, key="qs_ch")
                    qs_v = st.selectbox("Verse:", [1, 2, 3, 4, 5], index=0, key="qs_vs")
                    qs_ref = f"{qs_b} {qs_c}:{qs_v}"
                    qs_topic = qs_ref
                else:
                    qs_topic = st.text_input("Describe Situation:", value="Breaking Financial Debt & Finding Peace", key="qs_cust_t")
                    qs_ref = "Philippians 4:19"

                _, qs_v_txt, _, _ = lookup_reference_bilingual(qs_ref)
                qs_ref_spoken = format_reference_for_speech(qs_ref, is_hindi_speech=False)

                st.markdown(
                    f'<div class="verse-card">'
                    f'<div class="verse-hdr">📖 {qs_ref} ({qs_ref_spoken})</div>'
                    f'<div class="verse-body">"{qs_v_txt}"</div>'
                    f'</div>',
                    unsafe_allow_html=True
                )

                # 16 Opening Hooks Selector
                qs_opening = st.selectbox("🎯 Select Opening Hook (16 Options — Never Repetitive):", CLASSIC_OPENING_HOOKS, index=0, key="qs_opening_hook_sel")

                # Track signature of (topic, ref, opening hook) to force-refresh script & metadata
                qs_sig = f"{qs_topic}_{qs_ref}_{qs_opening}_{qs_v_txt[:25]}"

                if st.session_state.get("qs_last_sig") != qs_sig or "qs_spoken_script_area" not in st.session_state:
                    st.session_state["qs_last_sig"] = qs_sig
                    synced_pkg = vr.get_fully_synced_youtube_package(qs_topic, qs_ref, qs_v_txt, qs_opening)

                    def_full_script = (
                        f"{qs_opening} "
                        f"{qs_ref_spoken}. {qs_v_txt.strip()} "
                        f"{synced_pkg['reflection']} "
                        f"{synced_pkg['prayer']} "
                        f"Type AMEN if you receive this blessing today!"
                    )
                    st.session_state["qs_spoken_script_area"] = def_full_script
                    st.session_state["qs_synced_title_in"] = synced_pkg["title"]
                    st.session_state["qs_synced_desc_in"] = synced_pkg["description"]
                    st.session_state["qs_synced_tags_in"] = ", ".join(synced_pkg["tags"])
                    st.session_state["qs_synced_hook"] = synced_pkg["hook"]
                    st.session_state["qs_synced_thumb_prompt"] = synced_pkg["thumbnail_prompt"]

                q_h1, q_h2 = st.columns([3, 1])
                with q_h1:
                    st.caption("✏️ Auto-updates with your chosen Topic & Opening Hook. Fully editable:")
                with q_h2:
                    if st.button("🔄 Reset to Topic Script", key="qs_resync_btn", width="stretch"):
                        synced_pkg = vr.get_fully_synced_youtube_package(qs_topic, qs_ref, qs_v_txt, qs_opening)
                        st.session_state["qs_spoken_script_area"] = (
                            f"{qs_opening} {qs_ref_spoken}. {qs_v_txt.strip()} "
                            f"{synced_pkg['reflection']} {synced_pkg['prayer']} "
                            f"Type AMEN if you receive this blessing today!"
                        )
                        st.session_state["qs_synced_title_in"] = synced_pkg["title"]
                        st.session_state["qs_synced_desc_in"] = synced_pkg["description"]
                        st.session_state["qs_synced_tags_in"] = ", ".join(synced_pkg["tags"])
                        st.session_state["qs_synced_thumb_prompt"] = synced_pkg["thumbnail_prompt"]
                        st.rerun()

                qs_spoken_script = st.text_area(
                    "📜 Exact Spoken Voiceover Script (What Voice Says — Fully Editable):",
                    height=120,
                    key="qs_spoken_script_area"
                )

                words_cnt = len(qs_spoken_script.split())
                speed_fac = 2.35 * (1.0 + (global_speed_pct / 100.0))
                est_d = round(words_cnt / max(1.2, speed_fac) + 2.5, 1)
                st.markdown(
                    f'<div class="budget-badge">⏱️ Words: <b>{words_cnt}</b> | Est. Duration: <b>{est_d}s</b> [Target: 20–25s]</div>',
                    unsafe_allow_html=True
                )

                with st.expander("🎯 Synchronized YouTube SEO Package (Auto-Updates with Topic — Editable Before Render)", expanded=True):
                    qs_pub_title = st.text_input("🏆 YouTube Title (High-CTR):", value=st.session_state.get("qs_synced_title_in", f"God's Promise in {qs_ref} #shorts"), key="qs_synced_title_in")
                    qs_pub_desc = st.text_area("📝 Emotional Surrender Description & Hashtags (Clean — Zero [HASHTAGS] Brackets):", value=st.session_state.get("qs_synced_desc_in", ""), height=160, key="qs_synced_desc_in")
                    qs_pub_tags_str = st.text_area("🏷️ 380-Char Backend Search Tags (Sanitized, No Commas Inside Tags):", value=st.session_state.get("qs_synced_tags_in", ""), height=75, key="qs_synced_tags_in")
                    st.caption("🎨 AI-Analyzed Thumbnail Prompt for this Topic:")
                    st.code(st.session_state.get("qs_synced_thumb_prompt", "AI Thumbnail prompt ready."), language="text")

            with st.container(border=True):
                st.markdown("#### 🎨 Step 2: Visuals & Render")
                intro_files = get_media_files(backend.INTRO_DIR, (".mp4", ".mov", ".webm", ".mkv"))
                bg_files = get_media_files(backend.BG_DIR, (".jpg", ".jpeg", ".png", ".webp"))

                q_c1, q_c2, q_c3 = st.columns(3)
                with q_c1:
                    qs_v_mode = st.selectbox("⏱️ Video Mode:", ["Full Video", "10s Video ➔ Wallpaper", "20s Video ➔ Wallpaper", "Wallpaper Only"], index=0, key="qs_v_mode")
                with q_c2:
                    qs_vid = st.selectbox("🎬 B-Roll Video:", ["Auto / Newest"] + [f.name for f in intro_files], key="qs_int_dd")
                with q_c3:
                    qs_img = st.selectbox("🖼️ Jesus Wallpaper:", ["Auto / Newest"] + [f.name for f in bg_files], key="qs_bg_dd")

                q_stk_inv = sticker_studio.get_sticker_inventory()
                qst_c1, qst_c2 = st.columns(2)
                with qst_c1:
                    qs_stk_lbl = st.selectbox("🏷️ Floating Sticker Overlay:", list(q_stk_inv.keys()), index=1 if len(q_stk_inv) > 1 else 0, key="qs_stk_sel")
                    qs_stk_path = q_stk_inv[qs_stk_lbl]
                with qst_c2:
                    qs_stk_pos = st.selectbox("📍 Sticker Position:", ["Bottom Dock (Centered)", "Bottom Right (Floating)", "Top Right Corner"], key="qs_stk_pos")

                if st.button(f"⚡ GENERATE QUICK SHORT ({qs_ref})", key="qs_gen_btn", width="stretch"):
                    qs_loader = LiveTaskLoader("Generating Quick Short")
                    active_maker_voice = dict(global_v_obj, rate=global_rate_str, accent=global_acc, script_mode=SCRIPT_MODES[0])
                    save_active_voice(active_maker_voice)

                    script_obj = backend.BibleShortScript(
                        topic=qs_topic, title=st.session_state.get("qs_synced_title_in", f"God's Promise in {qs_ref} #shorts"),
                        verse_citation=qs_ref, verse_text=qs_v_txt,
                        meaning="Trust God's unshakeable provision today.", prayer="Lord Jesus, release Your breakthrough, Amen.",
                        thumbnail_hook=st.session_state.get("qs_synced_hook", "GOD WILL PROVIDE"),
                        hashtags=["#DailyPrayer", "#BibleVerse", "#Shorts"]
                    )

                    qs_loader.update(30, "🎙️ Synthesizing exact voiceover script...")
                    temp_voice = backend.BASE_DIR / "temp_voice.mp3"
                    backend.generate_voiceover(qs_spoken_script.strip(), temp_voice)

                    qs_loader.update(65, "⚡ Rendering 1080p Short + 3D Gold Thumbnail...")
                    seq_dir = backend.get_next_sequence_folder(backend.clean_filename(f"Quick_{qs_topic}_{qs_ref}"))
                    out_vid = seq_dir / f"{seq_dir.name}.mp4"
                    out_th = seq_dir / f"{seq_dir.name}_thumb.jpg"

                    c_intro_path = (backend.INTRO_DIR / qs_vid) if (qs_vid != "Auto / Newest") else (intro_files[0] if intro_files else backend.prepare_muted_short_main())
                    c_bg_path = (backend.BG_DIR / qs_img) if (qs_img != "Auto / Newest") else active_wall_path

                    ok_q = backend.render_faceless_bible_video(
                        script_obj, temp_voice, out_vid, out_th,
                        custom_intro=c_intro_path, custom_bg=c_bg_path, custom_thumb=c_bg_path,
                        palette_name=global_palette, custom_bgm=global_bgm_file, bgm_volume=global_bgm_vol,
                        video_mode=qs_v_mode, sticker_path=qs_stk_path, sticker_position=qs_stk_pos,
                        lyrics_words_per_card=global_lyrics_words
                    )
                    if temp_voice.exists():
                        temp_voice.unlink(missing_ok=True)
                    if ok_q:
                        synced_pkg_now = vr.get_fully_synced_youtube_package(qs_topic, qs_ref, qs_v_txt, qs_opening)
                        final_t = st.session_state.get("qs_synced_title_in") or synced_pkg_now["title"]
                        final_d = st.session_state.get("qs_synced_desc_in") or synced_pkg_now["description"]
                        final_tags_str = st.session_state.get("qs_synced_tags_in") or ", ".join(synced_pkg_now["tags"])
                        final_tags_raw = [t.strip() for t in final_tags_str.split(",") if t.strip()]
                        clean_tags = backend.sanitize_youtube_tags(final_tags_raw)
                        backend.save_clip_metadata(out_vid, final_t, final_d, clean_tags, topic=qs_topic)
                        st.session_state["last_created_video"] = str(out_vid)
                        qs_loader.complete(f"🎉 Created Short: `{out_vid.name}`!")
                        time.sleep(0.4)
                        st.rerun()

    # --- RIGHT COLUMN: UN-CROPPED LIVE MONITOR & DIRECT PUBLISHER ---
    with col_monitor:
        with st.container(border=True):
            st.markdown("#### 🎬 Live Output Monitor & Direct Publisher")
            mon_vid_str = st.session_state.get("last_grace_video") or st.session_state.get("last_created_video")
            if not mon_vid_str or not Path(mon_vid_str).exists():
                mon_vid_str = str(all_videos[0]) if all_videos else None

            if not mon_vid_str:
                st.info("💡 Generate your Short on the left to preview the video and 3D Gold Thumbnails here!")
            else:
                mvp = Path(mon_vid_str)
                m_meta = backend.load_clip_metadata(mvp)
                m_dur = cached_video_dur(str(mvp))

                st.markdown(f"**⏱️ Final Duration:** `{m_dur:.1f}s` &nbsp;|&nbsp; 📁 `{mvp.parent.name}`")
                st.video(str(mvp))

                # Custom Thumbnail Studio & Upload Selector
                chosen_cover = render_custom_thumbnail_manager(mvp, f"pub_{mvp.parent.name}")

                st.markdown(f"**🏆 Publish Title:** `{m_meta['title']}`")
                with st.expander("📝 View Description & Backend Tags", expanded=False):
                    st.text_area("Description:", value=m_meta["description"], height=120, key=f"mon_d_{mvp.parent.name}")
                    st.code(", ".join(m_meta.get("tags", [])), language="text")

                if m_meta.get("youtube_id"):
                    st.success(f"🎉 LIVE ON YOUTUBE: https://youtube.com/shorts/{m_meta['youtube_id']}")
                else:
                    if st.button(f"🚀 Publish Video + Selected Thumbnail to '{global_target_ch}'", key=f"pub_btn_{mvp.parent.name}", width="stretch"):
                        live_ed_d = st.session_state.get(f"mon_d_{mvp.parent.name}", m_meta.get("description", ""))
                        backend.save_clip_metadata(mvp, m_meta.get("title", ""), live_ed_d, m_meta.get("tags", []), topic=m_meta.get("topic", ""))
                        with st.spinner(f"Publishing to {global_target_ch}..."):
                            yt_id = backend.upload_video_to_youtube(global_target_ch, mvp, thumbnail_path=chosen_cover)
                            if yt_id:
                                gle.post_pinned_comment_if_possible(global_target_ch, yt_id, mvp)
                                st.success(f"Live on YouTube! https://youtube.com/shorts/{yt_id}")
                                time.sleep(1.0)
                                st.rerun()

# ==============================================================================
# TAB 2: HINDI SHORTS
# ==============================================================================
with tab_hi:
    st.markdown("### 🇮🇳 Hindi Shorts Maker (पवित्र बाइबिल)")
    hi_c1, hi_c2 = st.columns([1.18, 1.0], gap="large")
    with hi_c1:
        with st.container(border=True):
            hi_t_labels = [f"{item['id']}. {item['topic']}" for item in TOP_50_PRAYER_TOPICS]
            hi_chosen_lbl = st.selectbox("विषय चुनें (Select Topic):", hi_t_labels, key="hi_t_dd")
            hi_t_name = TOP_50_PRAYER_TOPICS[hi_t_labels.index(hi_chosen_lbl)]["topic"]
            hi_ref = TOP_50_PRAYER_TOPICS[hi_t_labels.index(hi_chosen_lbl)].get("ref", "Philippians 4:19")
            _, _, hi_verse_txt, _ = lookup_reference_bilingual(hi_ref)
            hi_ref_spoken = format_reference_for_speech(hi_ref, is_hindi_speech=True)

            st.markdown(
                f'<div class="verse-card">'
                f'<div class="verse-hdr">📖 {hi_ref} ({hi_ref_spoken})</div>'
                f'<div class="verse-body">"{hi_verse_txt}"</div>'
                f'</div>',
                unsafe_allow_html=True
            )

            hi_opening = st.selectbox(
                "शुरुआती वाक्य (Select Hindi Opening Hook):",
                [
                    "प्रभु यीशु, मैं इस प्रार्थना को आपके चरणों में लाता हूँ...",
                    "आज रात अपनी आँखें बंद करने से पहले, प्रभु के इस वचन को याद रखें...",
                    "एक गहरी सांस लें और प्रभु की शांति को अपने मन में महसूस करें...",
                    "यदि आज आपका दिल भारी है, तो प्रभु के इस जीवित वचन को सुनें...",
                    "आप इस लड़ाई में अकेले नहीं हैं, परमेश्वर आपके साथ खड़े हैं...",
                    "प्रभु आपके हर छिपे हुए आंसू को देखते हैं और आपके दर्द को जानते हैं..."
                ],
                index=0,
                key="hi_opening_sel"
            )

            hi_def_script = (
                f"{hi_opening} "
                f"पवित्र बाइबिल, {hi_ref_spoken}। {hi_verse_txt.strip()} "
                f"प्रभु के इस पवित्र वचन पर पूरा भरोसा रखें। "
                f"प्रभु यीशु, मेरे जीवन में अपनी अलौकिक शांति और आशीष दें, आमीन। "
                f"यदि आप इस आशीष को ग्रहण करते हैं, तो कमेंट में आमीन ज़रूर लिखें!"
            )

            hi_sig = f"{hi_t_name}_{hi_ref}_{hi_opening}"
            if st.session_state.get("hi_last_sig") != hi_sig or "hi_spoken_area" not in st.session_state:
                st.session_state["hi_last_sig"] = hi_sig
                st.session_state["hi_spoken_area"] = hi_def_script

            hi_spoken_script = st.text_area(
                "📜 बोला जाने वाला पूरा हिंदी स्क्रिप्ट (Fully Editable Spoken Hindi Script):",
                height=120,
                key="hi_spoken_area"
            )

            if st.button("⚡ GENERATE HINDI SHORT", key="hi_gen_btn", width="stretch"):
                hi_loader = LiveTaskLoader("Generating Hindi Short")
                temp_voice = backend.BASE_DIR / "temp_voice.mp3"
                backend.generate_voiceover(hi_spoken_script.strip(), temp_voice)

                seq_dir = backend.get_next_sequence_folder(backend.clean_filename(f"Hindi_{hi_t_name}_{hi_ref}"))
                out_vid = seq_dir / f"{seq_dir.name}.mp4"
                out_th = seq_dir / f"{seq_dir.name}_thumb.jpg"

                hi_script_obj = backend.BibleShortScript(
                    topic=hi_t_name, title=f"{hi_ref} पवित्र बाइबिल वचन #shorts",
                    verse_citation=hi_ref, verse_text=hi_verse_txt,
                    meaning="प्रभु के वचन पर विश्वास रखें।", prayer="प्रभु यीशु आशीष दें, आमीन।",
                    thumbnail_hook=f"{hi_ref} PROMISE", hashtags=["#HindiBible", "#YeshuMasih", "#Shorts"]
                )
                ok_h = backend.render_faceless_bible_video(
                    hi_script_obj, temp_voice, out_vid, out_th,
                    custom_intro=None, custom_bg=active_wall_path, custom_thumb=active_wall_path,
                    palette_name="Gold Classic", custom_bgm=global_bgm_file, bgm_volume=global_bgm_vol,
                    video_mode="Full Video", lyrics_words_per_card=3
                )
                if temp_voice.exists():
                    temp_voice.unlink(missing_ok=True)
                if ok_h:
                    backend.save_clip_metadata(out_vid, hi_script_obj.title, hi_spoken_script, ["HindiBible", "Shorts"], topic=hi_t_name)
                    st.session_state["last_created_video"] = str(out_vid)
                    hi_loader.complete(f"🎉 Created Hindi Short: `{out_vid.name}`!")
                    time.sleep(0.4)
                    st.rerun()

    with hi_c2:
        with st.container(border=True):
            st.markdown("#### 🎬 Monitor & Publisher")
            hi_last = st.session_state.get("last_created_video")
            if hi_last and Path(hi_last).exists():
                h_vp = Path(hi_last)
                st.video(str(h_vp))
                h_cov = render_custom_thumbnail_manager(h_vp, f"hi_pub_{h_vp.parent.name}")
                if st.button(f"🚀 Publish to '{global_target_ch}'", key=f"hi_pub_btn_{h_vp.parent.name}", width="stretch"):
                    yt_id = backend.upload_video_to_youtube(global_target_ch, h_vp, thumbnail_path=h_cov)
                    if yt_id:
                        st.success(f"Live! https://youtube.com/shorts/{yt_id}")

# ==============================================================================
# TAB 3: LONG-FORM PRAYER SANCTUARY (5M - 1 HOUR)
# ==============================================================================
with tab_long:
    st.markdown("### 🕊️ Long-Form Soul Prayer Sanctuary (5 Min • 10 Min • 20 Min • 30 Min • 1 Hour)")
    lf_left, lf_right = st.columns([1.18, 1.0], gap="large")

    with lf_left:
        with st.container(border=True):
            st.markdown("#### 🙏 Step 1: Prayer Duration & Topic")
            lf_c1, lf_c2 = st.columns(2)
            with lf_c1:
                lf_dur = st.selectbox("⏱️ Video Length:", list(lpe.DURATION_CONFIGS.keys()), index=1, key="lf_dur_sel")
            with lf_c2:
                lf_nature = st.selectbox("🌧️ Nature Ambience:", ["None (Pure Music)", "Gentle Night Rain", "Mountain Stream"], index=1, key="lf_nat_sel")

            lf_t_labels = [f"{item['id']}. {item['topic']}" for item in TOP_50_PRAYER_TOPICS]
            lf_chosen_lbl = st.selectbox("Select Topic:", lf_t_labels, key="lf_topic_dd")
            lf_topic = TOP_50_PRAYER_TOPICS[lf_t_labels.index(lf_chosen_lbl)]["topic"]

            if st.button("📜 1. Generate 5-Stage Prayer Script", key="lf_gen_script_btn", width="stretch"):
                with st.spinner(f"Crafting prayer journey for '{lf_topic}' ({lf_dur})..."):
                    st.session_state["lf_active_journey"] = lpe.generate_soul_prayer_journey(lf_topic, lf_dur)

            if "lf_active_journey" not in st.session_state:
                st.info("💡 Click **'1. Generate 5-Stage Prayer Script'** above to begin.")
                lf_journey = None
            else:
                lf_journey = st.session_state["lf_active_journey"]
                vers_list_str = ", ".join([v["ref"] for v in lf_journey["scriptures"]])
                st.markdown(
                    f'<div class="verse-card">'
                    f'<div class="verse-hdr">📖 {len(lf_journey["scriptures"])} Scriptures Loaded for {lf_dur}:</div>'
                    f'<div class="verse-body">{vers_list_str}</div>'
                    f'</div>',
                    unsafe_allow_html=True
                )
                with st.expander("📝 View / Edit 5 Prayer Movements Before Rendering", expanded=False):
                    for stg in lf_journey["stages"]:
                        st.markdown(f"**Stage {stg['stage_num']}: {stg['chapter_title']}**")
                        edited_stg = st.text_area(f"Spoken Prayer (Stage {stg['stage_num']}):", value=stg["full_text"], height=100, key=f"lf_stg_edit_{stg['stage_num']}")
                        stg["full_text"] = edited_stg.strip()
                        stg["paragraphs"] = [p.strip() for p in re.split(r"\n\s*\n", edited_stg) if p.strip()]

                v_col1, v_col2 = st.columns(2)
                intro_vids = get_media_files(backend.INTRO_DIR, (".mp4", ".mov", ".webm", ".mkv"))
                bg_imgs = get_media_files(backend.BG_DIR, (".jpg", ".jpeg", ".png", ".webp"))
                with v_col1:
                    lf_vis_mode = st.selectbox("🎬 16:9 Style:", ["Looping Video Background", "Cinematic Ken Burns Wallpaper"], key="lf_vis_mode")
                    lf_pick_vid = st.selectbox("🎬 Video:", ["Auto / Newest"] + [f.name for f in intro_vids], key="lf_vid_dd")
                with v_col2:
                    lf_pick_img = st.selectbox("🖼️ Wallpaper:", ["Auto / Newest"] + [f.name for f in bg_imgs], key="lf_img_dd")

                if st.button(f"🚀 2. RENDER {lf_dur.upper()} 16:9 VIDEO", key="lf_render_btn", width="stretch"):
                    lf_loader = LiveTaskLoader(f"Producing {lf_dur} Video")
                    out_folder = lpe.get_next_longform_folder(f"{lf_dur}_{lf_topic}")
                    voice_raw_mp3 = out_folder / "meditative_voice.mp3"
                    master_mix_mp3 = out_folder / "master_soaking_audio.mp3"
                    final_16x9_mp4 = out_folder / f"{out_folder.name}.mp4"
                    final_16x9_thumb = out_folder / f"{out_folder.name}_thumb.jpg"

                    lf_loader.update(25, "🎙️ Synthesizing voiceover...")
                    v_res = lpe.synthesize_meditative_voiceover(lf_journey, voice_raw_mp3, voice_name=global_v_obj["voice"], rate_str=global_rate_str, pitch_str="-2Hz")

                    lf_loader.update(55, f"🎵 Mixing {lf_dur} master audio with worship music...")
                    lpe.mix_longform_master_audio(voice_raw_mp3, master_mix_mp3, target_duration_sec=lf_journey["config"]["target_seconds"], bgm_file=global_bgm_file, bgm_volume=global_bgm_vol, nature_style=lf_nature)

                    lf_loader.update(80, "🎬 Rendering Full-HD 1920x1080 (16:9) Video...")
                    chosen_v = (backend.INTRO_DIR / lf_pick_vid) if (lf_pick_vid != "Auto / Newest") else (intro_vids[0] if intro_vids else backend.prepare_muted_short_main())
                    chosen_i = (backend.BG_DIR / lf_pick_img) if (lf_pick_img != "Auto / Newest") else active_wall_path

                    ok_lf = lpe.render_longform_16x9_video(
                        master_mix_mp3, final_16x9_mp4, final_16x9_thumb, lf_journey,
                        bg_image_path=chosen_i, bg_video_path=chosen_v,
                        visual_mode=lf_vis_mode, palette_name=global_palette, subtitle_mode=lf_sub_mode,
                        progress_cb=lambda pct, msg: lf_loader.update(pct, msg)
                    )
                    if ok_lf:
                        lf_title, lf_desc, lf_tags = lpe.build_longform_youtube_metadata(lf_journey, v_res["chapters"])
                        backend.save_clip_metadata(final_16x9_mp4, lf_title, lf_desc, lf_tags, topic=lf_topic)
                        st.session_state["last_longform_video"] = str(final_16x9_mp4)
                        lf_loader.complete(f"🎉 Ready: `{final_16x9_mp4.name}`!")
                        time.sleep(0.4)
                        st.rerun()

    with lf_right:
        with st.container(border=True):
            st.markdown("#### 📺 Monitor & Publisher")
            lf_existing = [f for f in sorted(list(lpe.LONGFORM_DIR.rglob("*.mp4")), key=lambda p: p.parent.name, reverse=True) if "temp_" not in str(f)]
            lf_prev = st.session_state.get("last_longform_video") or (str(lf_existing[0]) if lf_existing else None)
            if not lf_prev:
                st.info("💡 Long-Form videos will preview here.")
            else:
                lf_p = Path(lf_prev)
                st.markdown(f"**⏱️ Length:** `{lpe.format_mm_ss(cached_video_dur(str(lf_p)))}` &nbsp;|&nbsp; 📁 `{lf_p.parent.name}`")
                st.video(str(lf_p))

                # 1-Click .SRT Subtitle File Downloader
                lf_srt_f = lf_p.parent / "longform_subtitles.srt"
                if lf_srt_f.exists():
                    st.download_button(
                        "📥 Download Subtitle File (.SRT for YouTube CC)",
                        data=lf_srt_f.read_bytes(),
                        file_name=f"{lf_p.stem}_subtitles.srt",
                        mime="application/x-subrip",
                        width="stretch"
                    )
                lf_th = render_custom_thumbnail_manager(lf_p, f"lf_pub_{lf_p.parent.name}")
                if st.button(f"🚀 Publish to '{global_target_ch}'", key="lf_pub_main", width="stretch"):
                    yt_id = backend.upload_video_to_youtube(global_target_ch, lf_p, thumbnail_path=lf_th)
                    if yt_id:
                        st.success(f"Live! https://www.youtube.com/watch?v={yt_id}")

# ==============================================================================
# TAB 4: 3-MIN FLOW STORY MOVIES
# ==============================================================================
with tab_story:
    st.markdown("### 🎬 3-Minute Story Movies (Google Flow & Gemini Omni 1.2)")
    st_left, st_right = st.columns([1.18, 1.0], gap="large")

    with st_left:
        with st.container(border=True):
            st.markdown("#### 🧠 Step 1: Storyboard & Character DNA")
            st_ar = st.selectbox("Movie Format:", ["16:9 Horizontal (1920x1080)", "9:16 Vertical Short Movie (1080x1920)"], index=0, key="st_ar_sel")
            st_chosen_topic = st.selectbox("Select Story:", fse.PRESET_STORY_TOPICS, key="st_preset_dd")

            if st.button("🧠 1. Generate 12-Scene Storyboard", key="st_gen_board_btn", width="stretch"):
                sb_loader = LiveTaskLoader("Analyzing Story")
                sb_new = fse.analyze_and_create_story_board(st_chosen_topic, aspect_ratio=st_ar, num_scenes=12)
                st.session_state["active_story_board"] = sb_new
                st.session_state["active_story_folder"] = str(fse.get_next_story_folder(sb_new["story_title"]))
                sb_loader.complete("✅ Storyboard Ready!")

            if "active_story_board" not in st.session_state:
                st.info("💡 Click **'1. Generate 12-Scene Storyboard'** above to start.")
            else:
                sb = st.session_state["active_story_board"]
                work_dir = Path(st.session_state["active_story_folder"])
                scenes_dir = work_dir / "scenes"
                scenes_dir.mkdir(parents=True, exist_ok=True)

                st.markdown(
                    f'<div class="verse-card">'
                    f'<div class="verse-hdr">🎬 {sb["story_title"]}</div>'
                    f'<div class="verse-body"><b>🧬 Character DNA:</b> {sb["character_dna"][:160]}...</div>'
                    f'</div>',
                    unsafe_allow_html=True
                )

                st_b1, st_b2 = st.columns(2)
                with st_b1:
                    if st.button("🖼️ 2. Auto-Generate All 12 Scene Images", key="st_gen_all_imgs", width="stretch"):
                        img_loader = LiveTaskLoader("Generating 12 Images")
                        fse.generate_all_scene_images_parallel(sb, scenes_dir, progress_cb=lambda p, m: img_loader.update(p, m))
                        img_loader.complete("✅ All 12 Images Generated!")
                with st_b2:
                    csv_b = fse.build_google_flow_csv_bytes(sb)
                    st.download_button("📥 Export Flow CSV Queue", data=csv_b, file_name="flow_queue.csv", mime="text/csv", width="stretch")

                if st.button("🚀 3. MERGE 3-MINUTE MOVIE", key="st_render_movie_btn", width="stretch"):
                    mv_loader = LiveTaskLoader("Mastering 3-Minute Movie")
                    ok_m, out_mv, out_th = fse.render_complete_3min_story_movie(
                        sb, work_dir, voice_name=global_v_obj["voice"], voice_rate=global_rate_str,
                        bgm_file=global_bgm_file, bgm_vol=global_bgm_vol, palette_name=global_palette,
                        progress_cb=lambda pct, msg: mv_loader.update(pct, msg)
                    )
                    if ok_m:
                        backend.save_clip_metadata(out_mv, sb["story_title"], sb["story_title"], ["BibleStory", "Shorts"], topic=sb["topic"])
                        st.session_state["last_story_movie"] = str(out_mv)
                        mv_loader.complete(f"🎉 Movie Ready: `{out_mv.name}`!")
                        time.sleep(0.4)
                        st.rerun()

    with st_right:
        with st.container(border=True):
            st.markdown("#### 📺 Monitor & Publisher")
            existing_m = sorted(list(fse.STORY_MOVIES_DIR.rglob("ST*.mp4")), key=lambda p: p.parent.name, reverse=True)
            st_prev = st.session_state.get("last_story_movie") or (str(existing_m[0]) if existing_m else None)
            if not st_prev:
                st.info("💡 Rendered 3-Minute Movies will display here.")
            else:
                mv_p = Path(st_prev)
                st.video(str(mv_p))
                m_th = render_custom_thumbnail_manager(mv_p, f"st_pub_{mv_p.parent.name}")
                if st.button(f"🚀 Publish to '{global_target_ch}'", key="st_pub_main", width="stretch"):
                    yt_id = backend.upload_video_to_youtube(global_target_ch, mv_p, thumbnail_path=m_th)
                    if yt_id:
                        st.success(f"Live! https://www.youtube.com/watch?v={yt_id}")

# ==============================================================================
# TAB 5: VIDEO VAULT
# ==============================================================================
with tab_lib:
    st.markdown("### 📂 Video Vault")
    if not all_videos:
        st.info("No videos in clips/ yet.")
    else:
        show_all = st.checkbox(f"Show All {len(all_videos)} Videos (Default shows newest 6)", value=False, key="lib_show_all")
        disp_vids = all_videos if show_all else all_videos[:6]
        for i in range(0, len(disp_vids), 3):
            cols = st.columns(3, gap="medium")
            for j in range(3):
                if i + j < len(disp_vids):
                    vid = disp_vids[i + j]
                    thumb = vid.with_name(f"{vid.stem}_thumb.jpg")
                    meta = backend.load_clip_metadata(vid)
                    with cols[j]:
                        with st.container(border=True):
                            badge = "🟢 LIVE" if meta.get("youtube_id") else "🔵 READY"
                            st.markdown(f"**`{vid.parent.name}`** — `{badge}`")
                            if thumb.exists():
                                st.image(str(thumb), width="stretch")
                            st.caption(f"📌 **{meta['title']}**")
                            if meta.get("youtube_id"):
                                st.success(f"https://youtube.com/shorts/{meta['youtube_id']}")
                            else:
                                if st.button(f"🚀 Upload", key=f"grid_up_{vid.parent.name}", width="stretch"):
                                    backend.upload_video_to_youtube(global_target_ch, vid)
                                    st.rerun()

# ==============================================================================
# TAB 6: PODCAST CLIPPER
# ==============================================================================
with tab_pod:
    st.markdown("### 🎙️ Podcast Clipper")
    p_c1, p_c2 = st.columns(2, gap="large")
    with p_c1:
        with st.container(border=True):
            st.markdown("#### 🎙️ Auto-Scout 1M+ View Podcasts")
            cat_map = {v["name"]: k for k, v in backend.CATEGORIES.items()}
            ch_cat = st.selectbox("Niche:", list(cat_map.keys()))
            if st.button("⚡ Scout & Clip", width="stretch"):
                target = backend.find_viral_video(1_000_000, backend.CATEGORIES[cat_map[ch_cat]]["queries"])
                if target:
                    tr = backend.get_transcript(target["id"])
                    clips = backend.analyze_transcript(tr, ch_cat) if tr else backend.analyze_audio_fallback(target["url"], ch_cat)
                    for clip in clips:
                        s_s, e_s = backend.timestamp_to_seconds(clip.start_time), backend.timestamp_to_seconds(clip.end_time)
                        tmp = backend.BASE_DIR / "temp_slice.mp4"
                        try:
                            backend.download_slice(target["url"], s_s, e_s, tmp)
                            s_dir = backend.get_next_sequence_folder(f"{backend.clean_filename(clip.book_title)}_{backend.clean_filename(clip.title)}")
                            out_f = s_dir / f"{s_dir.name}.mp4"
                            if backend.render_podcast_short(tmp, clip, out_f, backend.CATEGORIES[cat_map[ch_cat]]["badge_tag"]):
                                backend.save_clip_metadata(out_f, clip.title, clip.hook_caption, clip.hashtags)
                                st.success(f"Created `{s_dir.name}`!")
                        finally:
                            tmp.unlink(missing_ok=True)
    with p_c2:
        with st.container(border=True):
            st.markdown("#### 🔥 Competitor Spy")
            spy_q = st.text_input("Topic to Spy On:", value="Miracle Debt Prayer")
            if st.button("🔥 Audit Competition", width="stretch"):
                comps = backend.scan_competitor_shorts(spy_q)
                for c in comps[:4]:
                    st.caption(f"🔥 **{c['title'][:48]}** — `{c.get('views_per_day', 0):,.0f} views/day`")

# ==============================================================================
# TAB 7: CHANNEL ANALYTICS
# ==============================================================================
with tab_stats:
    st.markdown("### 📊 Channel Analytics")
    ctl_c1, ctl_c2, ctl_c3 = st.columns([1.5, 1.2, 1.2])
    with ctl_c1:
        stat_ch = st.selectbox("Channel to Audit:", channel_names, key="stats_ch_sel")
    with ctl_c2:
        stat_days = st.selectbox("Period:", [28, 90, 365], index=1, format_func=lambda x: f"Last {x} Days", key="stats_period_sel")
    with ctl_c3:
        st.markdown("<div style='height:26px;'></div>", unsafe_allow_html=True)
        if st.button("🔄 Refresh Analytics", key="refresh_stats_btn", width="stretch"):
            st.session_state[f"full_intel_{stat_ch}_{stat_days}"] = cae.fetch_complete_channel_intelligence(stat_ch, days_back=stat_days)

    cache_k = f"full_intel_{stat_ch}_{stat_days}"
    intel = st.session_state.get(cache_k)
    if intel is None:
        st.info(f"💡 Click **'Refresh Analytics'** above to load live Subscribers, Video Audit, and Geography for **{stat_ch}**.")
    elif not intel.get("ok"):
        st.error(f"⚠️ {intel.get('error', 'Could not load data.')}")
    else:
        ov = intel["overview"]
        tot = intel["totals"]
        vids = intel["videos"]
        live_views = max(ov["lifetime_views"], sum(v["views"] for v in vids))
        wh_mins = tot["watch_time_minutes_period"]
        wh_hrs = round(wh_mins / 60.0, 1)

        r1 = st.columns(4)
        r1[0].metric("👥 Total Subscribers", f"{ov['subscribers']:,}")
        r1[1].metric("👁️ Total Channel Views", f"{live_views:,}", f"{tot['shorts_views']:,} Shorts • {tot['longform_views']:,} Long-Form")
        r1[2].metric("📹 Total Public Videos", f"{max(ov['total_videos'], len(vids)):,}", f"{tot['shorts_count']} Shorts • {tot['longform_count']} Long-Form")
        r1[3].metric("⏱️ Est. Watch Time", f"{wh_hrs:,.1f} hrs", f"{wh_mins:,} mins")

        r2 = st.columns(4)
        r2[0].metric("👍 Total Likes", f"{tot['total_likes']:,}")
        r2[1].metric("💬 Total Comments", f"{tot['total_comments']:,}")
        r2[2].metric("🔥 Engagement Rate", f"{tot['engagement_rate_pct']:.2f}%")
        top_v = max([v["views"] for v in vids], default=0)
        r2[3].metric("🚀 Top Video Views", f"{top_v:,}")

        if vids:
            st.write("")
            df_v = pd.DataFrame([{"Rank": f"#{i+1}", "Type": v["type"], "Title": v["title"][:50], "Views": v["views"], "Likes": v["likes"], "Comments": v["comments"], "Duration": v["duration_str"], "Date": v["published_date"]} for i, v in enumerate(vids)])
            st.dataframe(df_v, hide_index=True, width="stretch")
