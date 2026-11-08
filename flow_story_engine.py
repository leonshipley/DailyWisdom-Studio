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
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter
import edge_tts

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"
load_dotenv(ENV_FILE)

STORY_MOVIES_DIR = BASE_DIR / "story_movies"
STORY_MOVIES_DIR.mkdir(parents=True, exist_ok=True)

# Cache the working image model so we never waste time retrying failed endpoints on every scene
_WORKING_IMG_MODEL: Optional[str] = None

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
            "veo_video_api": "Using Local Motion / Flow Bridge"
        }
    report = {
        "text_brain": "Failed",
        "imagen_api": "Flux HD + 2K Lanczos Enhancer Ready",
        "veo_video_api": "Local 3D Motion + Flow Bridge Ready"
    }
    try:
        from google import genai
        client = genai.Client(api_key=key)
        for bm in ["gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite"]:
            try:
                res = client.models.generate_content(model=bm, contents="Say OK")
                if res and res.text:
                    report["text_brain"] = f"Connected ({bm})"
                    break
            except Exception as e_b:
                report["text_brain"] = f"Error on {bm}: {str(e_b)[:50]}"
        avail = [m.name.lower() for m in client.models.list()]
        img_m = [x for x in avail if "banana" in x or "image" in x or "imagen" in x]
        vid_m = [x for x in avail if "omni" in x or "veo" in x]
        if img_m:
            report["imagen_api"] = f"Visible on Key: {', '.join(img_m[:2])}"
        if vid_m:
            report["veo_video_api"] = f"Visible on Key: {', '.join(vid_m[:2])}"
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
        im.save(str(img_path), "JPEG", quality=96, subsampling=0)
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
    num_scenes: int = 12,
    log_cb=None
) -> Dict[str, Any]:
    clean_topic = re.sub(r"^\d+\.\s*", "", story_topic).strip()
    key = get_active_gemini_key()
    orient_str = "vertical 9:16 portrait (1080x1920)" if "9:16" in aspect_ratio else "horizontal 16:9 widescreen (1920x1080)"

    if log_cb:
        log_cb(f"Analyzing story topic '{clean_topic}' ({num_scenes} scenes, {orient_str})...")

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
            for m_id in ["gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite"]:
                try:
                    if log_cb:
                        log_cb(f"Requesting 12-scene storyboard from Google model '{m_id}'...")
                    res = client.models.generate_content(
                        model=m_id,
                        contents=prompt,
                        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.72)
                    )
                    if res and res.text:
                        ai_data = _extract_json(res.text)
                        if ai_data and ai_data.get("scenes"):
                            if log_cb:
                                log_cb(f"SUCCESS: '{m_id}' generated {len(ai_data['scenes'])} scenes!")
                            break
                except Exception as e_m:
                    if log_cb:
                        log_cb(f"Model '{m_id}' notice: {str(e_m)[:90]}")
                    continue
        except Exception as e_Outer:
            if log_cb:
                log_cb(f"Gemini SDK error: {str(e_Outer)[:90]}")

    if not ai_data or not ai_data.get("scenes"):
        if log_cb:
            log_cb("Using built-in high-retention 12-scene storyboard template...")
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
    image_model_pref: str = "Auto",
    log_cb=None
) -> Tuple[bool, str]:
    global _WORKING_IMG_MODEL
    out_img_path.parent.mkdir(parents=True, exist_ok=True)
    is_vert = "9:16" in aspect_ratio
    w, h = (1080, 1920) if is_vert else (1920, 1080)
    orient_hint = "Vertical 9:16 portrait composition." if is_vert else "Horizontal 16:9 widescreen cinematic composition."
    full_img_prompt = f"Generate a photorealistic, ultra-sharp 4K cinematic photograph ({orient_hint}): {prompt}"

    key = get_active_gemini_key()
    if key and "Flux Only" not in image_model_pref and _WORKING_IMG_MODEL != "FLUX_FALLBACK":
        try:
            from google import genai
            client = genai.Client(api_key=key)
            candidates = [_WORKING_IMG_MODEL] if _WORKING_IMG_MODEL else [
                "gemini-2.0-flash-preview-image-generation",
                "gemini-2.5-flash-image"
            ]
            for bm in candidates:
                if not bm:
                    continue
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
                                    _WORKING_IMG_MODEL = bm
                                    return True, f"Google {bm}"
                except Exception as e_img:
                    if log_cb and not _WORKING_IMG_MODEL:
                        log_cb(f"Google Image API ({bm}): {str(e_img)[:75]} -> Switching to Fast Flux HD")
                    continue
            if not _WORKING_IMG_MODEL:
                _WORKING_IMG_MODEL = "FLUX_FALLBACK"
        except Exception:
            _WORKING_IMG_MODEL = "FLUX_FALLBACK"

    # Fast High-Bitrate Flux HD + 2K Lanczos Mastering
    try:
        clean_p = urllib.parse.quote(
            f"masterpiece, award-winning 8k RAW cinema photograph, Arri Alexa 65, razor sharp focus, {prompt[:750]}"
        )
        flux_url = f"https://image.pollinations.ai/prompt/{clean_p}?width={w}&height={h}&seed={seed}&model=flux&enhance=true&nologo=true"
        req = urllib.request.Request(flux_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=22) as resp:
            data = resp.read()
            if data and len(data) > 8000:
                out_img_path.write_bytes(data)
                master_sharp_hd_image(out_img_path, w, h)
                return True, "Flux HD + 2K Lanczos Super-Sharp"
    except Exception as e_flx:
        if log_cb:
            log_cb(f"Flux image note: {str(e_flx)[:70]} -> Using local Jesus HD wallpaper")

    # Fallback: Copy an existing high-res Jesus image from custom_media/backgrounds so it is NEVER a blank box
    bg_dir = BASE_DIR / "custom_media" / "backgrounds"
    existing_bgs = sorted(list(bg_dir.glob("*.jpg")) + list(bg_dir.glob("*.png"))) if bg_dir.exists() else []
    if existing_bgs:
        chosen_fb = existing_bgs[seed % len(existing_bgs)]
        shutil.copy(chosen_fb, out_img_path)
        master_sharp_hd_image(out_img_path, w, h)
        return True, f"Studio HD Vault ({chosen_fb.name})"

    im = Image.new("RGB", (w, h), (10, 15, 28))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([40, 40, w - 40, h - 40], radius=30, outline=(225, 185, 65), width=4)
    im.save(str(out_img_path), "JPEG", quality=96, subsampling=0)
    return True, "Local HD Canvas"

