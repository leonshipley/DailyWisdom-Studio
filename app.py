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
import os
import asyncio
import platform
import streamlit as st

# FIX FOR WINDOWS ASYNCIO WINERROR 10054 CRASHES WITH EDGE-TTS
if platform.system() == 'Windows':
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass

from PIL import Image

warnings.filterwarnings("ignore")
logging.getLogger("streamlit").setLevel(logging.ERROR)

import importlib
import main as backend
importlib.reload(backend)
import sticker_studio
import importlib
import ai_emotional_tts_engine as aete
importlib.reload(aete)
import preacher_audio_engine as pae
import studio_screen_recorder as ssr
importlib.reload(ssr)
importlib.reload(pae)
import importlib
import longform_prayer_engine as lpe
importlib.reload(lpe)
import flow_story_engine as fse
import channel_analytics_engine as cae
import personal_ai_analyzer as paa
importlib.reload(paa)
import grace_of_lord_engine as gle
import viral_researcher as vr
import title_engine
import description_engine

from voice_studio import (
    VOICE_CATALOG,
    SCRIPT_MODES,
    load_active_voice,
    save_active_voice,
    synthesize_preview_sample,
    synthesize_bilingual_verse_preview,
    build_spoken_voice_script,
)
from bible_database import (
    TOP_50_PRAYER_TOPICS,
    BIBLE_66_BOOKS,
    get_verses_for_chapter,
    lookup_reference_bilingual,
    format_reference_for_speech,
    translate_any_text_to_hindi,
    ai_pick_relevant_verse_for_topic,
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
@st.cache_data(ttl=120.0, show_spinner=False)
def get_all_sequence_videos():
    return sorted(list(backend.CLIPS_DIR.rglob("*.mp4")), key=lambda p: p.parent.name, reverse=True)

@st.cache_data(ttl=120.0, show_spinner=False)
def get_media_files(folder_path_str: str, exts: tuple):
    folder = Path(folder_path_str)
    if not folder.exists():
        return []
    return sorted([f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in exts], key=lambda x: x.stat().st_mtime, reverse=True)

@st.cache_data(ttl=120.0, show_spinner=False)
def get_jesus_wallpapers() -> dict:
    backend.ensure_sacred_assets()
    walls = {}
    def_j = backend.get_jesus_image()
    if def_j and def_j.exists():
        walls["Sacred Jesus Default"] = def_j
    for folder in [backend.BG_DIR, getattr(backend, "PIN_IMG_DIR", backend.BG_DIR), backend.THUMB_DIR]:
        if folder and folder.exists():
            for f in get_media_files(str(folder), (".jpg", ".jpeg", ".png", ".webp"))[:15]:
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

@st.cache_data(ttl=120.0, show_spinner=False)
def get_available_bgm_tracks():
    tracks = {
        "Default Worship Piano": backend.get_worship_bgm(),
        "🔇 No Music (Voice Only)": "NONE",
        "432Hz Cathedral Soaking Pad": lpe.ensure_soaking_worship_pad(),
        "Ambient Pad": backend.BGM_PODCAST_FILE
    }
    flow_m_dir = backend.BASE_DIR / 'custom_media' / 'flow_music'
    if flow_m_dir.exists():
        for fm in sorted(flow_m_dir.glob('*.mp3'), key=lambda x: x.stat().st_mtime, reverse=True):
            tracks[f'🎵 [Flow AI] {fm.stem.replace("FlowAI_", "")}'] = fm
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
@st.cache_data(ttl=120.0, show_spinner=False)
def _cached_kpis():
    import json
    vids = get_all_sequence_videos()
    upld = sum(1 for v in vids if v.with_suffix('.json').exists() and json.loads(v.with_suffix('.json').read_bytes()).get("youtube_id"))
    return vids, upld, len(vids) - upld

all_videos, uploaded_count, pending_count = _cached_kpis()
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

# === SIDEBAR SCREEN RECORDER START ===
    st.divider()
    with st.expander("🎥 Screen + Mic Recorder (`recordings/`)", expanded=True):
        next_phase_path = ssr.get_next_phase_filename("Graceofthe lord phase")
        rec_custom_name = st.text_input(
            "📝 Recording Name (Auto-Increments):",
            value=next_phase_path.stem,
            key="sb_rec_name_in"
        )
        rec_use_mic = st.checkbox("🎙️ Enable Microphone While Recording", value=True, key="sb_rec_mic_chk")
        avail_mics = ssr.list_windows_microphones()
        if rec_use_mic:
            if avail_mics:
                sel_mic_dev = st.selectbox("🎤 Select Mic:", avail_mics, index=0, key="sb_rec_mic_sel")
            else:
                sel_mic_dev = "No Microphone Found"
                st.caption("⚠️ No DirectShow mic detected; use the Browser Screen+Mic button below.")
        else:
            sel_mic_dev = ""

        is_rec_now = ssr.is_recording_active()
        rc_b1, rc_b2 = st.columns(2)
        with rc_b1:
            if not is_rec_now:
                if st.button("🔴 Rec Desktop+Mic", key="sb_start_rec_btn", width="stretch"):
                    ok_r, msg_r, _ = ssr.start_desktop_mic_recording(
                        enable_mic=rec_use_mic,
                        mic_device=sel_mic_dev,
                        custom_name=rec_custom_name
                    )
                    if ok_r:
                        st.toast(msg_r)
                        time.sleep(0.3)
                        st.rerun()
                    else:
                        st.error(msg_r)
            else:
                st.markdown("🔴 **RECORDING LIVE...**")
        with rc_b2:
            if st.button("⏹️ Stop & Save", key="sb_stop_rec_btn", width="stretch", disabled=not is_rec_now):
                ok_s, saved_rec_p, msg_s = ssr.stop_desktop_mic_recording()
                if ok_s and saved_rec_p:
                    st.session_state["last_saved_recording"] = str(saved_rec_p)
                    st.success(msg_s)
                    time.sleep(0.4)
                    st.rerun()
                else:
                    st.warning(msg_s)

        # Also provide Browser Screen + Tab Audio + Mic Recorder
        ssr.render_browser_screen_mic_widget(rec_custom_name)

        all_recs = ssr.get_all_recordings()
        if all_recs:
            sel_rec_file = st.selectbox(
                f"📂 Saved in `recordings/` ({len(all_recs)}):",
                all_recs,
                format_func=lambda p: p.name,
                index=0,
                key="sb_saved_recs_dd"
            )
            st.video(str(sel_rec_file))
            fo_c1, fo_c2 = st.columns(2)
            with fo_c1:
                st.download_button(
                    "📤 Download to Send",
                    data=sel_rec_file.read_bytes(),
                    file_name=sel_rec_file.name,
                    mime="video/mp4",
                    key="sb_dl_rec_btn",
                    width="stretch"
                )
            with fo_c2:
                if st.button("📂 Open Folder", key="sb_open_rec_dir", width="stretch"):
                    os.startfile(str(ssr.RECORDINGS_DIR))
# === SIDEBAR SCREEN RECORDER END ===


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
    # --- 5-SLOT AFFILIATE & BIO LINK MANAGER (GLOBAL) ---
    with st.expander("??? 5 Affiliate & Bio Links Manager", expanded=False):
        st.caption("Paste your Amazon or custom links below. **Leave blank to remove.**")
        import description_engine
        current_affs = description_engine.load_affiliates()
        updated_affs = []
        for i in range(5):
            st.markdown(f"**Link #{i + 1}**")
            aff_cur = current_affs[i] if (isinstance(current_affs, list) and i < len(current_affs)) else {}
            h_val = st.text_input(f"Title / Heading #{i + 1}:", value=aff_cur.get("heading", ""), key=f"g_aff_h_{i}", placeholder="e.g. ?? Study Bible:")
            u_val = st.text_input(f"URL #{i + 1}:", value=aff_cur.get("url", ""), key=f"g_aff_u_{i}", placeholder="https://amzn.to/...")
            updated_affs.append({"heading": h_val, "url": u_val})
            
        if st.button("?? Save Links (Applies Everywhere)", key="btn_save_g_affs", width="stretch"):
            description_engine.save_affiliates(updated_affs)
            st.cache_data.clear()
            st.success("? Saved!")
            import time
            time.sleep(0.5)
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
# CSS STYLING: SACRED PHOTO COLLAGE + PREMIUM GLASSMORPHISM
# ==============================================================================
st.markdown('''
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap');
    html, body, [class*="css"] { font-family: 'Plus Jakarta Sans', -apple-system, sans-serif; }
    
    /* 1. Cinematic Sacred Photo Collage Background */
    @keyframes slowDrift {
        0% { opacity: 0.85; }
        50% { opacity: 1.0; }
        100% { opacity: 0.85; }
    }
    .stApp { 
        background-color: #05070E !important;
        background-image: 
            /* Top Layer: Dark frosted overlay to keep UI readable */
            radial-gradient(circle at 50% 50%, rgba(10, 15, 25, 0.85) 0%, rgba(5, 7, 12, 0.96) 100%),
            /* Collage Image 1: Cross on Hill (Top Left) */
            url('https://images.unsplash.com/photo-1544830237-7d5d28b12f66?w=600&q=80&auto=format&fit=crop'),
            /* Collage Image 2: Stained Glass Jesus (Bottom Right) */
            url('https://images.unsplash.com/photo-1558299105-961f6874a123?w=600&q=80&auto=format&fit=crop'),
            /* Collage Image 3: Bible & Light (Center Right) */
            url('https://images.unsplash.com/photo-1614252365287-2be5188f6153?w=600&q=80&auto=format&fit=crop'),
            /* Collage Image 4: Angelic Light (Bottom Left) */
            url('https://images.unsplash.com/photo-1506501139174-099022df5260?w=600&q=80&auto=format&fit=crop'),
            /* Collage Image 5: Divine Church Light (Top Right) */
            url('https://images.unsplash.com/photo-1574246604907-3932454a856f?w=600&q=80&auto=format&fit=crop') !important;
        
        background-position: 
            center center,
            top -5% left -5%,
            bottom -5% right -5%,
            center right 15%,
            bottom 15% left -5%,
            top 15% right -5% !important;
            
        background-size: 
            cover,
            35%, 35%, 25%, 30%, 30% !important;
            
        background-repeat: no-repeat !important;
        background-attachment: fixed !important;
        animation: slowDrift 10s ease-in-out infinite !important;
    }
    
    .block-container { padding-top: 3rem !important; padding-bottom: 2.5rem !important; padding-left: 2rem !important; padding-right: 2rem !important; max-width: 100% !important; }
    header[data-testid="stHeader"] { background: transparent !important; z-index: 10 !important; }
    
    /* 2. Floating Frosted Glass Cards */
    div[data-testid="stVerticalBlockBorderWrapper"] { 
        background: rgba(15, 20, 35, 0.65) !important; 
        backdrop-filter: blur(20px) !important; 
        -webkit-backdrop-filter: blur(20px) !important;
        border: 1px solid rgba(255, 255, 255, 0.15) !important; 
        border-radius: 16px !important; 
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.6), inset 0 0 0 1px rgba(255, 255, 255, 0.08) !important; 
        transition: transform 0.3s ease, box-shadow 0.3s ease !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:hover {
        transform: translateY(-3px);
        box-shadow: 0 12px 40px 0 rgba(235, 185, 55, 0.15), inset 0 0 0 1px rgba(235, 185, 55, 0.2) !important;
    }

    /* 3. Animated Gradient Buttons */
    .stButton>button { 
        background: linear-gradient(90deg, #DC2626 0%, #991B1B 50%, #DC2626 100%) !important; 
        background-size: 200% auto !important;
        color: #FFFFFF !important; 
        font-weight: 800 !important; 
        border-radius: 10px !important; 
        border: 1px solid rgba(255,255,255,0.2) !important; 
        padding: 10px 20px !important; 
        box-shadow: 0 4px 15px rgba(220, 38, 38, 0.4) !important; 
        transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1) !important; 
    }
    .stButton>button:hover { 
        background-position: right center !important;
        transform: translateY(-2px) scale(1.02); 
        box-shadow: 0 8px 25px rgba(220, 38, 38, 0.6) !important; 
    }
    
    div[data-testid="stHorizontalBlock"] .stButton>button, section[data-testid="stSidebar"] .stButton>button { 
        background: linear-gradient(90deg, #2563EB 0%, #1E40AF 50%, #2563EB 100%) !important; 
        background-size: 200% auto !important;
        box-shadow: 0 4px 15px rgba(37, 99, 235, 0.4) !important; 
    }
    div[data-testid="stHorizontalBlock"] .stButton>button:hover, section[data-testid="stSidebar"] .stButton>button:hover {
        background-position: right center !important;
        box-shadow: 0 8px 25px rgba(37, 99, 235, 0.6) !important; 
    }

    section[data-testid="stSidebar"] { 
        background: rgba(8, 12, 20, 0.85) !important; 
        backdrop-filter: blur(25px) !important; 
        border-right: 1px solid rgba(235, 185, 55, 0.3) !important; 
    }

    /* 4. Smooth Tabs */
    .stTabs [data-baseweb="tab"] { 
        background: rgba(15, 20, 35, 0.7) !important; 
        border: 1px solid rgba(255, 255, 255, 0.08) !important; 
        border-radius: 10px 10px 0 0 !important; 
        color: #94A3B8 !important; 
        transition: all 0.3s ease !important;
        font-weight: 700 !important;
    }
    .stTabs [data-baseweb="tab"]:hover { background: rgba(30, 41, 59, 0.9) !important; color: #E2E8F0 !important; }
    .stTabs [aria-selected="true"] { background: rgba(30, 41, 59, 0.98) !important; border-color: #EBB937 !important; color: #EBB937 !important; border-bottom: 3px solid #DC2626 !important; }
    
    /* 5. Pulsing Gold Title Glow */
    .studio-title {
        background: linear-gradient(to right, #FDE047, #F59E0B, #D97706);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 26px;
        font-weight: 800;
        letter-spacing: -0.5px;
        animation: pulseGold 3s infinite alternate;
    }
    @keyframes pulseGold {
        0% { filter: drop-shadow(0 0 4px rgba(245,158,11,0.3)); }
        100% { filter: drop-shadow(0 0 12px rgba(245,158,11,0.7)); }
    }

    /* Dynamic Badges & Spinners */
    @keyframes studio-spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    .live-loader-card { background: rgba(15, 23, 42, 0.85); backdrop-filter: blur(15px); border: 2px solid #EBB937; border-left: 6px solid #DC2626; border-radius: 14px; padding: 14px 20px; margin: 10px 0; display: flex; align-items: center; gap: 16px; box-shadow: 0 8px 32px rgba(235,185,55,0.2); }
    .live-spinner-ring { width: 32px; height: 32px; min-width: 32px; border: 4px solid rgba(235,185,55,0.2); border-top: 4px solid #EF4444; border-right: 4px solid #EBB937; border-radius: 50%; animation: studio-spin 0.85s linear infinite; }
    .live-loader-title { font-size: 15px; font-weight: 800; color: #FFFFFF; }
    .live-loader-sub { font-size: 12.5px; color: #FDE047; font-weight: 600; margin-top: 2px; }
    
    .status-pill { background: linear-gradient(135deg, rgba(235,185,55,0.2), rgba(17,24,39,0.9)); border: 1px solid #EBB937; color: #F8FAFC; padding: 5px 14px; border-radius: 999px; font-size: 13px; font-weight: 700; box-shadow: 0 0 10px rgba(235,185,55,0.2); }
    .status-pill-red { background: linear-gradient(135deg, rgba(153,27,27,0.8), rgba(17,24,39,0.9)); border: 1px solid #EF4444; color: #FCA5A5; padding: 5px 14px; border-radius: 999px; font-size: 13px; font-weight: 700; box-shadow: 0 0 10px rgba(239,68,68,0.3); }
    .budget-badge { background: rgba(15, 23, 42, 0.7); border: 1px solid #EBB937; border-radius: 8px; padding: 8px 14px; font-size: 13px; color: #FDE047; font-weight: 700; display: inline-block; box-shadow: inset 0 0 8px rgba(235,185,55,0.1); }
    
    /* Verse Cards */
    .verse-card { background: rgba(15, 23, 42, 0.8); backdrop-filter: blur(12px); border: 1px solid rgba(235, 185, 55, 0.4); border-left: 5px solid #DC2626; border-radius: 12px; padding: 16px; margin: 10px 0; transition: transform 0.2s; }
    .verse-card:hover { transform: scale(1.01); box-shadow: 0 4px 20px rgba(0,0,0,0.5); }
    .verse-hdr { font-size: 15px; font-weight: 800; color: #FDE047; margin-bottom: 5px; }
    .verse-body { font-size: 14.5px; color: #F8FAFC; line-height: 1.5; }
    
    img { border-radius: 10px; }
    video { width: 100% !important; max-height: 620px !important; border-radius: 12px; background: #000; border: 1px solid rgba(255,255,255,0.15); box-shadow: 0 8px 30px rgba(0,0,0,0.7); }

    /* Luxury 2x4 Grid Studio Navigation Deck */
    div[data-testid="stRadio"]:has(input[name*="fast_nav_bar"]) > div[role="radiogroup"] {
        display: grid !important;
        grid-template-columns: repeat(4, 1fr) !important;
        gap: 10px !important;
        background: rgba(10, 15, 28, 0.85) !important;
        backdrop-filter: blur(20px) !important;
        border: 1px solid rgba(235, 185, 55, 0.35) !important;
        border-radius: 14px !important;
        padding: 10px !important;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.6) !important;
        margin-bottom: 15px !important;
    }

    /* Hide the awkward radio dot circle */
    div[data-testid="stRadio"]:has(input[name*="fast_nav_bar"]) label > div:first-child {
        display: none !important;
    }

    /* Style the tabs as luxury clickable buttons */
    div[data-testid="stRadio"]:has(input[name*="fast_nav_bar"]) label {
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        background: rgba(20, 28, 48, 0.7) !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        border-radius: 10px !important;
        padding: 12px 14px !important;
        margin: 0 !important;
        cursor: pointer !important;
        transition: all 0.25s cubic-bezier(0.25, 0.8, 0.25, 1) !important;
        text-align: center !important;
    }

    div[data-testid="stRadio"]:has(input[name*="fast_nav_bar"]) label div,
    div[data-testid="stRadio"]:has(input[name*="fast_nav_bar"]) label p {
        font-size: 13.5px !important;
        font-weight: 700 !important;
        color: #CBD5E1 !important;
        margin: 0 !important;
    }

    /* Smooth Hover Glow */
    div[data-testid="stRadio"]:has(input[name*="fast_nav_bar"]) label:hover {
        background: rgba(30, 41, 59, 0.95) !important;
        border-color: #EBB937 !important;
        transform: translateY(-2px) !important;
        box-shadow: 0 4px 18px rgba(235, 185, 55, 0.25) !important;
    }
    div[data-testid="stRadio"]:has(input[name*="fast_nav_bar"]) label:hover p {
        color: #FDE047 !important;
    }

    /* Selected Active Tab Highlight (Red & Gold Studio Theme) */
    div[data-testid="stRadio"]:has(input[name*="fast_nav_bar"]) label:has(input:checked) {
        background: linear-gradient(135deg, #DC2626 0%, #991B1B 50%, #B91C1C 100%) !important;
        border: 1px solid #FDE047 !important;
        box-shadow: 0 6px 22px rgba(220, 38, 38, 0.6), inset 0 0 12px rgba(253, 224, 71, 0.3) !important;
        transform: scale(1.02) !important;
    }
    div[data-testid="stRadio"]:has(input[name*="fast_nav_bar"]) label:has(input:checked) p {
        color: #FFFFFF !important;
        font-weight: 800 !important;
        text-shadow: 0 1px 4px rgba(0,0,0,0.8) !important;
    }

</style>
''', unsafe_allow_html=True)

# ==============================================================================
# TOP BANNER
# ==============================================================================
ch_disp = channel_names[0] if channel_names else "Grace of the Lord (@GraceAndDailyPrayer)"

with st.container(border=True):
    tb_c1, tb_c2 = st.columns([1.5, 1.2], gap="medium")
    with tb_c1:
        st.markdown(
            f'<div style="display:flex;flex-direction:column;gap:4px;">'
            f'<span class="studio-title">✝️ DailyWisdom Sacred AI Studio</span>'
            f'<span style="font-size:13px;color:#CBD5E1;font-weight:600;">Active Workspace: <b style="color:#FFFFFF;">{ch_disp}</b></span>'
            f'</div>',
            unsafe_allow_html=True
        )
    with tb_c2:
        st.markdown(
            f'<div style="display:flex;gap:8px;align-items:center;justify-content:flex-end;flex-wrap:wrap;padding-top:6px;">'
            f'<span class="status-pill">📺 {ch_disp}</span>'
            f'<span class="status-pill">🎬 {len(all_videos)} Renders</span>'
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
        global_target_ch = st.selectbox("📺 Target Channel:", channel_names, index=0, key="top_target_ch")
        g_acc_choices = list(VOICE_CATALOG.keys())
        us_idx = next((i for i, k in enumerate(g_acc_choices) if "en-US" in k or "American" in k), 0)
        global_acc = st.selectbox("🇺🇸 Target Voice Accent:", g_acc_choices, index=us_idx, key="top_acc")
        g_v_list = VOICE_CATALOG[global_acc]
        g_v_names = [v["name"] for v in g_v_list]
        global_v_name = st.selectbox("🎙️ Voice:", g_v_names, index=0, key="top_voice")
        global_v_obj = g_v_list[g_v_names.index(global_v_name)]

    with top_c2:
        global_speed_pct = st.slider("⚡ Voice Speed (%):", min_value=-20, max_value=16, value=4, step=2, key="top_speed")
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
        is_no_music = (global_bgm_file == "NONE" or "No Music" in str(global_bgm_lbl))

        if not is_no_music:
            global_bgm_vol = st.slider("🔊 Music Volume:", min_value=0.05, max_value=0.45, value=0.18, step=0.01, key="top_bgm_vol")
            if st.checkbox("🎧 Preview BGM Audio", value=False, key="top_prev_bgm") and global_bgm_file and Path(str(global_bgm_file)).exists():
                st.audio(str(global_bgm_file), format="audio/mp3")
        else:
            global_bgm_vol = 0.0
            global_bgm_file = "NONE"
            st.info("🔇 Voice Only (Music Muted)")

    with top_c4:
        global_palette = st.selectbox("🎨 Thumbnail Palette:", ["Gold Classic", "Midnight Blue", "Sunrise", "Crimson Glory"], key="top_pal")
        if st.button(f"🎧 Audition Voice ({global_rate_str})", key="top_test_voice_btn", width="stretch"):
            with st.spinner("Generating sample..."):
                sample_txt = "If your heart feels heavy tonight... take a deep breath. Psalm 34, verse 18 declares: The Lord is near to the brokenhearted. In the mighty name of Jesus, break every chain of fear! Type Amen."
                mp3_test = backend.BASE_DIR / "assets" / "voice_previews" / "preacher_live_test.mp3"
                pae.synthesize_preacher_voiceover(sample_txt, mp3_test, voice_name=global_v_obj["voice"], base_rate=global_rate_str, base_pitch=global_v_obj.get("pitch", "+0Hz"))
                st.session_state["top_sample_mp3"] = str(mp3_test)
        if st.session_state.get("top_sample_mp3") and Path(st.session_state["top_sample_mp3"]).exists():
            st.caption("🎙️ Voice Audition:")
            st.audio(st.session_state["top_sample_mp3"], format="audio/mp3")

# === PREACHER STUDIO DECK START ===
with st.container(border=True):
    st.markdown("##### 🎙️ AI-Powered Preacher Emotion Director & Google Flow Music Studio")
    p_cfg = pae.load_preacher_config()

    pr_top1, pr_top2, pr_top3, pr_top4 = st.columns([1.4, 1.1, 1.1, 1.0], gap="medium")
    with pr_top1:
        p_mode = st.selectbox(
            "🔥 Preacher Delivery Mode:",
            pae.PREACHER_MODES,
            index=pae.PREACHER_MODES.index(p_cfg.get("mode", pae.PREACHER_MODES[0])) if p_cfg.get("mode") in pae.PREACHER_MODES else 0,
            key="deck_preacher_mode"
        )
    with pr_top2:
        p_auto_ai = st.checkbox("🤖 AI Auto-Direct Emotions on Render", value=p_cfg.get("auto_ai_direct", True), key="deck_auto_ai")
        p_sfx_on = st.checkbox("🔔 Enable Word-Triggered Sacred SFX", value=p_cfg.get("sfx_enabled", True), key="deck_sfx_on")
    with pr_top3:
        p_rev_on = st.checkbox("🏛️ Cathedral Sanctuary Reverb & EQ", value=p_cfg.get("reverb_enabled", True), key="deck_rev_on")
    with pr_top4:
        p_sfx_vol = st.slider("🔊 Sacred SFX Volume:", min_value=0.05, max_value=0.80, value=float(p_cfg.get("sfx_vol", 0.35)), step=0.02, key="deck_sfx_vol")

    with st.expander("🎛️ AI Preacher Emotion Director (Angry, Empathy, Whisper, Warfare) + 🎵 AI Flow Music Generator", expanded=True):
        tab_preach_dir, tab_flow_music = st.tabs([
            "🎭 1. AI Sentence Emotion, Pitch & SFX Director",
            "🎵 2. AI Flow Worship Music & Ambience Generator (Connected to API)"
        ])

        with tab_preach_dir:
            st.markdown("##### 🌟 ElevenLabs-Style AI Acting Voice & Natural-Language Feeling Command")
            el_c1, el_c2 = st.columns([1.15, 1.15], gap="medium")
            with el_c1:
                cur_eng = p_cfg.get("tts_engine", aete.ENGINE_CHOICES[0])
                sel_tts_eng = st.selectbox(
                    "🧠 Select Voice Synthesis Brain:",
                    aete.ENGINE_CHOICES,
                    index=aete.ENGINE_CHOICES.index(cur_eng) if cur_eng in aete.ENGINE_CHOICES else 0,
                    key="sel_tts_brain_engine"
                )
            with el_c2:
                cur_gv = p_cfg.get("gemini_acting_voice", list(aete.GEMINI_ACTING_VOICES.keys())[0])
                gv_keys = list(aete.GEMINI_ACTING_VOICES.keys())
                sel_gem_voice = st.selectbox(
                    "🎭 Select AI Emotional Acting Preacher Voice:",
                    gv_keys,
                    index=gv_keys.index(cur_gv) if cur_gv in gv_keys else 0,
                    key="sel_gem_acting_voice"
                )
            feel_prompt_in = st.text_input(
                "💬 Natural-Language Feeling / Acting Command (Tell the AI *how* to feel & preach — just like ElevenLabs v3!):",
                value=p_cfg.get("custom_feeling_prompt", "Start with deep tearful empathy and a soft sigh, build into fiery righteous preacher authority on power words, and finish with a warm, slow, comforting whisper on Amen."),
                key="in_custom_feeling_cmd"
            )
            st.divider()
            st.info("""💡 **AI-Powered or Manual Control:** Click **'🤖 AI Auto-Direct Emotions & SFX'** below and Gemini AI will automatically read your script and inject **`[angry]`**, **`[empathy]`**, **`[whisper]`**, **`[warfare]`**, **`[scripture]`**, **`[boom]`**, and **`*POWER WORDS*`** so the preacher sounds 100% human!""")

            pc1, pc2, pc3, pc4, pc5 = st.columns(5, gap="small")
            with pc1:
                st.markdown("**😡 1. Angry / Fierce**")
                st.caption("Tag: `[angry]`")
                ang_p = st.slider("Angry Pitch (Hz):", -10, 15, int(p_cfg.get("angry_pitch", 6)), key="sl_ang_p")
                ang_r = st.slider("Angry Speed (%):", -10, 25, int(p_cfg.get("angry_rate", 9)), key="sl_ang_r")
                ang_v = st.slider("Angry Volume (%):", 0, 30, int(p_cfg.get("angry_vol", 18)), key="sl_ang_v")
            with pc2:
                st.markdown("**🥺 2. Empathy / Sad**")
                st.caption("Tag: `[empathy]`")
                emp_p = st.slider("Empathy Pitch (Hz):", -14, 6, int(p_cfg.get("empathy_pitch", -5)), key="sl_emp_p")
                emp_r = st.slider("Empathy Speed (%):", -24, 10, int(p_cfg.get("empathy_rate", -10)), key="sl_emp_r")
                emp_v = st.slider("Empathy Volume (%):", -15, 15, int(p_cfg.get("empathy_vol", -4)), key="sl_emp_v")
            with pc3:
                st.markdown("**🤫 3. Soft Whisper**")
                st.caption("Tag: `[whisper]`")
                whi_p = st.slider("Whisper Pitch (Hz):", -14, 4, int(p_cfg.get("whisper_pitch", -7)), key="sl_whi_p")
                whi_r = st.slider("Whisper Speed (%):", -26, 5, int(p_cfg.get("whisper_rate", -14)), key="sl_whi_r")
                whi_v = st.slider("Whisper Volume (%):", -25, 5, int(p_cfg.get("whisper_vol", -12)), key="sl_whi_v")
            with pc4:
                st.markdown("**🔥 4. Warfare / Bold**")
                st.caption("Tag: `[warfare]`")
                war_p = st.slider("Warfare Pitch (Hz):", -8, 14, int(p_cfg.get("warfare_pitch", 4)), key="sl_war_p")
                war_r = st.slider("Warfare Speed (%):", -10, 20, int(p_cfg.get("warfare_rate", 5)), key="sl_war_r")
                war_v = st.slider("Warfare Volume (%):", 0, 25, int(p_cfg.get("warfare_vol", 12)), key="sl_war_v")
            with pc5:
                st.markdown("**📖 5. Scripture & Amen**")
                st.caption("Tag: `[scripture]` / `[amen]`")
                scr_p = st.slider("Scripture Pitch (Hz):", -12, 6, int(p_cfg.get("scripture_pitch", -2)), key="sl_scr_p")
                scr_r = st.slider("Scripture Speed (%):", -22, 10, int(p_cfg.get("scripture_rate", -5)), key="sl_scr_r")
                amn_p = st.slider("Amen Pitch (Hz):", -14, 6, int(p_cfg.get("amen_pitch", -5)), key="sl_amn_p")

            st.divider()
            sfx_files_map = pae.ensure_sacred_sfx_files()
            sc_sfx1, sc_sfx2, sc_sfx3, sc_sfx4 = st.columns(4, gap="small")
            with sc_sfx1:
                chk_shim = st.checkbox("✨ Scripture Shimmer Chime", value=p_cfg.get("sfx_shimmer", True), key="chk_sfx_shim")
                st.audio(str(sfx_files_map["shimmer"]), format="audio/mp3")
            with sc_sfx2:
                chk_swel = st.checkbox("🌊 Holy Sub-Bass Swell", value=p_cfg.get("sfx_swell", True), key="chk_sfx_swel")
                st.audio(str(sfx_files_map["swell"]), format="audio/mp3")
            with sc_sfx3:
                chk_boom = st.checkbox("⚡ Thunder / Warfare Boom", value=p_cfg.get("sfx_boom", True), key="chk_sfx_boom")
                st.audio(str(sfx_files_map["boom"]), format="audio/mp3")
            with sc_sfx4:
                chk_bell = st.checkbox("🔔 'Amen' Sanctuary Bell", value=p_cfg.get("sfx_bell", True), key="chk_sfx_bell")
                st.audio(str(sfx_files_map["bell"]), format="audio/mp3")

            st.divider()
            aud_c1, aud_c2 = st.columns([1.28, 1.72], gap="medium")
            with aud_c1:
                if "deck_test_script_in" not in st.session_state:
                    st.session_state["deck_test_script_in"] = (
                        "[empathy] If your heart feels broken and exhausted tonight... take a deep breath. "
                        "[angry] [boom] Enough is *ENOUGH*! The devil is a liar and he cannot have your family! "
                        "[scripture] [shimmer] Psalm 34, verse 18 declares: The Lord is near to the brokenhearted. "
                        "[warfare] [swell] In the mighty name of Jesus, break every chain of fear right now! "
                        "[amen] [bell] Rest in His peace, Amen."
                    )

                ai_b1, ai_b2 = st.columns(2)
                with ai_b1:
                    if st.button("🤖 AI Auto-Direct Emotions & SFX", key="btn_ai_direct_now", width="stretch"):
                        with st.spinner("Gemini AI analyzing sentence emotions, power words & SFX cues..."):
                            dir_txt, dir_note = pae.ai_direct_preacher_script(st.session_state["deck_test_script_in"])
                            st.session_state["deck_test_script_in"] = dir_txt
                            st.session_state["last_ai_dir_note"] = dir_note
                            st.rerun()
                with ai_b2:
                    if st.button("🔄 Sync Active Tab 1 Script Here", key="btn_sync_tab1_to_deck", width="stretch"):
                        if st.session_state.get("qs_spoken_script_area"):
                            dir_txt, dir_note = pae.ai_direct_preacher_script(st.session_state["qs_spoken_script_area"])
                            st.session_state["deck_test_script_in"] = dir_txt
                            st.session_state["qs_spoken_script_area"] = dir_txt
                            st.session_state["last_ai_dir_note"] = f"Synced & AI-Directed Tab 1 Script! ({dir_note})"
                            st.rerun()

                if st.session_state.get("last_ai_dir_note"):
                    st.success(st.session_state["last_ai_dir_note"])

                tag_cols = st.columns(6)
                for t_i, (btn_lbl, tag_code_str) in enumerate([
                    ("😡 [angry]", "[angry] "),
                    ("🥺 [empathy]", "[empathy] "),
                    ("🤫 [whisper]", "[whisper] "),
                    ("🔥 [warfare]", "[warfare] "),
                    ("📖 [scripture]", "[scripture] "),
                    ("⚡ [boom]", "[boom] ")
                ]):
                    with tag_cols[t_i]:
                        if st.button(btn_lbl, key=f"ins_tag_{t_i}", width="stretch"):
                            st.session_state["deck_test_script_in"] = tag_code_str + st.session_state["deck_test_script_in"]
                            st.rerun()

                test_preach_txt = st.text_area(
                    "🎙️ Preacher Script Playground (AI-Directed or Manual Tags):",
                    height=115,
                    key="deck_test_script_in"
                )

            with aud_c2:
                st.markdown("**🎬 Per-Sentence Emotion & SFX Override Table (Change Any Sentence Emotion Live!):**")
                raw_sents = pae.split_into_preacher_sentences(test_preach_txt)
                cur_overrides = p_cfg.get("sentence_overrides", {})
                ed_rows = []
                for s_idx, s_txt in enumerate(raw_sents):
                    _, p_auto, r_auto, _, emo_auto = pae.classify_sentence_prosody(s_txt, global_rate_str, global_v_obj.get("pitch", "+0Hz"), p_cfg, sent_idx=-1)
                    saved_ov = cur_overrides.get(str(s_idx), {})
                    ed_rows.append({
                        "ID": str(s_idx),
                        "Force Emotion": saved_ov.get("emotion", "🤖 Auto-Detect"),
                        "Force SFX": saved_ov.get("sfx", "Auto"),
                        "Active Feel": emo_auto,
                        "Sentence": pae.strip_emotion_tags(s_txt)
                    })

                edited_df = st.data_editor(
                    pd.DataFrame(ed_rows),
                    column_config={
                        "ID": st.column_config.TextColumn("#", disabled=True, width="small"),
                        "Force Emotion": st.column_config.SelectboxColumn("🎭 Emotion Override", options=pae.EMOTION_PRESETS, required=True, width="medium"),
                        "Force SFX": st.column_config.SelectboxColumn("🔔 SFX Override", options=pae.SFX_CHOICES, required=True, width="medium"),
                        "Active Feel": st.column_config.TextColumn("Detected", disabled=True, width="medium"),
                        "Sentence": st.column_config.TextColumn("Spoken Sentence", disabled=True, width="large"),
                    },
                    hide_index=True,
                    width="stretch",
                    key="preacher_sent_editor"
                )

                new_overrides = {}
                for _, row in edited_df.iterrows():
                    s_id = str(row["ID"])
                    if row["Force Emotion"] != "🤖 Auto-Detect" or row["Force SFX"] != "Auto":
                        new_overrides[s_id] = {"emotion": row["Force Emotion"], "sfx": row["Force SFX"]}

            updated_p_cfg = {
                "mode": p_mode,
                "auto_ai_direct": p_auto_ai,
                "sfx_enabled": p_sfx_on,
                "reverb_enabled": p_rev_on,
                "sfx_vol": p_sfx_vol,
                "angry_pitch": ang_p,
                "angry_rate": ang_r,
                "angry_vol": ang_v,
                "empathy_pitch": emp_p,
                "empathy_rate": emp_r,
                "empathy_vol": emp_v,
                "whisper_pitch": whi_p,
                "whisper_rate": whi_r,
                "whisper_vol": whi_v,
                "scripture_pitch": scr_p,
                "scripture_rate": scr_r,
                "warfare_pitch": war_p,
                "warfare_rate": war_r,
                "warfare_vol": war_v,
                "amen_pitch": amn_p,
                "sfx_shimmer": chk_shim,
                "sfx_swell": chk_swel,
                "sfx_boom": chk_boom,
                "sfx_bell": chk_bell,
                "sentence_overrides": new_overrides,
                "tts_engine": sel_tts_eng,
                "gemini_acting_voice": sel_gem_voice,
                "custom_feeling_prompt": feel_prompt_in
            }
            pae.save_preacher_config(updated_p_cfg)

            with aud_c1:
                p_btn1, p_btn2 = st.columns(2)
                with p_btn1:
                    if st.button("🧪 Load Extreme Contrast Test ([soft] ➔ [angry] ➔ [whisper])", key="btn_load_contrast_test", width="stretch"):
                        st.session_state["deck_test_script_in"] = (
                            "[soft] Listen closely, my friend... I know you are tired and carrying so much pain. "
                            "[angry] [boom] But *ENOUGH* is *ENOUGH*! Devil, take your hands off this family right *NOW*! "
                            "[scripture] [shimmer] Isaiah 54, verse 17 says: No weapon formed against you shall prosper. "
                            "[whisper] [swell] Close your eyes... Jesus is right here in your room. "
                            "[amen] [bell] Be healed and rest in peace, Amen."
                        )
                        st.rerun()

                    if st.button("🔥 Audition Preacher Voice + Verify Tags Now", key="btn_deck_audition", width="stretch"):
                        with st.spinner("Synthesizing Angry, Empathy & Warfare pitch shifts + Sacred SFX..."):
                            out_test_p = backend.BASE_DIR / "assets" / "voice_previews" / "deck_preacher_audition.mp3"
                            pae.synthesize_preacher_voiceover(
                                test_preach_txt,
                                out_test_p,
                                voice_name=global_v_obj["voice"],
                                base_rate=global_rate_str,
                                base_pitch=global_v_obj.get("pitch", "+0Hz")
                            )
                            st.session_state["deck_audition_mp3"] = str(out_test_p)
                with p_btn2:
                    if st.button("📲 Push Directed Script to Tab 1 Short", key="btn_push_dir_tab1", width="stretch"):
                        st.session_state["qs_spoken_script_area"] = test_preach_txt
                        st.toast("✅ Pushed AI-Directed Preacher Script into Tab 1!")
                if st.session_state.get("deck_audition_mp3") and Path(st.session_state["deck_audition_mp3"]).exists():
                    st.audio(st.session_state["deck_audition_mp3"], format="audio/mp3", autoplay=True)
                    ver_rows = pae.preview_script_preacher_breakdown(test_preach_txt, base_rate=global_rate_str, base_pitch=global_v_obj.get("pitch", "+0Hz"))
                    st.markdown("##### ✅ Live Tag & Pitch Verification Log (What Just Played):")
                    for vr_item in ver_rows:
                        st.caption(f"**Chunk {int(vr_item['ID'])+1}** | **{vr_item['Emotion']}** (`Pitch: {vr_item['Pitch']}`, `Speed: {vr_item['Speed']}`, `Vol: {vr_item['Vol']}`, `SFX: {vr_item['SFX']}`) ➔ *'{vr_item["Clean Sentence"]}'*")

        with tab_flow_music:
            st.markdown("#### 🎵 AI Flow Worship Music & Underscore Generator (Connected to Your API Key)")
            st.caption("Generate custom worship pads, spiritual warfare underscores, or 3 AM soaking music powered by Gemini / Google Flow AI and use them immediately as your video BGM!")
            fm_c1, fm_c2 = st.columns([1.3, 1.2], gap="large")
            with fm_c1:
                fm_preset = st.selectbox("🎼 Select Preaching Music Mood:", list(pae.FLOW_MUSIC_PRESETS.keys()), index=0, key="fm_preset_sel")
                fm_custom_p = st.text_input(
                    "✨ Custom AI Music Prompt (Optional — Gemini AI designs harmonic chords for your prompt):",
                    value="",
                    placeholder="e.g. Emotional tearful cello and warm church organ for breaking financial debt, 60 BPM",
                    key="fm_cust_prompt"
                )
                fm_dur = st.slider("⏱️ Track Length (Seconds):", min_value=30, max_value=180, value=90, step=15, key="fm_dur_sl")
                if st.button("🎵 Generate AI Flow Worship Track & Add to Studio BGM", key="btn_gen_flow_music", width="stretch"):
                    with st.spinner("Connecting to Gemini / Flow Music Architect & synthesizing stereo track..."):
                        ok_fm, out_fm_mp3, msg_fm = pae.generate_ai_flow_music_track(fm_preset, fm_custom_p, duration_sec=fm_dur)
                        if ok_fm:
                            st.cache_data.clear()
                            st.session_state["last_flow_music_mp3"] = str(out_fm_mp3)
                            st.session_state["last_flow_music_msg"] = msg_fm
                            st.rerun()
                        else:
                            st.error(msg_fm)
            with fm_c2:
                if st.session_state.get("last_flow_music_msg"):
                    st.success(st.session_state["last_flow_music_msg"])
                if st.session_state.get("last_flow_music_mp3") and Path(st.session_state["last_flow_music_mp3"]).exists():
                    fm_p = Path(st.session_state["last_flow_music_mp3"])
                    st.markdown(f"**🎧 Active AI Track:** `{fm_p.name}`")
                    st.audio(str(fm_p), format="audio/mp3", autoplay=True)
                    st.caption("💡 This track is now selectable at the top of your **'🎵 Worship BGM'** dropdown in the Master Strip above!")
# === PREACHER STUDIO DECK END ===

# ==============================================================================
# REUSABLE CUSTOM THUMBNAIL STUDIO WIDGET
# ==============================================================================
def render_multi_channel_publish_box(video_path: Path, chosen_cover: Path | None, key_prefix: str, live_desc_override: str | None = None):
    """Renders a live Multi-Channel Selector (Grace of the Lord, Iron & Faith, or BOTH Channels) + Publish Button."""
    live_channels_dict = backend.load_channels()
    live_ch_names = list(live_channels_dict.keys())

    m_meta = backend.load_clip_metadata(video_path)
    up_map = m_meta.get("uploaded_channels", {})
    if not isinstance(up_map, dict):
        up_map = {}

    if up_map:
        for ch_k, y_id in up_map.items():
            st.success(f"🟢 Live on **{ch_k}**: https://youtu.be/{y_id}")
    elif m_meta.get("youtube_id"):
        st.success(f"🟢 Live on YouTube: https://youtu.be/{m_meta['youtube_id']}")

    if len(live_ch_names) > 1:
        both_label = "🔥 BOTH Channels (" + " + ".join([c.split("(")[0].strip() for c in live_ch_names]) + ")"
        pub_opts = [both_label] + live_ch_names
    else:
        pub_opts = live_ch_names

    sel_pub_target = st.radio(
        "📺 Select Where to Publish This Video:",
        pub_opts,
        index=0,
        key=f"{key_prefix}_ch_target_radio"
    )

    if st.button(f"🚀 Publish Now to: {sel_pub_target}", key=f"{key_prefix}_multi_pub_btn", width="stretch"):
        if live_desc_override is not None:
            backend.save_clip_metadata(video_path, m_meta.get("title", ""), live_desc_override, m_meta.get("tags", []), topic=m_meta.get("topic", ""))
        with st.spinner(f"Publishing '{video_path.name}' to {sel_pub_target}..."):
            pub_res = backend.publish_video_to_selected_target(sel_pub_target, video_path, thumbnail_path=chosen_cover)
            if pub_res:
                st.cache_data.clear()
                for c_done, y_done in pub_res:
                    st.success(f"🎉 Published to **{c_done}**: https://youtu.be/{y_done}")
                time.sleep(0.8)
                st.rerun()
            else:
                st.error("❌ Upload failed or selected channel needs re-authentication. Click '➕ Add Channel' in Sidebar if token expired.")


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

    with st.expander("🎨 Custom Thumbnail Studio: Download Plain Image • Copy AI Prompt • Upload External", expanded=False):
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
_NAV_TABS = [
    "🎬 1. English Shorts",
    "🇮🇳 2. Hindi Shorts",
    "🕊️ 3. Long-Form Prayers",
    "🎥 4. 3-Min Story Movies",
    "📂 5. Master Video Vault",
    "🎙️ 6. Podcast Clipper",
    "🧠 7. Personal AI Analyzer",
    "🧪 8. AI Tester Lab",
]
active_nav_tab = st.radio("Studio Navigation:", _NAV_TABS, index=0, horizontal=True, label_visibility="collapsed", key="fast_nav_bar")

# ==============================================================================
# TAB 1: CONSOLIDATED & ORGANIZED ENGLISH SHORTS STUDIO
# ==============================================================================
if "1." in active_nav_tab:
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

                if st.button("🎙️ 1. AI Direct Pitch & SFX + Preview 3-Scene Preacher Audio First", key="gr_step1_audio_btn", width="stretch"):
                    if "active_grace_pkg" not in st.session_state:
                        st.warning("Please click '1. Write 3-Scene Script' above first!")
                    else:
                        with st.spinner("🤖 Gemini AI modulating word-by-word Pitch, Speed & Sacred SFX across all 3 scenes..."):
                            g_segs_now = st.session_state["active_grace_pkg"].get("spoken_script_segments", [])
                            full_3sc_txt = " ".join([s.get("spoken_text", "") for s in g_segs_now])
                            chosen_v_id = tone_info["voice"] if use_rec_tone else global_v_obj["voice"]
                            pre_v3 = backend.BASE_DIR / "assets" / "voice_previews" / "approved_3sc_voice.mp3"
                            pre_m3 = backend.BASE_DIR / "assets" / "voice_previews" / "approved_3sc_mix.mp3"
                            aud_3sc = pae.build_ai_directed_preacher_audio_preview(
                                full_3sc_txt,
                                out_voice_mp3=pre_v3,
                                out_mixed_preview_mp3=pre_m3,
                                voice_name=chosen_v_id,
                                base_rate=global_rate_str,
                                base_pitch=global_v_obj.get("pitch", "+0Hz"),
                                bgm_file=global_bgm_file,
                                bgm_vol=global_bgm_vol
                            )
                            st.session_state["approved_3sc_audio_pkg"] = aud_3sc

                if st.session_state.get("approved_3sc_audio_pkg"):
                    a3 = st.session_state["approved_3sc_audio_pkg"]
                    st.success(f"{a3['ai_note']} (Total Audio: **{a3['duration_sec']}s**)")
                    st.markdown("🎧 **Listen to Your 3-Scene AI-Directed Preacher Audio Before Rendering Video:**")
                    st.audio(a3["preview_mp3"], format="audio/mp3", autoplay=True)
                    with st.expander("🎛️ View AI Word/Phrase Pitch & SFX Cue Sheet", expanded=False):
                        st.dataframe(pd.DataFrame(a3["segments"]), hide_index=True, width="stretch")

                if st.button("🎬 2. RENDER 3-SCENE CINEMATIC VIDEO (Using Approved Preacher Audio)", key="gr_render_3sc_btn", width="stretch"):
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
                    if st.session_state.get("en_ai_last_t") != qs_topic or "en_ai_bundle" not in st.session_state:
                        st.session_state["en_ai_last_t"] = qs_topic
                        st.session_state["en_ai_bundle"] = ai_pick_relevant_verse_for_topic(qs_topic, lang="en")
                    if st.button("🎲 AI Pick Another Relevant Verse & Explanation for This Topic", key="en_reroll_v", width="stretch"):
                        with st.spinner(f"AI picking a fresh unused Bible verse for '{qs_topic}'..."):
                            st.session_state["en_ai_bundle"] = ai_pick_relevant_verse_for_topic(qs_topic, lang="en")
                    qs_ref = st.session_state["en_ai_bundle"]["verse_citation"]
                    qs_why_explain = st.session_state["en_ai_bundle"]["why_en"]
                elif "66-Book" in qs_mode:
                    b_labels = [f"{i+1:02d}. {b_en.strip()} — {b_hi}" for i, (b_en, b_hi, _) in enumerate(BIBLE_66_BOOKS)]
                    sel_b_str = st.selectbox("1. Book (All 66 Books):", b_labels, index=18, key="qs_bk")
                    b_idx = b_labels.index(sel_b_str)
                    qs_b, _, max_ch = BIBLE_66_BOOKS[b_idx]
                    qs_b = qs_b.strip()
                    bc1, bc2 = st.columns(2)
                    with bc1:
                        qs_c = st.selectbox("2. Chapter:", list(range(1, max_ch + 1)), index=0, key="qs_ch")
                    v_map = get_verses_for_chapter(qs_b, qs_c)
                    v_nums = list(v_map.keys()) if v_map else [1]
                    with bc2:
                        qs_v = st.selectbox("3. Verse:", v_nums, format_func=lambda vn: f"Verse {vn}: {v_map.get(vn, '')[:28]}...", key="qs_vs")
                    qs_ref = f"{qs_b} {qs_c}:{qs_v}"
                    qs_topic = qs_ref
                    qs_why_explain = f"Selected directly from {qs_ref} in the 66-Book Bible Library."
                else:
                    qs_topic = st.text_input("Describe Situation:", value="Breaking Financial Debt & Finding Peace", key="qs_cust_t")
                    if st.button("🎲 AI Find Best Verse & Explanation", key="en_cust_reroll", width="stretch") or "en_ai_bundle" not in st.session_state:
                        st.session_state["en_ai_bundle"] = ai_pick_relevant_verse_for_topic(qs_topic, lang="en")
                    qs_ref = st.session_state["en_ai_bundle"]["verse_citation"]
                    qs_why_explain = st.session_state["en_ai_bundle"]["why_en"]

                _, qs_v_txt, qs_v_hi, qs_v_rom = lookup_reference_bilingual(qs_ref)
                qs_ref_spoken = format_reference_for_speech(qs_ref, is_hindi_speech=False)

                st.markdown(
                    f'<div class="verse-card">'
                    f'<div class="verse-hdr">📖 {qs_ref} ({qs_ref_spoken})</div>'
                    f'<div class="verse-body">"{qs_v_txt}"</div>'
                    f'<div style="font-size:12.5px;color:#93C5FD;margin-top:6px;">💡 <b>Why AI Picked This Verse:</b> {qs_why_explain}</div>'
                    f'</div>',
                    unsafe_allow_html=True
                )
                if st.button("🔊 Listen to This English Verse", key="en_listen_v_btn", width="stretch"):
                    mp3_en = synthesize_bilingual_verse_preview(qs_ref, qs_v_txt, qs_v_hi, qs_v_rom, listen_mode="english")
                    st.audio(str(mp3_en), format="audio/mp3", autoplay=True)

                qs_opening = st.selectbox("🎯 Select Opening Hook (16 Options — Never Repetitive):", CLASSIC_OPENING_HOOKS, index=0, key="qs_opening_hook_sel")

                qs_sig = f"{qs_topic}_{qs_ref}_{qs_opening}_{qs_v_txt[:25]}"

                if st.session_state.get("qs_last_sig") != qs_sig or "qs_spoken_script_area" not in st.session_state:
                    st.session_state["qs_last_sig"] = qs_sig
                    synced_pkg = {
                        "title": f"God's Promise For {qs_topic[:28]} 🙏 ({qs_ref}) #shorts",
                        "description": f"🙏 Hold onto God's promise in {qs_ref}: \"{qs_v_txt}\"\n\nType AMEN if you receive this today!\n\n#ChristianShorts #DailyPrayer #BibleVerse #JesusChrist #FaithOverFear",
                        "tags": [qs_topic, f"{qs_topic} Prayer", qs_ref, "Daily Prayer", "Bible Verse", "Christian Shorts", "Jesus Christ"],
                        "hook": "GOD WILL PROVIDE",
                        "reflection": f"Hold fast to God's promise in {qs_ref}; His grace surrounds you right now.",
                        "prayer": f"Lord Jesus, release Your peace and breakthrough over {qs_topic} today, Amen.",
                        "thumbnail_prompt": f"Vertical 9:16 Christian devotional thumbnail for {qs_topic} ({qs_ref})"
                    }

                    # Strict viral budget: 38-42 words total = strictly 20-23 seconds!
                    v_words = qs_v_txt.strip().split()
                    core_v = (" ".join(v_words[:14]) + ".") if len(v_words) > 15 else qs_v_txt.strip()
                    if not core_v.endswith("."): core_v += "."

                    # Compact 1-sentence prayer under 8 words
                    short_pray = re.sub(r"^(Lord Jesus,|Lord,)\s*", "", synced_pkg.get("prayer", "Grant peace and breakthrough, Amen.")).strip()
                    pray_words = short_pray.split()
                    compact_p = " ".join(pray_words[:8]) if len(pray_words) > 8 else short_pray
                    if not compact_p.lower().endswith("amen.") and not compact_p.lower().endswith("amen"):
                        compact_p = compact_p.rstrip(". ") + ", Amen."

                    # Ultra-punchy 6-word hook
                    short_hook = qs_opening.split(",")[0].strip() if "," in qs_opening else qs_opening[:35]
                    if not short_hook.endswith("..."): short_hook += "..."

                    def_full_script = f"{short_hook} {qs_ref_spoken}: {core_v} Lord, {compact_p} Type AMEN to claim this!"
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
                # Real preacher speed calculation including prosody + pauses
                est_d = round((words_cnt / 1.95) + 1.8, 1)
                if est_d <= 25.0:
                    status_badge = f'<span style="color:#4ADE80;font-weight:800;">🟢 {est_d}s — Perfect Viral Sweet Spot (&lt;25s)</span>'
                elif est_d <= 30.0:
                    status_badge = f'<span style="color:#FACC15;font-weight:800;">🟡 {est_d}s — Good (Under 30s)</span>'
                else:
                    status_badge = f'<span style="color:#F87171;font-weight:800;">🔴 {est_d}s — TOO LONG (&gt;30s)! Trim to under 42 words!</span>'
                st.markdown(
                    f'<div class="budget-badge">⏱️ Spoken Words: <b>{words_cnt}</b> &nbsp;|&nbsp; Estimated Duration: {status_badge}</div>',
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
                intro_files = get_media_files(str(backend.INTRO_DIR), (".mp4", ".mov", ".webm", ".mkv"))
                bg_files = get_media_files(str(backend.BG_DIR), (".jpg", ".jpeg", ".png", ".webp"))

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

                st.markdown("##### 🎙️ Step 2A: AI Direct Words, Pitch & SFX ➔ Listen to Final Preacher Audio First")
                pa_col1, pa_col2 = st.columns([1.25, 1.0])
                with pa_col1:
                    if st.button("🎙️ 1. AI Direct Pitch & SFX + Generate Preacher Audio Preview", key="qs_step1_audio_btn", width="stretch"):
                        with st.spinner("🤖 Gemini AI directing word-by-word Pitch, Speed & Sacred SFX and mastering audio..."):
                            pre_voice_mp3 = backend.BASE_DIR / "assets" / "voice_previews" / "approved_short_voice.mp3"
                            pre_mix_mp3 = backend.BASE_DIR / "assets" / "voice_previews" / "approved_short_full_mix.mp3"
                            aud_pkg = pae.build_ai_directed_preacher_audio_preview(
                                qs_spoken_script.strip(),
                                out_voice_mp3=pre_voice_mp3,
                                out_mixed_preview_mp3=pre_mix_mp3,
                                voice_name=global_v_obj["voice"],
                                base_rate=global_rate_str,
                                base_pitch=global_v_obj.get("pitch", "+0Hz"),
                                bgm_file=global_bgm_file,
                                bgm_vol=global_bgm_vol
                            )
                            st.session_state["approved_qs_audio_pkg"] = aud_pkg
                            st.session_state["approved_qs_script_sig"] = qs_spoken_script.strip()

                if st.session_state.get("approved_qs_audio_pkg"):
                    apkg = st.session_state["approved_qs_audio_pkg"]
                    st.success(f"{apkg['ai_note']} (Total Audio Duration: **{apkg['duration_sec']}s**)")
                    st.markdown("🎧 **Listen to Your AI-Directed Preacher Audio (Voice + Pitch Shifts + SFX + BGM) Before Rendering Video:**")
                    st.audio(apkg["preview_mp3"], format="audio/mp3", autoplay=True)

                    with st.expander("🎛️ View / Tweak AI Phrase-by-Phrase Pitch, Speed & SFX Cue Sheet (Optional)", expanded=False):
                        ed_seg_df = st.data_editor(
                            pd.DataFrame(apkg["segments"]),
                            column_config={
                                "idx": st.column_config.NumberColumn("#", disabled=True, width="small"),
                                "emotion": st.column_config.TextColumn("AI Emotion", width="medium"),
                                "pitch": st.column_config.TextColumn("Pitch (e.g. +5Hz, -5Hz)", width="small"),
                                "rate": st.column_config.TextColumn("Speed (e.g. +8%, -10%)", width="small"),
                                "volume": st.column_config.TextColumn("Vol (e.g. +15%)", width="small"),
                                "pause": st.column_config.NumberColumn("Pause (s)", min_value=0.05, max_value=1.2, step=0.05, width="small"),
                                "sfx": st.column_config.SelectboxColumn("SFX Trigger", options=["none", "boom", "shimmer", "swell", "bell"], width="small"),
                                "text": st.column_config.TextColumn("Spoken Words", width="large"),
                            },
                            hide_index=True,
                            width="stretch",
                            key="qs_word_cue_editor"
                        )
                        if st.button("🔄 Re-Synthesize Preacher Audio With My Table Edits Above", key="qs_rebuild_edited_audio", width="stretch"):
                            with st.spinner("Re-synthesizing with your custom phrase pitch & SFX edits..."):
                                pre_voice_mp3 = backend.BASE_DIR / "assets" / "voice_previews" / "approved_short_voice.mp3"
                                pre_mix_mp3 = backend.BASE_DIR / "assets" / "voice_previews" / "approved_short_full_mix.mp3"
                                aud_pkg = pae.build_ai_directed_preacher_audio_preview(
                                    qs_spoken_script.strip(),
                                    out_voice_mp3=pre_voice_mp3,
                                    out_mixed_preview_mp3=pre_mix_mp3,
                                    voice_name=global_v_obj["voice"],
                                    base_rate=global_rate_str,
                                    base_pitch=global_v_obj.get("pitch", "+0Hz"),
                                    bgm_file=global_bgm_file,
                                    bgm_vol=global_bgm_vol,
                                    custom_segments=ed_seg_df.to_dict("records")
                                )
                                st.session_state["approved_qs_audio_pkg"] = aud_pkg
                                st.rerun()

                st.markdown("##### 🎬 Step 2B: Happy With the Audio? Click Below to Render the Video")
                if st.button(f"🎬 2. RENDER VIDEO USING APPROVED PREACHER AUDIO ({qs_ref})", key="qs_gen_btn", width="stretch"):
                    qs_loader = LiveTaskLoader("Rendering Video from Approved Preacher Audio")
                    active_maker_voice = dict(global_v_obj, rate=global_rate_str, accent=global_acc, script_mode=SCRIPT_MODES[0])
                    save_active_voice(active_maker_voice)

                    script_obj = backend.BibleShortScript(
                        topic=qs_topic, title=st.session_state.get("qs_synced_title_in", f"God's Promise in {qs_ref} #shorts"),
                        verse_citation=qs_ref, verse_text=qs_v_txt,
                        meaning="Trust God's unshakeable provision today.", prayer="Lord Jesus, release Your breakthrough, Amen.",
                        thumbnail_hook=st.session_state.get("qs_synced_hook", "GOD WILL PROVIDE"),
                        hashtags=["#DailyPrayer", "#BibleVerse", "#Shorts"]
                    )

                    temp_voice = backend.BASE_DIR / "temp_voice.mp3"
                    temp_json = backend.BASE_DIR / "temp_voice.json"
                    apkg = st.session_state.get("approved_qs_audio_pkg")
                    if apkg and Path(apkg["voice_mp3"]).exists() and st.session_state.get("approved_qs_script_sig") == qs_spoken_script.strip():
                        qs_loader.update(40, "🎙️ Using your pre-approved AI Preacher Audio & SFX track...")
                        shutil.copy(apkg["voice_mp3"], temp_voice)
                        if Path(apkg["timings_json"]).exists():
                            shutil.copy(apkg["timings_json"], temp_json)
                    else:
                        qs_loader.update(30, "🎙️ AI directing word-by-word Pitch & SFX and synthesizing voiceover...")
                        pre_voice_mp3 = backend.BASE_DIR / "assets" / "voice_previews" / "approved_short_voice.mp3"
                        pre_mix_mp3 = backend.BASE_DIR / "assets" / "voice_previews" / "approved_short_full_mix.mp3"
                        apkg = pae.build_ai_directed_preacher_audio_preview(
                            qs_spoken_script.strip(),
                            out_voice_mp3=pre_voice_mp3,
                            out_mixed_preview_mp3=pre_mix_mp3,
                            voice_name=global_v_obj["voice"],
                            base_rate=global_rate_str,
                            base_pitch=global_v_obj.get("pitch", "+0Hz"),
                            bgm_file=global_bgm_file,
                            bgm_vol=global_bgm_vol
                        )
                        st.session_state["approved_qs_audio_pkg"] = apkg
                        st.session_state["approved_qs_script_sig"] = qs_spoken_script.strip()
                        shutil.copy(apkg["voice_mp3"], temp_voice)
                        if Path(apkg["timings_json"]).exists():
                            shutil.copy(apkg["timings_json"], temp_json)

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
                        st.cache_data.clear()
                        final_t = st.session_state.get("qs_synced_title_in") or f"God's Promise in {qs_ref} 🙏 #shorts"
                        final_d = st.session_state.get("qs_synced_desc_in") or f"📖 {qs_ref}: \"{qs_v_txt}\"\n\nType AMEN below! #Shorts #DailyPrayer #BibleVerse"
                        final_tags_str = st.session_state.get("qs_synced_tags_in") or f"{qs_topic}, {qs_ref}, Daily Prayer, Bible Verse, Christian Shorts"
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

                chosen_cover = render_custom_thumbnail_manager(mvp, f"pub_{mvp.parent.name}")

                st.markdown(f"**🏆 Publish Title:** `{m_meta['title']}`")
                with st.expander("📝 View Description & Backend Tags", expanded=False):
                    st.text_area("Description:", value=m_meta["description"], height=120, key=f"mon_d_{mvp.parent.name}")
                    st.code(", ".join(m_meta.get("tags", [])), language="text")

                live_ed_d = st.session_state.get(f"mon_d_{mvp.parent.name}", m_meta.get("description", ""))
                render_multi_channel_publish_box(mvp, chosen_cover, f"tab1_{mvp.parent.name}", live_desc_override=live_ed_d)
# ==============================================================================
# TAB 2: HINDI SHORTS
# ==============================================================================
elif "2." in active_nav_tab:
    st.markdown("### 🇮🇳 Hindi Shorts Maker (पवित्र बाइबिल)")
    hi_c1, hi_c2 = st.columns([1.18, 1.0], gap="large")
    with hi_c1:
        with st.container(border=True):
            hi_voices = VOICE_CATALOG["🇮🇳 Hindi / Indian Accent (hi-IN)"]
            hi_v_names = [v["name"] for v in hi_voices]
            hi_sel_v_name = st.selectbox("🎙️ हिंदी आवाज़ चुनें (Select Hindi Narrator Voice):", hi_v_names, index=0, key="hi_voice_sel")
            hi_sel_v_obj = hi_voices[hi_v_names.index(hi_sel_v_name)]

            hi_pick_mode = st.radio("चयन विधि (Choose Verse By):", ["🎲 50 प्रार्थना विषय (AI Random Verse + अर्थ)", "📖 सम्पूर्ण बाइबिल (66 पुस्तकें ➔ अध्याय ➔ वचन)"], horizontal=True, key="hi_pick_mode")

            if "50" in hi_pick_mode:
                hi_t_labels = [f"{item['id']}. {item['topic']}" for item in TOP_50_PRAYER_TOPICS]
                hi_chosen_lbl = st.selectbox("विषय चुनें (Select Topic):", hi_t_labels, key="hi_t_dd")
                hi_t_name = TOP_50_PRAYER_TOPICS[hi_t_labels.index(hi_chosen_lbl)]["topic"]
                if st.session_state.get("hi_ai_last_t") != hi_t_name or "hi_ai_bundle" not in st.session_state:
                    st.session_state["hi_ai_last_t"] = hi_t_name
                    st.session_state["hi_ai_bundle"] = ai_pick_relevant_verse_for_topic(hi_t_name, lang="hi", use_ai_network=False)
                if st.button("🎲 इस विषय के लिए नया बाइबिल वचन और अर्थ चुनें (AI Pick Another Verse)", key="hi_reroll_v", width="stretch"):
                    with st.spinner("AI नया पवित्र वचन और अर्थ चुन रहा है..."):
                        st.session_state["hi_ai_bundle"] = ai_pick_relevant_verse_for_topic(hi_t_name, lang="hi", use_ai_network=True)
                hi_ref = st.session_state["hi_ai_bundle"]["verse_citation"]
                hi_why_explain = st.session_state["hi_ai_bundle"]["why_hi"]
            else:
                hb_labels = [f"{i+1:02d}. {b_hi} — {b_en.strip()}" for i, (b_en, b_hi, _) in enumerate(BIBLE_66_BOOKS)]
                hsel_b = st.selectbox("1. पुस्तक चुनें (66 Books):", hb_labels, index=18, key="hi_bk")
                hb_idx = hb_labels.index(hsel_b)
                h_book_en, _, h_max_ch = BIBLE_66_BOOKS[hb_idx]
                h_book_en = h_book_en.strip()
                hc1, hc2 = st.columns(2)
                with hc1:
                    h_ch = st.selectbox("2. अध्याय (Chapter):", list(range(1, h_max_ch + 1)), index=0, key="hi_ch")
                hv_map = get_verses_for_chapter(h_book_en, h_ch)
                hv_nums = list(hv_map.keys()) if hv_map else [1]
                with hc2:
                    h_vs = st.selectbox("3. वचन (Verse):", hv_nums, key="hi_vs")
                hi_ref = f"{h_book_en} {h_ch}:{h_vs}"
                hi_t_name = hi_ref
                hi_why_explain = "पवित्र बाइबिल से चुना गया वचन।"

            _, hi_en_txt, hi_verse_txt, hi_rom_txt = lookup_reference_bilingual(hi_ref)
            hi_ref_spoken = format_reference_for_speech(hi_ref, is_hindi_speech=True)

            st.markdown(
                f'<div class="verse-card">'
                f'<div class="verse-hdr">📖 {hi_ref_spoken} ({hi_ref})</div>'
                f'<div class="verse-body" style="color:#FDE047;font-size:16px;">"{hi_verse_txt}"</div>'
                f'<div style="font-size:12.5px;color:#CBD5E1;margin-top:6px;">🇬🇧 <i>"{hi_en_txt}"</i></div>'
                f'<div style="font-size:12.5px;color:#93C5FD;margin-top:6px;">💡 <b>वचन का महत्व (AI Explanation):</b> {hi_why_explain}</div>'
                f'</div>',
                unsafe_allow_html=True
            )
            hb_l1, hb_l2 = st.columns(2)
            with hb_l1:
                if st.button("🔊 हिन्दी में वचन सुनें (Hear in Hindi)", key="hi_listen_btn", width="stretch"):
                    save_active_voice(dict(hi_sel_v_obj, rate=global_rate_str, accent="🇮🇳 Hindi / Indian Accent (hi-IN)", script_mode=SCRIPT_MODES[1]))
                    mp3_hi = synthesize_bilingual_verse_preview(hi_ref, hi_en_txt, hi_verse_txt, hi_rom_txt, listen_mode="hindi")
                    st.audio(str(mp3_hi), format="audio/mp3", autoplay=True)
            with hb_l2:
                if st.button("🌍 दोनों भाषाओं में सुनें (Hear English + Hindi)", key="hi_listen_both_btn", width="stretch"):
                    mp3_b = synthesize_bilingual_verse_preview(hi_ref, hi_en_txt, hi_verse_txt, hi_rom_txt, listen_mode="both")
                    st.audio(str(mp3_b), format="audio/mp3", autoplay=True)

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
                save_active_voice(dict(hi_sel_v_obj, rate=global_rate_str, accent="🇮🇳 Hindi / Indian Accent (hi-IN)", script_mode=SCRIPT_MODES[1]))
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
                render_multi_channel_publish_box(h_vp, h_cov, f"tab2_hi_{h_vp.parent.name}")
# ==============================================================================
# TAB 3: LONG-FORM PRAYER SANCTUARY (5M - 1 HOUR) — 5-CHAPTER STRICT JSON ENGINE
# ==============================================================================
elif "3." in active_nav_tab:
    st.markdown("### 🕊️ Long-Form Soaking Prayer Sanctuary (15 Min • 30 Min • 5m–1Hr Multi-Chapter Pastoral Engine)")
    lf_left, lf_right = st.columns([1.22, 1.0], gap="large")

    with lf_left:
        with st.container(border=True):
            st.markdown("#### 🙏 Step 1: Select Content Format & Details")
            lf_mode = st.radio(
                "🎬 Content Format:",
                ["🕊️ 5-Chapter Pastoral Soaking Prayer", "📖 Full Bible Chapter Reading"],
                horizontal=True,
                key="lf_mode_rad"
            )

            lf_c1, lf_c2, lf_c3 = st.columns([1.2, 1.1, 1.0])
            with lf_c1:
                if "Soaking" in lf_mode:
                    lf_dur = st.selectbox("⏱️ Video Length:", list(lpe.DURATION_CONFIGS.keys()), index=0, key="lf_dur_sel")
                else:
                    st.info("⏱️ Auto-Calculated Duration")
                    lf_dur = "Auto"
            with lf_c2:
                lf_nature = st.selectbox("🌧️ Nature Ambience:", ["Gentle Night Rain", "Mountain Stream", "None (Pure Music)"], index=0, key="lf_nat_sel")
            with lf_c3:
                lf_lang_mode = st.selectbox("🌐 Language:", ["🇬🇧 English", "🇮🇳 Hindi"], index=0, key="lf_lang_sel")

            if "Soaking" in lf_mode:
                lf_t_labels = ["✍️ Custom Topic (Type Below)"] + [f"{item['id']}. {item['topic']}" for item in TOP_50_PRAYER_TOPICS]
                lf_chosen_lbl = st.selectbox("Select Prayer Topic (or Type Custom Below):", lf_t_labels, index=1, key="lf_topic_dd")
                if lf_chosen_lbl == "✍️ Custom Topic (Type Below)":
                    lf_topic = st.text_input("Enter Custom Soaking Prayer Topic:", value="Complete Financial Restoration & Deep Midnight Peace", key="lf_cust_topic_in")
                else:
                    lf_topic = TOP_50_PRAYER_TOPICS[lf_t_labels.index(lf_chosen_lbl) - 1]["topic"]
                exact_book, exact_ch = None, None
            else:
                b_labels = [f"{i+1:02d}. {b_en.strip()} — {b_hi}" for i, (b_en, b_hi, _) in enumerate(BIBLE_66_BOOKS)]
                lf_b_lbl = st.selectbox("1. Select Book:", b_labels, index=18, key="lf_bk_dd")
                b_idx = b_labels.index(lf_b_lbl)
                exact_book, _, max_chapters = BIBLE_66_BOOKS[b_idx]
                exact_book = exact_book.strip()
                exact_ch = st.selectbox("2. Select Chapter:", list(range(1, max_chapters + 1)), index=0, key="lf_ch_dd")
                lf_topic = f"{exact_book} {exact_ch}"

            btn_lbl = "📜 1. Generate Soaking Prayer Script" if "Soaking" in lf_mode else f"📖 1. Prepare '{exact_book} {exact_ch}' Reading Script"
            if st.button(btn_lbl, key="lf_gen_script_btn", width="stretch"):
                with st.spinner(f"Preparing script for '{lf_topic}'..."):
                    lang_c = "hi" if "Hindi" in lf_lang_mode else "en"
                    if "Soaking" in lf_mode:
                        st.session_state["lf_active_journey"] = lpe.generate_soul_prayer_journey(lf_topic, lf_dur, lang=lang_c)
                    else:
                        st.session_state["lf_active_journey"] = lpe.generate_full_chapter_reading_journey(exact_book, exact_ch, lang=lang_c)

            if "lf_active_journey" not in st.session_state:
                st.info("💡 Click **'1. Generate 5-Chapter Pastoral Soaking Prayer'** above to generate the 5 chapters, title, pinned comment, and SEO tags.")
                lf_journey = None
            else:
                lf_journey = st.session_state["lf_active_journey"]
                vers_list_str = ", ".join([v["ref"] for v in lf_journey["scriptures"]])
                st.markdown(
                    f'<div class="verse-card">'
                    f'<div class="verse-hdr">📖 Scriptures Woven Into This 5-Chapter Journey:</div>'
                    f'<div class="verse-body">{vers_list_str}</div>'
                    f'</div>',
                    unsafe_allow_html=True
                )

                lf_journey["youtube_title"] = st.text_input("🏆 YouTube Long-Form Title:", value=lf_journey.get("youtube_title", ""), key="lf_title_ed")
                lf_journey["pinned_comment"] = st.text_input("📌 Pinned Community Comment:", value=lf_journey.get("pinned_comment", ""), key="lf_pin_ed")
                lf_journey["youtube_tags"] = st.text_input("🏷️ 15 SEO Keywords / Tags:", value=lf_journey.get("youtube_tags", ""), key="lf_tags_ed")

                st.markdown("##### 🎙️ Step 1B: AI Preacher Tone, Pitch & Sacred SFX Director for All 5 Chapters")
                lf_d1, lf_d2 = st.columns([1.3, 1.0])
                with lf_d1:
                    if st.button("🤖 AI Auto-Direct Tone, Pitch & Sacred SFX Across All 5 Chapters", key="lf_ai_direct_5ch_btn", width="stretch"):
                        with st.spinner("🤖 Gemini AI directing Empathy, Scripture, Angry/Warfare Rebuke, Blessing & Amen SFX across all 5 chapters..."):
                            lf_journey, ch_cues = lpe.ai_direct_longform_5chapters(lf_journey)
                            st.session_state["lf_active_journey"] = lf_journey
                            st.session_state["lf_ch_cue_summary"] = ch_cues
                            for stg_u in lf_journey["stages"]:
                                st.session_state[f"lf_stg_edit_{stg_u['stage_num']}"] = stg_u["full_text"]
                            st.rerun()
                with lf_d2:
                    st.caption("💡 Automatically shifts from **🥺 Empathy (Ch 1)** ➔ **📖 Scripture Shimmer (Ch 2)** ➔ **😡🔥 Fierce Warfare Boom (Ch 3)** ➔ **✨ Blessing (Ch 4)** ➔ **🙏 Amen Bell (Ch 5)**!")

                if st.session_state.get("lf_ch_cue_summary"):
                    with st.expander("📊 View 5-Chapter AI Tone, Pitch & Sacred SFX Map", expanded=True):
                        st.dataframe(pd.DataFrame(st.session_state["lf_ch_cue_summary"]), hide_index=True, width="stretch")

                with st.expander("📖 View / Edit All 5 Chapters (Supports [empathy], [angry], [warfare], [whisper], [boom], [shimmer], [swell], [bell] & *WORD*)", expanded=True):
                    for idx_c, stg in enumerate(lf_journey["stages"]):
                        st.markdown(f"**Chapter {stg['stage_num']}: {stg['chapter_title']}**")
                        edited_stg = st.text_area(
                            f"Spoken Script (Chapter {stg['stage_num']}):",
                            value=stg["full_text"],
                            height=105,
                            key=f"lf_stg_edit_{stg['stage_num']}"
                        )
                        stg["full_text"] = edited_stg.strip()
                        stg["spoken_script"] = edited_stg.strip()
                        stg["paragraphs"] = [p.strip() for p in re.split(r"\n\s*\n", edited_stg) if p.strip()]
                        if idx_c < len(lf_journey.get("chapters", [])):
                            lf_journey["chapters"][idx_c]["spoken_script"] = edited_stg.strip()

                with st.expander("🧾 View / Copy Strict JSON Output", expanded=False):
                    lf_journey["strict_json"]["youtube_title"] = lf_journey["youtube_title"]
                    lf_journey["strict_json"]["pinned_comment"] = lf_journey["pinned_comment"]
                    lf_journey["strict_json"]["youtube_tags"] = lf_journey["youtube_tags"]
                    st.code(json.dumps(lf_journey["strict_json"], indent=2, ensure_ascii=False), language="json")

                st.markdown("##### 🎨 Step 1C: 16:9 Visuals & Synced On-Screen Subtitle Font Designer")
                v_col1, v_col2 = st.columns(2)
                intro_vids = get_media_files(str(backend.INTRO_DIR), (".mp4", ".mov", ".webm", ".mkv"))
                bg_imgs = get_media_files(str(backend.BG_DIR), (".jpg", ".jpeg", ".png", ".webp"))
                with v_col1:
                    lf_sub_mode = st.selectbox(
                        "📝 On-Screen Subtitles Mode:",
                        [
                            "⚡ Fast Burned-In Subtitles (100% Synced On-Screen Like Shorts — Recommended!)",
                            "⚡ Instant 3-Second Render (No On-Screen Text — YouTube CC .SRT Only)"
                        ],
                        index=0,
                        key="lf_sub_mode_sel"
                    )
                    lf_vis_mode = st.selectbox("🎬 16:9 Style:", ["Cinematic Ken Burns Wallpaper (Fastest Burned-In Subs)", "Looping Video Background"], index=0, key="lf_vis_mode")
                    lf_pick_vid = st.selectbox("🎬 Video:", ["Auto / Newest"] + [f.name for f in intro_vids], key="lf_vid_dd")
                with v_col2:
                    lf_pick_img = st.selectbox("🖼️ Wallpaper:", ["Auto / Newest"] + [f.name for f in bg_imgs], key="lf_img_dd")
                    lf_sub_font = st.selectbox("🔤 Subtitle Font:", list(lpe.LONGFORM_FONT_OPTIONS.keys()), index=0, key="lf_sub_font_sel")
                    lf_sub_color = st.selectbox("🎨 Subtitle Color & Style:", list(lpe.LONGFORM_COLOR_THEMES.keys()), index=0, key="lf_sub_col_sel")

                sub_c1, sub_c2, sub_c3 = st.columns(3)
                with sub_c1:
                    lf_sub_size = st.slider("📏 Font Size (px):", min_value=48, max_value=130, value=98, step=2, key="lf_sub_sz_sl")
                with sub_c2:
                    lf_sub_pos = st.selectbox("📍 Subtitle Screen Position:", list(lpe.LONGFORM_POSITIONS.keys()), index=0, key="lf_sub_pos_sel")
                with sub_c3:
                    lf_sub_words = st.slider("⏱️ Words Per Subtitle Card:", min_value=2, max_value=8, value=4, step=1, key="lf_sub_w_sl")

                st.markdown("##### 🎙️ Step 2A: Generate & Listen to AI-Directed Long-Form Preacher Audio + SFX First")
                lf_aud_c1, lf_aud_c2 = st.columns([1.2, 1.0])
                with lf_aud_c1:
                    if st.button("🎧 1. Generate & Audition 60s Multi-Emotion Highlight (Fast Test)", key="lf_fast_aud_btn", width="stretch"):
                        with st.spinner("Synthesizing 60s Preacher Highlight (Empathy ➔ Warfare Boom ➔ Amen Bell) with SFX & BGM..."):
                            # Take 1 sentence from Ch1 (Empathy), Ch2 (Scripture), Ch3 (Angry/Warfare), and Ch5 (Amen)
                            s_ch1 = lf_journey["stages"][0]["paragraphs"][0].split(".")[0] + "."
                            s_ch2 = lf_journey["stages"][min(1, len(lf_journey["stages"])-1)]["paragraphs"][0].split(".")[0] + "."
                            s_ch3 = lf_journey["stages"][min(2, len(lf_journey["stages"])-1)]["paragraphs"][0].split(".")[0] + "!"
                            s_ch5 = lf_journey["stages"][-1]["paragraphs"][-1].split(".")[-2] + ". In Jesus' name, Amen." if "." in lf_journey["stages"][-1]["paragraphs"][-1] else "In Jesus' name, Amen."
                            sample_5ch = f"[empathy] [swell] {pae.strip_emotion_tags(s_ch1)} [scripture] [shimmer] {pae.strip_emotion_tags(s_ch2)} [angry] [boom] {pae.strip_emotion_tags(s_ch3)} [amen] [bell] {pae.strip_emotion_tags(s_ch5)}"
                            use_v_name = "hi-IN-MadhurNeural" if "Hindi" in lf_lang_mode else global_v_obj["voice"]
                            hl_v = backend.BASE_DIR / "assets" / "voice_previews" / "lf_highlight_voice.mp3"
                            hl_m = backend.BASE_DIR / "assets" / "voice_previews" / "lf_highlight_mix.mp3"
                            hl_pkg = pae.build_ai_directed_preacher_audio_preview(
                                sample_5ch,
                                out_voice_mp3=hl_v,
                                out_mixed_preview_mp3=hl_m,
                                voice_name=use_v_name,
                                base_rate=global_rate_str,
                                base_pitch=global_v_obj.get("pitch", "-2Hz"),
                                bgm_file=global_bgm_file,
                                bgm_vol=global_bgm_vol
                            )
                            st.session_state["lf_highlight_pkg"] = hl_pkg

                with lf_aud_c2:
                    if st.button(f"🎙️ 2. Pre-Master Full {lf_dur} Audio (Voice + SFX + BGM + {lf_nature})", key="lf_full_aud_btn", width="stretch"):
                        lf_aud_loader = LiveTaskLoader(f"Mastering Full {lf_dur} Preacher Audio & SFX")
                        # Auto-direct chapters if not already tagged
                        if not st.session_state.get("lf_ch_cue_summary"):
                            lf_aud_loader.update(15, "🤖 AI directing 5-Chapter Preacher Tone, Pitch & Sacred SFX...")
                            lf_journey, ch_cues = lpe.ai_direct_longform_5chapters(lf_journey)
                            st.session_state["lf_active_journey"] = lf_journey
                            st.session_state["lf_ch_cue_summary"] = ch_cues

                        out_folder = lpe.get_next_longform_folder(f"{lf_dur}_{lf_topic}")
                        voice_raw_mp3 = out_folder / "meditative_voice.mp3"
                        master_mix_mp3 = out_folder / "master_soaking_audio.mp3"

                        lf_aud_loader.update(40, "🎙️ Synthesizing 5-Chapter Dynamic Preacher Voice + Sacred SFX...")
                        use_v_name = "hi-IN-MadhurNeural" if "Hindi" in lf_lang_mode else global_v_obj["voice"]
                        v_res = lpe.synthesize_meditative_voiceover(lf_journey, voice_raw_mp3, voice_name=use_v_name, rate_str=global_rate_str, pitch_str=global_v_obj.get("pitch", "-2Hz"))

                        lf_aud_loader.update(80, f"🎵 Mixing {lf_dur} Master Audio with Worship Pad & {lf_nature}...")
                        lpe.mix_longform_master_audio(voice_raw_mp3, master_mix_mp3, target_duration_sec=lf_journey["config"]["target_seconds"], bgm_file=global_bgm_file, bgm_volume=global_bgm_vol, nature_style=lf_nature)

                        st.session_state["lf_preapproved_audio"] = {
                            "folder": str(out_folder),
                            "voice_mp3": str(voice_raw_mp3),
                            "master_mp3": str(master_mix_mp3),
                            "v_res": v_res,
                            "topic": lf_topic,
                            "dur_label": lf_dur
                        }
                        lf_aud_loader.complete(f"🎧 Full {lf_dur} Master Preacher Audio Ready! Listen below before rendering video.")

                if st.session_state.get("lf_highlight_pkg"):
                    hl = st.session_state["lf_highlight_pkg"]
                    st.info(f"🎧 **60s Multi-Emotion Highlight Preview ({hl['duration_sec']}s):** {hl['ai_note']}")
                    st.audio(hl["preview_mp3"], format="audio/mp3", autoplay=True)
                    with st.expander("🎛️ View Highlight Phrase-by-Phrase Pitch & SFX Cue Sheet", expanded=False):
                        st.dataframe(pd.DataFrame(hl["segments"]), hide_index=True, width="stretch")

                if st.session_state.get("lf_preapproved_audio"):
                    pa_lf = st.session_state["lf_preapproved_audio"]
                    if Path(pa_lf["master_mp3"]).exists():
                        st.success(f"✅ **Approved Full Master Audio Ready (`{Path(pa_lf['folder']).name}`):** Listen below, then click Render Video!")
                        st.audio(pa_lf["master_mp3"], format="audio/mp3")

                st.markdown("##### 🎬 Step 2B: Render Full-HD 16:9 Long-Form Video")
                if st.button(f"🚀 3. RENDER {lf_dur.upper()} 16:9 SOAKING PRAYER VIDEO (Uses Approved AI Preacher Audio)", key="lf_render_btn", width="stretch"):
                    lf_loader = LiveTaskLoader(f"Producing {lf_dur} Soaking Prayer Video")

                    # Auto-direct chapters with AI Tone & SFX if not already directed
                    if not st.session_state.get("lf_ch_cue_summary"):
                        lf_loader.update(12, "🤖 AI directing 5-Chapter Preacher Tone, Pitch & Sacred SFX...")
                        lf_journey, ch_cues = lpe.ai_direct_longform_5chapters(lf_journey)
                        st.session_state["lf_active_journey"] = lf_journey
                        st.session_state["lf_ch_cue_summary"] = ch_cues

                    pa_lf = st.session_state.get("lf_preapproved_audio")
                    if pa_lf and Path(pa_lf["master_mp3"]).exists() and pa_lf.get("topic") == lf_topic and pa_lf.get("dur_label") == lf_dur:
                        out_folder = Path(pa_lf["folder"])
                        voice_raw_mp3 = Path(pa_lf["voice_mp3"])
                        master_mix_mp3 = Path(pa_lf["master_mp3"])
                        v_res = pa_lf["v_res"]
                        lf_loader.update(65, "🎙️ Using your pre-approved Master Preacher Audio & SFX track...")
                    else:
                        out_folder = lpe.get_next_longform_folder(f"{lf_dur}_{lf_topic}")
                        voice_raw_mp3 = out_folder / "meditative_voice.mp3"
                        master_mix_mp3 = out_folder / "master_soaking_audio.mp3"

                        lf_loader.update(25, "🎙️ Synthesizing 5-Chapter AI Preacher Voiceover + Pitch Shifts + Sacred SFX...")
                        use_v_name = "hi-IN-MadhurNeural" if "Hindi" in lf_lang_mode else global_v_obj["voice"]
                        v_res = lpe.synthesize_meditative_voiceover(lf_journey, voice_raw_mp3, voice_name=use_v_name, rate_str=global_rate_str, pitch_str=global_v_obj.get("pitch", "-2Hz"))

                        lf_loader.update(55, f"🎵 Mixing {lf_dur} master soaking audio with worship pad & {lf_nature}...")
                        lpe.mix_longform_master_audio(voice_raw_mp3, master_mix_mp3, target_duration_sec=lf_journey["config"]["target_seconds"], bgm_file=global_bgm_file, bgm_volume=global_bgm_vol, nature_style=lf_nature)

                    final_16x9_mp4 = out_folder / f"{out_folder.name}.mp4"
                    final_16x9_thumb = out_folder / f"{out_folder.name}_thumb.jpg"

                    (out_folder / "soaking_prayer_script.json").write_text(json.dumps(lf_journey["strict_json"], indent=2, ensure_ascii=False), encoding="utf-8")
                    (out_folder / "pinned_comment.txt").write_text(lf_journey.get("pinned_comment", ""), encoding="utf-8")

                    lf_loader.update(80, "🎬 Rendering Full-HD 1920x1080 (16:9) Video...")
                    chosen_v = (backend.INTRO_DIR / lf_pick_vid) if (lf_pick_vid != "Auto / Newest") else (intro_vids[0] if intro_vids else backend.prepare_muted_short_main())
                    chosen_i = (backend.BG_DIR / lf_pick_img) if (lf_pick_img != "Auto / Newest") else active_wall_path

                    ok_lf = lpe.render_longform_16x9_video(
                        master_mix_mp3, final_16x9_mp4, final_16x9_thumb, lf_journey,
                        bg_image_path=chosen_i, bg_video_path=chosen_v,
                        visual_mode=lf_vis_mode, palette_name=global_palette,
                        subtitle_mode=lf_sub_mode,
                        sub_font=lf_sub_font,
                        sub_size=lf_sub_size,
                        sub_color=lf_sub_color,
                        sub_pos=lf_sub_pos,
                        sub_words=lf_sub_words,
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
                st.info("💡 Long-Form soaking prayer videos will preview here.")
            else:
                lf_p = Path(lf_prev)
                lf_meta = backend.load_clip_metadata(lf_p)
                st.markdown(f"**⏱️ Length:** `{lpe.format_mm_ss(cached_video_dur(str(lf_p)))}` &nbsp;|&nbsp; 📁 `{lf_p.parent.name}`")
                st.video(str(lf_p))

                lf_srt_f = lf_p.parent / "longform_subtitles.srt"
                if lf_srt_f.exists():
                    st.download_button(
                        "📥 Download Subtitles (.SRT for YouTube CC)",
                        data=lf_srt_f.read_bytes(),
                        file_name=f"{lf_p.stem}_subtitles.srt",
                        mime="application/x-subrip",
                        width="stretch"
                    )

                lf_th = render_custom_thumbnail_manager(lf_p, f"lf_pub_{lf_p.parent.name}")
                st.markdown(f"**🏆 Title:** `{lf_meta.get('title', '')}`")
                render_multi_channel_publish_box(lf_p, lf_th, f"tab3_lf_{lf_p.parent.name}")
# ==============================================================================
# TAB 4: 3-MIN FLOW STORY MOVIES
# ==============================================================================
elif "4." in active_nav_tab:
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
                render_multi_channel_publish_box(mv_p, m_th, f"tab4_st_{mv_p.parent.name}")
# ==============================================================================
# TAB 5: VIDEO VAULT (POST TO GRACE OF THE LORD, IRON & FAITH, OR BOTH CHANNELS)
# ==============================================================================
elif "5." in active_nav_tab:
    st.markdown("### 📂 Master Video Vault (Post Any Video to Grace of the Lord, Iron & Faith, or BOTH Channels)")

    live_ch_map = backend.load_channels()
    live_ch_list = list(live_ch_map.keys())
    if len(live_ch_list) > 1:
        both_vault_lbl = "🔥 BOTH Channels (" + " + ".join([c.split("(")[0].strip() for c in live_ch_list]) + ")"
        vault_pub_opts = [both_vault_lbl] + live_ch_list
    else:
        vault_pub_opts = live_ch_list

    vault_vids_sh = [
        f for f in sorted(list(backend.CLIPS_DIR.rglob("*.mp4")), key=lambda p: p.stat().st_mtime, reverse=True)
        if "temp_" not in str(f) and "muted_" not in f.name and f.parent.name not in ("scenes", "grace_scenes", "muted_cache")
    ]
    vault_vids_lf = [
        f for f in sorted(list(lpe.LONGFORM_DIR.rglob("*.mp4")), key=lambda p: p.stat().st_mtime, reverse=True)
        if "temp_" not in str(f) and "instant_base" not in f.name
    ]
    vault_vids_st = [
        f for f in sorted(list(fse.STORY_MOVIES_DIR.rglob("ST*.mp4")), key=lambda p: p.stat().st_mtime, reverse=True)
        if "temp_" not in str(f)
    ]

    with st.container(border=True):
        vf_c1, vf_c2, vf_c3, vf_c4 = st.columns([1.45, 1.15, 0.9, 0.9])
        with vf_c1:
            vault_cat = st.radio(
                "Filter Vault By Format:",
                [
                    f"📱 Shorts ({len(vault_vids_sh)})",
                    f"🎬 All ({len(vault_vids_sh) + len(vault_vids_lf) + len(vault_vids_st)})",
                    f"🕊️ Long-Form ({len(vault_vids_lf)})",
                    f"🎥 Movies ({len(vault_vids_st)})"
                ],
                horizontal=True,
                key="vault_cat_filter"
            )
        with vf_c2:
            vault_status_filter = st.selectbox(
                "Filter By Upload Status:",
                [
                    "All Videos (Live + Ready)",
                    "🔵 Ready / Not Posted to Both Yet",
                    "🟢 Already Live on YouTube"
                ],
                index=0,
                key="vault_status_filter_dd"
            )
        with vf_c3:
            vault_default_ch = st.selectbox("📺 Default Target:", vault_pub_opts, index=0, key="vault_def_ch_sel")
        with vf_c4:
            st.markdown("<div style='height:26px;'></div>", unsafe_allow_html=True)
            show_all = st.checkbox("Show All Videos", value=False, key="lib_show_all")

    if "Shorts" in vault_cat:
        raw_vault_list = vault_vids_sh
    elif "Long-Form" in vault_cat:
        raw_vault_list = vault_vids_lf
    elif "Movies" in vault_cat:
        raw_vault_list = vault_vids_st
    else:
        raw_vault_list = sorted(vault_vids_sh + vault_vids_lf + vault_vids_st, key=lambda p: p.stat().st_mtime, reverse=True)

    # Apply status filter
    active_vault_list = []
    for v_item in raw_vault_list:
        m_item = backend.load_clip_metadata(v_item)
        up_ch = m_item.get("uploaded_channels", {}) if isinstance(m_item.get("uploaded_channels"), dict) else {}
        has_any_id = bool(up_ch or m_item.get("youtube_id"))
        if "Ready" in vault_status_filter and len(up_ch) >= len(live_ch_list) and len(live_ch_list) > 1:
            continue
        if "Already Live" in vault_status_filter and not has_any_id:
            continue
        active_vault_list.append(v_item)

    if not active_vault_list:
        st.info("No videos match the current filter.")
    else:
        disp_vids = active_vault_list if show_all else active_vault_list[:9]
        for i in range(0, len(disp_vids), 3):
            cols = st.columns(3, gap="medium")
            for j in range(3):
                if i + j < len(disp_vids):
                    vid = disp_vids[i + j]
                    thumb = vid.with_name(f"{vid.stem}_thumb.jpg")
                    meta = backend.load_clip_metadata(vid)
                    up_channels = meta.get("uploaded_channels", {}) if isinstance(meta.get("uploaded_channels"), dict) else {}
                    if not up_channels and meta.get("youtube_id"):
                        # Legacy single-channel upload was on Grace of the Lord
                        up_channels = {live_ch_list[0]: meta["youtube_id"]}

                    with cols[j]:
                        with st.container(border=True):
                            badge = f"🟢 LIVE ({len(up_channels)}/{len(live_ch_list)} Ch)" if up_channels else "🔵 READY"
                            st.markdown(f"**`{vid.parent.name}`** — `{badge}`")
                            if thumb.exists():
                                st.image(str(thumb), width="stretch")

                            with st.expander("▶️ Watch Video / Edit Title & Description / Custom Cover", expanded=False):
                                st.video(str(vid))
                                ed_vt = st.text_input("Title:", value=meta.get("title", ""), key=f"v_ed_t_{vid.parent.name}_{i}_{j}")
                                ed_vd = st.text_area("Description:", value=meta.get("description", ""), height=100, key=f"v_ed_d_{vid.parent.name}_{i}_{j}")
                                if st.button("💾 Save Metadata Changes", key=f"v_sv_m_{vid.parent.name}_{i}_{j}", width="stretch"):
                                    backend.save_clip_metadata(vid, ed_vt, ed_vd, meta.get("tags", []), topic=meta.get("topic", ""))
                                    st.cache_data.clear()
                                    st.toast("✅ Saved!")
                                    st.rerun()

                            st.caption(f"📌 **{meta.get('title', vid.stem)}**")

                            # Show exact channel status badges
                            for ch_name_check in live_ch_list:
                                ch_short = ch_name_check.split("(")[0].strip()
                                if ch_name_check in up_channels:
                                    st.caption(f"🟢 **{ch_short}:** https://youtu.be/{up_channels[ch_name_check]}")
                                else:
                                    st.caption(f"⚪ **{ch_short}:** *Not posted yet*")

                            # Channel radio selector on EVERY card (even if already posted to 1 channel!)
                            card_target = st.radio(
                                "Select Channel to Post:",
                                vault_pub_opts,
                                index=vault_pub_opts.index(vault_default_ch) if vault_default_ch in vault_pub_opts else 0,
                                key=f"vault_rad_{vid.parent.name}_{i}_{j}"
                            )

                            if st.button(f"🚀 Post to: {card_target.split('(')[0].strip()}", key=f"grid_up_{vid.parent.name}_{i}_{j}", width="stretch"):
                                with st.spinner(f"Publishing '{vid.name}' to {card_target}..."):
                                    th_to_use = thumb if thumb.exists() else None
                                    pub_res = backend.publish_video_to_selected_target(card_target, vid, thumbnail_path=th_to_use)
                                    if pub_res:
                                        st.cache_data.clear()
                                        for c_ok, y_ok in pub_res:
                                            st.success(f"🎉 Live on {c_ok}: https://youtu.be/{y_ok}")
                                        time.sleep(0.6)
                                        st.rerun()
                                    else:
                                        st.error("❌ Upload failed — check terminal logs.")

# ==============================================================================
# TAB 6: PODCAST CLIPPER
# ==============================================================================
elif "6." in active_nav_tab:
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
# TAB 7: PERSONAL AI VIDEO ANALYZER & CHANNEL ANALYTICS
# ==============================================================================
elif "7." in active_nav_tab:
    st.markdown("### 🧠 Personal AI Video Analyzer & Channel Intelligence Hub")

    ana_mode_tab1, ana_mode_tab2, ana_mode_tab3 = st.tabs([
        "🤖 1. Personal AI Video Analyzer (Scans All Your Videos + 1-Click Fix)",
        "💬 2. Ask Your Personal AI Analyst (Chat With Your Video Data)",
        "📊 3. Live YouTube Channel & Geography Analytics"
    ])

    # Gather live YouTube video stats if cached in session_state
    cached_yt_vids = []
    for k_st, v_st in st.session_state.items():
        if k_st.startswith("full_intel_") and isinstance(v_st, dict) and v_st.get("videos"):
            cached_yt_vids = v_st["videos"]
            break

    all_scanned_vids = paa.scan_all_studio_videos(live_yt_videos=cached_yt_vids)

    # --- SUB-TAB 1: PERSONAL AI PORTFOLIO & SINGLE-VIDEO ANALYZER ---
    with ana_mode_tab1:
        tot_v = len(all_scanned_vids)
        live_cnt = sum(1 for x in all_scanned_vids if "LIVE" in x["status"])
        ready_cnt = tot_v - live_cnt
        avg_health = int(round(sum(x["health_score"] for x in all_scanned_vids) / max(1, tot_v))) if tot_v else 0
        needs_fix_cnt = sum(1 for x in all_scanned_vids if x["issues"])

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("🎬 Total Videos Scanned", f"{tot_v}", f"{live_cnt} Live • {ready_cnt} Ready")
        k2.metric("🏆 Avg Viral Readiness Score", f"{avg_health}/100", "Across Shorts & Long-Form")
        k3.metric("⚡ Ready to Upload Now", f"{ready_cnt}", "In clips/ & longform_videos/")
        k4.metric("🔧 Videos With Fixable Issues", f"{needs_fix_cnt}", "1-Click AI Fix Available Below")

        with st.container(border=True):
            st.markdown("#### 🧠 Step 1: AI Master Portfolio Coach (Analyzes All Your Videos Together)")
            ac_b1, ac_b2 = st.columns([1.4, 1.0])
            with ac_b1:
                if st.button("🚀 Run Personal AI Audit on All My Videos Now", key="btn_run_full_ai_audit", width="stretch"):
                    with st.spinner(f"🤖 Gemini AI analyzing all {tot_v} videos in your studio..."):
                        st.session_state["personal_ai_audit_rep"] = paa.run_ai_portfolio_master_audit(all_scanned_vids, channel_name=global_target_ch)
            with ac_b2:
                if st.button("📡 Sync Live YouTube Views Into Analyzer", key="btn_sync_yt_into_ana", width="stretch"):
                    with st.spinner(f"Fetching live YouTube views & velocity for {global_target_ch}..."):
                        st.session_state[f"full_intel_{global_target_ch}_90"] = cae.fetch_complete_channel_intelligence(global_target_ch, days_back=90)
                        st.rerun()

            if "personal_ai_audit_rep" not in st.session_state and paa.AI_AUDIT_CACHE_FILE.exists():
                try:
                    st.session_state["personal_ai_audit_rep"] = json.loads(paa.AI_AUDIT_CACHE_FILE.read_text(encoding="utf-8"))
                except Exception:
                    pass

            if "personal_ai_audit_rep" in st.session_state:
                rep_a = st.session_state["personal_ai_audit_rep"]
                st.markdown(
                    f'<div class="verse-card">'
                    f'<div class="verse-hdr">🏆 Overall Studio Grade: <b>{rep_a.get("overall_channel_grade", "A")}</b> &nbsp;|&nbsp; '
                    f'🧠 Engine: <b>{rep_a.get("model_used", "Gemini AI")}</b></div>'
                    f'<div class="verse-body">{rep_a.get("executive_summary", "")}</div>'
                    f'</div>',
                    unsafe_allow_html=True
                )
                col_w1, col_w2 = st.columns(2, gap="large")
                with col_w1:
                    st.markdown("##### ✅ What Is Working Best Across Your Videos")
                    for w_item in rep_a.get("what_is_working_best", []):
                        st.markdown(f"- 🟢 {w_item}")
                with col_w2:
                    st.markdown("##### 🔧 Hidden Bottlenecks Costing You Views")
                    for b_item in rep_a.get("bottlenecks_to_fix", []):
                        st.markdown(f"- 🟠 {b_item}")

                if rep_a.get("next_5_viral_video_ideas"):
                    with st.expander("🔥 AI 5-Video Next Upload Blueprint (Exact Topics, Verses, Titles & Preacher Emotions)", expanded=True):
                        st.dataframe(pd.DataFrame(rep_a["next_5_viral_video_ideas"]), hide_index=True, width="stretch")

        with st.container(border=True):
            st.markdown("#### 📋 Complete Video Library Health & Audit Table (All Shorts, Long-Form & Movies)")
            if all_scanned_vids:
                df_all = pd.DataFrame([{
                    "Status": x["status"],
                    "Type": x["category"],
                    "Folder": x["folder"],
                    "Health": f"{x['health_score']}/100",
                    "Dur (s)": f"{x['duration_sec']:.1f}s",
                    "Title": x["title"],
                    "Views": x["views"],
                    "Vel/Day": x["views_per_day"],
                    "Tags (c)": f"{x['tag_chars']}/380",
                    "Audit Diagnosis": x["issues_str"]
                } for x in all_scanned_vids])
                st.dataframe(df_all, hide_index=True, width="stretch")

        with st.container(border=True):
            st.markdown("#### 🩺 Step 2: Single-Video AI Doctor & 1-Click Metadata Optimizer")
            if all_scanned_vids:
                vid_opts = [f"[{x['status']} | {x['health_score']}/100] {x['folder']} — {x['title'][:45]}" for x in all_scanned_vids]
                sel_v_lbl = st.selectbox("Select Any Video to Diagnose, Preview & Upgrade:", vid_opts, index=0, key="paa_single_sel")
                sel_v_obj = all_scanned_vids[vid_opts.index(sel_v_lbl)]

                d_left, d_right = st.columns([1.05, 1.35], gap="large")
                with d_left:
                    st.video(sel_v_obj["path"])
                    st.caption(f"📂 **Folder:** `{sel_v_obj['folder']}` | ⏱️ **Duration:** `{sel_v_obj['duration_sec']}s` | 🎯 **Health Score:** `{sel_v_obj['health_score']}/100`")
                    st.markdown(f"**🔍 Automated Audit Check:**\n`{sel_v_obj['issues_str']}`")

                with d_right:
                    if st.button(f"🤖 Ask AI Doctor to Diagnose & Upgrade '{sel_v_obj['folder']}'", key="btn_doc_single", width="stretch"):
                        with st.spinner("Gemini AI inspecting video metadata, title CTR & tags..."):
                            st.session_state["paa_single_doc"] = paa.ai_diagnose_and_upgrade_single_video(sel_v_obj)
                            st.session_state["paa_single_doc_folder"] = sel_v_obj["folder"]

                    if st.session_state.get("paa_single_doc") and st.session_state.get("paa_single_doc_folder") == sel_v_obj["folder"]:
                        doc = st.session_state["paa_single_doc"]
                        st.info(f"🩺 **AI Critique ({doc['model_used']}):** {doc['ai_critique']}")
                        up_t = st.text_input("🏆 AI Upgraded High-CTR Title:", value=doc["upgraded_title"], key=f"doc_t_{sel_v_obj['folder']}")
                        st.caption(f"💡 *Why this beats the old title:* {doc['why_title_is_better']}")
                        up_d = st.text_area("📝 AI Upgraded Clean Description (With Your Affiliates):", value=doc["upgraded_description"], height=150, key=f"doc_d_{sel_v_obj['folder']}")
                        up_p = st.text_input("📌 AI Upgraded Pinned Comment:", value=doc["upgraded_pinned_comment"], key=f"doc_p_{sel_v_obj['folder']}")
                        up_tags = st.text_area("🏷️ AI Upgraded 380-Char SEO Tags:", value=", ".join(doc["upgraded_tags"]), height=68, key=f"doc_g_{sel_v_obj['folder']}")

                        if st.button(f"🔒 Lock All AI Upgrades Into '{sel_v_obj['folder']}' (100/100 Ready!)", key="btn_lock_doc_up", width="stretch"):
                            v_p = Path(sel_v_obj["path"])
                            clean_t_list = backend.sanitize_youtube_tags([t.strip() for t in up_tags.split(",") if t.strip()])
                            backend.save_clip_metadata(v_p, up_t.strip(), up_d.strip(), clean_t_list, topic=sel_v_obj["topic"])
                            (v_p.parent / "pinned_comment.txt").write_text(up_p.strip(), encoding="utf-8")
                            st.cache_data.clear()
                            st.success(f"🎉 Locked upgraded Title, Description, Pinned Comment & {len(clean_t_list)} Tags into `{sel_v_obj['folder']}`!")
                            time.sleep(0.5)
                            st.rerun()

    # --- SUB-TAB 2: ASK YOUR PERSONAL AI ANALYST ---
    with ana_mode_tab2:
        with st.container(border=True):
            st.markdown("#### 💬 Chat With Your Personal AI Channel & Video Strategist")
            st.caption("Ask anything about your videos—Gemini AI has your full video list, durations, health scores, and views loaded in context!")
            q_presets = [
                "Custom Question (Type Below)",
                "Which 3 of my READY unuploaded videos should I publish first and why?",
                "Analyze my video titles — which ones have the highest CTR potential and which ones need rewriting?",
                "How should I balance my 25-second Shorts with my 15-minute Long-Form Soaking Prayers this week?",
                "Give me a 7-day upload schedule using my existing videos plus new topics."
            ]
            q_pick = st.selectbox("⚡ Quick Strategy Questions:", q_presets, index=1, key="paa_q_preset")
            q_custom = st.text_input(
                "✍️ Or Ask Your Own Question:",
                value="" if q_pick != "Custom Question (Type Below)" else "How can I get more views and AMEN comments on my next 5 Shorts?",
                key="paa_q_custom"
            )
            final_q = q_custom.strip() if q_pick == "Custom Question (Type Below)" else q_pick
            if st.button("🧠 Ask Personal AI Analyst", key="btn_ask_paa", width="stretch"):
                with st.spinner("Gemini AI analyzing your video library to answer..."):
                    st.session_state["paa_chat_answer"] = paa.ask_personal_ai_analyst(final_q, all_scanned_vids, channel_name=global_target_ch)
            if st.session_state.get("paa_chat_answer"):
                st.markdown("---")
                st.markdown(st.session_state["paa_chat_answer"])

    # --- SUB-TAB 3: LIVE YOUTUBE CHANNEL ANALYTICS ---
    with ana_mode_tab3:
        ctl_c1, ctl_c2, ctl_c3 = st.columns([1.5, 1.2, 1.2])
        with ctl_c1:
            stat_ch = st.selectbox("Channel to Audit:", channel_names, key="stats_ch_sel")
        with ctl_c2:
            stat_days = st.selectbox("Period:", [28, 90, 365], index=1, format_func=lambda x: f"Last {x} Days", key="stats_period_sel")
        with ctl_c3:
            st.markdown("<div style='height:26px;'></div>", unsafe_allow_html=True)
            if st.button("🔄 Refresh Live YouTube Analytics", key="refresh_stats_btn", width="stretch"):
                st.session_state[f"full_intel_{stat_ch}_{stat_days}"] = cae.fetch_complete_channel_intelligence(stat_ch, days_back=stat_days)
                st.rerun()

        cache_k = f"full_intel_{stat_ch}_{stat_days}"
        intel = st.session_state.get(cache_k)
        if intel is None:
            st.info(f"💡 Click **'Refresh Live YouTube Analytics'** above to load live Subscribers, Video Audit, and Geography for **{stat_ch}**.")
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
                df_v = pd.DataFrame([{"Rank": f"#{i+1}", "Type": v["type"], "Title": v["title"][:50], "Views": v["views"], "Vel/Day": v["views_per_day"], "Likes": v["likes"], "Comments": v["comments"], "Duration": v["duration_str"], "Date": v["published_date"]} for i, v in enumerate(vids)])
                st.dataframe(df_v, hide_index=True, width="stretch")

elif "8. AI Engine Tester Lab" in active_nav_tab:
    st.markdown("### 🧪 Live AI Engine Tester & Command Lab (Clean Data • Multi-Engine Studio)")

    engine_choice = st.radio(
        "Select Studio Engine to Inspect, Command & Lock:",
        [
            "🏆 Engine 1: Title Researcher & Competitor Engine (title_engine.py)",
            "📝 Engine 2: Viral Description, Affiliate & Hashtag Engine (description_engine.py)",
            "🏷️ Engine 3: 380-Char Backend SEO Tags Engine (main.py)",
            "📜 Engine 4: Spoken Script & 3-Scene Storyboard Engine (grace_of_lord_engine.py)",
            "🎨 Engine 5: 3D Gold Thumbnail & AI Prompt Engine (pro_design_addon.py)",
        ],
        index=0,
        horizontal=True,
        key="tester_engine_selector"
    )

    t_left, t_right = st.columns([1.1, 1.3], gap="large")

    with t_left:
        with st.container(border=True):
            st.markdown("#### 🎲 1. Topic & Scripture Source")
            sync_source = st.radio(
                "Choose Topic Source:",
                [
                    "🔥 50 Prayer Topics (Picks a New Random Relevant Verse Every Time)",
                    "📂 Existing Video Folder in clips/ (e.g. 051_Quick...)",
                    "✍️ Type Custom Topic",
                ],
                index=0,
                horizontal=True,
                key="lab_sync_source"
            )

            target_vid_to_lock = None
            if "Existing Video" in sync_source and all_videos:
                vid_labels = [f"{v.parent.name}  --  [Current: {backend.load_clip_metadata(v).get('title', '')[:36]}]" for v in all_videos[:30]]
                picked_v_lbl = st.selectbox("Select Video Folder:", vid_labels, index=0, key="lab_vid_dd")
                target_vid_to_lock = all_videos[vid_labels.index(picked_v_lbl)]
                v_meta = backend.load_clip_metadata(target_vid_to_lock)
                selected_topic_str = title_engine._clean_topic_name(v_meta.get("topic") or target_vid_to_lock.parent.name)
            elif "50 Prayer" in sync_source:
                t50_labels = [f"{item['id']}. {item['topic']}  --  [🎲 Random AI Scripture]" for item in TOP_50_PRAYER_TOPICS]
                picked_t50 = st.selectbox("Select Prayer Topic (1-50):", t50_labels, index=0, key="lab_t50_dd")
                selected_topic_str = TOP_50_PRAYER_TOPICS[t50_labels.index(picked_t50)]["topic"]
            else:
                selected_topic_str = st.text_input("Type Custom Topic:", value="Debt & Financial Freedom", key="lab_cust_t_in")

            if st.session_state.get("lab_last_topic") != selected_topic_str or "lab_verse_bundle" not in st.session_state:
                st.session_state["lab_last_topic"] = selected_topic_str
                st.session_state["lab_verse_bundle"] = title_engine.match_topic_to_canonical_verse(selected_topic_str, use_ai_network=False)

            r_col1, r_col2 = st.columns([1.35, 1])
            with r_col1:
                if st.button("🎲 Roll New Random Verse for This Topic Now", key="btn_lab_reroll_verse", width="stretch"):
                    with st.spinner(f"AI picking a fresh unused Bible verse for '{selected_topic_str}'..."):
                        st.session_state["lab_verse_bundle"] = title_engine.match_topic_to_canonical_verse(selected_topic_str, use_ai_network=True)
                        st.session_state["en_ai_bundle"] = st.session_state["lab_verse_bundle"]
                        st.rerun()
            with r_col2:
                auto_roll_on_run = st.checkbox("🎲 Roll Different Verse During Run", value=False, key="lab_auto_roll_chk")

            vb = st.session_state["lab_verse_bundle"]
            active_test_topic = vb["topic_en"]
            active_test_ref = vb["verse_citation"]
            active_test_v_txt = vb["en_verse"]
            active_hi_v_txt = vb.get("hi_verse", "")
            active_why_v = vb.get("why_en", "")

            st.markdown(
                f'<div class="verse-card">'
                f'<div class="verse-hdr">📖 Selected Scripture for "{active_test_topic}": <b>{active_test_ref}</b></div>'
                f'<div class="verse-body">🇬🇧 <b>English:</b> "{active_test_v_txt}"</div>'
                f'<div style="font-size:14px;color:#FDE047;margin-top:5px;">🇮🇳 <b>Hindi:</b> "{active_hi_v_txt}"</div>'
                f'<div style="font-size:12.5px;color:#93C5FD;margin-top:6px;">💡 <b>Why AI Picked `{active_test_ref}`:</b> {active_why_v}</div>'
                f'</div>',
                unsafe_allow_html=True
            )

            # --- ENGINE 1 CONTROLS ---
            if "Engine 1" in engine_choice:
                st.markdown("#### 💬 2. Give Command to Title Engine & Run Live")
                test_lang = st.selectbox("Target Audience & Language:", ["🇺🇸 US American Audience (en-US)", "🇮🇳 Hindi Audience (hi-IN)"], index=0, key="lab_lang_sel")
                lang_code = "hi" if "Hindi" in test_lang else "en"

                default_cmd = title_engine.build_default_title_command(
                    active_test_topic, active_test_ref, active_test_v_txt, "", lang=lang_code
                )
                custom_user_cmd = st.text_area(
                    "Engine Command / Prompt Instructions (Editable):",
                    value=default_cmd,
                    height=165,
                    key=f"lab_cmd_{active_test_topic[:18]}_{active_test_ref}_{lang_code}"
                )

                scrape_live = st.checkbox("🌐 Scrape Live YouTube Competitor Shorts (Takes ~15-30s)", value=True, key="lab_scrape_chk")

                if st.button("🚀 EXECUTE COMMAND & RUN LIVE TITLE ENGINE", key="btn_exec_live_title", width="stretch"):
                    loader = LiveTaskLoader("Executing Live Title Engine")
                    log_expander = st.expander("📡 Live Step-by-Step Execution Console", expanded=True)
                    log_placeholder = log_expander.empty()
                    live_logs = []

                    def _on_step(pct: int, stage: str, detail: str):
                        loader.update(pct, f"{stage}: {detail}")
                        live_logs.append(f"* [{pct:02d}%] {stage} -> {detail}")
                        log_placeholder.code("\n".join(live_logs), language="text")

                    try:
                        rep = title_engine.research_and_generate_titles(
                            topic=active_test_topic,
                            verse_ref=active_test_ref,
                            verse_text=active_test_v_txt,
                            channel_name=global_target_ch,
                            lang=lang_code,
                            scan_live_competitors=scrape_live,
                            custom_command=custom_user_cmd,
                            auto_roll_new_verse=auto_roll_on_run,
                            step_cb=_on_step,
                        )
                        st.session_state["lab_title_report"] = rep
                        st.session_state["lab_verse_bundle"] = {
                            "topic_en": rep["topic"],
                            "verse_citation": rep["verse_ref"],
                            "en_verse": rep["verse_text"],
                            "hi_verse": rep.get("hi_verse_text", active_hi_v_txt),
                            "why_en": rep.get("verse_why_explanation", active_why_v),
                        }
                        loader.complete(f"Live AI Execution Complete in {rep['elapsed_sec']}s via {rep['engine_used']} (Verse: {rep['verse_ref']})!")
                    except Exception as e_run:
                        loader.box.error(f"Live Engine Error: {e_run}")

            # --- ENGINE 2 CONTROLS ---
            elif "Engine 2" in engine_choice:
                st.markdown("#### 📝 2. Configure Viral Description & Affiliate Engine")

                desc_style_choice = st.selectbox(
                    "Select Tested Description Style:",
                    [
                        "Style A: Emotional Surrender & Prayer (High Comment Retention)",
                        "Style B: Scripture Study & Biblical Teaching (High SEO)",
                        "Style C: Compact Quick-Prayer & Blessing (Mobile Fast)",
                    ],
                    index=0,
                    key="lab_desc_style_sel"
                )
                desc_lang_choice = st.selectbox("Description Language:", ["🇬🇧 English", "🇮🇳 Hindi (पवित्र बाइबिल)"], index=0, key="lab_desc_lang_sel")
                d_lang = "hi" if "Hindi" in desc_lang_choice else "en"

                with st.expander("🛍️ Manage Your 5 Affiliate Link Titles & URLs (Leave blank to remove)", expanded=False):
                    st.caption("Configure up to 5 custom links. Empty slots are automatically skipped!")
                    lab_affs = description_engine.load_affiliates()
                    new_lab_affs = []
                    for i in range(5):
                        aff_lab_cur = lab_affs[i] if (isinstance(lab_affs, list) and i < len(lab_affs)) else {}
                        a_c1, a_c2 = st.columns([1.2, 1.8])
                        with a_c1:
                            lh = st.text_input(f"Link #{i+1} Title:", value=aff_lab_cur.get("heading", ""), key=f"lab_aff_h_{i}", placeholder=f"Link #{i+1} Title:")
                        with a_c2:
                            lu = st.text_input(f"Link #{i+1} URL:", value=aff_lab_cur.get("url", ""), key=f"lab_aff_u_{i}", placeholder="https://amzn.to/... (or leave blank)")
                        new_lab_affs.append({"heading": lh, "url": lu})

                    if st.button("💾 Save Links & Refresh Description", key="btn_save_lab_affs", width="stretch"):
                        if hasattr(description_engine, "save_affiliates"):
                            description_engine.save_affiliates(new_lab_affs)
                        else:
                            import json
                            clean_d = [{"heading": str(it.get("heading", "")).strip(), "url": str(it.get("url", "")).strip()} for it in new_lab_affs[:5]]
                            (backend.BASE_DIR / "affiliate_links.json").write_text(json.dumps(clean_d, indent=2, ensure_ascii=False), encoding="utf-8")
                        st.cache_data.clear()
                        d_pkg = description_engine.build_curated_description(
                            active_test_topic, active_test_ref, active_test_v_txt,
                            reflection=vb.get("why_en", "") if "vb" in locals() and isinstance(vb, dict) else "",
                            prayer=f"Lord Jesus, release Your breakthrough in {active_test_topic}, Amen.",
                            style=desc_style_choice, lang=d_lang
                        )
                        st.session_state["lab_desc_report"] = d_pkg
                        st.success("✅ Saved! Only your filled links will appear.")
                        time.sleep(0.4)
                        st.rerun()

                use_ai_custom_desc = st.checkbox("🤖 Use Live Gemini AI to research & craft custom description", value=True, key="lab_desc_ai_chk")
                custom_desc_notes = st.text_input("Special Focus / Angle (Optional):", value="", placeholder="e.g. Focus on immediate nighttime peace and casting burdens upon Jesus", key="lab_desc_notes")

                if st.button("🚀 EXECUTE COMMAND & GENERATE DESCRIPTION", key="btn_exec_desc_eng", width="stretch"):
                    with st.spinner("Generating viral description, affiliate links & hashtags..."):
                        try:
                            # Safely extract reflection & prayer from session state
                            cur_bundle = st.session_state.get("lab_verse_bundle", {})
                            safe_refl = cur_bundle.get("why_en", "God is with you through this.") if isinstance(cur_bundle, dict) else "God is with you."
                            safe_pray = f"Lord Jesus, release Your breakthrough in {active_test_topic}, Amen."
                            
                            if use_ai_custom_desc:
                                d_pkg = description_engine.research_and_generate_description_ai(
                                    active_test_topic, active_test_ref, active_test_v_txt,
                                    reflection=safe_refl, prayer=safe_pray,
                                    style=desc_style_choice, lang=d_lang, custom_instructions=custom_desc_notes
                                )
                            else:
                                d_pkg = description_engine.build_curated_description(
                                    active_test_topic, active_test_ref, active_test_v_txt,
                                    reflection=safe_refl, prayer=safe_pray,
                                    style=desc_style_choice, lang=d_lang
                                )
                            st.session_state["lab_desc_report"] = d_pkg
                        except Exception as e_desc:
                            st.error(f"❌ Description Engine Error: {e_desc}")

            elif "Engine 3" in engine_choice:
                st.markdown("#### 🏷️ 2. Configure SEO Tags Engine")
                use_ai_tags = st.checkbox("🤖 Use Live Gemini AI to research competitor tags", value=True, key="lab_tags_ai_chk")
                custom_tag_focus = st.text_input("Special Keyword Focus (Optional):", value="", placeholder="e.g. spiritual warfare, midnight prayer", key="lab_tags_notes")

                if st.button("🚀 EXECUTE COMMAND & GENERATE SEO TAGS", key="btn_exec_tags_eng", width="stretch"):
                    with st.spinner("Researching search volume & packing 380-char YouTube tags..."):
                        import viral_researcher as vr
                        if use_ai_tags:
                            pkg_t = vr.research_viral_scripture_package(active_test_topic, global_target_ch)
                            raw_tags = pkg_t.get("tags", [])
                        else:
                            pkg_t = vr.get_fully_synced_youtube_package(active_test_topic, active_test_ref, active_test_v_txt)
                            raw_tags = pkg_t.get("tags", [])
                        
                        if custom_tag_focus:
                            raw_tags.extend([x.strip() for x in custom_tag_focus.split(",")])

                        clean_t_list = backend.sanitize_youtube_tags(raw_tags)
                        st.session_state["lab_tags_report"] = {
                            "tags": clean_t_list,
                            "total_chars": sum(len(x) + 1 for x in clean_t_list)
                        }

            elif "Engine 4" in engine_choice:
                if st.button("🚀 RUN LIVE 3-SCENE SCRIPT ENGINE", key="btn_exec_sc_eng", width="stretch"):
                    with st.spinner("Running 3-Scene Storyboard Engine..."):
                        st.session_state["lab_script_report"] = gle.generate_grace_3scene_script(active_test_topic)

            elif "Engine 5" in engine_choice:
                if st.button("🚀 GENERATE 3D GOLD THUMBNAIL & AI PROMPT PREVIEW", key="btn_exec_th_eng", width="stretch"):
                    with st.spinner("Rendering 3D Gold Thumbnail..."):
                        import pro_design_addon as pda
                        from types import SimpleNamespace
                        test_th_out = backend.BASE_DIR / "assets" / "lab_test_thumb.jpg"
                        dummy_s = SimpleNamespace(topic=active_test_topic, verse_citation=active_test_ref, thumbnail_hook=f"PRAY OVER {active_test_topic.upper()[:14]}", title=active_test_topic)
                        pda.render_pro_thumbnails(active_wall_path, dummy_s, test_th_out, palette_name=global_palette)
                        ai_p = pda.build_ai_thumbnail_prompt(active_test_topic, active_test_ref, dummy_s.thumbnail_hook)
                        st.session_state["lab_thumb_report"] = {"path": str(test_th_out), "prompt": ai_p}

    with t_right:
        with st.container(border=True):
            # --- ENGINE 1 OUTPUT & LOCK ---
            if "Engine 1" in engine_choice:
                st.markdown("#### 🎯 Choose & Lock Your Title Option")

                if "lab_title_report" in st.session_state:
                    rep = st.session_state["lab_title_report"]
                    active_cands = rep.get("candidates", [])
                    engine_badge_str = f"🧠 Live AI: <b>{rep['engine_used']}</b> | ⏱️ <b>{rep['elapsed_sec']}s</b>"
                    comp_analysis_text = rep.get("competitor_pattern_analysis", "")
                    comps_list = rep.get("competitors", [])
                    logs_list = rep.get("process_logs", [])
                    active_ref_str = rep.get("verse_ref", active_test_ref)
                else:
                    active_cands = title_engine.get_curated_or_fallback_candidates(active_test_topic, active_test_ref)
                    engine_badge_str = "⭐ <b>Instant Curated High-CTR Options</b> (Click Execute to run Live AI Scraping)"
                    comp_analysis_text = "These 5 title options are engineered for the US YouTube Shorts feed to beat generic competitor titles through emotional hooks and clear promises."
                    comps_list = []
                    logs_list = []
                    active_ref_str = active_test_ref

                st.markdown(f'<div class="budget-badge">{engine_badge_str}</div>', unsafe_allow_html=True)

                option_labels = [
                    f"Option {c['rank']}: {c['title']}  ({len(c['title'])}c) — [{c['angle']}]"
                    for c in active_cands
                ]

                selected_opt_lbl = st.radio(
                    "👉 Select Title Option to Lock & Publish:",
                    option_labels,
                    index=0,
                    key="lab_title_option_radio"
                )
                selected_idx = option_labels.index(selected_opt_lbl)
                chosen_opt = active_cands[selected_idx]

                with st.container(border=True):
                    st.markdown("##### 🏆 Selected Title for YouTube:")
                    title_hash = abs(hash(chosen_opt["title"])) % 1000000
                    ed_chosen_title = st.text_input(
                        "Edit Selected Title:",
                        value=chosen_opt["title"],
                        key=f"ed_live_t_{chosen_opt['rank']}_{title_hash}",
                        label_visibility="collapsed"
                    )

                    c_info1, c_info2 = st.columns([2, 1])
                    with c_info1:
                        char_cnt = len(ed_chosen_title)
                        status_str = "Optimal for mobile" if 28 <= char_cnt <= 58 else ("Slightly long" if char_cnt > 58 else "Short")
                        st.caption(f"📏 Length: **{char_cnt} chars** ({status_str}) | Style: **{chosen_opt['angle']}**")
                    with c_info2:
                        st.caption(f"📊 CTR Score: **{chosen_opt.get('score', 95)}/100**")

                    st.markdown(f"💡 **Why This Works (Psychological Trigger):**\n*{chosen_opt['why_it_works']}*")
                    st.markdown(f"⚔️ **How It Beats Competitors:**\n*{chosen_opt['vs_competitors']}*")

                    lock_btn_text = (
                        f"🔒 Lock Selected Title into '{target_vid_to_lock.parent.name}' & Studio"
                        if target_vid_to_lock else
                        "🔒 Lock Selected Title into Studio"
                    )
                    if st.button(lock_btn_text, key="btn_lock_chosen_option", width="stretch"):
                        st.session_state["qs_synced_title_in"] = ed_chosen_title
                        if target_vid_to_lock and target_vid_to_lock.exists():
                            title_engine.lock_title_for_video(target_vid_to_lock, ed_chosen_title, chosen_opt["why_it_works"])
                            st.cache_data.clear()
                            st.success(f"🎉 Successfully locked `{ed_chosen_title}` into `{target_vid_to_lock.parent.name}`!")
                        else:
                            title_engine.save_title_to_history(ed_chosen_title)
                            st.success(f"🎉 Successfully locked `{ed_chosen_title}` into Studio Tab 1!")

                with st.expander("🔍 View All 5 Title Options & Competitor Audit Details", expanded=False):
                    st.markdown(f"**🧠 AI Competitor Pattern Analysis:**\n*{comp_analysis_text}*")
                    if comps_list:
                        st.markdown("**Live Competitor Shorts on YouTube:**")
                        df_comp = pd.DataFrame([
                            {"Rank": f"#{i+1}", "Competitor Title": c["title"], "Views": f"{c['views']:,}", "Velocity": f"{c['views_per_day']:,.0f}/day", "Chars": len(c["title"])}
                            for i, c in enumerate(comps_list)
                        ])
                        st.dataframe(df_comp, hide_index=True, width="stretch")

                    if logs_list:
                        st.markdown("**Full 5-Stage Execution Trace:**")
                        st.code("\n".join(logs_list), language="text")

            # --- ENGINE 2 OUTPUT & LOCK ---
            elif "Engine 2" in engine_choice:
                st.markdown("#### 📝 3. Live Description, Affiliate & Pinned Comment Output")
                if "lab_desc_report" not in st.session_state:
                    init_refl = vb.get("why_hi" if "Hindi" in str(locals().get("desc_lang_choice", "")) else "why_en", "") if "vb" in locals() and isinstance(vb, dict) else ""
                    init_pray = vb.get("prayer_hi" if "Hindi" in str(locals().get("desc_lang_choice", "")) else "prayer_en", "") if "vb" in locals() and isinstance(vb, dict) else ""
                    init_desc = description_engine.build_curated_description(
                        active_test_topic, active_test_ref, active_test_v_txt,
                        reflection=init_refl, prayer=init_pray
                    )
                    st.session_state["lab_desc_report"] = init_desc

                d_rep = st.session_state["lab_desc_report"]
                st.markdown(
                    f'<div class="budget-badge">📝 Style: <b>{d_rep.get("style", "Emotional")}</b> | '
                    f'📏 Length: <b>{d_rep.get("char_count", len(d_rep["description"]))} chars</b> | '
                    f'🏷️ Hashtags: <b>{len(d_rep.get("hashtags", []))}</b></div>',
                    unsafe_allow_html=True
                )

                desc_hash = abs(hash(d_rep["description"])) % 100000
                ed_desc_val = st.text_area("Generated Description (Clean — Zero [HASHTAGS] Brackets — Fully Editable):", value=d_rep["description"], height=280, key=f"ed_lab_desc_{desc_hash}")
                ed_pin_val = st.text_input("📌 Pinned Community Comment (Drives 'AMEN' Engagement):", value=d_rep.get("pinned_comment", "Type AMEN to agree in faith! 🙏"), key=f"ed_lab_pin_{desc_hash}")

                st.caption(f"🏷️ **Hashtags Injected:** `{', '.join(d_rep.get('hashtags', []))}`")
                with st.expander("🛍️ View Amazon Affiliate Items & FTC Disclaimer Included in Description", expanded=False):
                    for af in description_engine.load_affiliates():
                        st.caption(f"• **{af['heading']}** `{af['url']}`")
                    st.caption("• *Disclaimer: As an Amazon Associate, I earn from qualifying purchases at no extra cost to you.*")

                lock_desc_btn = (
                    f"🔒 Lock Description into '{target_vid_to_lock.parent.name}' & Studio"
                    if target_vid_to_lock else
                    "🔒 Lock Description into Studio Tab 1"
                )
                b_d1, b_d2 = st.columns([1.2, 1.3])
                with b_d1:
                    if st.button(lock_desc_btn, key="btn_lock_desc_lab", width="stretch"):
                        st.session_state["qs_synced_desc_in"] = ed_desc_val
                        if target_vid_to_lock and target_vid_to_lock.exists():
                            description_engine.lock_description_for_video(target_vid_to_lock, ed_desc_val, ed_pin_val)
                            st.cache_data.clear()
                            st.success(f"🎉 Locked Description into `{target_vid_to_lock.parent.name}`!")
                        else:
                            st.success("🎉 Locked Description into Studio!")
                with b_d2:
                    if st.button("🚀 Push Engine 2 to All Studios", key="btn_push_e2_all", width="stretch"):
                        st.session_state["qs_synced_desc_in"] = ed_desc_val
                        st.cache_data.clear()
                        st.success("✅ Engine 2 (Description & Affiliate Engine) is now active and locked across all generators!")

            elif "Engine 3" in engine_choice:
                st.markdown("#### 🏷️ 3. Live SEO Tags Output & Lock")
                if "lab_tags_report" not in st.session_state:
                    st.session_state["lab_tags_report"] = {"tags": [active_test_topic, "Daily Prayer", "Bible Verse", "Christian Shorts"], "total_chars": 50}
                
                t_rep = st.session_state["lab_tags_report"]
                tags_str = ", ".join(t_rep["tags"])
                char_count = len(tags_str)

                st.markdown(
                    f'<div class="budget-badge">🏷️ Tags Generated: <b>{len(t_rep["tags"])}</b> &nbsp;|&nbsp; '
                    f'📏 Length: <b>{char_count}/400 chars</b></div>',
                    unsafe_allow_html=True
                )

                ed_tags_val = st.text_area("Backend SEO Tags (Comma separated — Fully Editable):", value=tags_str, height=150, key=f"ed_lab_tags_{char_count}")

                if char_count > 400:
                    st.error("⚠️ Warning: Tags exceed YouTube's 400 character limit! Please shorten them.")

                b_t1, b_t2 = st.columns([1.2, 1.3])
                with b_t1:
                    lock_tags_btn = f"🔒 Lock Tags into '{target_vid_to_lock.parent.name}'" if target_vid_to_lock else "🔒 Lock Tags into Studio"
                    if st.button(lock_tags_btn, key="btn_lock_tags_lab", width="stretch"):
                        st.session_state["qs_synced_tags_in"] = ed_tags_val
                        if target_vid_to_lock and target_vid_to_lock.exists():
                            m_meta = backend.load_clip_metadata(target_vid_to_lock)
                            backend.save_clip_metadata(target_vid_to_lock, m_meta["title"], m_meta["description"], [t.strip() for t in ed_tags_val.split(",") if t.strip()], topic=m_meta.get("topic", ""))
                            st.cache_data.clear()
                            st.success(f"🎉 Locked SEO Tags into `{target_vid_to_lock.parent.name}`!")
                        else:
                            st.success("🎉 Locked SEO Tags into Studio Tab 1!")
                with b_t2:
                    if st.button("🚀 Push Engine 3 to All Studios", key="btn_push_e3_all", width="stretch"):
                        st.session_state["qs_synced_tags_in"] = ed_tags_val
                        st.cache_data.clear()
                        st.success("✅ Engine 3 (SEO Tags) is now active and locked across all generators!")

            elif "Engine 4" in engine_choice and "lab_script_report" in st.session_state:
                s_rep = st.session_state["lab_script_report"]
                st.markdown("#### 📜 Live 3-Scene Storyboard JSON Output")
                st.code(json.dumps(s_rep, indent=2, ensure_ascii=False), language="json")

            elif "Engine 5" in engine_choice and "lab_thumb_report" in st.session_state:
                th_rep = st.session_state["lab_thumb_report"]
                st.markdown("#### 🎨 Live 3D Gold Thumbnail & AI Prompt")
                st.image(th_rep["path"], width=280)
                st.code(th_rep["prompt"], language="text")