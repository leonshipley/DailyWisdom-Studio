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
    synthesize_bilingual_verse_preview,
    build_spoken_voice_script,
)
from bible_database import (
    TOP_50_PRAYER_TOPICS,
    BIBLE_66_BOOKS,
    get_verses_for_chapter,
    translate_verse_to_hindi,
    lookup_reference_bilingual,
    format_reference_for_speech,
    translate_any_text_to_hindi,
    ai_pick_relevant_verse_for_topic,
)

st.set_page_config(
    page_title="DailyWisdom Dual-Channel AI Studio",
    page_icon="✝️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .block-container {
        padding-top: 1.0rem !important;
        padding-bottom: 1.0rem !important;
        padding-left: 1.4rem !important;
        padding-right: 1.4rem !important;
        max-width: 100% !important;
    }
    section[data-testid="stSidebar"] {
        background-color: #0B0F19 !important;
        border-right: 1px solid #1F2937 !important;
    }
    .top-nav {
        background: linear-gradient(90deg, #0F172A 0%, #1E1B4B 50%, #0F172A 100%);
        border: 1px solid #334155;
        border-left: 5px solid #FFD700;
        border-radius: 12px;
        padding: 12px 20px;
        margin-bottom: 12px;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .nav-title { font-size: 23px; font-weight: 900; color: #FFD700; margin: 0; }
    .nav-sub { font-size: 13px; color: #94A3B8; margin-top: 2px; }
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
    .kpi-card {
        background: linear-gradient(145deg, #111827, #0F172A);
        border: 1px solid #1F2937;
        border-top: 3px solid #FFD700;
        border-radius: 10px;
        padding: 10px 15px;
    }
    .kpi-label { font-size: 11px; color: #9CA3AF; text-transform: uppercase; font-weight: 700; }
    .kpi-val { font-size: 21px; font-weight: 900; color: #FFFFFF; margin-top: 2px; }
    .kpi-sub { font-size: 11px; color: #FFD700; }
    .verse-box {
        background-color: #0F172A;
        border: 1px solid #FFD700;
        border-left: 5px solid #FFD700;
        border-radius: 10px;
        padding: 12px 14px;
        margin-top: 6px;
        margin-bottom: 8px;
    }
    .explain-box {
        background-color: #111827;
        border: 1px solid #374151;
        border-left: 4px solid #10B981;
        border-radius: 8px;
        padding: 10px 14px;
        margin-top: 6px;
        margin-bottom: 10px;
        font-size: 13.5px;
        color: #E5E7EB;
    }
    .verse-ref-hdr { font-size: 15px; font-weight: 800; color: #FFD700; margin-bottom: 6px; }
    .verse-en { font-size: 14px; color: #FFFFFF; margin-bottom: 6px; line-height: 1.45; }
    .verse-hi { font-size: 15px; color: #FDE047; margin-bottom: 4px; line-height: 1.5; }
    .stButton>button {
        background: linear-gradient(90deg, #FFD700 0%, #EAB308 100%);
        color: #090D16 !important;
        font-weight: 800 !important;
        border-radius: 8px !important;
        border: none !important;
    }
</style>
""", unsafe_allow_html=True)

def get_all_sequence_videos():
    return sorted(list(backend.CLIPS_DIR.rglob("*.mp4")), key=lambda p: p.parent.name, reverse=True)

def get_media_files(folder: Path, exts: tuple):
    if not folder.exists():
        return []
    return sorted([f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in exts], key=lambda x: x.stat().st_mtime, reverse=True)

channels = backend.load_channels()
channel_names = list(channels.keys()) if channels else ["TheDailyWisdom_Hub"]
cur_v_cfg = load_active_voice()
all_videos = get_all_sequence_videos()
uploaded_count = sum(1 for v in all_videos if backend.load_clip_metadata(v).get("youtube_id"))
pending_count = len(all_videos) - uploaded_count

# --- LEFT SIDEBAR COMMAND CENTER ---
with st.sidebar:
    st.markdown("### 🎛️ Global Command Center")
    sb_c1, sb_c2 = st.columns(2)
    with sb_c1:
        if st.button("➕ Add Channel", width="stretch"):
            new_c = backend.connect_new_channel()
            if new_c:
                st.rerun()
    with sb_c2:
        if st.button("☁️ Git Save", width="stretch"):
            with st.spinner("Pushing..."):
                ok, msg = backend.save_everything_to_git()
                st.toast("Saved to GitHub!" if ok else msg, icon="✅" if ok else "⚠️")

    if st.button("🛑 Stop / Cancel Active Task", width="stretch"):
        subprocess.run(["taskkill", "/F", "/IM", "ffmpeg.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["taskkill", "/F", "/IM", "yt-dlp.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        st.warning("Stopped active tasks.")
        st.stop()

    st.divider()
    st.markdown("### 📌 Pinterest Quick-Grab")
    pin_in = st.text_input("Paste Pin URL (Video or Image):", placeholder="https://pin.it/...")
    if st.button("📥 Download Pin to Studio", width="stretch") and pin_in.strip():
        with st.spinner("Downloading Pin..."):
            saved_p = backend.download_pinterest_media(pin_in.strip(), sync_to_studio=True)
            if saved_p:
                st.success(f"Saved: {saved_p.name}")
                time.sleep(0.5)
                st.rerun()

# --- TOP NAVBAR & KPI CARDS ---
st.markdown(f"""
<div class="top-nav">
    <div>
        <div class="nav-title">✝️ DailyWisdom Dual-Channel AI Studio</div>
        <div class="nav-sub">Separated 🇬🇧 English Channel Maker & 🇮🇳 Hindi Channel Maker • AI Random Verse + Explanation Picker • 66 Books</div>
    </div>
    <div>
        <span class="status-pill">📺 {len(channel_names)} Channels Connected</span>
        <span class="status-pill">📖 66 Books + 50 Topics</span>
        <span class="status-pill">🟢 AI Engine Online</span>
    </div>
</div>
""", unsafe_allow_html=True)

k1, k2, k3, k4 = st.columns(4)
with k1:
    st.markdown(f'<div class="kpi-card"><div class="kpi-label">Total Sequential Shorts</div><div class="kpi-val">{len(all_videos)}</div><div class="kpi-sub">Sorted in clips/001_...</div></div>', unsafe_allow_html=True)
with k2:
    st.markdown(f'<div class="kpi-card"><div class="kpi-label">Ready to Upload</div><div class="kpi-val">{pending_count}</div><div class="kpi-sub">{uploaded_count} Live on YouTube</div></div>', unsafe_allow_html=True)
with k3:
    pin_v_cnt = len(get_media_files(backend.PIN_VID_DIR, (".mp4",))) if hasattr(backend, "PIN_VID_DIR") else 0
    pin_i_cnt = len(get_media_files(backend.PIN_IMG_DIR, (".jpg", ".png"))) if hasattr(backend, "PIN_IMG_DIR") else 0
    st.markdown(f'<div class="kpi-card"><div class="kpi-label">Pinterest Media Vault</div><div class="kpi-val">{pin_v_cnt + pin_i_cnt}</div><div class="kpi-sub">{pin_v_cnt} Videos • {pin_i_cnt} HD Images</div></div>', unsafe_allow_html=True)
with k4:
    st.markdown(f'<div class="kpi-card"><div class="kpi-label">Connected Channels</div><div class="kpi-val">{len(channel_names)}</div><div class="kpi-sub">{", ".join(channel_names)[:32]}</div></div>', unsafe_allow_html=True)

st.write("")

# ==============================================================================
# REUSABLE MAKER RENDERER FOR TAB 1 (ENGLISH MAKER) & TAB 2 (HINDI MAKER)
# ==============================================================================
def render_maker_workspace(lang_code: str):
    """
    Renders a dedicated, self-contained Maker workspace:
    - lang_code == 'en': 100% English Channel Maker
    - lang_code == 'hi': 100% Hindi Channel Maker (पवित्र बाइबिल)
    """
    is_hi = (lang_code == "hi")
    pfx = "hi" if is_hi else "en"
    maker_title = "🇮🇳 Hindi Channel Maker (पवित्र बाइबिल — 100% Pure Hindi Shorts)" if is_hi else "🇬🇧 English Channel Maker (100% English Devotional Shorts)"

    col_left, col_mid, col_right = st.columns([1.35, 1.15, 1.3], gap="medium")

    with col_left:
        with st.container(border=True):
            st.markdown(f"#### {maker_title}")

            # 1. Target Channel & Voice Picker for this specific Maker
            c_ch, c_acc = st.columns(2)
            with c_ch:
                def_ch_idx = (1 if (is_hi and len(channel_names) > 1) else 0)
                target_ch = st.selectbox("📺 Target YouTube Channel:", channel_names, index=def_ch_idx, key=f"{pfx}_target_ch")
            with c_acc:
                if is_hi:
                    acc_choices = ["🇮🇳 Hindi / Indian Accent (hi-IN)", "🇮🇳 Indian English (en-IN)"]
                else:
                    acc_choices = ["🇺🇸 American English (en-US)", "🇬🇧 British English (en-GB)", "🇮🇳 Indian English (en-IN)"]
                chosen_acc = st.selectbox("🌍 Voice Accent:", acc_choices, index=0, key=f"{pfx}_acc")

            v_list = VOICE_CATALOG[chosen_acc]
            v_names = [v["name"] for v in v_list]
            sel_v_name = st.selectbox("🎙️ Select Narrator Voice:", v_names, index=0, key=f"{pfx}_voice")
            sel_v_obj = v_list[v_names.index(sel_v_name)]

            # 2. Topic OR Exact Book/Chapter/Verse Selector
            sel_mode = st.radio(
                "How do you want to pick the Bible Verse?",
                [
                    "🎲 50 Prayer Topics (AI Picks New Relevant Verse + Explanation Every Time)",
                    "📖 Full 66-Book Bible Browser (Book ➔ Chapter ➔ Verse)",
                    "✍️ Custom Topic (AI Picks Relevant Verse + Explanation)",
                ],
                key=f"{pfx}_sel_mode",
            )

            state_key = f"{pfx}_active_verse_bundle"

            if "50 Prayer Topics" in sel_mode:
                topic_labels = [f"{item['id']}. {item['topic']}" for item in TOP_50_PRAYER_TOPICS]
                chosen_t_lbl = st.selectbox("Select Prayer Topic (1-50):", topic_labels, key=f"{pfx}_topic_dd")
                chosen_t_obj = TOP_50_PRAYER_TOPICS[topic_labels.index(chosen_t_lbl)]
                topic_name = chosen_t_obj["topic"]

                # Auto-pick or let user click '🎲 AI Pick Another Relevant Verse'
                if st.session_state.get(f"{pfx}_last_topic") != topic_name or state_key not in st.session_state:
                    st.session_state[f"{pfx}_last_topic"] = topic_name
                    st.session_state[state_key] = ai_pick_relevant_verse_for_topic(topic_name, lang=pfx)

                if st.button("🎲 AI Pick Another Relevant Verse & Explanation for This Topic", key=f"{pfx}_reroll_btn", width="stretch"):
                    with st.spinner(f"AI selecting a new relevant Bible verse for '{topic_name}'..."):
                        st.session_state[state_key] = ai_pick_relevant_verse_for_topic(topic_name, lang=pfx)

            elif "Full 66-Book" in sel_mode:
                book_labels = [f"{i+1:02d}. {b_en.strip()} — {b_hi}" for i, (b_en, b_hi, _) in enumerate(BIBLE_66_BOOKS)]
                sel_b_lbl = st.selectbox("1. Select Book (66 Books):", book_labels, index=18, key=f"{pfx}_bk")
                b_idx = book_labels.index(sel_b_lbl)
                exact_book, _, max_ch = BIBLE_66_BOOKS[b_idx]
                exact_book = exact_book.strip()

                cc1, cc2 = st.columns(2)
                with cc1:
                    exact_ch = st.selectbox("2. Chapter:", list(range(1, max_ch + 1)), index=0, key=f"{pfx}_ch")
                verses_dict = get_verses_for_chapter(exact_book, exact_ch)
                v_nums = list(verses_dict.keys()) if verses_dict else [1]
                with cc2:
                    exact_v = st.selectbox("3. Verse:", v_nums, format_func=lambda vn: f"Verse {vn}: {verses_dict.get(vn, '')[:26]}...", key=f"{pfx}_vs")

                ref_manual = f"{exact_book} {exact_ch}:{exact_v}"
                if st.session_state.get(f"{pfx}_last_manual_ref") != ref_manual or state_key not in st.session_state:
                    st.session_state[f"{pfx}_last_manual_ref"] = ref_manual
                    _, en_v_txt, hi_v_dev, hi_v_rom = lookup_reference_bilingual(ref_manual)
                    why_en_m = f"This verse from {ref_manual} reveals God's eternal truth and comfort for your life today."
                    mean_en_m = f"Let the promise of {ref_manual} anchor your heart. God's word never fails those who trust in Him."
                    pray_en_m = f"Lord Jesus, let the truth of {ref_manual} come alive in my life and bless my family today, Amen."
                    st.session_state[state_key] = {
                        "topic_en": ref_manual,
                        "topic_hi": format_reference_for_speech(ref_manual, is_hindi_speech=True),
                        "verse_citation": ref_manual,
                        "en_spoken_ref": format_reference_for_speech(ref_manual, is_hindi_speech=False),
                        "hi_spoken_ref": format_reference_for_speech(ref_manual, is_hindi_speech=True),
                        "en_verse": en_v_txt,
                        "hi_verse": hi_v_dev,
                        "rom_verse": hi_v_rom,
                        "why_en": why_en_m,
                        "why_hi": translate_any_text_to_hindi(why_en_m),
                        "meaning_en": mean_en_m,
                        "meaning_hi": translate_any_text_to_hindi(mean_en_m),
                        "prayer_en": pray_en_m,
                        "prayer_hi": translate_any_text_to_hindi(pray_en_m),
                        "hook_en": f"{ref_manual.upper()} PROMISE",
                        "title_en": f"God's Promise in {ref_manual} #shorts",
                        "title_hi": f"{format_reference_for_speech(ref_manual, is_hindi_speech=True)} #shorts",
                    }
            else:
                custom_t_in = st.text_input("Enter Custom Topic:", value="Financial Miracle & Peace", key=f"{pfx}_cust_in")
                if st.button("🎲 AI Pick Relevant Verse & Explanation", key=f"{pfx}_cust_btn", width="stretch") or state_key not in st.session_state:
                    with st.spinner("AI finding the best Bible verse & explanation..."):
                        st.session_state[state_key] = ai_pick_relevant_verse_for_topic(custom_t_in, lang=pfx)

            bundle = st.session_state[state_key]
            preview_ref = bundle["verse_citation"]
            en_preview = bundle["en_verse"]
            dev_hi = bundle["hi_verse"]
            rom_hi = bundle["rom_verse"]
            en_spoken_name = bundle["en_spoken_ref"]
            hi_spoken_name = bundle["hi_spoken_ref"]

            # --- TWO SEPARATE VERSE BOXES (BOX 1: ENGLISH | BOX 2: HINDI) ---
            box_en, box_hi = st.columns(2, gap="small")
            with box_en:
                st.markdown(f"""
                <div class="verse-box" style="border-color: #38BDF8; border-left: 5px solid #38BDF8; min-height: 145px;">
                    <div class="verse-ref-hdr" style="color: #38BDF8;">🇬🇧 ENGLISH VERSE ({preview_ref})<br><span style="font-size:11px; color:#94A3B8;">{en_spoken_name}</span></div>
                    <div class="verse-en">"{en_preview}"</div>
                </div>
                """, unsafe_allow_html=True)
                if st.button("🔊 Hear English Verse", key=f"{pfx}_hear_en", width="stretch"):
                    save_active_voice(dict(sel_v_obj, accent=chosen_acc, script_mode=SCRIPT_MODES[0]))
                    mp3_f = synthesize_bilingual_verse_preview(preview_ref, en_preview, dev_hi, rom_hi, listen_mode="english")
                    st.session_state[f"{pfx}_aud_mp3"] = str(mp3_f)

            with box_hi:
                st.markdown(f"""
                <div class="verse-box" style="border-color: #FFD700; border-left: 5px solid #FFD700; min-height: 145px;">
                    <div class="verse-ref-hdr" style="color: #FFD700;">🇮🇳 HINDI VERSE (पवित्र बाइबिल)<br><span style="font-size:11px; color:#FDE047;">{hi_spoken_name}</span></div>
                    <div class="verse-hi">"{dev_hi}"</div>
                </div>
                """, unsafe_allow_html=True)
                if st.button("🔊 Hear Hindi Verse (हिन्दी)", key=f"{pfx}_hear_hi", width="stretch"):
                    save_active_voice(dict(sel_v_obj, accent=chosen_acc, script_mode=SCRIPT_MODES[1]))
                    mp3_f = synthesize_bilingual_verse_preview(preview_ref, en_preview, dev_hi, rom_hi, listen_mode="hindi")
                    st.session_state[f"{pfx}_aud_mp3"] = str(mp3_f)

            if st.button("🌍 Hear Both Together (English First ➔ Then Hindi)", key=f"{pfx}_hear_both", width="stretch"):
                mp3_f = synthesize_bilingual_verse_preview(preview_ref, en_preview, dev_hi, rom_hi, listen_mode="both")
                st.session_state[f"{pfx}_aud_mp3"] = str(mp3_f)

            if st.session_state.get(f"{pfx}_aud_mp3") and Path(st.session_state[f"{pfx}_aud_mp3"]).exists():
                st.audio(st.session_state[f"{pfx}_aud_mp3"], format="audio/mp3", autoplay=True)

            # --- AI EXPLANATION & MEANING BOX (SHOWN EVERY TIME BEFORE GENERATING) ---
            why_txt = bundle["why_hi"] if is_hi else bundle["why_en"]
            st.markdown(f"""
            <div class="explain-box">
                <b>💡 Why AI Picked `{preview_ref}` for this Topic:</b><br>{why_txt}
            </div>
            """, unsafe_allow_html=True)

            edit_meaning = st.text_area(
                "📝 Spiritual Explanation / अर्थ (Spoken in Video — Editable):" if is_hi else "📝 Spiritual Explanation / Meaning (Spoken in Video — Editable):",
                value=bundle["meaning_hi"] if is_hi else bundle["meaning_en"],
                height=78,
                key=f"{pfx}_mean_{preview_ref}",
            )
            edit_prayer = st.text_area(
                "🙏 Breakthrough Prayer / प्रार्थना (Spoken in Video — Editable):" if is_hi else "🙏 Breakthrough Prayer (Spoken in Video — Editable):",
                value=bundle["prayer_hi"] if is_hi else bundle["prayer_en"],
                height=68,
                key=f"{pfx}_pray_{preview_ref}",
            )

            gen_btn = st.button(
                f"✨ GENERATE {'100% HINDI' if is_hi else '100% ENGLISH'} SHORT WITH {preview_ref}",
                key=f"{pfx}_gen_btn",
                width="stretch",
            )

    with col_mid:
        with st.container(border=True):
            st.markdown("#### 🎨 Step 2: Visuals & Thumbnail Picker")
            palette_style = st.selectbox("Thumbnail Palette:", ["Gold Classic", "Midnight Blue", "Sunrise", "Crimson Glory"], key=f"{pfx}_pal")
            raw_thumb_toggle = st.checkbox("Use uploaded thumbnail raw (No 3D text)", value=False, key=f"{pfx}_raw_th")

            intro_files = get_media_files(backend.INTRO_DIR, (".mp4", ".mov", ".webm", ".mkv"))
            bg_files = get_media_files(backend.BG_DIR, (".jpg", ".jpeg", ".png", ".webp"))
            thumb_files = get_media_files(backend.THUMB_DIR, (".jpg", ".jpeg", ".png", ".webp"))

            pick_intro_name = st.selectbox("📹 10s Intro Video (Auto-Muted):", ["Auto / Newest"] + [f.name for f in intro_files], key=f"{pfx}_int_dd")
            up_intro = st.file_uploader("Drop New Intro Video:", type=["mp4", "mov", "webm"], label_visibility="collapsed", key=f"{pfx}_u_int")

            pick_bg_name = st.selectbox("🖼️ Main Background Image (10s-End):", ["Auto / Newest"] + [f.name for f in bg_files], key=f"{pfx}_bg_dd")
            up_bg = st.file_uploader("Drop New Background Image:", type=["jpg", "jpeg", "png", "webp"], label_visibility="collapsed", key=f"{pfx}_u_bg")

            pick_thumb_name = st.selectbox("🔥 Thumbnail Background:", ["Same as Main Background"] + [f.name for f in thumb_files], key=f"{pfx}_th_dd")
            up_thumb = st.file_uploader("Drop Custom Thumbnail Image:", type=["jpg", "jpeg", "png", "webp"], label_visibility="collapsed", key=f"{pfx}_u_th")

    if gen_btn:
        with col_left:
            status = st.empty()
            prog = st.progress(0)

            # Lock in the exact voice & language mode for this Maker
            active_maker_voice = dict(
                sel_v_obj,
                accent=chosen_acc,
                script_mode=SCRIPT_MODES[1] if is_hi else SCRIPT_MODES[0],
            )
            save_active_voice(active_maker_voice)

            script = backend.BibleShortScript(
                topic=bundle["topic_hi"] if is_hi else bundle["topic_en"],
                title=bundle["title_hi"] if is_hi else bundle["title_en"],
                verse_citation=preview_ref,
                verse_text=dev_hi if is_hi else en_preview,
                meaning=edit_meaning.strip(),
                prayer=edit_prayer.strip(),
                thumbnail_hook=bundle["hook_en"],
                hashtags=["#HindiBible", "#YeshuMasih", "#Prarthana", "#Shorts"] if is_hi else ["#BibleVerse", "#DailyPrayer", "#Faith", "#Shorts"],
            )

            status.info(f"🎙️ [1/3] Synthesizing {'100% Pure Hindi' if is_hi else '100% English'} Voiceover ({sel_v_obj['name']})...")
            prog.progress(35)
            voice_script = build_spoken_voice_script(script)
            temp_voice = backend.BASE_DIR / "temp_voice.mp3"
            backend.generate_voiceover(voice_script, temp_voice)

            status.info("⚡ [2/3] Fast-Rendering 1080p Video & Graphical Thumbnails...")
            prog.progress(70)
            tag_prefix = "Hindi_Bible" if is_hi else "English_Bible"
            clean_name = backend.clean_filename(f"{tag_prefix}_{bundle['topic_en']}_{preview_ref}")
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
                status.info("🔥 [3/3] Running Virality Engine...")
                prog.progress(90)
                if is_hi:
                    raw_desc = (
                        f"📖 पवित्र बाइबिल वचन: {hi_spoken_name} ({preview_ref})\n"
                        f"\"{dev_hi}\"\n\n"
                        f"💡 वचन का अर्थ:\n{edit_meaning}\n\n"
                        f"🙏 प्रार्थना:\n{edit_prayer}\n\n"
                        f"कमेंट में \"AMEN\" ज़रूर लिखें! 🙏\n\n"
                        f"---\nDisclaimer: As an Amazon Associate, I earn from qualifying purchases."
                    )
                else:
                    raw_desc = (
                        f"📖 Scripture: {preview_ref}\n"
                        f"\"{en_preview}\"\n\n"
                        f"💡 Reflection:\n{edit_meaning}\n\n"
                        f"🙏 Prayer:\n{edit_prayer}\n\n"
                        f"Type \"AMEN\" in the comments if you receive this word today! 🙏\n\n"
                        f"---\nDisclaimer: As an Amazon Associate, I earn from qualifying purchases."
                    )

                opt_title, opt_desc, opt_tags = backend.optimize_with_virality_engine(
                    bundle["topic_en"], script.title, raw_desc, script.hashtags, target_ch
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
                st.info("Your generated Short and 1-Click Publish buttons will appear here!")
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
                with st.expander("📝 View Description & SEO Tags"):
                    st.text_area("Description:", value=meta["description"], height=120, key=f"{pfx}_mon_desc")

                if meta.get("youtube_id"):
                    st.success(f"✅ Live on YouTube! https://youtube.com/shorts/{meta['youtube_id']}")
                else:
                    for ch_n in channel_names:
                        if st.button(f"🚀 Publish to {ch_n}", key=f"{pfx}_mon_up_{ch_n}", width="stretch"):
                            with st.spinner(f"Publishing to {ch_n}..."):
                                yt_id = backend.upload_video_to_youtube(ch_n, vp)
                                if yt_id:
                                    st.success(f"Live! https://youtube.com/shorts/{yt_id}")
                                    time.sleep(1)
                                    st.rerun()


# ==============================================================================
# 4 MAIN STUDIO TABS (SEPARATED ENGLISH MAKER & HINDI MAKER)
# ==============================================================================
tab_en, tab_hi, tab_lib, tab_pod = st.tabs([
    "🇬🇧 1. English Channel Shorts Maker",
    "🇮🇳 2. Hindi Channel Shorts Maker (पवित्र बाइबिल)",
    "📁 3. Sequential Video Library & Publisher",
    "🎙️ 4. Podcast Clipper & Virality Spy",
])

with tab_en:
    render_maker_workspace("en")

with tab_hi:
    render_maker_workspace("hi")

with tab_lib:
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

with tab_pod:
    p_c1, p_c2 = st.columns(2, gap="medium")
    with p_c1:
        with st.container(border=True):
            st.markdown("#### 🎙️ Auto-Scout 1M+ View Podcasts & Clip")
            cat_map = {v["name"]: k for k, v in backend.CATEGORIES.items()}
            chosen_cat_name = st.selectbox("Select Niche:", list(cat_map.keys()))
            cat_cfg = backend.CATEGORIES[cat_map[chosen_cat_name]]
            if st.button(f"⚡ Auto-Scout & Clip '{chosen_cat_name}'", width="stretch"):
                with st.spinner("Hunting 1M+ view videos..."):
                    target = backend.find_viral_video(1_000_000, cat_cfg["queries"])
                    if target:
                        tr = backend.get_transcript(target["id"])
                        clips = backend.analyze_transcript(tr, chosen_cat_name) if tr else backend.analyze_audio_fallback(target["url"], chosen_cat_name)
                        for clip in clips:
                            s_sec, e_sec = backend.timestamp_to_seconds(clip.start_time), backend.timestamp_to_seconds(clip.end_time)
                            tmp = backend.BASE_DIR / "temp_slice.mp4"
                            try:
                                backend.download_slice(target["url"], s_sec, e_sec, tmp)
                                seq_name = f"{backend.clean_filename(clip.book_title)}_{backend.clean_filename(clip.title)}"
                                seq_dir = backend.get_next_sequence_folder(seq_name)
                                out_f = seq_dir / f"{seq_name}.mp4"
                                if backend.render_podcast_short(tmp, clip, out_f, cat_cfg["badge_tag"]):
                                    backend.save_clip_metadata(out_f, clip.title, clip.hook_caption, clip.hashtags)
                                    st.success(f"Created `{seq_dir.name}`!")
                            finally:
                                tmp.unlink(missing_ok=True)
    with p_c2:
        with st.container(border=True):
            st.markdown("#### 🔥 Competitor Title Spy & SEO Generator")
            spy_q = st.text_input("Topic / Keyword to Spy On:", value="Miracle Debt Prayer")
            if st.button("🔥 Spy on Competitors & Generate Winning Title", width="stretch"):
                with st.spinner("Analyzing top YouTube Shorts..."):
                    comps = backend.scan_competitor_shorts(spy_q)
                    for c in comps[:5]:
                        st.caption(f"🔥 **{c['title']}** — `{c['views']:,} views`")
                    win_t, _, win_tags = backend.optimize_with_virality_engine(spy_q, f"Prayer for {spy_q}", "", ["Shorts"], channel_names[0])
                    st.success(f"🚀 **Winning Title:** `{win_t}`")
                    st.code(", ".join(win_tags), language="text")