def generate_all_scene_images_parallel(
    storyboard: Dict[str, Any],
    scenes_dir: Path,
    image_model_pref: str = "Auto",
    progress_cb=None,
    log_cb=None
) -> int:
    """Generates scene images in parallel (4 workers) so 12 scenes finish in ~20s with live logs!"""
    scenes = storyboard.get("scenes", [])
    ar = storyboard.get("aspect_ratio", "16:9")
    total = max(1, len(scenes))
    completed = 0

    def _worker(sc_obj):
        s_num = sc_obj["scene_num"]
        t0 = time.time()
        out_p = scenes_dir / f"scene_{s_num:02d}.jpg"
        ok, eng = generate_scene_image(
            sc_obj["flow_image_prompt"], out_p, ar, seed=400 + s_num, image_model_pref=image_model_pref, log_cb=None
        )
        dt = time.time() - t0
        return s_num, ok, eng, dt

    if log_cb:
        log_cb(f"Starting parallel HD image generation for {total} scenes (4 concurrent workers)...")

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_worker, sc): sc["scene_num"] for sc in scenes}
        for fut in as_completed(futures):
            s_num, ok, eng, dt = fut.result()
            completed += 1
            pct = int(completed / total * 100)
            msg = f"Scene {s_num:02d}/{total} HD Image Ready in {dt:.1f}s ({eng})"
            if log_cb:
                log_cb(f"[OK] {msg}")
            if progress_cb:
                progress_cb(pct, msg)

    return completed

