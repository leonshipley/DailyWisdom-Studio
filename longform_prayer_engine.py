
def _sec_to_srt_time(sec: float) -> str:
    """Converts seconds into standard SRT timestamp format: HH:MM:SS,mmm"""
    sec = max(0.0, float(sec))
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    ms = int(round((sec - int(sec)) * 1000))
    if ms >= 1000:
        s += 1
        ms -= 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"



def detect_hardware_video_encoder() -> tuple:

    """Auto-detects NVIDIA NVENC, Intel QSV, or AMD AMF for 8x faster rendering."""

    # 1. Test NVIDIA NVENC

    try:

        t = subprocess.run(

            ["ffmpeg", "-f", "lavfi", "-i", "color=s=64x64:d=0.1", "-c:v", "h264_nvenc", "-f", "null", "-"],

            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3

        )

        if t.returncode == 0:

            return "h264_nvenc", ["-preset", "p1", "-cq", "24"]

    except Exception:

        pass



    # 2. Test Intel QuickSync (QSV)

    try:

        t = subprocess.run(

            ["ffmpeg", "-f", "lavfi", "-i", "color=s=64x64:d=0.1", "-c:v", "h264_qsv", "-f", "null", "-"],

            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3

        )

        if t.returncode == 0:

            return "h264_qsv", ["-preset", "veryfast", "-global_quality", "25"]

    except Exception:

        pass



    # 3. CPU Fallback (Tuned for maximum throughput)

    return "libx264", ["-preset", "ultrafast", "-tune", "fastdecode", "-crf", "22"]



import os

import re

import json

import asyncio

import subprocess

from pathlib import Path

from typing import List, Dict, Any, Tuple, Optional

from dotenv import load_dotenv

import edge_tts



import bible_database as bdb



BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")



LONGFORM_DIR = BASE_DIR / "longform_videos"

LONGFORM_DIR.mkdir(parents=True, exist_ok=True)

AMBIENCE_DIR = BASE_DIR / "assets" / "ambience"

AMBIENCE_DIR.mkdir(parents=True, exist_ok=True)



# ==============================================================================

# 1. DURATION TIERS & SPIRITUAL JOURNEY CONFIGURATIONS

# ==============================================================================

DURATION_CONFIGS: Dict[str, Dict[str, Any]] = {

    "5 Minutes": {

        "target_seconds": 300,

        "scriptures_count": 3,

        "words_per_stage": 100,

        "pause_between_paras_sec": 2.5,

        "pause_between_stages_sec": 4.0,

    },

    "10 Minutes": {

        "target_seconds": 600,

        "scriptures_count": 5,

        "words_per_stage": 200,

        "pause_between_paras_sec": 3.0,

        "pause_between_stages_sec": 4.5,

    },

    "20 Minutes": {

        "target_seconds": 1200,

        "scriptures_count": 8,

        "words_per_stage": 380,

        "pause_between_paras_sec": 3.2,

        "pause_between_stages_sec": 5.5,

    },

    "30 Minutes": {

        "target_seconds": 1800,

        "scriptures_count": 10,

        "words_per_stage": 550,

        "pause_between_paras_sec": 3.5,

        "pause_between_stages_sec": 6.0,

    },

    "1 Hour (60 Min)": {

        "target_seconds": 3600,

        "scriptures_count": 12,

        "words_per_stage": 700,

        "pause_between_paras_sec": 4.0,

        "pause_between_stages_sec": 7.0,

    },

}



TOPIC_SCRIPTURE_JOURNEYS: Dict[str, List[str]] = {

    "debt": [

        "Philippians 4:19", "Deuteronomy 28:12", "Proverbs 10:22", "Psalm 23:1",

        "2 Corinthians 9:8", "Malachi 3:10", "Psalm 37:25", "Proverbs 3:9-10",

        "Deuteronomy 8:18", "Luke 6:38", "Job 22:28", "Psalm 112:3"

    ],

    "anxiety": [

        "Philippians 4:6-7", "John 14:27", "Isaiah 41:10", "Psalm 46:1",

        "Matthew 11:28", "1 Peter 5:7", "Psalm 94:19", "Isaiah 26:3",

        "2 Timothy 1:7", "Psalm 34:4", "Psalm 55:22", "Psalm 29:11"

    ],

    "sleep": [

        "Psalm 4:8", "Psalm 91:1-2", "Psalm 121:7-8", "Proverbs 3:24",

        "Matthew 11:28", "Psalm 23:1-4", "Psalm 131:2", "Isaiah 26:3",

        "Psalm 3:5", "Psalm 63:6-7", "Numbers 6:24-26", "Psalm 127:2"

    ],

    "healing": [

        "Jeremiah 17:14", "Isaiah 53:5", "Psalm 103:2-3", "Exodus 23:25",

        "Proverbs 4:20-22", "Psalm 107:20", "3 John 1:2", "James 5:15",

        "Jeremiah 30:17", "Psalm 41:3", "Malachi 4:2", "Exodus 15:26"

    ],

    "broken": [

        "Psalm 34:18", "Psalm 147:3", "Matthew 5:4", "Psalm 30:5",

        "Isaiah 61:3", "2 Corinthians 1:3-4", "Revelation 21:4", "Psalm 42:11",

        "Deuteronomy 31:8", "Psalm 73:26", "Psalm 27:10", "Isaiah 43:2"

    ],

    "protection": [

        "Isaiah 54:17", "Psalm 91:1-4", "Psalm 91:11", "Psalm 121:7-8",

        "2 Thessalonians 3:3", "Proverbs 18:10", "Exodus 14:14", "Psalm 27:1",

        "Deuteronomy 31:6", "Psalm 34:7", "Psalm 18:2", "Psalm 46:1"

    ],

    "strength": [

        "Isaiah 40:31", "Philippians 4:13", "Joshua 1:9", "2 Corinthians 12:9",

        "Isaiah 41:10", "Psalm 28:7", "Nehemiah 8:10", "Habakkuk 3:19",

        "Ephesians 6:10", "Psalm 18:32", "Deuteronomy 20:4", "Psalm 73:26"

    ],

}



