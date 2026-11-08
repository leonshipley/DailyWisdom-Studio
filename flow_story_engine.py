import os
import re
import csv
import io
import json
import time
import base64
import shutil
import asyncio
import urllib.request
import urllib.parse
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter
import edge_tts

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"
load_dotenv(ENV_FILE)

STORY_MOVIES_DIR = BASE_DIR / "story_movies"
STORY_MOVIES_DIR.mkdir(parents=True, exist_ok=True)

def get_active_gemini_key() -> str:
    load_dotenv(ENV_FILE, override=True)
    return os.getenv("GEMINI_API_KEY", "").strip()

def save_gemini_key_to_env(new_key: str) -> bool:
    clean_k = new_key.strip()
    if not clean_k:
        return False
    os.environ["GEMINI_API_KEY"] = clean_k
    lines = []
    if ENV_FILE.exists():
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    found = False
    new_lines = []
    for ln in lines:
        if ln.strip().startswith("GEMINI_API_KEY="):
            new_lines.append(f"GEMINI_API_KEY={clean_k}")
            found = True
        else:
            new_lines.append(ln)
    if not found:
        new_lines.append(f"GEMINI_API_KEY={clean_k}")
    ENV_FILE.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    return True

def test_gemini_key_capabilities(api_key: str = "") -> Dict[str, str]:
    key = (api_key or get_active_gemini_key()).strip()
    if not key:
        return {
            "text_brain": "No API Key Found",
            "imagen_api": "Using HD Super-Sharp Fallback",
            "veo_video_api": "Using Flow Web Studio Bridge"
        }
    report = {
        "text_brain": "Failed",
        "imagen_api": "Nano Banana 2.1 + 2K Lanczos Enhancer Ready",
        "veo_video_api": "Gemini Omni 1.2 Flash + Flow Studio Bridge Ready"
    }
    try:
        from google import genai
        client = genai.Client(api_key=key)
        for bm in ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-2.5-flash"]:
            try:
                res = client.models.generate_content(model=bm, contents="Say OK")
                if res and res.text:
                    report["text_brain"] = f"Connected ({bm})"
                    break
            except Exception:
                continue
        avail = [m.name.lower() for m in client.models.list()]
        if any("banana" in x or "image" in x for x in avail):
            report["imagen_api"] = "Gemini Nano Banana Image API Active on Key"
        if any("omni" in x for x in avail):
            report["veo_video_api"] = "Gemini Omni 1.2 Flash (15s Video) Visible on Key"
    except Exception as e:
        report["text_brain"] = f"Error: {str(e)[:60]}"
    return report

def master_sharp_hd_image(img_path: Path, target_w: int, target_h: int):
    if not img_path.exists():
        return
    try:
        im = Image.open(img_path).convert("RGB")
        ir = im.width / max(1, im.height)
        tr = target_w / max(1, target_h)
        nw, nh = (int(target_h * ir), target_h) if ir > tr else (target_w, int(target_w / max(0.01, ir)))
        im = im.resize((nw, nh), Image.Resampling.LANCZOS)
        left = (nw - target_w) // 2
        top = (nh - target_h) // 2
        im = im.crop((left, top, left + target_w, top + target_h))
        im = im.filter(ImageFilter.UnsharpMask(radius=1.6, percent=135, threshold=2))
        im = ImageEnhance.Contrast(im).enhance(1.08)
        im = ImageEnhance.Color(im).enhance(1.06)
        im = ImageEnhance.Sharpness(im).enhance(1.25)
        im.save(str(img_path), "JPEG", quality=98, subsampling=0, optimize=True)
    except Exception:
        pass

