import os
import re
import time
import json
import shutil
import subprocess
from pathlib import Path
import streamlit as st

import main as backend
from voice_studio import (
    VOICE_CATALOG,
    SCRIPT_MODES,
    DEFAULT_SAMPLE_TEXTS,
    load_active_voice,
    save_active_voice,
    combine_prosody,
    synthesize_preview_sample,
    build_spoken_voice_script,
)

st.set_page_config(
    page_title="DailyWisdom AI Studio",
    page_icon="✝️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- FULL-BLEED SaaS WEBSITE CSS ---
st.markdown("""
<style>
    /* Fill every corner cleanly */
    .block-container {
        padding-top: 1.2rem !important;
        padding-bottom: 1.2rem !important;
        padding-left: 1.5rem !important;
        padding-right: 1.5rem !important;
        max-width: 100% !important;
    }
    section[data-testid="stSidebar"] {
        background-color: #0B0F19 !important;
        border-right: 1px solid #1F2937 !important;
    }
    /* Top Navbar Banner */
    .top-nav {
        background: linear-gradient(90deg, #0F172A 0%, #1E1B4B 50%, #0F172A 100%);
        border: 1px solid #334155;
        border-left: 5px solid #FFD700;
        border-radius: 12px;
        padding: 14px 22px;
        margin-bottom: 14px;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .nav-title {
        font-size: 24px;
        font-weight: 900;
        color: #FFD700;
        letter-spacing: 0.5px;
        margin: 0;
    }
    .nav-sub {
        font-size: 13px;
        color: #94A3B8;
        margin-top: 2px;
    }
    .status-pill {
        background-color: #1E293B;
        border: 1px solid #475569;
        color: #F8FAFC;
        padding: 5px 12px;
        border-radius: 999px;
        font-size: 12px;
        font-weight: 700;
        display: inline-block;
        margin-left: 8px;
    }
    /* KPI Metric Cards */
    .kpi-card {
        background: linear-gradient(145deg, #111827, #0F172A);
        border: 1px solid #1F2937;
        border-top: 3px solid #FFD700;
        border-radius: 10px;
        padding: 12px 16px;
        text-align: left;
    }
    .kpi-label { font-size: 12px; color: #9CA3AF; text-transform: uppercase; font-weight: 700; }
    .kpi-val { font-size: 22px; font-weight: 900; color: #FFFFFF; margin-top: 2px; }
    .kpi-sub { font-size: 11px; color: #FFD700; }

    /* Golden Primary Buttons */
    .stButton>button {
        background: linear-gradient(90deg, #FFD700 0%, #EAB308 100%);
        color: #090D16 !important;
        font-weight: 800 !important;
        border-radius: 8px !important;
        border: none !important;
        transition: all 0.15s ease-in-out;
    }
    .stButton>button:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 14px rgba(255, 215, 0, 0.35);
    }
</style>
""", unsafe_allow_html=True)

# --- FAST HELPER SCANNERS ---
def get_all_sequence_videos():
    return sorted(list(backend.CLIPS_DIR.rglob("*.mp4")), key=lambda p: p.parent.name, reverse=True)

def get_media_files(folder: Path, exts: tuple):
    if not folder.exists():
        return []
    return sorted(
        [f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in exts],
        key=lambda x: x.stat().st_mtime,
        reverse=True,
    )

channels = backend.load_channels()
channel_names = list(channels.keys()) if channels else ["TheDailyWisdom_Hub"]
cur_v_cfg = load_active_voice()
all_videos = get_all_sequence_videos()
uploaded_count = sum(1 for v in all_videos if backend.load_clip_metadata(v).get("youtube_id"))
pending_count = len(all_videos) - uploaded_count

# ==============================================================================
# LEFT SIDEBAR: GLOBAL COMMAND CENTER (VOICE STUDIO + PINTEREST + CHANNELS)
# ==============================================================================
with st.sidebar:
    st.markdown("### 🎛️ Command Center")

    # 1. Active Channel Selector
    active_channel = st.selectbox("📺 Target YouTube Channel:", channel_names, key="sb_channel")
    sb_c1, sb_c2 = st.columns(2)
    with sb_c1:
        if st.button("➕ Add Channel", width="stretch"):
            new_c = backend.connect_new_channel()
            if new_c:
                st.success(f"Added {new_c}")
                st.rerun()
    with sb_c2:
        if st.button("☁️ Git Save", width="stretch"):
            with st.spinner("Pushing..."):
                ok, msg = backend.save_everything_to_git()
                st.toast("Saved to GitHub!" if ok else msg, icon="✅" if ok else "⚠️")

    if st.button("🛑 Stop / Cancel Active Task", width="stretch"):
        subprocess.run(["taskkill", "/F", "/IM", "ffmpeg.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["taskkill", "/F", "/IM", "yt-dlp.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        st.warning("Stopped active background tasks.")
        st.stop()

    st.divider()

    # 2. Voice & Accent Audition Studio (Always accessible in sidebar)
    st.markdown("### 🎙️ Voice & Accent Studio")
    accent_list = list(VOICE_CATALOG.keys())
    def_acc_i = accent_list.index(cur_v_cfg.get("accent")) if cur_v_cfg.get("accent") in accent_list else 0
    sel_accent = st.selectbox("1. Accent / Language:", accent_list, index=def_acc_i)

    voices_in_acc = VOICE_CATALOG[sel_accent]
    v_labels = [v["name"] for v in voices_in_acc]
    def_v_i = next((i for i, v in enumerate(voices_in_acc) if v["id"] == cur_v_cfg.get("id")), 0)
    sel_v_name = st.selectbox("2. Voice Model:", v_labels, index=def_v_i)
    chosen_v = voices_in_acc[v_labels.index(sel_v_name)]
    st.caption(f"✨ {chosen_v['style']}")

    sel_script_mode = st.radio(
        "3. Verse Reading Mode:",
        SCRIPT_MODES,
        index=0 if "English" in cur_v_cfg.get("script_mode", SCRIPT_MODES[0]) else 1,
    )

    sp_col, pt_col = st.columns(2)
    with sp_col:
        spd_off = st.slider("Speed (%)", -15, 15, 0)
    with pt_col:
        pit_off = st.slider("Pitch (Hz)", -10, 10, 0)

    final_rate = combine_prosody(chosen_v["rate"], spd_off, "%")
    final_pitch = combine_prosody(chosen_v["pitch"], pit_off, "Hz")

    # Auto-sync voice config only when changed
    new_v_state = dict(chosen_v, accent=sel_accent, rate=final_rate, pitch=final_pitch, script_mode=sel_script_mode)
    if new_v_state != cur_v_cfg:
        save_active_voice(new_v_state)
        cur_v_cfg = new_v_state

    aud_text = st.text_input("Audition Phrase:", value=DEFAULT_SAMPLE_TEXTS[sel_accent])
    if st.button("🔊 Listen to Voice Sample", width="stretch"):
        with st.spinner("Synthesizing preview..."):
            mp3_p = synthesize_preview_sample(chosen_v["voice"], final_rate, final_pitch, aud_text)
            st.session_state["sb_audition_mp3"] = str(mp3_p)

    if st.session_state.get("sb_audition_mp3") and Path(st.session_state["sb_audition_mp3"]).exists():
        st.audio(st.session_state["sb_audition_mp3"], format="audio/mp3", autoplay=True)

    st.divider()

    # 3. Quick Pinterest Downloader in Sidebar
    st.markdown("### 📌 Pinterest Quick-Grab")
    pin_in = st.text_input("Paste Pin URL (Video or Image):", placeholder="https://pin.it/...")
    if st.button("📥 Download Pin to Studio", width="stretch") and pin_in.strip():
        with st.spinner("Downloading & sorting Pin..."):
            saved_p = backend.download_pinterest_media(pin_in.strip(), sync_to_studio=True)
            if saved_p:
                st.success(f"Saved: {saved_p.name}")
                time.sleep(0.6)
                st.rerun()
            else:
                st.error("Failed to grab Pin.")

# ==============================================================================
# TOP NAVBAR & 4-COLUMN KPI METRICS ROW
# ==============================================================================
st.markdown(f"""
<div class="top-nav">
    <div>
        <div class="nav-title">✝️ DailyWisdom & Prayer AI Studio</div>
        <div class="nav-sub">Full-Stack Viral Shorts Engine • 1080x1920 @ 30fps • Multi-Channel YouTube Publisher</div>
    </div>
    <div>
        <span class="status-pill">🎙️ {cur_v_cfg['name'].split('—')[0].strip()}</span>
        <span class="status-pill">📺 {active_channel}</span>
        <span class="status-pill">🟢 AI Engine Online</span>
    </div>
</div>
""", unsafe_allow_html=True)

k1, k2, k3, k4 = st.columns(4)
with k1:
    st.markdown(f'<div class="kpi-card"><div class="kpi-label">Total Sequential Shorts</div><div class="kpi-val">{len(all_videos)}</div><div class="kpi-sub">Sorted in clips/001_...</div></div>', unsafe_allow_html=True)
with k2:
    st.markdown(f'<div class="kpi-card"><div class="kpi-label">Ready to Upload</div><div class="kpi-val">{pending_count}</div><div class="kpi-sub">{uploaded_count} Already Live on YouTube</div></div>', unsafe_allow_html=True)
with k3:
    pin_v_cnt = len(get_media_files(backend.PIN_VID_DIR, (".mp4",))) if hasattr(backend, "PIN_VID_DIR") else 0
    pin_i_cnt = len(get_media_files(backend.PIN_IMG_DIR, (".jpg", ".png"))) if hasattr(backend, "PIN_IMG_DIR") else 0
    st.markdown(f'<div class="kpi-card"><div class="kpi-label">Pinterest Media Vault</div><div class="kpi-val">{pin_v_cnt + pin_i_cnt}</div><div class="kpi-sub">{pin_v_cnt} Videos • {pin_i_cnt} HD Images</div></div>', unsafe_allow_html=True)
with k4:
    st.markdown(f'<div class="kpi-card"><div class="kpi-label">Active Voice & Mode</div><div class="kpi-val">{cur_v_cfg["accent"].split()[1]}</div><div class="kpi-sub">{cur_v_cfg["script_mode"].split("(")[0].strip()}</div></div>', unsafe_allow_html=True)

st.write("")

# ==============================================================================
# MAIN WORKSPACE TABS (FILLS 100% OF SCREEN)
# ==============================================================================
tab1, tab2, tab3, tab4 = st.tabs([
    "✝️ 1. Bible Short Creation Workspace",
    "📁 2. Sequential Video Library & 1-Click Publisher",
    "🎙️ 3. Podcast Clipper & YouTube Downloader",
    "🔥 4. Virality Engine & Competitor Spy",
])

# ------------------------------------------------------------------------------
# TAB 1: 3-COLUMN CREATION WORKSPACE (LEFT: SCRIPT, CENTER: VISUALS, RIGHT: PREVIEW)
# ------------------------------------------------------------------------------
with tab1:
    col_left, col_mid, col_right = st.columns([1.15, 1.25, 1.4], gap="medium")

    with col_left:
        with st.container(border=True):
            st.markdown("#### 🧠 Step 1: Choose Topic OR Exact Bible Verse")
            from bible_database import TOP_50_PRAYER_TOPICS, BIBLE_66_BOOKS, get_verses_for_chapter, translate_verse_to_hindi

            selection_mode = st.radio(
                "Selection Mode:",
                [
                    "🔥 50 Most-Searched Life Prayer Topics",
                    "📖 Full Bible Browser (Book ➔ Chapter ➔ Verse)",
                    "✍️ Custom Prayer Topic",
                ],
                index=0,
            )

            exact_book, exact_ch, exact_v = None, None, None

            if selection_mode == "🔥 50 Most-Searched Life Prayer Topics":
                topic_labels = [f"{item['id']}. {item['topic']} ({item['ref']})" for item in TOP_50_PRAYER_TOPICS]
                chosen_label = st.selectbox("Select from 50 High-Search Prayer Topics:", topic_labels)
                chosen_obj = TOP_50_PRAYER_TOPICS[topic_labels.index(chosen_label)]
                final_topic = f"{chosen_obj['topic']} (Suggested Verse: {chosen_obj['ref']})"
                st.caption(f"📖 **Recommended Scripture:** `{chosen_obj['ref']}` | **Category:** `{chosen_obj['cat']}`")

            elif selection_mode == "📖 Full Bible Browser (Book ➔ Chapter ➔ Verse)":
                book_labels = [f"{i+1:02d}. {b_en.strip()} — {b_hi}" for i, (b_en, b_hi, _) in enumerate(BIBLE_66_BOOKS)]
                sel_b_label = st.selectbox("1. Choose Bible Book (All 66 Books):", book_labels, index=18)
                b_idx = book_labels.index(sel_b_label)
                exact_book, b_hi_name, max_chapters = BIBLE_66_BOOKS[b_idx]
                exact_book = exact_book.strip()

                ch_col, v_col = st.columns(2)
                with ch_col:
                    exact_ch = st.selectbox("2. Chapter:", list(range(1, max_chapters + 1)), index=0)

                verses_dict = get_verses_for_chapter(exact_book, exact_ch)
                v_numbers = list(verses_dict.keys()) if verses_dict else [1]
                with v_col:
                    exact_v = st.selectbox(
                        "3. Verse:",
                        v_numbers,
                        format_func=lambda vn: f"Verse {vn}: {verses_dict.get(vn, '')[:32]}..."
                    )

                en_preview = verses_dict.get(exact_v, "")
                st.success(f"🇬🇧 **English ({exact_book} {exact_ch}:{exact_v}):** \"{en_preview}\"")

                if st.checkbox("🇮🇳 Show Hindi / Hinglish Translation Preview", value=("Hindi" in cur_v_cfg.get("script_mode", ""))):
                    dev_hi, rom_hi = translate_verse_to_hindi(f"{exact_book} {exact_ch}:{exact_v}", en_preview)
                    if dev_hi:
                        st.info(f"🇮🇳 **Hindi (पवित्र बाइबिल):** {dev_hi} | **Hinglish:** *{rom_hi}*")

                final_topic = f"{exact_book} {exact_ch}:{exact_v}"

            else:
                custom_topic = st.text_input("Type Any Custom Prayer Topic:", value="Exam & Career Success")
                final_topic = custom_topic.strip() or "Peace & Strength"

            palette_style = st.selectbox("Thumbnail & Accent Palette:", ["Gold Classic", "Midnight Blue", "Sunrise", "Crimson Glory"])
            raw_thumb_toggle = st.checkbox("Use uploaded thumbnail image raw (No 3D text overlay)", value=False)

            st.caption(f"🎙️ **Voice:** `{cur_v_cfg['name']}` | **Mode:** `{cur_v_cfg['script_mode']}`")
            gen_clicked = st.button("✨ GENERATE BIBLE SHORT NOW", width="stretch")

    with col_mid:
        with st.container(border=True):
            st.markdown("#### 🎨 Step 2: Visuals & Thumbnail Picker")

            intro_files = get_media_files(backend.INTRO_DIR, (".mp4", ".mov", ".webm", ".mkv"))
            bg_files = get_media_files(backend.BG_DIR, (".jpg", ".jpeg", ".png", ".webp"))
            thumb_files = get_media_files(backend.THUMB_DIR, (".jpg", ".jpeg", ".png", ".webp"))

            pick_intro_name = st.selectbox("📹 10s Intro Video (Auto-Muted):", ["Auto / Newest"] + [f.name for f in intro_files])
            up_intro = st.file_uploader("Or Drop New Intro Video:", type=["mp4", "mov", "webm"], label_visibility="collapsed", key="u_int")

            pick_bg_name = st.selectbox("🖼️ Main Background Image (10s-End):", ["Auto / Newest"] + [f.name for f in bg_files])
            up_bg = st.file_uploader("Or Drop New Background Image:", type=["jpg", "jpeg", "png", "webp"], label_visibility="collapsed", key="u_bg")

            pick_thumb_name = st.selectbox("🔥 Thumbnail Background:", ["Same as Main Background"] + [f.name for f in thumb_files])
            up_thumb = st.file_uploader("Or Drop Custom Thumbnail Image:", type=["jpg", "jpeg", "png", "webp"], label_visibility="collapsed", key="u_th")

            # Live miniature visual preview of selected background
            preview_bg_path = None
            if pick_bg_name != "Auto / Newest" and (backend.BG_DIR / pick_bg_name).exists():
                preview_bg_path = backend.BG_DIR / pick_bg_name
            elif bg_files:
                preview_bg_path = bg_files[0]

            if preview_bg_path and preview_bg_path.exists():
                with st.expander("👁️ Preview Selected Background Image", expanded=False):
                    st.image(str(preview_bg_path), caption=f"Selected: {preview_bg_path.name}", width="stretch")

    if gen_clicked:
        with col_left:
            status = st.empty()
            prog = st.progress(0)

            status.info(f"🧠 [1/4] Generating Scripture & Prayer for '{final_topic}'...")
            prog.progress(20)
            if exact_book and exact_ch and exact_v:
                script = backend.generate_bible_content_from_exact_verse(exact_book, exact_ch, exact_v)
            else:
                script = backend.generate_bible_content(final_topic)

            status.info(f"🎙️ [2/4] Speaking with {cur_v_cfg['name']}...")
            prog.progress(45)
            voice_script = build_spoken_voice_script(script)
            temp_voice = backend.BASE_DIR / "temp_voice.mp3"
            backend.generate_voiceover(voice_script, temp_voice)

            status.info("⚡ [3/4] Fast-Rendering 1080p Video & Multi-Thumbnail Suite...")
            prog.progress(70)
            clean_name = backend.clean_filename(f"Bible_{script.topic}_{script.verse_citation}")
            seq_dir = backend.get_next_sequence_folder(clean_name)
            out_video = seq_dir / f"{clean_name}.mp4"
            out_thumb = seq_dir / f"{clean_name}_thumb.jpg"

            c_intro_path = None
            if up_intro is not None:
                c_intro_path = backend.INTRO_DIR / f"{backend.clean_filename(Path(up_intro.name).stem)}{Path(up_intro.name).suffix.lower()}"
                c_intro_path.write_bytes(up_intro.getvalue())
                c_intro_path = backend.mute_any_video(c_intro_path)
            elif pick_intro_name != "Auto / Newest":
                c_intro_path = backend.mute_any_video(backend.INTRO_DIR / pick_intro_name)
            elif intro_files:
                c_intro_path = backend.mute_any_video(intro_files[0])

            c_bg_path = None
            if up_bg is not None:
                c_bg_path = backend.BG_DIR / f"{backend.clean_filename(Path(up_bg.name).stem)}{Path(up_bg.name).suffix.lower()}"
                c_bg_path.write_bytes(up_bg.getvalue())
            elif pick_bg_name != "Auto / Newest":
                c_bg_path = backend.BG_DIR / pick_bg_name
            elif bg_files:
                c_bg_path = bg_files[0]

            c_thumb_path = None
            if up_thumb is not None:
                c_thumb_path = backend.THUMB_DIR / f"{backend.clean_filename(Path(up_thumb.name).stem)}{Path(up_thumb.name).suffix.lower()}"
                c_thumb_path.write_bytes(up_thumb.getvalue())
            elif pick_thumb_name != "Same as Main Background":
                c_thumb_path = backend.THUMB_DIR / pick_thumb_name
            else:
                c_thumb_path = c_bg_path

            ok = backend.render_faceless_bible_video(
                script, temp_voice, out_video, out_thumb,
                custom_intro=c_intro_path, custom_bg=c_bg_path,
                custom_thumb=c_thumb_path, raw_thumb_only=raw_thumb_toggle
            )
            if temp_voice.exists():
                temp_voice.unlink(missing_ok=True)

            if ok:
                status.info("🔥 [4/4] Running Virality Engine (Title & SEO Optimization)...")
                prog.progress(90)
                raw_desc = (
                    f"If you are dealing with {script.topic}, let this powerful scripture speak to your spirit.\n\n"
                    f"📖 Scripture: {script.verse_citation}\n\"{script.verse_text}\"\n\n"
                    f"💡 Reflection:\n{script.meaning}\n\n"
                    f"🙏 Prayer:\n{script.prayer}\n\n"
                    f"Type \"AMEN\" in the comments if you receive this word today! 🙏\n\n"
                    f"---\nDisclaimer: As an Amazon Associate, I earn from qualifying purchases at no extra cost to you."
                )
                opt_title, opt_desc, opt_tags = backend.optimize_with_virality_engine(
                    script.topic, script.title, raw_desc, script.hashtags + ["Bible", "Jesus", "Prayer"], active_channel
                )
                backend.save_clip_metadata(out_video, opt_title, opt_desc, opt_tags)
                prog.progress(100)
                status.success(f"🎉 Created `{seq_dir.name}`!")
                st.session_state["last_created_video"] = str(out_video)
                time.sleep(0.5)
                st.rerun()

    with col_right:
        with st.container(border=True):
            st.markdown("#### 🎬 Step 3: Live Output Monitor & Instant Publish")
            target_preview = st.session_state.get("last_created_video")
            if not target_preview or not Path(target_preview).exists():
                target_preview = str(all_videos[0]) if all_videos else None

            if not target_preview:
                st.info("Your generated Short, Graphical Thumbnails, and 1-Click YouTube Upload buttons will appear right here!")
            else:
                vp = Path(target_preview)
                tp_jpg = vp.with_name(f"{vp.stem}_thumb.jpg")
                tp_16x9 = vp.parent / "thumbnail_16x9.png"
                meta = backend.load_clip_metadata(vp)

                st.caption(f"📂 Folder: `{vp.parent.name}`")
                v_sub1, v_sub2 = st.columns([1.15, 1])
                with v_sub1:
                    st.video(str(vp))
                with v_sub2:
                    if tp_jpg.exists():
                        st.image(str(tp_jpg), caption="9:16 Thumbnail", width="stretch")
                    if tp_16x9.exists():
                        st.image(str(tp_16x9), caption="16:9 Thumbnail", width="stretch")

                st.markdown(f"**Winning Title:** `{meta['title']}`")
                with st.expander("📝 View / Copy Description & SEO Tags"):
                    st.text_area("Description:", value=meta["description"], height=130, key="mon_desc")

                if meta.get("youtube_id"):
                    st.success(f"✅ Live on YouTube! https://youtube.com/shorts/{meta['youtube_id']}")
                else:
                    p_cols = st.columns(len(channel_names))
                    for idx_c, ch_n in enumerate(channel_names):
                        with p_cols[idx_c]:
                            if st.button(f"🚀 Post to {ch_n[:18]}", key=f"mon_up_{ch_n}", width="stretch"):
                                with st.spinner(f"Publishing to {ch_n}..."):
                                    yt_id = backend.upload_video_to_youtube(ch_n, vp)
                                    if yt_id:
                                        st.success(f"Live! https://youtube.com/shorts/{yt_id}")
                                        time.sleep(1)
                                        st.rerun()

# ------------------------------------------------------------------------------
# TAB 2: SEQUENTIAL VIDEO LIBRARY (3-COLUMN FULL-SCREEN GRID)
# ------------------------------------------------------------------------------
with tab2:
    st.markdown("### 📁 Sequential Shorts Vault (`001_`, `002_`, `003_...`)")
    if not all_videos:
        st.info("No videos generated yet.")
    else:
        for i in range(0, len(all_videos), 3):
            cols = st.columns(3, gap="medium")
            for j in range(3):
                if i + j < len(all_videos):
                    vid = all_videos[i + j]
                    thumb = vid.with_name(f"{vid.stem}_thumb.jpg")
                    meta = backend.load_clip_metadata(vid)
                    with cols[j]:
                        with st.container(border=True):
                            badge = "🟢 LIVE" if meta.get("youtube_id") else "🟡 READY"
                            st.markdown(f"**📂 `{vid.parent.name}`** — `{badge}`")
                            vc_a, vc_b = st.columns([1.15, 1])
                            with vc_a:
                                st.video(str(vid))
                            with vc_b:
                                if thumb.exists():
                                    st.image(str(thumb), width="stretch")
                            st.caption(f"📌 **{meta['title']}**")

                            if meta.get("youtube_id"):
                                st.success(f"https://youtube.com/shorts/{meta['youtube_id']}")
                            else:
                                for ch_name in channel_names:
                                    if st.button(f"🚀 Upload to {ch_name}", key=f"grid_up_{vid.parent.name}_{ch_name}", width="stretch"):
                                        with st.spinner(f"Uploading to {ch_name}..."):
                                            yt_id = backend.upload_video_to_youtube(ch_name, vid)
                                            if yt_id:
                                                st.rerun()

                            if st.button(f"🗑️ Delete {vid.parent.name}", key=f"grid_del_{vid.parent.name}", width="stretch"):
                                shutil.rmtree(vid.parent, ignore_errors=True)
                                st.rerun()

# ------------------------------------------------------------------------------
# TAB 3: PODCAST CLIPPER + YOUTUBE MP3/MP4 DOWNLOADERS
# ------------------------------------------------------------------------------
with tab3:
    p_c1, p_c2, p_c3 = st.columns(3, gap="medium")

    with p_c1:
        with st.container(border=True):
            st.markdown("#### 🎙️ 1. Auto-Scout 1M+ View Podcasts")
            cat_map = {v["name"]: k for k, v in backend.CATEGORIES.items()}
            chosen_cat_name = st.selectbox("Select Niche:", list(cat_map.keys()))
            cat_cfg = backend.CATEGORIES[cat_map[chosen_cat_name]]
            if st.button(f"⚡ Auto-Scout & Clip '{chosen_cat_name}'", width="stretch"):
                with st.spinner("Hunting 1M+ view videos..."):
                    target = backend.find_viral_video(1_000_000, cat_cfg["queries"])
                    if not target:
                        st.warning("No new unprocessed 1M+ view videos found.")
                    else:
                        tr = backend.get_transcript(target["id"])
                        clips = backend.analyze_transcript(tr, chosen_cat_name) if tr else backend.analyze_audio_fallback(target["url"], chosen_cat_name)
                        for clip in clips:
                            s_sec = backend.timestamp_to_seconds(clip.start_time)
                            e_sec = backend.timestamp_to_seconds(clip.end_time)
                            tmp = backend.BASE_DIR / "temp_slice.mp4"
                            try:
                                backend.download_slice(target["url"], s_sec, e_sec, tmp)
                                seq_name = f"{backend.clean_filename(clip.book_title)}_{backend.clean_filename(clip.title)}"
                                seq_dir = backend.get_next_sequence_folder(seq_name)
                                out_f = seq_dir / f"{seq_name}.mp4"
                                if backend.render_podcast_short(tmp, clip, out_f, cat_cfg["badge_tag"]):
                                    opt_t, opt_d, opt_tags = backend.optimize_with_virality_engine(chosen_cat_name, clip.title, clip.hook_caption, clip.hashtags, active_channel)
                                    backend.save_clip_metadata(out_f, opt_t, opt_d, opt_tags)
                                    st.success(f"Created `{seq_dir.name}`!")
                            finally:
                                tmp.unlink(missing_ok=True)

    with p_c2:
        with st.container(border=True):
            st.markdown("#### 🔗 2. Clip Custom YouTube URL")
            c_url = st.text_input("YouTube Video Link:")
            tm1, tm2 = st.columns(2)
            with tm1:
                m_start = st.text_input("Start (e.g. 00:10):", "")
            with tm2:
                m_end = st.text_input("End (e.g. 00:50):", "")
            if st.button("⚡ Clip Custom URL", width="stretch") and c_url.strip():
                m = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", c_url)
                if m:
                    with st.spinner("Clipping video..."):
                        vid_id = m.group(1)
                        if m_start.strip() and m_end.strip():
                            clips = [backend.BookClip(title="Highlight", start_time=m_start.strip(), end_time=m_end.strip(), book_title="Highlight", book_author="Studio", hook_caption="Watch this.", hashtags=["#Shorts"])]
                        else:
                            tr = backend.get_transcript(vid_id)
                            clips = backend.analyze_transcript(tr, "Wisdom") if tr else backend.analyze_audio_fallback(c_url.strip(), "Wisdom")
                        for clip in clips:
                            s_sec, e_sec = backend.timestamp_to_seconds(clip.start_time), backend.timestamp_to_seconds(clip.end_time)
                            tmp = backend.BASE_DIR / "temp_slice.mp4"
                            try:
                                backend.download_slice(c_url.strip(), s_sec, e_sec, tmp)
                                seq_name = f"{backend.clean_filename(clip.book_title)}_{backend.clean_filename(clip.title)}"
                                seq_dir = backend.get_next_sequence_folder(seq_name)
                                out_f = seq_dir / f"{seq_name}.mp4"
                                if backend.render_podcast_short(tmp, clip, out_f, "HIGHLIGHT"):
                                    backend.save_clip_metadata(out_f, clip.title, clip.hook_caption, clip.hashtags)
                                    st.success(f"Created `{seq_dir.name}`!")
                            finally:
                                tmp.unlink(missing_ok=True)

    with p_c3:
        with st.container(border=True):
            st.markdown("#### 📥 3. Direct YouTube MP3 / MP4 Downloader")
            dl_url = st.text_input("Paste YouTube URL to Download:", key="dl_yt_box")
            if st.button("🎵 Download Audio (MP3 192kbps)", width="stretch") and dl_url.strip():
                with st.spinner("Extracting MP3 to downloads/ folder..."):
                    subprocess.run(["yt-dlp", "-x", "--audio-format", "mp3", "-o", str(backend.DOWNLOADS_DIR / "%(title)s.%(ext)s"), dl_url.strip()])
                    st.success("Saved MP3 in `downloads/` folder!")
            if st.button("📹 Download Full HD Video (1080p MP4)", width="stretch") and dl_url.strip():
                with st.spinner("Downloading 1080p MP4 to downloads/ folder..."):
                    subprocess.run(["yt-dlp", "-f", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best", "--merge-output-format", "mp4", "-o", str(backend.DOWNLOADS_DIR / "%(title)s.%(ext)s"), dl_url.strip()])
                    st.success("Saved 1080p MP4 in `downloads/` folder!")

# ------------------------------------------------------------------------------
# TAB 4: VIRALITY ENGINE & COMPETITOR SPY
# ------------------------------------------------------------------------------
with tab4:
    v_left, v_right = st.columns(2, gap="medium")
    with v_left:
        with st.container(border=True):
            st.markdown(f"#### 🏆 Top Performing Shorts on `{active_channel}`")
            if st.button("🔄 Fetch Live Channel Analytics", width="stretch"):
                backend._CHANNEL_STATS_CACHE.pop(active_channel, None)
                my_shorts = backend.get_my_top_shorts(active_channel, max_results=10)
                if not my_shorts:
                    st.info("No public videos indexed yet.")
                else:
                    for idx, s in enumerate(my_shorts):
                        st.markdown(f"**#{idx + 1}. {s['title']}** — 👁️ `{s['views']:,}` | 👍 `{s['likes']}` | 💬 `{s['comments']}`")

    with v_right:
        with st.container(border=True):
            st.markdown("#### 🔍 Competitor Title Spy & SEO Generator")
            spy_q = st.text_input("Topic / Keyword to Spy On:", value="Miracle Debt Prayer")
            if st.button("🔥 Spy on Competitors & Generate Winning Title", width="stretch"):
                with st.spinner("Analyzing top YouTube Shorts..."):
                    comps = backend.scan_competitor_shorts(spy_q)
                    for c in comps[:5]:
                        st.caption(f"🔥 **{c['title']}** — `{c['views']:,} views`")
                    win_t, _, win_tags = backend.optimize_with_virality_engine(spy_q, f"Prayer for {spy_q}", "", ["Shorts"], active_channel)
                    st.success(f"🚀 **Winning Title:** `{win_t}`")
                    st.code(", ".join(win_tags), language="text")