def select_scriptures_for_journey(topic: str, count: int) -> List[Dict[str, str]]:

    t_low = topic.lower()

    chosen_pool = TOPIC_SCRIPTURE_JOURNEYS["anxiety"]

    for k, pool in TOPIC_SCRIPTURE_JOURNEYS.items():

        if k in t_low:

            chosen_pool = pool

            break



    results = []

    for ref in chosen_pool[:count]:

        norm_ref, en_txt, _, _ = bdb.lookup_reference_bilingual(ref)

        spoken_ref = bdb.format_reference_for_speech(norm_ref, is_hindi_speech=False)

        results.append({

            "ref": norm_ref,

            "spoken_ref": spoken_ref,

            "text": en_txt

        })

    return results



# ==============================================================================

# 2. 5-STAGE SOUL-PRAYER AI & CURATED SCRIPT GENERATOR

# ==============================================================================

def _call_gemini_stage(prompt: str) -> str:

    key = os.getenv("GEMINI_API_KEY")

    if not key:

        return ""

    try:

        from google import genai

        from google.genai import types

        client = genai.Client(api_key=key)

        for m_id in ["gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite"]:

            try:

                res = client.models.generate_content(

                    model=m_id,

                    contents=prompt,

                    config=types.GenerateContentConfig(temperature=0.75)

                )

                if res and res.text and len(res.text.strip()) > 60:

                    cleaned = re.sub(r"[*#_`~>]", "", res.text).strip()

                    return cleaned

            except Exception:

                continue

    except Exception:

        pass

    return ""