PRESET_STORY_TOPICS: List[str] = [
    "01. David and Goliath - The Shepherd Boy Who Faced the Impossible Giant (1 Samuel 17)",
    "02. Daniel in the Lions' Den - The Night Angels Shut the Lions' Mouths (Daniel 6)",
    "03. The Prodigal Son - The Father Who Ran to Forgive His Broken Child (Luke 15)",
    "04. The Widow's Jars of Oil - How God Paid an Impossible Debt Overnight (2 Kings 4)",
    "05. Job's Double Restoration - When God Turned Ashes into Double Glory (Job 42)",
    "06. Peter Walking on Water - In the Middle of the Storm, Jesus Reached Out (Matthew 14)",
    "07. Joseph's Journey - Betrayed by Brothers, Crowned in the Palace (Genesis 50:20)",
    "08. The Woman With the Issue of Blood - One Touch of Faith Changed Everything (Mark 5)",
    "09. Ruth and Boaz - From Emptiness and Grief to Redeemed Abundance (Ruth 2)",
    "10. Shadrach, Meshach & Abednego - The Fourth Man in the Fiery Furnace (Daniel 3)",
    "11. Modern Faith Story - The Poor Carpenter Who Left His Last Dollar at the Altar",
    "12. Modern Miracle Story - The Late-Night Knock That Saved a Family from Losing Everything"
]

def _extract_json(text: str) -> dict | None:
    if not text:
        return None
    s = text.find("{")
    e = text.rfind("}")
    if s != -1 and e != -1 and e > s:
        try:
            return json.loads(text[s:e+1])
        except Exception:
            pass
    return None