def render_local_3d_motion_clip(
    sc_img: Path,
    out_mp4: Path,
    duration_sec: float = 8.0,
    aspect_ratio: str = "16:9 Horizontal",
    scene_num: int = 1
) -> Tuple[bool, str]:
    """Renders a smooth 1080p 30fps camera-motion MP4 clip locally from the scene's HD image in ~2.5s!"""
    is_vert = "9:16" in aspect_ratio
    w, h = (1080, 1920) if is_vert else (1920, 1080)
    if not sc_img.exists():
        return False, f"Scene {scene_num} image missing"

    sw, sh = int(w * 1.15), int(h * 1.15)
    if scene_num % 2 == 1:
        crop_expr = f"crop={w}:{h}:'(in_w-out_w)/2':'(in_h-out_h)*(0.15+0.70*t/{duration_sec:.2f})'"
    else:
        crop_expr = f"crop={w}:{h}:'(in_w-out_w)*(0.15+0.70*t/{duration_sec:.2f})':'(in_h-out_h)/2'"

    vf_chain = f"scale={sw}:{sh}:force_original_aspect_ratio=increase:flags=lanczos,{crop_expr},fps=30,unsharp=5:5:0.9:5:5:0.0,format=yuv420p,setsar=1"
    cmd = [
        "ffmpeg", "-y", "-threads", "0",
        "-loop", "1", "-t", f"{duration_sec:.2f}", "-i", str(sc_img.absolute()),
        "-vf", vf_chain,
        "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        str(out_mp4.absolute())
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode == 0 and out_mp4.exists() and out_mp4.stat().st_size > 5000:
        return True, f"Rendered 1080p 30fps Motion Clip ({duration_sec:.0f}s)"
    return False, f"FFmpeg error: {res.stderr[-160:]}"

def generate_scene_video_omni(
    video_prompt: str,
    out_mp4_path: Path,
    ref_image_path: Path | None = None,
    aspect_ratio: str = "16:9 Horizontal",
    duration_sec: int = 10,
    resolution: str = "1080p",
    scene_num: int = 1,
    allow_local_fallback: bool = True,
    log_cb=None
) -> Tuple[bool, str]:
    """
    1. Tries Google's Video API (Omni / Veo) and logs the exact response or error immediately.
    2. If API returns 429/404 (Free-Tier key without Paid Video Billing), automatically renders
       a 1080p 30fps 3D Camera Motion video clip from the Scene's HD Image so it NEVER fails!
    """
    key = get_active_gemini_key()
    ar_str = "9:16" if "9:16" in aspect_ratio else "16:9"
    dur_str = f"{min(15, max(5, int(duration_sec)))}s"

    if key:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/interactions?key={key}"
            payload = {
                "model": "models/gemini-omni-1.2-flash",
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
            with urllib.request.urlopen(req, timeout=25) as resp:
                r_data = json.loads(resp.read().decode("utf-8"))
                vid_b64 = r_data.get("output_video", {}).get("data")
                if not vid_b64:
                    for o_it in r_data.get("outputs", []):
                        if o_it.get("type") == "video" and o_it.get("data"):
                            vid_b64 = o_it["data"]
                            break
                if vid_b64:
                    out_mp4_path.write_bytes(base64.b64decode(vid_b64))
                    return True, "Generated via Gemini Omni 1.2 Flash API"
        except urllib.error.HTTPError as he:
            err_body = ""
            try:
                err_body = he.read().decode("utf-8", errors="replace")[:140]
            except Exception:
                pass
            api_err_msg = f"Google Omni API HTTP {he.code}: {err_body or he.reason}"
            if log_cb:
                log_cb(f"[API Notice] Scene {scene_num}: {api_err_msg}")
            if not allow_local_fallback:
                return False, api_err_msg
        except Exception as e_gen:
            if log_cb:
                log_cb(f"[API Notice] Scene {scene_num}: {str(e_gen)[:100]}")
            if not allow_local_fallback:
                return False, str(e_gen)[:100]

    # Automatic Local 1080p 3D Camera Motion Fallback so the user ALWAYS gets a playable MP4 clip
    if allow_local_fallback and ref_image_path and ref_image_path.exists():
        if log_cb:
            log_cb(f"Scene {scene_num}: Rendering instant 1080p 30fps 3D Camera Motion clip from Scene Image...")
        return render_local_3d_motion_clip(ref_image_path, out_mp4_path, duration_sec=float(duration_sec), aspect_ratio=aspect_ratio, scene_num=scene_num)

    return False, "No video generated (Generate Scene Images first or enable local motion fallback)."

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

def create_scene_subtitle_overlay_png(out_png: Path, text_line1: str, text_line2: str, act_label: str, w: int, h: int):
    """
    Renders a crystal-clear transparent RGBA subtitle & act badge overlay using Pillow.
    100% immune to FFmpeg drawtext apostrophe/quote crashes!
    """
    ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(ov)

    is_vert = h > w
    f_sz = 40 if is_vert else 36
    f_act_sz = 24 if is_vert else 22

    font_main = ImageFont.load_default()
    font_act = ImageFont.load_default()
    for fp in ["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/arial.ttf"]:
        if Path(fp).exists():
            try:
                font_main = ImageFont.truetype(fp, f_sz)
                font_act = ImageFont.truetype(fp, f_act_sz)
                break
            except Exception:
                pass

    # Bottom gradient bar for readability
    bar_h = 200 if is_vert else 150
    for y in range(h - bar_h, h):
        alpha = int(215 * ((y - (h - bar_h)) / float(bar_h)))
        draw.line([(0, y), (w, y)], fill=(5, 8, 16, alpha))

    # Top-left subtle Act pill
    if act_label:
        ab = draw.textbbox((0, 0), act_label.upper(), font=font_act)
        aw, ah = ab[2] - ab[0] + 36, ab[3] - ab[1] + 18
        draw.rounded_rectangle([36, 36, 36 + aw, 36 + ah], radius=ah // 2, fill=(8, 13, 26, 200), outline=(225, 185, 65, 200), width=2)
        draw.text((54 - ab[0], 45 - ab[1]), act_label.upper(), font=font_act, fill=(255, 240, 175, 255))

    y1 = h - (155 if is_vert else 115)
    y2 = y1 + (52 if is_vert else 46)

    for ln_txt, y_pos, col in [(text_line1, y1, (255, 255, 255, 255)), (text_line2, y2, (255, 215, 0, 255))]:
        if not ln_txt:
            continue
        bb = draw.textbbox((0, 0), ln_txt, font=font_main, stroke_width=4)
        tw = bb[2] - bb[0]
        tx = (w - tw) // 2 - bb[0]
        draw.text((tx, y_pos), ln_txt, font=font_main, fill=col, stroke_width=4, stroke_fill=(0, 0, 0, 245))

    ov.save(str(out_png), "PNG")

def render_complete_3min_story_movie(
    storyboard: Dict[str, Any],
    work_folder: Path,
    voice_name: str = "en-US-ChristopherNeural",
    voice_rate: str = "-6%",
    bgm_file: Path | None = None,
    bgm_vol: float = 0.16,
    palette_name: str = "Gold Classic",
    progress_cb=None,
    log_cb=None
) -> Tuple[bool, Path, Path]:
    import pro_design_addon as pda
    from types import SimpleNamespace

    is_vert = "9:16" in storyboard.get("aspect_ratio", "")
    w, h = (1080, 1920) if is_vert else (1920, 1080)

    scenes_dir = work_folder / "scenes"
    scenes_dir.mkdir(parents=True, exist_ok=True)

    # Step A: Ensure all scene images exist first (parallel if missing)
    scenes_list = storyboard.get("scenes", [])
    total_sc = max(1, len(scenes_list))
    missing_imgs = [
        sc for sc in scenes_list
        if not (scenes_dir / f"scene_{sc['scene_num']:02d}.jpg").exists()
        and not (scenes_dir / f"scene_{sc['scene_num']:02d}_flow.mp4").exists()
    ]
    if missing_imgs:
        if log_cb:
            log_cb(f"Generating {len(missing_imgs)} missing scene image(s) in parallel first...")
        generate_all_scene_images_parallel(storyboard, scenes_dir, progress_cb=progress_cb, log_cb=log_cb)

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

    for idx, sc in enumerate(scenes_list, start=1):
        t_sc0 = time.time()
        pct_now = int((idx - 1) / total_sc * 78)
        if progress_cb:
            progress_cb(pct_now, f"Mastering Scene {idx}/{total_sc} ({sc.get('act', '')})...")
        if log_cb:
            log_cb(f"Scene {idx:02d}/{total_sc}: Synthesizing voiceover & mastering 1080p video...")

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
        if sc_img.exists():
            master_sharp_hd_image(sc_img, w, h)

        # Build crash-proof Pillow PNG subtitle overlay for this scene
        words = sc.get("narration", "").strip().split()
        mid = len(words) // 2
        line_a = " ".join(words[:mid])[:68]
        line_b = " ".join(words[mid:])[:68]
        sub_png = scenes_dir / f"sc_{idx:02d}_sub.png"
        create_scene_subtitle_overlay_png(sub_png, line_a, line_b, sc.get("act", ""), w, h)

        sc_out_mp4 = scenes_dir / f"scene_{idx:02d}_rendered.mp4"
        sharp_chain = "unsharp=5:5:0.85:5:5:0.0,eq=contrast=1.04:saturation=1.05"

        if flow_clip.exists() and flow_clip.stat().st_size > 5000:
            cmd_sc = [
                "ffmpeg", "-y", "-threads", "0",
                "-stream_loop", "-1", "-t", f"{sc_dur:.2f}", "-i", str(flow_clip.absolute()),
                "-loop", "1", "-t", f"{sc_dur:.2f}", "-i", str(sub_png.absolute()),
                "-i", str(padded_v.absolute()),
                "-filter_complex",
                f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,crop={w}:{h},fps=24,{sharp_chain},format=yuv420p,setsar=1[bg];"
                f"[bg][1:v]overlay=0:0:format=auto,format=yuv420p[vout]",
                "-map", "[vout]", "-map", "2:a:0",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
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
                "ffmpeg", "-y", "-threads", "0",
                "-loop", "1", "-t", f"{sc_dur:.2f}", "-i", str(sc_img.absolute()),
                "-loop", "1", "-t", f"{sc_dur:.2f}", "-i", str(sub_png.absolute()),
                "-i", str(padded_v.absolute()),
                "-filter_complex",
                f"[0:v]scale={sw}:{sh}:force_original_aspect_ratio=increase:flags=lanczos,{crop_expr},fps=24,{sharp_chain},format=yuv420p,setsar=1[bg];"
                f"[bg][1:v]overlay=0:0:format=auto,format=yuv420p[vout]",
                "-map", "[vout]", "-map", "2:a:0",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                "-c:a", "aac", "-b:a", "192k", "-t", f"{sc_dur:.2f}",
                str(sc_out_mp4.absolute())
            ]

        res_sc = subprocess.run(cmd_sc, cwd=str(BASE_DIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
        if res_sc.returncode == 0 and sc_out_mp4.exists() and sc_out_mp4.stat().st_size > 5000:
            rendered_scene_mp4s.append(sc_out_mp4)
            if log_cb:
                log_cb(f"[OK] Scene {idx:02d} rendered ({sc_dur:.1f}s clip in {time.time() - t_sc0:.1f}s)")
        else:
            if log_cb:
                log_cb(f"[ERROR] Scene {idx:02d} FFmpeg error: {res_sc.stderr[-220:]}")

    if not rendered_scene_mp4s:
        return False, work_folder, work_folder

    if progress_cb:
        progress_cb(85, "Merging all 1080p scenes & mixing cinematic soundtrack...")
    if log_cb:
        log_cb(f"Concatenating {len(rendered_scene_mp4s)} scenes & mixing background music...")

    concat_vid_txt = scenes_dir / "all_scenes.txt"
    concat_vid_txt.write_text("\n".join([f"file '{p.absolute().as_posix()}'" for p in rendered_scene_mp4s]), encoding="utf-8")
    merged_no_bgm = scenes_dir / "merged_no_bgm.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_vid_txt.absolute()),
        "-c", "copy", str(merged_no_bgm.absolute())
    ], capture_output=True, text=True, encoding="utf-8", errors="replace")

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
        ], capture_output=True, text=True, encoding="utf-8", errors="replace")
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
    if log_cb:
        log_cb(f"MOVIE READY: {final_movie_mp4.name} ({total_movie_dur:.1f}s)")

    return final_movie_mp4.exists(), final_movie_mp4, final_thumb_jpg
