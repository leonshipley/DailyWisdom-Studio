import os
import re
import time
from pathlib import Path
import streamlit as st

import main as backend

st.set_page_config(page_title="DailyWisdom & Prayer Studio", page_icon="✝️", layout="wide")

st.markdown("""
<style>
    .main-header { font-size: 30px; font-weight: 800; color: #FFD700; margin-bottom: 2px; }
    .sub-header { font-size: 14px; color: #9CA3AF; margin-bottom: 18px; }
    .stButton>button {
        background: linear-gradient(90deg, #FFD700, #CA8A04);
        color: #0B0F19;
        font-weight: 800;
        border-radius: 8px;
        border: none;
    }
    .seq-card {
        background-color: #111827;
        border: 1px solid #374151;
        border-radius: 12px;
        padding: 14px;
        margin-bottom: 16px;
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-header">✝️ DailyWisdom & Prayer Studio (Frontend + Backend Connected)</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Connected directly to main.py • 102pt Synced Subtitles • Graphical Pillow Thumbnails • AI Virality Engine • Sequential Folders</div>', unsafe_allow_html=True)

# --- TOP BAR: MULTI-CHANNEL SELECTOR ---
channels = backend.load_channels()
channel_names = list(channels.keys())

col_ch1, col_ch2, col_ch3, col_ch4 = st.columns([2, 1.5, 1, 1.2])
with col_ch1:
    if channel_names:
        active_channel = st.selectbox("📺 Default Target YouTube Channel:", channel_names)
    else:
        st.warning("⚠️ No channels connected yet.")
        active_channel = "TheDailyWisdom_Hub"

with col_ch2:
    seq_folders = sorted([d for d in backend.CLIPS_DIR.iterdir() if d.is_dir() and re.match(r"^\d{3}_", d.name)], reverse=True)
    st.metric("📁 Sequential Video Folders in clips/", len(seq_folders))

with col_ch3:
    st.write("")
    if st.button("➕ Connect Channel", width="stretch"):
        new_ch = backend.connect_new_channel()
        if new_ch:
            st.success(f"Connected {new_ch}!")
            st.rerun()

with col_ch4:
    st.write("")
    if st.button("☁️ Save to GitHub", width="stretch"):
        with st.spinner("Saving & pushing to GitHub..."):
            ok, msg = backend.save_everything_to_git()
            if ok:
                st.toast("Saved to GitHub!", icon="✅")
                st.success(msg)
            else:
                st.warning(msg)

st.divider()

# --- 4 CLICKABLE STUDIO TABS ---
tab_bible, tab_podcast, tab_virality, tab_library = st.tabs([
    "✝️ 1. Bible Short & Thumbnail Studio",
    "🎙️ 2. Podcast & Custom URL Clipper",
    "🔥 3. Virality Engine & Competitor Spy",
    "📁 4. Sequential Folders & 1-Click Uploader"
])

# =========================================================
# TAB 1: BIBLE SHORT GENERATOR
# =========================================================
with tab_bible:
    st.subheader("📖 Generate Faceless Bible Short + Graphical Thumbnail")

    c1, c2 = st.columns([1, 1])
    with c1:
        preset_topics = [v["topic"] for v in backend.CURATED_BIBLE_VAULT.values()]
        picked = st.selectbox("Quick-Pick Popular Prayer Topic:", preset_topics)
    with c2:
        custom_t = st.text_input("Or Type Custom Topic (Leave blank to use Quick-Pick):", placeholder="e.g. Marriage Restoration, Exam Success, Sleep Peace")

    final_topic = custom_t.strip() if custom_t.strip() else picked

    st.markdown("#### 📌 Download from Pinterest (Auto-Sorted into `Pinterest/Images` & `Pinterest/Videos` + Auto-Muted)")
    p_col1, p_col2 = st.columns([3, 1])
    with p_col1:
        pin_url_input = st.text_input("Paste Pinterest Link (Image or Video Pin):", placeholder="https://pin.it/... or https://www.pinterest.com/pin/...", key="pin_url_box")
    with p_col2:
        st.write("")
        if st.button("📌 Download Pin & Add to Studio", width="stretch"):
            if pin_url_input.strip():
                with st.spinner("Downloading from Pinterest, sorting & auto-muting..."):
                    saved_pin = backend.download_pinterest_media(pin_url_input.strip(), sync_to_studio=True)
                    if saved_pin:
                        st.success(f"✅ Saved `{saved_pin.name}` in `Pinterest/{saved_pin.parent.name}/` & added to dropdowns below!")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("Could not extract media from that Pinterest link.")

    st.markdown("#### 🎨 Custom Background & Thumbnail (Just Upload — Everything Else Is Automatic!)")
    up_col1, up_col2, up_col3 = st.columns(3)

    with up_col1:
        up_intro = st.file_uploader("📹 1. Upload Intro Video (0-10s, Auto-Muted)", type=["mp4", "mov", "webm", "mkv"], key="up_intro")
        saved_intros = ["Auto / Default"] + [f.name for f in sorted(backend.INTRO_DIR.glob("*.*"), key=lambda x: x.stat().st_mtime, reverse=True) if f.is_file()]
        pick_intro_name = st.selectbox("Or pick saved Intro Video:", saved_intros)

    with up_col2:
        up_bg = st.file_uploader("🖼️ 2. Upload Main Background Image (10s-End)", type=["jpg", "jpeg", "png", "webp"], key="up_bg")
        saved_bgs = ["Auto / Default"] + [f.name for f in sorted(backend.BG_DIR.glob("*.*"), key=lambda x: x.stat().st_mtime, reverse=True) if f.is_file()]
        pick_bg_name = st.selectbox("Or pick saved Background Image:", saved_bgs)

    with up_col3:
        up_thumb = st.file_uploader("🔥 3. Upload Thumbnail Image", type=["jpg", "jpeg", "png", "webp"], key="up_thumb")
        saved_thumbs = ["Same as Background Image"] + [f.name for f in sorted(backend.THUMB_DIR.glob("*.*"), key=lambda x: x.stat().st_mtime, reverse=True) if f.is_file()]
        pick_thumb_name = st.selectbox("Or pick saved Thumbnail:", saved_thumbs)
        raw_thumb_toggle = st.checkbox("Use uploaded thumbnail as-is (Don't add 3D text)", value=False)

    if st.button(f"✨ Generate Bible Short for '{final_topic}'", width="stretch"):
        status = st.empty()
        prog = st.progress(0)

        status.info(f"🧠 [1/4] AI generating unique Scripture & Prayer for '{final_topic}'...")
        prog.progress(20)
        script = backend.generate_bible_content(final_topic)

        status.info("🎙️ [2/4] Generating solemn narrator voiceover & millisecond word timings...")
        prog.progress(45)
        voice_script = f"If you are struggling with {script.topic}, hold onto this verse. {script.verse_citation}. {script.verse_text}. {script.meaning}. Let us pray. {script.prayer} Type Amen in the comments to receive this blessing."
        temp_voice = backend.BASE_DIR / "temp_voice.mp3"
        backend.generate_voiceover(voice_script, temp_voice)

        status.info("🎨 [3/4] Rendering 102pt Video (10s Short_Main + Jesus_Lord) & Graphical Thumbnail...")
        prog.progress(70)
        clean_name = backend.clean_filename(f"Bible_{script.topic}_{script.verse_citation}")
        seq_dir = backend.get_next_sequence_folder(clean_name) if hasattr(backend, "get_next_sequence_folder") else backend.CLIPS_DIR
        out_video = seq_dir / f"{clean_name}.mp4"
        out_thumb = seq_dir / f"{clean_name}_thumb.jpg"

        # Automatically save & process any uploaded files
        c_intro_path = None
        if up_intro is not None:
            c_intro_path = backend.INTRO_DIR / backend.clean_filename(Path(up_intro.name).stem)
            c_intro_path = c_intro_path.with_suffix(Path(up_intro.name).suffix)
            c_intro_path.write_bytes(up_intro.getvalue())
            c_intro_path = backend.mute_any_video(c_intro_path)
        elif pick_intro_name != "Auto / Default":
            c_intro_path = backend.mute_any_video(backend.INTRO_DIR / pick_intro_name)

        c_bg_path = None
        if up_bg is not None:
            c_bg_path = backend.BG_DIR / f"{backend.clean_filename(Path(up_bg.name).stem)}{Path(up_bg.name).suffix}"
            c_bg_path.write_bytes(up_bg.getvalue())
        elif pick_bg_name != "Auto / Default":
            c_bg_path = backend.BG_DIR / pick_bg_name

        c_thumb_path = None
        if up_thumb is not None:
            c_thumb_path = backend.THUMB_DIR / f"{backend.clean_filename(Path(up_thumb.name).stem)}{Path(up_thumb.name).suffix}"
            c_thumb_path.write_bytes(up_thumb.getvalue())
        elif pick_thumb_name != "Same as Background Image":
            c_thumb_path = backend.THUMB_DIR / pick_thumb_name
        else:
            c_thumb_path = c_bg_path

        ok = backend.render_faceless_bible_video(
            script, temp_voice, out_video, out_thumb,
            custom_intro=c_intro_path, custom_bg=c_bg_path,
            custom_thumb=c_thumb_path, raw_thumb_only=raw_thumb_toggle
        )
        if temp_voice.exists():
            temp_voice.unlink()

        if ok:
            status.info("🔥 [4/4] Running Virality Engine (Comparing with Competitors & Your Top Shorts)...")
            prog.progress(90)
            raw_desc = (
                f"If you are dealing with {script.topic}, let this powerful scripture speak to your spirit.\n\n"
                f"📖 Scripture: {script.verse_citation}\n\"{script.verse_text}\"\n\n"
                f"💡 Reflection:\n{script.meaning}\n\n"
                f"🙏 Prayer:\n{script.prayer}\n\n"
                f"Type \"AMEN\" in the comments if you receive this word today! 🙏\n\n"
                f"---\nDisclaimer: As an Amazon Associate, I earn from qualifying purchases at no extra cost to you."
            )
            if hasattr(backend, "optimize_with_virality_engine"):
                opt_title, opt_desc, opt_tags = backend.optimize_with_virality_engine(
                    script.topic, script.title, raw_desc, script.hashtags + ["Bible", "Jesus", "Prayer"], active_channel
                )
            else:
                opt_title, opt_desc, opt_tags = script.title, raw_desc, script.hashtags

            backend.save_clip_metadata(out_video, opt_title, opt_desc, opt_tags)
            prog.progress(100)
            status.success(f"🎉 Created in folder `{seq_dir.name}/`! Switch to Tab 4 or use the uploader below.")
            st.session_state["last_created_video"] = str(out_video)

    last_vid = st.session_state.get("last_created_video")
    if last_vid and Path(last_vid).exists():
        v_path = Path(last_vid)
        t_path = v_path.with_name(f"{v_path.stem}_thumb.jpg")
        meta = backend.load_clip_metadata(v_path)
        st.divider()
        st.markdown(f"### 🎬 Latest Created Short: `{v_path.parent.name}`")
        cv, ct, ci = st.columns([1.5, 1.2, 2])
        with cv:
            st.video(str(v_path))
        with ct:
            if t_path.exists():
                st.image(str(t_path), caption="Graphical Thumbnail", width="stretch")
        with ci:
            st.markdown(f"**Winning Title:** `{meta['title']}`")
            st.text_area("Optimized Description & Pinned Comment:", value=meta["description"], height=200, key="last_desc_preview")
            st.write("**Choose Channel to Upload To:**")
            for ch in channel_names:
                if st.button(f"🚀 Upload Now to {ch}", key=f"imm_up_{ch}", width="stretch"):
                    with st.spinner(f"Uploading to {ch}..."):
                        yt_id = backend.upload_video_to_youtube(ch, v_path)
                        if yt_id:
                            st.success(f"🎉 Live on {ch}! https://youtube.com/shorts/{yt_id}")

# =========================================================
# TAB 2: PODCAST & CUSTOM URL CLIPPER
# =========================================================
with tab_podcast:
    st.subheader("🎙️ Viral Podcast Clipper (1M+ Views) & Custom URL Clipper")
    col_p1, col_p2 = st.columns([1, 1])

    with col_p1:
        st.markdown("#### Mode A: Auto-Scout 1M+ View Videos")
        cat_map = {v["name"]: k for k, v in backend.CATEGORIES.items()}
        chosen_cat_name = st.selectbox("Select Niche Category:", list(cat_map.keys()))
        cat_cfg = backend.CATEGORIES[cat_map[chosen_cat_name]]

        if st.button(f"⚡ Auto-Scout & Clip '{chosen_cat_name}'", width="stretch"):
            with st.spinner("Scanning influencer channels for 1M+ view videos..."):
                target = backend.find_viral_video(1_000_000, cat_cfg["queries"])
                if not target:
                    st.warning("No new unprocessed 1M+ view videos found.")
                else:
                    st.info(f"Found: {target['title']} ({target['views']:,} views)")
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
                                desc = f"{clip.hook_caption}\n\n📖 Featured Book: {clip.book_title} ({clip.book_author})\n👉 Link in channel bio!\n\n---\nDisclaimer: As an Amazon Associate, I earn from qualifying purchases."
                                opt_t, opt_d, opt_tags = backend.optimize_with_virality_engine(chosen_cat_name, clip.title, desc, clip.hashtags, active_channel)
                                backend.save_clip_metadata(out_f, opt_t, opt_d, opt_tags)
                                st.success(f"Created in `{seq_dir.name}/`!")
                        finally:
                            if tmp.exists():
                                tmp.unlink()

    with col_p2:
        st.markdown("#### Mode B: Custom YouTube URL")
        c_url = st.text_input("Paste YouTube URL:")
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            man_start = st.text_input("Start Time (Optional, e.g. 00:10):", value="")
        with col_m2:
            man_end = st.text_input("End Time (Optional, e.g. 00:50):", value="")

        if st.button("⚡ Clip Custom Video", width="stretch") and c_url.strip():
            m = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", c_url)
            if not m:
                st.error("Invalid YouTube URL.")
            else:
                vid_id = m.group(1)
                with st.spinner("Processing custom video..."):
                    if man_start.strip() and man_end.strip():
                        clips = [backend.BookClip(title="Inspiring Highlight", start_time=man_start.strip(), end_time=man_end.strip(), book_title="Special Highlight", book_author="Daily Wisdom", hook_caption="Watch this powerful moment.", hashtags=["#Shorts", "#Wisdom"])]
                    else:
                        tr = backend.get_transcript(vid_id)
                        clips = backend.analyze_transcript(tr, "Wisdom") if tr else backend.analyze_audio_fallback(c_url.strip(), "Wisdom")
                    for clip in clips:
                        s_sec = backend.timestamp_to_seconds(clip.start_time)
                        e_sec = backend.timestamp_to_seconds(clip.end_time)
                        tmp = backend.BASE_DIR / "temp_slice.mp4"
                        try:
                            backend.download_slice(c_url.strip(), s_sec, e_sec, tmp)
                            seq_name = f"{backend.clean_filename(clip.book_title)}_{backend.clean_filename(clip.title)}"
                            seq_dir = backend.get_next_sequence_folder(seq_name)
                            out_f = seq_dir / f"{seq_name}.mp4"
                            if backend.render_podcast_short(tmp, clip, out_f, "SPECIAL HIGHLIGHT"):
                                desc = f"{clip.hook_caption}\n\n👉 Subscribe for daily inspiration!"
                                opt_t, opt_d, opt_tags = backend.optimize_with_virality_engine(clip.title, clip.title, desc, clip.hashtags, active_channel)
                                backend.save_clip_metadata(out_f, opt_t, opt_d, opt_tags)
                                st.success(f"Created in `{seq_dir.name}/`!")
                        finally:
                            if tmp.exists():
                                tmp.unlink()

# =========================================================
# TAB 3: VIRALITY ENGINE & COMPETITOR SPY
# =========================================================
with tab_virality:
    st.subheader("🔥 Virality Engine: Channel Analytics & Competitor Title Spy")
    v_col1, v_col2 = st.columns([1, 1])

    with v_col1:
        st.markdown(f"#### 🏆 Your Most Viewed Shorts on `{active_channel}`")
        if st.button("🔄 Refresh My Channel Analytics", width="stretch"):
            backend._CHANNEL_STATS_CACHE.pop(active_channel, None)
            my_shorts = backend.get_my_top_shorts(active_channel, max_results=10)
            if not my_shorts:
                st.info("No public videos found or stats still indexing.")
            else:
                for idx, s in enumerate(my_shorts):
                    st.markdown(f"**#{idx + 1}. {s['title']}** — 👁️ `{s['views']:,}` views | 👍 `{s['likes']}` | 💬 `{s['comments']}`")

    with v_col2:
        st.markdown("#### 🔍 Spy on Competitor Shorts & Generate Winning Title")
        spy_topic = st.text_input("Enter Topic to Spy On:", value="Debt Breakthrough Prayer")
        if st.button("🔥 Analyze Competitors & Generate Winning Title", width="stretch"):
            with st.spinner("Scanning top YouTube Shorts..."):
                comps = backend.scan_competitor_shorts(spy_topic)
                if comps:
                    st.write("**Top Performing Competitor Shorts:**")
                    for c in comps[:4]:
                        st.caption(f"• {c['title']} ({c['views']:,} views)")
                win_t, win_d, win_tags = backend.optimize_with_virality_engine(spy_topic, f"Prayer for {spy_topic}", "", ["Shorts"], active_channel)
                st.success(f"🚀 **Winning Title:** `{win_t}`")
                st.code(", ".join(win_tags), language="text")

# =========================================================
# TAB 4: SEQUENTIAL FOLDERS & 1-CLICK MULTI-CHANNEL UPLOADER
# =========================================================
with tab_library:
    st.subheader("📁 Sequential Video Folders (`001_`, `002_`, ...) & Multi-Channel Uploader")
    all_mp4s = sorted(list(backend.CLIPS_DIR.rglob("*.mp4")), key=lambda p: p.parent.name, reverse=True)

    if not all_mp4s:
        st.info("No videos in clips/ yet. Generate your first Short in Tab 1!")
    else:
        for i in range(0, len(all_mp4s), 2):
            cols = st.columns(2)
            for j in range(2):
                if i + j < len(all_mp4s):
                    vid = all_mp4s[i + j]
                    thumb = vid.with_name(f"{vid.stem}_thumb.jpg")
                    meta = backend.load_clip_metadata(vid)
                    with cols[j]:
                        st.markdown(f"#### 📂 `{vid.parent.name}`")
                        sc1, sc2 = st.columns([1.2, 1])
                        with sc1:
                            st.video(str(vid))
                        with sc2:
                            if thumb.exists():
                                st.image(str(thumb), width="stretch")
                        st.markdown(f"**Title:** `{meta['title']}`")

                        if meta.get("youtube_id"):
                            st.success(f"✅ Uploaded: https://youtube.com/shorts/{meta['youtube_id']}")
                        else:
                            # Separate 1-Click Upload Button for EACH connected channel!
                            for ch_name in channel_names:
                                if st.button(f"🚀 Post to {ch_name}", key=f"lib_up_{vid.parent.name}_{ch_name}", width="stretch"):
                                    with st.spinner(f"Uploading to {ch_name}..."):
                                        yt_id = backend.upload_video_to_youtube(ch_name, vid)
                                        if yt_id:
                                            st.success(f"Live! https://youtube.com/shorts/{yt_id}")
                                            time.sleep(1)
                                            st.rerun()

                        if st.button(f"🗑️ Delete {vid.parent.name}", key=f"del_{vid.parent.name}"):
                            import shutil
                            shutil.rmtree(vid.parent, ignore_errors=True)
                            st.rerun()