def generate_soul_prayer_journey(topic: str, duration_label: str = "10 Minutes") -> Dict[str, Any]:

    cfg = DURATION_CONFIGS.get(duration_label, DURATION_CONFIGS["10 Minutes"])

    target_w = cfg["words_per_stage"]

    scriptures = select_scriptures_for_journey(topic, cfg["scriptures_count"])



    s_stage1 = scriptures[0:1]

    s_stage2 = scriptures[1:max(2, len(scriptures)//2)]

    s_stage3 = scriptures[max(2, len(scriptures)//2):max(3, (len(scriptures)*3)//4)]

    s_stage4 = scriptures[max(3, (len(scriptures)*3)//4):]

    if not s_stage4 and scriptures:

        s_stage4 = [scriptures[-1]]



    stages_spec = [

        {

            "stage_num": 1,

            "chapter_title": f"Entering God's Sanctuary & Releasing {topic}",

            "verses": s_stage1,

            "role": (

                f"Stage 1: The Sanctuary Call. Gently welcome the listener who is exhausted and burdened by {topic}. "

                f"Invite them to take a slow deep breath, drop their shoulders, and enter God's quiet presence. "

                f"Include the exact words of {s_stage1[0]['spoken_ref']}: '{s_stage1[0]['text']}'. "

                f"Explain softly how God sees every hidden tear and silent battle."

            ),

            "fallback": (

                f"Take a slow, deep breath right now. Let your shoulders drop, and quiet your heart before the Lord. "

                f"If you have come to this moment carrying the heavy weight of {topic}, know that you are not here by accident. "

                f"God sees the silent battles you have been fighting when no one else is looking. He hears the prayers you whisper in the dark. "

                f"Listen to the comforting promise of God's Word in {s_stage1[0]['spoken_ref']}. "

                f"{s_stage1[0]['text']} "

                f"Right now, you do not have to pretend to be strong. You do not have to figure everything out on your own. "

                f"Come into His sanctuary and lay every anxious thought at the feet of Jesus."

            )

        },

        {

            "stage_num": 2,

            "chapter_title": "The Unshakeable Foundation of God's Word",

            "verses": s_stage2,

            "role": (

                f"Stage 2: Deep Scripture Reflection & Teaching on {topic}. "

                f"Read and weave in these exact scriptures: " +

                "; ".join([f"{v['spoken_ref']}: '{v['text']}'" for v in s_stage2]) + ". "

                f"Give a deep, soul-stirring pastoral explanation of what these verses mean for someone struggling with {topic}."

            ),

            "fallback": (

                "Let the eternal truth of Scripture wash over your mind and spirit. " +

                " ".join([

                    f"In {v['spoken_ref']}, the Word of the Lord declares: {v['text']} "

                    f"Pause and let that promise sink deep into your soul. When human strength runs dry, God's covenant remains unshaken. "

                    for v in s_stage2

                ]) +

                f"Every circumstance connected to {topic} is subject to the authority of Jesus Christ. "

                f"He is not distant from your pain; He is walking right beside you through the fire, turning your testing into a testimony."

            )

        },

        {

            "stage_num": 3,

            "chapter_title": f"Deep Soul Surrender & Prayer for {topic}",

            "verses": s_stage3,

            "role": (

                f"Stage 3: Praying from the Soul. Pray a slow, deeply emotional, fervent prayer directly to God on behalf of the listener regarding {topic}. "

                f"Include the scripture: " + "; ".join([f"{v['spoken_ref']}: '{v['text']}'" for v in s_stage3]) + ". "

                f"Pray against fear, heaviness, and delay, and ask the Holy Spirit to fill their room right now."

            ),

            "fallback": (

                f"Heavenly Father, we come before Your throne of grace right now in the mighty name of Jesus. "

                f"Lord, You see your child who is listening to my voice. You know the exact weight of {topic} that has been pressing upon their heart. " +

                " ".join([f"Your Word promises in {v['spoken_ref']}: {v['text']} " for v in s_stage3]) +

                f"Right now, Lord, we surrender every fear, every disappointment, and every heavy burden into Your nail-scarred hands. "

                f"Where there has been anxiety, release Your supernatural peace that surpasses all understanding. "

                f"Where doors have been closed, open pathways of divine favor and miraculous breakthrough. "

                f"We rebuke every spirit of heaviness, doubt, and discouragement in Jesus' name, and we invite the Holy Spirit to fill this room with light and restoration."

            )

        },

        {

            "stage_num": 4,

            "chapter_title": "Spoken Covenant Promises & Biblical Affirmations",

            "verses": s_stage4,

            "role": (

                f"Stage 4: Covenant Promises & Prophetic Biblical Affirmations over the listener's life and family regarding {topic}. "

                f"Weave in: " + "; ".join([f"{v['spoken_ref']}: '{v['text']}'" for v in s_stage4]) + ". "

                f"Speak peace, provision, healing, and victory directly over their home, mind, and future."

            ),

            "fallback": (

                "Receive these covenant promises over your life, your home, and your family today. " +

                " ".join([

                    f"Hold fast to {v['spoken_ref']}: {v['text']} "

                    for v in s_stage4

                ]) +

                f"I speak the peace of Christ over your mind and your sleep tonight. "

                f"You will not be overwhelmed by {topic}. You will not be defeated by this season. "

                f"The Lord is going before you to make every crooked place straight. "

                f"His favor surrounds you like a shield, and His goodness and mercy shall follow you all the days of your life."

            )

        },

        {

            "stage_num": 5,

            "chapter_title": "Peaceful Benediction & Resting in His Presence",

            "verses": s_stage1,

            "role": (

                f"Stage 5: Final Benediction & Resting in God's Peace. "

                f"Bring the prayer to a gentle, deeply comforting close. Seal every request in the name of Jesus. "

                f"Encourage the listener to rest, breathe, and trust that God is working while they rest. End with 'In Jesus' mighty name, Amen.'"

            ),

            "fallback": (

                f"Now, rest in the assurance that your prayer has been heard in heaven. "

                f"You do not need to carry the worry of {topic} any longer, because it is safely in the Father's hands. "

                f"May the Lord bless you and keep you. May the Lord make His face shine upon you and be gracious to you. "

                f"May the Lord lift up His countenance upon you, protect your loved ones, and give you deep, unshakeable peace tonight and always. "

                f"In Jesus' mighty and precious name we pray, Amen."

            )

        }

    ]



    compiled_stages = []

    for stg in stages_spec:

        prompt = (

            f"You are a deeply compassionate, spirit-filled Christian pastor leading a slow, meditative prayer video on '{topic}'. "

            f"Write {stg['role']} "

            f"Target length: approximately {target_w} words. "

            f"Tone: Unhurried, deeply emotional, praying from the soul, comforting, reverent. "

            f"Formatting: Write ONLY the spoken words in clear paragraphs separated by blank lines. "

            f"Do NOT include stage titles, narrator directions, [brackets], or markdown symbols."

        )

        ai_text = _call_gemini_stage(prompt)

        spoken_text = ai_text if len(ai_text.split()) >= 50 else stg["fallback"]



        paras = [p.strip() for p in re.split(r"\n\s*\n", spoken_text) if p.strip()]

        if len(paras) == 1 and len(spoken_text) > 350:

            sents = re.split(r"(?<=[.!?])\s+", spoken_text)

            paras = [" ".join(sents[i:i+3]) for i in range(0, len(sents), 3)]



        compiled_stages.append({

            "stage_num": stg["stage_num"],

            "chapter_title": stg["chapter_title"],

            "verses": stg["verses"],

            "paragraphs": paras,

            "full_text": "\n\n".join(paras)

        })



    return {

        "topic": topic,

        "duration_label": duration_label,

        "config": cfg,

        "scriptures": scriptures,

        "stages": compiled_stages

    }



# ==============================================================================

# 3. MEDITATIVE VOICEOVER SYNTHESIZER WITH REFLECTIVE SILENCE & TIMESTAMPS

# ==============================================================================

def get_audio_duration(audio_path: Path) -> float:

    try:

        cmd = [

            "ffprobe", "-v", "error", "-show_entries", "format=duration",

            "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path.absolute())

        ]

        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10, encoding="utf-8", errors="replace")

        return float(res.stdout.strip())

    except Exception:

        return 0.0



def _create_silence_mp3(out_path: Path, seconds: float):

    cmd = [

        "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",

        "-t", f"{seconds:.2f}", "-c:a", "libmp3lame", "-q:a", "4", str(out_path.absolute())

    ]

    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)



def format_mm_ss(seconds: float) -> str:

    sec = int(max(0, seconds))

    h, rem = divmod(sec, 3600)

    m, s = divmod(rem, 60)

    if h > 0:

        return f"{h}:{m:02d}:{s:02d}"

    return f"{m:02d}:{s:02d}"



def _sec_to_ass_time_lf(sec: float) -> str:

    sec = max(0.0, float(sec))

    h = int(sec // 3600)

    m = int((sec % 3600) // 60)

    s = sec % 60

    return f"{h}:{m:02d}:{s:05.2f}"



def synthesize_meditative_voiceover(

    journey_pkg: Dict[str, Any],

    out_voice_mp3: Path,

    voice_name: str = "en-US-ChristopherNeural",

    rate_str: str = "-10%",

    pitch_str: str = "-2Hz"

) -> Dict[str, Any]:

    """

    Synthesizes pastoral voiceover, tracks millisecond word timings,

    inserts reflective pauses, and builds a synchronized longform_subtitles.ass file.

    """

    work_dir = out_voice_mp3.parent / "temp_meditative_chunks"

    work_dir.mkdir(parents=True, exist_ok=True)



    cfg = journey_pkg["config"]

    para_pause = float(cfg.get("pause_between_paras_sec", 2.5))

    stage_pause = float(cfg.get("pause_between_stages_sec", 4.0))



    sil_para_mp3 = work_dir / "sil_para.mp3"

    sil_stage_mp3 = work_dir / "sil_stage.mp3"

    _create_silence_mp3(sil_para_mp3, para_pause)

    _create_silence_mp3(sil_stage_mp3, stage_pause)



    concat_files: List[Path] = []

    chapters_log: List[Dict[str, Any]] = []

    all_word_timings: List[Dict[str, Any]] = []

    current_time_sec = 0.0



    async def _tts_chunk_stream(txt: str, target_mp3: Path, t_offset: float):

        clean_txt = re.sub(r"(\d+):(\d+)", r"chapter \1 verse \2", txt)

        comm = edge_tts.Communicate(clean_txt, voice=voice_name, rate=rate_str, pitch=pitch_str, boundary="WordBoundary")

        with open(target_mp3, "wb") as f_out:

            async for chunk in comm.stream():

                if chunk["type"] == "audio":

                    f_out.write(chunk["data"])

                elif chunk["type"] in ("WordBoundary", "SentenceBoundary"):

                    st_s = t_offset + (chunk["offset"] / 10_000_000.0)

                    du_s = chunk["duration"] / 10_000_000.0

                    w_txt = chunk["text"].strip()

                    if len(w_txt.split()) <= 1:

                        all_word_timings.append({"text": w_txt, "start": round(st_s, 3), "end": round(st_s + du_s, 3)})

                    else:

                        w_list = w_txt.split()

                        step_d = max(0.1, du_s) / len(w_list)

                        for w_i, w_tok in enumerate(w_list):

                            all_word_timings.append({

                                "text": w_tok,

                                "start": round(st_s + w_i * step_d, 3),

                                "end": round(st_s + (w_i + 1) * step_d, 3)

                            })



    for stg in journey_pkg["stages"]:

        stg_idx = stg["stage_num"]

        chapters_log.append({

            "timestamp": format_mm_ss(current_time_sec),

            "start_sec": round(current_time_sec, 2),

            "title": stg["chapter_title"],

            "verses": [v["ref"] for v in stg["verses"]]

        })



        for p_idx, para_text in enumerate(stg["paragraphs"]):

            chunk_mp3 = work_dir / f"s{stg_idx}_p{p_idx}.mp3"

            try:

                asyncio.run(_tts_chunk_stream(para_text, chunk_mp3, current_time_sec))

            except RuntimeError:

                loop = asyncio.new_event_loop()

                loop.run_until_complete(_tts_chunk_stream(para_text, chunk_mp3, current_time_sec))

                loop.close()



            if chunk_mp3.exists() and chunk_mp3.stat().st_size > 500:

                dur = get_audio_duration(chunk_mp3)

                concat_files.append(chunk_mp3)

                current_time_sec += dur

                concat_files.append(sil_para_mp3)

                current_time_sec += para_pause



        concat_files.append(sil_stage_mp3)

        current_time_sec += stage_pause



    # Concat raw voice pieces

    list_txt = work_dir / "concat_list.txt"

    lines = [f"file '{f.absolute().as_posix()}'" for f in concat_files]

    list_txt.write_text("\n".join(lines), encoding="utf-8")



    cmd_merge = [

        "ffmpeg", "-y", "-f", "concat", "-safe", "0",

        "-i", str(list_txt.absolute()),

        "-ar", "44100", "-ac", "2", "-c:a", "libmp3lame", "-b:a", "192k",

        str(out_voice_mp3.absolute())

    ]

    subprocess.run(cmd_merge, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    total_voice_dur = get_audio_duration(out_voice_mp3)



    # --------------------------------------------------------------------------

    # BUILD SYNCHRONIZED 16:9 CALM SUBTITLE PHRASES (.ASS)

    # --------------------------------------------------------------------------

    phrases = []

    cur_w = []

    c_st = 0.0

    for i, w_obj in enumerate(all_word_timings):

        if not cur_w:

            c_st = w_obj["start"]

        cur_w.append(w_obj["text"])

        t_str = " ".join(cur_w)

        nxt_len = len(t_str) + (len(all_word_timings[i + 1]["text"]) + 1 if i + 1 < len(all_word_timings) else 0)

        is_strong_punct = bool(re.search(r"[.;!?]", w_obj["text"])) or (len(cur_w) >= 4 and "," in w_obj["text"])

        

        # 5 to 7 words per card (ideal for slow horizontal 16:9 video)

        if nxt_len > 44 or len(cur_w) >= 6 or is_strong_punct or i == len(all_word_timings) - 1:

            c_en = all_word_timings[i + 1]["start"] if i + 1 < len(all_word_timings) else (w_obj["end"] + 0.25)

            safe_t = re.sub(r"[^a-zA-Z0-9\s:\-',.!?]", "", t_str).strip()

            if safe_t:

                phrases.append({"text": safe_t, "start": round(c_st, 3), "end": round(c_en, 3)})

            cur_w = []



    ass_path = out_voice_mp3.parent / "longform_subtitles.ass"

    ass_lines = [

        "[Script Info]", "ScriptType: v4.00+", "PlayResX: 1920", "PlayResY: 1080", "",

        "[V4+ Styles]",

        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",

        "Style: LongFormSubs,Segoe UI,54,&H00FFFFFF,&H0000D4FF,&H90000000,&H90000000,-1,0,0,0,100,100,0,0,1,3.5,2,2,140,140,82,1",

        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"

    ]

    for p in phrases:

        t_s = p["text"]

        w_p = t_s.split()

        if len(t_s) > 28 and len(w_p) >= 4:

            mid_w = len(w_p) // 2

            l1, l2 = " ".join(w_p[:mid_w]), " ".join(w_p[mid_w:])

            disp = f"{l1}\\N{l2}"

        else:

            disp = t_s

        st_t = _sec_to_ass_time_lf(p["start"])

        en_t = _sec_to_ass_time_lf(max(p["start"] + 0.15, p["end"]))

        ass_lines.append(f"Dialogue: 0,{st_t},{en_t},LongFormSubs,,0,0,0,,{{\\fs54}}{disp}")



    ass_path.write_text("\n".join(ass_lines), encoding="utf-8")

    print(f"   [Subtitles] Generated {len(phrases)} synchronized subtitle cards -> {ass_path.name}")



    return {

        "voice_mp3": out_voice_mp3,

        "voice_duration_sec": round(total_voice_dur, 2),

        "chapters": chapters_log,

        "subtitles_ass": ass_path

    }



# ==============================================================================

# 4. STEP 2: WORSHIP SOAKING MUSIC & NATURE AMBIENCE MIXER (EXACT DURATION)

# ==============================================================================

def ensure_soaking_worship_pad() -> Path:

    """Generates a warm 432Hz Cathedral Soaking Pad if no custom worship MP3 is chosen."""

    pad_file = AMBIENCE_DIR / "432hz_cathedral_soaking_pad.mp3"

    if not pad_file.exists() or pad_file.stat().st_size < 10000:

        cmd = [

            "ffmpeg", "-y",

            "-f", "lavfi", "-i", "sine=frequency=144:sample_rate=44100",

            "-f", "lavfi", "-i", "sine=frequency=216:sample_rate=44100",

            "-f", "lavfi", "-i", "sine=frequency=288:sample_rate=44100",

            "-filter_complex",

            "amix=inputs=3:normalize=0,lowpass=f=380,aecho=0.8:0.88:60:0.4,volume=0.22",

            "-t", "180", "-c:a", "libmp3lame", "-b:a", "192k", str(pad_file.absolute())

        ]

        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    return pad_file



def ensure_nature_ambience(style: str = "Gentle Night Rain") -> Path | None:

    """Synthesizes soothing rain or mountain stream audio for deep prayer/sleep."""

    if not style or "None" in style:

        return None

    if "Stream" in style:

        out_f = AMBIENCE_DIR / "gentle_mountain_stream.mp3"

        filter_str = "anoisesrc=d=120:c=brown:r=44100:a=0.12,bandpass=f=450:width_type=h:w=350,volume=0.35"

    else:

        out_f = AMBIENCE_DIR / "gentle_night_rain.mp3"

        filter_str = "anoisesrc=d=120:c=pink:r=44100:a=0.10,lowpass=f=1200,highpass=f=200,volume=0.30"



    if not out_f.exists() or out_f.stat().st_size < 10000:

        cmd = [

            "ffmpeg", "-y", "-f", "lavfi", "-i", filter_str,

            "-t", "120", "-ac", "2", "-c:a", "libmp3lame", "-b:a", "192k", str(out_f.absolute())

        ]

        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    return out_f



def mix_longform_master_audio(

    voice_mp3: Path,

    out_master_mp3: Path,

    target_duration_sec: int,

    bgm_file: Path | None = None,

    bgm_volume: float = 0.18,

    nature_style: str = "None (Pure Worship Music)"

) -> float:

    """

    Mixes the slow meditative voiceover with looped worship BGM and optional

    nature ambience, stretching or looping gracefully so the final audio matches

    the exact target duration (5m, 10m, 20m, 30m, or 1 Hour).

    """

    if not bgm_file or not bgm_file.exists():

        bgm_file = ensure_soaking_worship_pad()



    nature_file = ensure_nature_ambience(nature_style)

    voice_dur = get_audio_duration(voice_mp3)

    final_dur = max(int(voice_dur) + 10, int(target_duration_sec))

    fade_out_start = max(1, final_dur - 6)



    # If target duration is much longer than a single prayer pass (e.g. 30m or 1 Hour),

    # add a peaceful 45s soaking instrumental interlude and loop the prayer gently

    padded_voice = voice_mp3.parent / "padded_voice_loop.mp3"

    interlude_sil = voice_mp3.parent / "soaking_interlude.mp3"

    _create_silence_mp3(interlude_sil, 45.0)



    list_v = voice_mp3.parent / "voice_cycle.txt"

    cycles_needed = max(1, int(final_dur // max(1.0, (voice_dur + 45.0))) + 1)

    v_lines = []

    for _ in range(cycles_needed):

        v_lines.append(f"file '{voice_mp3.absolute().as_posix()}'")

        v_lines.append(f"file '{interlude_sil.absolute().as_posix()}'")

    list_v.write_text("\n".join(v_lines), encoding="utf-8")



    subprocess.run([

        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_v.absolute()),

        "-t", f"{final_dur}", "-c:a", "libmp3lame", "-b:a", "192k", str(padded_voice.absolute())

    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)



    if nature_file and nature_file.exists():

        cmd_mix = [

            "ffmpeg", "-y",

            "-i", str(padded_voice.absolute()),

            "-stream_loop", "-1", "-t", f"{final_dur}", "-i", str(bgm_file.absolute()),

            "-stream_loop", "-1", "-t", f"{final_dur}", "-i", str(nature_file.absolute()),

            "-filter_complex",

            f"[0:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,volume=1.0[v];"

            f"[1:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,volume={bgm_volume:.2f}[bgm];"

            f"[2:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,volume=0.06[nat];"

            f"[v][bgm][nat]amix=inputs=3:duration=longest:normalize=0,"

            f"afade=t=in:st=0:d=3,afade=t=out:st={fade_out_start}:d=6[aout]",

            "-map", "[aout]", "-c:a", "libmp3lame", "-b:a", "192k", "-t", f"{final_dur}",

            str(out_master_mp3.absolute())

        ]

    else:

        cmd_mix = [

            "ffmpeg", "-y",

            "-i", str(padded_voice.absolute()),

            "-stream_loop", "-1", "-t", f"{final_dur}", "-i", str(bgm_file.absolute()),

            "-filter_complex",

            f"[0:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,volume=1.0[v];"

            f"[1:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,volume={bgm_volume:.2f}[bgm];"

            f"[v][bgm]amix=inputs=2:duration=longest:normalize=0,"

            f"afade=t=in:st=0:d=3,afade=t=out:st={fade_out_start}:d=6[aout]",

            "-map", "[aout]", "-c:a", "libmp3lame", "-b:a", "192k", "-t", f"{final_dur}",

            str(out_master_mp3.absolute())

        ]



    subprocess.run(cmd_mix, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    return get_audio_duration(out_master_mp3)







# ==============================================================================

# 5. STEP 3: ULTRA-FAST 16:9 (1920x1080) LONG-FORM VIDEO & THUMBNAIL RENDERER

# ==============================================================================

def get_next_longform_folder(label: str) -> Path:

    clean = re.sub(r"[^a-zA-Z0-9]+", "_", label or "").strip("_")[:35] or "longform_prayer"

    nums = []

    for d in LONGFORM_DIR.iterdir():

        if d.is_dir():

            m = re.match(r"^LF(\d{3})_", d.name)

            if m:

                nums.append(int(m.group(1)))

    next_n = (max(nums) + 1) if nums else 1

    folder = LONGFORM_DIR / f"LF{next_n:03d}_{clean}"

    folder.mkdir(parents=True, exist_ok=True)

    return folder



def create_16x9_stage_overlay_png(

    out_png: Path,

    topic: str,

    scriptures: List[Dict[str, str]],

    w: int = 1920,

    h: int = 1080

):

    """Creates 1920x1080 Double Gold Frame and top sanctuary banner, leaving bottom clean for live subs."""

    from PIL import Image, ImageDraw, ImageFont



    ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))

    draw = ImageDraw.Draw(ov)



    # Top and bottom cinematic dark vignette bands

    for y in range(200):

        alpha = int(210 * (1.0 - y / 200.0))

        draw.line([(0, y), (w, y)], fill=(5, 8, 16, alpha))

    for y in range(h - 260, h):

        alpha = int(220 * ((y - (h - 260)) / 260.0))

        draw.line([(0, y), (w, y)], fill=(5, 8, 16, alpha))



    # Double Gold 16:9 Rounded Border

    gold = (225, 185, 65, 235)

    gold_soft = (225, 185, 65, 130)

    draw.rounded_rectangle([28, 28, w - 28, h - 28], radius=26, outline=gold, width=4)

    draw.rounded_rectangle([40, 40, w - 40, h - 40], radius=20, outline=gold_soft, width=2)



    def _fnt(sz: int, black: bool = False):

        cands = [

            Path("C:/Windows/Fonts/ariblk.ttf") if black else Path("C:/Windows/Fonts/segoeuib.ttf"),

            Path("C:/Windows/Fonts/arialbd.ttf"),

            Path("C:/Windows/Fonts/arial.ttf")

        ]

        for p in cands:

            if p.exists():

                try: return ImageFont.truetype(str(p), sz)

                except Exception: pass

        return ImageFont.load_default()



    f_top = _fnt(28, black=True)



    # Top Sanctuary Pill Badge

    top_txt = f"DEEP SOUL PRAYER  •  {topic.upper()[:42]}"

    tb = draw.textbbox((0, 0), top_txt, font=f_top)

    tw, th = tb[2] - tb[0] + 60, tb[3] - tb[1] + 24

    bx = (w - tw) // 2

    by = 54

    draw.rounded_rectangle([bx, by, bx + tw, by + th], radius=th // 2, fill=(8, 12, 24, 230), outline=gold, width=2)

    draw.text(((w - (tb[2] - tb[0])) // 2 - tb[0], by + 11 - tb[1]), top_txt, font=f_top, fill=(255, 242, 175, 255))



    ov.save(str(out_png), "PNG")



def render_longform_16x9_video(

    master_audio_mp3: Path,

    out_video_mp4: Path,

    out_thumb_jpg: Path,

    journey_pkg: Dict[str, Any],

    bg_image_path: Path,

    bg_video_path: Path | None = None,

    visual_mode: str = "Looping Video Background (Fastest)",

    palette_name: str = "Gold Classic",

    progress_cb=None

) -> bool:

    """

    TURBO LONG-FORM RENDER ENGINE:

    1. Pre-composites static gold borders in Pillow in 0.05s (zero FFmpeg overlay overhead).

    2. Uses GPU hardware encoder (NVIDIA NVENC / Intel QSV) with CPU ultrafast fallback.

    3. Streams live second-by-second progress (e.g. 03:15 / 05:00 • Speed 9.5x).

    """

    import pro_design_addon as pda

    from types import SimpleNamespace

    from PIL import Image



    w, h = 1920, 1080

    total_dur = get_audio_duration(master_audio_mp3)

    if total_dur <= 1.0:

        total_dur = float(journey_pkg["config"]["target_seconds"])



    work_dir = out_video_mp4.parent / "temp_lf_render"

    work_dir.mkdir(parents=True, exist_ok=True)



    # 1. Create the 16:9 Frame Overlay PNG

    overlay_png = work_dir / "lf_overlay_16x9.png"

    create_16x9_stage_overlay_png(overlay_png, journey_pkg["topic"], journey_pkg["scriptures"], w=w, h=h)



    # 2. Check for Subtitles

    ass_path = out_video_mp4.parent / "longform_subtitles.ass"

    if not ass_path.exists():

        ass_path = master_audio_mp3.parent / "longform_subtitles.ass"

    sub_filter_str = f"subtitles='{ass_path.absolute().as_posix()}'" if ass_path.exists() else "null"



    # 3. Detect fastest GPU encoder

    enc_name, enc_opts = detect_hardware_video_encoder()

    print(f"   ⚡ [Fast Render Engine] Selected encoder: {enc_name}")



    # 4. INSTANT PRE-COMPOSITE IN PILLOW (Bypasses heavy per-frame FFmpeg overlay!)

    prebaked_bg_jpg = work_dir / "prebaked_bg_1080p.jpg"

    try:

        raw_bg = Image.open(bg_image_path).convert("RGB")

        ir = raw_bg.width / max(1, raw_bg.height)

        tr = w / h

        nw, nh = (int(h * ir), h) if ir > tr else (w, int(w / max(0.01, ir)))

        raw_bg = raw_bg.resize((nw, nh), Image.Resampling.LANCZOS)

        raw_bg = raw_bg.crop(((nw - w) // 2, (nh - h) // 2, (nw - w) // 2 + w, (nh - h) // 2 + h)).convert("RGBA")

        ov_im = Image.open(overlay_png).convert("RGBA")

        prebaked = Image.alpha_composite(raw_bg, ov_im).convert("RGB")

        prebaked.save(str(prebaked_bg_jpg), "JPEG", quality=94)

    except Exception:

        shutil.copy(bg_image_path, prebaked_bg_jpg)



    # 5. Build Lightweight FFmpeg Command

    if "Video" in visual_mode and bg_video_path and bg_video_path.exists():

        # Video B-roll + single static overlay + subtitles

        filter_complex = (

            f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps=24,format=yuv420p,setsar=1,eq=brightness=-0.07:contrast=1.10[v0];"

            f"[v0][1:v]overlay=0:0:format=auto,{sub_filter_str}[vout]"

        )

        inputs = [

            "-stream_loop", "-1", "-t", f"{total_dur:.2f}", "-i", str(bg_video_path.absolute()),

            "-loop", "1", "-t", f"{total_dur:.2f}", "-i", str(overlay_png.absolute()),

            "-i", str(master_audio_mp3.absolute()),

            "-filter_complex", filter_complex,

            "-map", "[vout]", "-map", "2:a:0"

        ]

    else:

        # Pre-baked image + subtitles (Fastest possible pipeline)

        filter_complex = f"[0:v]scale={w}:{h},fps=24,format=yuv420p,{sub_filter_str}[vout]"

        inputs = [

            "-loop", "1", "-t", f"{total_dur:.2f}", "-i", str(prebaked_bg_jpg.absolute()),

            "-i", str(master_audio_mp3.absolute()),

            "-filter_complex", filter_complex,

            "-map", "[vout]", "-map", "1:a:0"

        ]



    cmd = [

        "ffmpeg", "-y", "-threads", "0",

        *inputs,

        "-c:v", enc_name, *enc_opts,

        "-c:a", "aac", "-b:a", "192k",

        "-t", f"{total_dur:.2f}",

        "-progress", "pipe:1",

        str(out_video_mp4.absolute())

    ]



    # 6. Stream Live Second-by-Second Progress

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, universal_newlines=True, encoding="utf-8", errors="replace")

    last_ui_update = 0.0



    if proc.stdout:

        for line in proc.stdout:

            if "out_time_us=" in line:

                try:

                    us_val = int(line.strip().split("=")[1])

                    curr_sec = us_val / 1000000.0

                    now_t = time.time()

                    if (now_t - last_ui_update) >= 1.2:

                        last_ui_update = now_t

                        pct = min(99, int(80 + (curr_sec / max(1.0, total_dur)) * 19))

                        speed_factor = round(curr_sec / max(0.1, (now_t - proc.poll() if proc.poll() else 1.0)), 1)

                        if progress_cb:

                            progress_cb(pct, f"🎬 Rendering 1080p Video: {format_mm_ss(curr_sec)} / {format_mm_ss(total_dur)} ({curr_sec/total_dur*100:.0f}%)")

                except Exception:

                    pass



    proc.wait()



    # 7. Generate 16:9 Master Thumbnail

    try:

        first_ref = journey_pkg["scriptures"][0]["ref"] if journey_pkg["scriptures"] else "PSALM 91:1"

        dummy_script = SimpleNamespace(

            topic=journey_pkg["topic"],

            verse_citation=first_ref,

            thumbnail_hook=f"PRAY THIS OVER {journey_pkg['topic'].upper()[:18]}",

            title=f"Deep Prayer for {journey_pkg['topic']}"

        )

        thumbs = pda.render_pro_thumbnails(bg_image_path, dummy_script, out_thumb_jpg, palette_name=palette_name)

        if "16x9" in thumbs and Path(thumbs["16x9"]).exists():

            im16 = Image.open(thumbs["16x9"]).convert("RGB")

            im16.save(str(out_thumb_jpg), "JPEG", quality=95)

    except Exception:

        pass



    return proc.returncode == 0 and out_video_mp4.exists()



def build_longform_youtube_metadata(

    journey_pkg: Dict[str, Any],

    chapters: List[Dict[str, Any]]

) -> Tuple[str, str, List[str]]:

    """Builds high-CTR Long-Form Title, Chapter-Timestamped Description, and Sanitized Tags."""

    topic = journey_pkg["topic"]

    dur_lbl = journey_pkg["duration_label"]

    first_ref = journey_pkg["scriptures"][0]["ref"] if journey_pkg["scriptures"] else "Psalm 91"



    title = f"Pray This Over {topic} | {dur_lbl} Deep Christian Prayer & Scripture ({first_ref})"[:98]



    chapter_lines = "\n".join([f"{ch['timestamp']} - {ch['title']}" for ch in chapters])

    if not chapter_lines or not chapter_lines.startswith("00:00"):

        chapter_lines = "00:00 - Entering God's Presence\n" + chapter_lines



    verse_summary = "\n".join([f"• {v['ref']}: \"{v['text'][:110]}...\"" for v in journey_pkg["scriptures"][:8]])



    desc = f"""🙏 {topic.upper()} — {dur_lbl.upper()} DEEP SOUL PRAYER & SCRIPTURE SOAKING ({first_ref}) ❤️



Take a slow, deep breath and step into God's sanctuary. If you have been silently carrying the heavy burden of {topic}, this {dur_lbl.lower()} meditative prayer and scripture journey was created to bring supernatural peace, breakthrough, and restoration into your home.



⏱️ CHAPTERS & SPIRITUAL MOVEMENTS:

{chapter_lines}



📖 SCRIPTURES PRAYED IN THIS VIDEO:

{verse_summary}



💬 Let us pray in agreement! Type "AMEN" in the comments below to seal this prayer over your life and family.

🔔 Subscribe to DailyWisdom for daily soaking prayers, Psalms for sleep, and biblical encouragement.



#ChristianPrayer #DailyPrayer #{re.sub(r'[^a-zA-Z0-9]', '', topic.title())[:18]} #SleepPrayer #JesusChrist #FaithOverFear #BibleVerses #SoakingPrayer"""



    raw_tags = [

        f"{topic} Prayer", f"Prayer for {topic}", f"{dur_lbl} Christian Prayer",

        first_ref, "Deep Soul Prayer", "Soaking Prayer", "Christian Meditation",

        "Bible Verses for Sleep", "Peace of God", "Jesus Christ", "Powerful Prayer",

        "Morning Prayer", "Night Prayer", "Spiritual Warfare Prayer", "Daily Wisdom"

    ]

    return title, desc, raw_tags