def analyze_and_create_story_board(
    story_topic: str,
    aspect_ratio: str = "16:9 Horizontal (1920x1080)",
    num_scenes: int = 12
) -> Dict[str, Any]:
    clean_topic = re.sub(r"^\d+\.\s*", "", story_topic).strip()
    key = get_active_gemini_key()
    orient_str = "vertical 9:16 portrait (1080x1920)" if "9:16" in aspect_ratio else "horizontal 16:9 widescreen (1920x1080)"

    prompt = (
        f"You are an elite Christian Film Director and Google Flow (Gemini Omni 1.2 Flash & Nano Banana 2.1) Prompt Architect.\n"
        f"Create a 3-MINUTE (180-second) Biblical/Faith Short Story Movie broken into EXACTLY {num_scenes} scenes (15s per scene).\n"
        f"Story Topic: {clean_topic}\n"
        f"Aspect Ratio: {orient_str}\n\n"
        f"Respond ONLY in valid JSON with keys: story_title, anchor_verse_ref, anchor_verse_text, character_dna, camera_style_lock, thumbnail_hook, "
        f"and 'scenes' (list of {num_scenes} objects with scene_num, act, narration [28-35 words], flow_image_prompt [full descriptive sentence including character_dna], flow_video_prompt [15s camera + subject motion], caption)."
    )

    ai_data = None
    if key:
        try:
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=key)
            for m_id in ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-2.5-flash", "gemini-2.0-flash"]:
                try:
                    res = client.models.generate_content(
                        model=m_id,
                        contents=prompt,
                        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.72)
                    )
                    if res and res.text:
                        ai_data = _extract_json(res.text)
                        if ai_data and ai_data.get("scenes"):
                            break
                except Exception:
                    continue
        except Exception:
            pass

    if not ai_data or not ai_data.get("scenes"):
        char_dna = "A 33-year-old Middle-Eastern man with warm expressive brown eyes, a neatly trimmed dark beard, and shoulder-length wavy dark-brown hair, wearing a textured cream-white handwoven linen tunic with an earth-brown wool shawl."
        cam_lock = f"Photorealistic {orient_str} cinematic frame on Arri Alexa 65, 50mm anamorphic lens at f/1.8, golden-hour volumetric rays, razor-sharp 8K photorealism."
        fallback_scenes = []
        acts = [
            ("Act 1: The Hook", "In the quiet stillness of the valley, a heavy burden pressed down until there seemed to be no way forward and no strength left to stand."),
            ("Act 1: The Hook", "Every human door had closed, and the whispers of doubt grew louder in the shadows of the night, testing the very foundation of faith."),
            ("Act 1: The Hook", "Yet even in the darkest hour, heaven was watching closely, preparing a miracle that no human eye could yet see."),
            ("Act 2: The Breaking Point", "Falling to his knees on the cold stone floor, he lifted trembling hands toward heaven and whispered a prayer from the depths of his soul."),
            ("Act 2: The Breaking Point", "He surrendered every fear, every broken plan, and every tear into the hands of the Almighty, choosing to trust when nothing made sense."),
            ("Act 3: The Divine Encounter", "Suddenly, a warm golden light broke through the darkness, filling the room with an unshakeable peace that surpassed all understanding."),
            ("Act 3: The Divine Encounter", "The voice of the Lord spoke softly to his spirit: Fear not, for I am with you; I will never leave you nor forsake you."),
            ("Act 3: The Divine Encounter", "Strength returned to his weary bones as he rose to his feet, knowing the battle belonged not to man, but to the living God."),
            ("Act 4: The Climax", "When the moment of testing arrived, what looked like an impossible giant began to crumble before the power of unwavering faith."),
            ("Act 4: The Climax", "Doors that had been locked for years swung wide open, and God poured out a blessing so abundant there was not room enough to contain it."),
            ("Act 5: The Moral & Scripture", "Those who had witnessed the struggle stood in awe, realizing that when God fights for you, no weapon formed against you shall prosper."),
            ("Act 5: The Moral & Scripture", "Whatever giant you are facing today, do not give up. Place your trust in Jesus Christ, for your story is about to turn into a testimony. Amen.")
        ]
        for idx, (act_name, narr) in enumerate(acts[:num_scenes], start=1):
            fallback_scenes.append({
                "scene_num": idx,
                "act": act_name,
                "narration": narr,
                "flow_image_prompt": f"{cam_lock} {char_dna} In this scene: {narr} Crisp focus on the eyes, natural lighting, zero text.",
                "flow_video_prompt": f"One continuous 15-second slow cinematic dolly push-in shot at 24fps. {char_dna} Subtle breathing and eye movement as wind stirs the linen tunic and golden light rays shift.",
                "caption": f"Scene {idx}: {act_name.split(':')[-1].strip()}"
            })
        ai_data = {
            "story_title": f"{clean_topic[:55]} | 3-Minute Faith Story",
            "anchor_verse_ref": "Isaiah 41:10",
            "anchor_verse_text": "Fear thou not; for I am with thee: be not dismayed; for I am thy God: I will strengthen thee.",
            "character_dna": char_dna,
            "camera_style_lock": cam_lock,
            "thumbnail_hook": "GOD FOUGHT THE BATTLE",
            "scenes": fallback_scenes
        }

    return {
        "topic": clean_topic,
        "aspect_ratio": aspect_ratio,
        "story_title": ai_data.get("story_title", clean_topic),
        "anchor_verse_ref": ai_data.get("anchor_verse_ref", "Isaiah 41:10"),
        "anchor_verse_text": ai_data.get("anchor_verse_text", ""),
        "character_dna": ai_data.get("character_dna", ""),
        "camera_style_lock": ai_data.get("camera_style_lock", ""),
        "thumbnail_hook": ai_data.get("thumbnail_hook", "GOD NEVER FAILS"),
        "scenes": ai_data.get("scenes", [])
    }

def generate_scene_image(
    prompt: str,
    out_img_path: Path,
    aspect_ratio: str = "16:9 Horizontal",
    seed: int = 42,
    image_model_pref: str = "Auto"
) -> Tuple[bool, str]:
    out_img_path.parent.mkdir(parents=True, exist_ok=True)
    is_vert = "9:16" in aspect_ratio
    w, h = (1080, 1920) if is_vert else (1920, 1080)
    orient_hint = "Vertical 9:16 portrait composition." if is_vert else "Horizontal 16:9 widescreen cinematic composition."
    full_img_prompt = f"Generate a photorealistic, ultra-sharp 4K cinematic photograph ({orient_hint}): {prompt}"

    key = get_active_gemini_key()
    if key and "Flux Only" not in image_model_pref:
        try:
            from google import genai
            client = genai.Client(api_key=key)
            banana_models = [
                "gemini-nano-banana-2.1",
                "gemini-3.1-flash-image-preview",
                "gemini-3.1-flash-lite-image",
                "gemini-2.5-flash-image"
            ]
            if hasattr(client, "interactions"):
                for bm in banana_models:
                    try:
                        inter = client.interactions.create(model=bm, input=full_img_prompt)
                        for out_item in getattr(inter, "outputs", []) or []:
                            if getattr(out_item, "type", "") == "image" and getattr(out_item, "data", None):
                                raw_b = base64.b64decode(out_item.data) if isinstance(out_item.data, str) else out_item.data
                                if len(raw_b) > 5000:
                                    out_img_path.write_bytes(raw_b)
                                    master_sharp_hd_image(out_img_path, w, h)
                                    return True, f"Google {bm}"
                    except Exception:
                        continue
            for bm in banana_models:
                try:
                    res = client.models.generate_content(model=bm, contents=[full_img_prompt])
                    for cand in getattr(res, "candidates", []) or []:
                        for part in getattr(cand.content, "parts", []) or []:
                            inl = getattr(part, "inline_data", None)
                            if inl and getattr(inl, "data", None):
                                raw_b = base64.b64decode(inl.data) if isinstance(inl.data, str) else inl.data
                                if len(raw_b) > 5000:
                                    out_img_path.write_bytes(raw_b)
                                    master_sharp_hd_image(out_img_path, w, h)
                                    return True, f"Google {bm}"
                except Exception:
                    continue
        except Exception:
            pass

    try:
        clean_p = urllib.parse.quote(
            f"masterpiece, award-winning 8k RAW cinema photograph, Arri Alexa 65, razor sharp focus, {prompt[:850]}"
        )
        flux_url = f"https://image.pollinations.ai/prompt/{clean_p}?width={w}&height={h}&seed={seed}&model=flux&enhance=true&nologo=true"
        req = urllib.request.Request(flux_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
            if data and len(data) > 10000:
                out_img_path.write_bytes(data)
                master_sharp_hd_image(out_img_path, w, h)
                return True, "Flux HD + 2K Lanczos Super-Sharp"
    except Exception:
        pass

    im = Image.new("RGB", (w, h), (10, 15, 28))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([40, 40, w - 40, h - 40], radius=30, outline=(225, 185, 65), width=4)
    im.save(str(out_img_path), "JPEG", quality=98, subsampling=0)
    return True, "Local HD Canvas"

def generate_scene_video_omni(
    video_prompt: str,
    out_mp4_path: Path,
    ref_image_path: Path | None = None,
    aspect_ratio: str = "16:9 Horizontal",
    duration_sec: int = 15,
    resolution: str = "1080p"
) -> Tuple[bool, str]:
    key = get_active_gemini_key()
    if not key:
        return False, "No GEMINI_API_KEY configured."

    ar_str = "9:16" if "9:16" in aspect_ratio else "16:9"
    dur_str = f"{min(15, max(3, int(duration_sec)))}s"
    omni_models = ["gemini-omni-1.2-flash", "gemini-omni-1.1-flash"]

    for om in omni_models:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/interactions?key={key}"
            payload = {
                "model": f"models/{om}",
                "input": video_prompt,
                "response_format": {
                    "aspect_ratio": ar_str,
                    "resolution": resolution,
                    "duration": dur_str
                }
            }
            req = urllib.request.Request(
                url,
                headers={"Content-Type": "application/json", "x-goog-api-key": key},
                data=json.dumps(payload).encode("utf-8")
            )
            with urllib.request.urlopen(req, timeout=90) as resp:
                r_data = json.loads(resp.read().decode("utf-8"))
                vid_b64 = r_data.get("output_video", {}).get("data")
                if not vid_b64:
                    for o_it in r_data.get("outputs", []):
                        if o_it.get("type") == "video" and o_it.get("data"):
                            vid_b64 = o_it["data"]
                            break
                if vid_b64:
                    out_mp4_path.write_bytes(base64.b64decode(vid_b64))
                    return True, f"Generated 15s Clip with {om}"
        except urllib.error.HTTPError as he:
            if he.code == 429:
                return False, "Gemini Omni 1.2 Flash requires Paid Tier-1 Billing on Google AI Studio (0 Free-Tier quota). Use the Exported Google Flow CSV Queue in flow.google or Ultra-Sharp 1080p Camera Motion!"
            continue
        except Exception:
            continue

    return False, "Omni API requires Tier-1 billing or Flow Web Studio. Use the Exported Google Flow CSV Queue or Ultra-Sharp 1080p Camera Motion!"

def build_google_flow_csv_bytes(storyboard: Dict[str, Any]) -> bytes:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Scene", "Act", "Model", "Duration", "Aspect_Ratio", "Image_Ingredient_Prompt", "Omni_Video_Motion_Prompt", "Spoken_Narration"])
    ar = "9:16" if "9:16" in storyboard.get("aspect_ratio", "") else "16:9"
    for sc in storyboard.get("scenes", []):
        writer.writerow([
            f"Scene_{sc['scene_num']:02d}",
            sc.get("act", ""),
            "gemini-omni-1.2-flash",
            "15s",
            ar,
            sc.get("flow_image_prompt", ""),
            sc.get("flow_video_prompt", ""),
            sc.get("narration", "")
        ])
    return out.getvalue().encode("utf-8")

def get_media_dur(p: Path) -> float:
    try:
        cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(p.absolute())]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=8, encoding="utf-8", errors="replace")
        return float(r.stdout.strip())
    except Exception:
        return 0.0

def get_next_story_folder(title: str) -> Path:
    clean = re.sub(r"[^a-zA-Z0-9]+", "_", title or "").strip("_")[:35] or "story_movie"
    nums = []
    for d in STORY_MOVIES_DIR.iterdir():
        if d.is_dir():
            m = re.match(r"^ST(\d{3})_", d.name)
            if m:
                nums.append(int(m.group(1)))
    next_n = (max(nums) + 1) if nums else 1
    folder = STORY_MOVIES_DIR / f"ST{next_n:03d}_{clean}"
    folder.mkdir(parents=True, exist_ok=True)
    return folder

def render_complete_3min_story_movie(
    storyboard: Dict[str, Any],
    work_folder: Path,
    voice_name: str = "en-US-ChristopherNeural",
    voice_rate: str = "-6%",
    bgm_file: Path | None = None,
    bgm_vol: float = 0.16,
    palette_name: str = "Gold Classic",
    progress_cb=None
) -> Tuple[bool, Path, Path]:
    import pro_design_addon as pda
    from types import SimpleNamespace

    is_vert = "9:16" in storyboard.get("aspect_ratio", "")
    w, h = (1080, 1920) if is_vert else (1920, 1080)

    scenes_dir = work_folder / "scenes"
    scenes_dir.mkdir(parents=True, exist_ok=True)

    sil_mp3 = scenes_dir / "pause_1_2s.mp3"
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-t", "1.20", "-c:a", "libmp3lame", "-q:a", "2", str(sil_mp3.absolute())
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    async def _tts(txt: str, out_p: Path):
        clean_t = re.sub(r"(\d+):(\d+)", r"chapter \1 verse \2", txt)
        comm = edge_tts.Communicate(clean_t, voice=voice_name, rate=voice_rate, pitch="-2Hz")
        await comm.save(str(out_p))

    rendered_scene_mp4s: List[Path] = []
    scenes_list = storyboard.get("scenes", [])
    total_sc = max(1, len(scenes_list))

    local_font = BASE_DIR / "bold_font.ttf"
    if not local_font.exists():
        for fp in ["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/arial.ttf"]:
            if Path(fp).exists():
                shutil.copy(fp, local_font)
                break

    for idx, sc in enumerate(scenes_list, start=1):
        if progress_cb:
            progress_cb(int((idx - 1) / total_sc * 75), f"Mastering Scene {idx}/{total_sc} in 1080p HD ({sc.get('act', '')})...")

        raw_v = scenes_dir / f"sc_{idx:02d}_raw.mp3"
        padded_v = scenes_dir / f"sc_{idx:02d}_voice.mp3"
        try:
            asyncio.run(_tts(sc["narration"], raw_v))
        except RuntimeError:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(_tts(sc["narration"], raw_v))
            loop.close()

        l_txt = scenes_dir / f"sc_{idx:02d}_aud_list.txt"
        l_txt.write_text(f"file '{raw_v.absolute().as_posix()}'\nfile '{sil_mp3.absolute().as_posix()}'\n", encoding="utf-8")
        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(l_txt.absolute()),
            "-c:a", "libmp3lame", "-b:a", "192k", str(padded_v.absolute())
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        sc_dur = max(4.0, get_media_dur(padded_v))

        flow_clip = scenes_dir / f"scene_{idx:02d}_flow.mp4"
        sc_img = scenes_dir / f"scene_{idx:02d}.jpg"
        if not sc_img.exists() and not flow_clip.exists():
            generate_scene_image(sc["flow_image_prompt"], sc_img, storyboard.get("aspect_ratio", "16:9"), seed=200 + idx)
        elif sc_img.exists():
            master_sharp_hd_image(sc_img, w, h)

        cap_raw = re.sub(r"[^a-zA-Z0-9\s,\.\-']", "", sc.get("narration", "")).strip()
        words = cap_raw.split()
        mid = len(words) // 2
        line_a = " ".join(words[:mid])[:62]
        line_b = " ".join(words[mid:])[:62]
        half_d = sc_dur / 2.0

        sc_out_mp4 = scenes_dir / f"scene_{idx:02d}_rendered.mp4"
        f_sz = 42 if is_vert else 36
        y_pos = h - 220 if is_vert else h - 110

        sub_filter = (
            f"drawbox=x=0:y={y_pos - 30}:w={w}:h=110:color=black@0.60:t=fill,"
            f"drawtext=fontfile='bold_font.ttf':text='{line_a}':fontcolor=white:fontsize={f_sz}:shadowcolor=black:shadowx=3:shadowy=3:x=(w-text_w)/2:y={y_pos}:enable='lt(t,{half_d:.2f})',"
            f"drawtext=fontfile='bold_font.ttf':text='{line_b}':fontcolor=0xFFD700:fontsize={f_sz}:shadowcolor=black:shadowx=3:shadowy=3:x=(w-text_w)/2:y={y_pos}:enable='gte(t,{half_d:.2f})'"
        )
        sharp_chain = "unsharp=5:5:0.95:5:5:0.0,eq=contrast=1.05:saturation=1.06"

        if flow_clip.exists() and flow_clip.stat().st_size > 5000:
            cmd_sc = [
                "ffmpeg", "-y",
                "-stream_loop", "-1", "-t", f"{sc_dur:.2f}", "-i", str(flow_clip.absolute()),
                "-i", str(padded_v.absolute()),
                "-vf", f"scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,crop={w}:{h},fps=30,{sharp_chain},format=yuv420p,setsar=1,{sub_filter}",
                "-map", "0:v:0", "-map", "1:a:0",
                "-c:v", "libx264", "-preset", "fast", "-crf", "17",
                "-c:a", "aac", "-b:a", "192k", "-t", f"{sc_dur:.2f}",
                str(sc_out_mp4.absolute())
            ]
        else:
            sw, sh = int(w * 1.14), int(h * 1.14)
            if idx % 2 == 1:
                crop_expr = f"crop={w}:{h}:'(in_w-out_w)/2':'(in_h-out_h)*(0.15+0.70*t/{sc_dur:.2f})'"
            else:
                crop_expr = f"crop={w}:{h}:'(in_w-out_w)*(0.15+0.70*t/{sc_dur:.2f})':'(in_h-out_h)/2'"

            cmd_sc = [
                "ffmpeg", "-y",
                "-loop", "1", "-t", f"{sc_dur:.2f}", "-i", str(sc_img.absolute()),
                "-i", str(padded_v.absolute()),
                "-vf", f"scale={sw}:{sh}:force_original_aspect_ratio=increase:flags=lanczos,{crop_expr},fps=30,{sharp_chain},format=yuv420p,setsar=1,{sub_filter}",
                "-map", "0:v:0", "-map", "1:a:0",
                "-c:v", "libx264", "-preset", "fast", "-crf", "17",
                "-c:a", "aac", "-b:a", "192k", "-t", f"{sc_dur:.2f}",
                str(sc_out_mp4.absolute())
            ]

        subprocess.run(cmd_sc, cwd=str(BASE_DIR), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if sc_out_mp4.exists():
            rendered_scene_mp4s.append(sc_out_mp4)

    if not rendered_scene_mp4s:
        return False, work_folder, work_folder

    if progress_cb:
        progress_cb(82, "Merging all 1080p scenes & mixing cinematic soundtrack...")

    concat_vid_txt = scenes_dir / "all_scenes.txt"
    concat_vid_txt.write_text("\n".join([f"file '{p.absolute().as_posix()}'" for p in rendered_scene_mp4s]), encoding="utf-8")
    merged_no_bgm = scenes_dir / "merged_no_bgm.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_vid_txt.absolute()),
        "-c", "copy", str(merged_no_bgm.absolute())
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    total_movie_dur = max(10.0, get_media_dur(merged_no_bgm))
    final_movie_mp4 = work_folder / f"{work_folder.name}.mp4"
    final_thumb_jpg = work_folder / f"{work_folder.name}_thumb.jpg"

    if bgm_file and Path(bgm_file).exists():
        fade_out_st = max(1.0, total_movie_dur - 5.0)
        subprocess.run([
            "ffmpeg", "-y",
            "-i", str(merged_no_bgm.absolute()),
            "-stream_loop", "-1", "-t", f"{total_movie_dur:.2f}", "-i", str(Path(bgm_file).absolute()),
            "-filter_complex",
            f"[0:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,volume=1.0[v];"
            f"[1:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,volume={bgm_vol:.2f},afade=t=out:st={fade_out_st:.1f}:d=5[bgm];"
            f"[v][bgm]amix=inputs=2:duration=first:normalize=0[aout]",
            "-map", "0:v:0", "-map", "[aout]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            str(final_movie_mp4.absolute())
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        shutil.copy(merged_no_bgm, final_movie_mp4)

    first_img = scenes_dir / "scene_01.jpg"
    if first_img.exists():
        try:
            dummy = SimpleNamespace(
                topic=storyboard.get("topic", "FAITH STORY")[:28],
                verse_citation=storyboard.get("anchor_verse_ref", "ISAIAH 41:10"),
                thumbnail_hook=storyboard.get("thumbnail_hook", "GOD FOUGHT FOR HIM"),
                title=storyboard.get("story_title", "Faith Story")
            )
            thumbs = pda.render_pro_thumbnails(first_img, dummy, final_thumb_jpg, palette_name=palette_name)
            if not is_vert and "16x9" in thumbs and Path(thumbs["16x9"]).exists():
                Image.open(thumbs["16x9"]).convert("RGB").save(str(final_thumb_jpg), "JPEG", quality=98, subsampling=0)
        except Exception:
            shutil.copy(first_img, final_thumb_jpg)

    if progress_cb:
        progress_cb(100, "3-Minute 1080p HD Story Movie Complete!")

    return final_movie_mp4.exists(), final_movie_mp4, final_thumb_jpg
