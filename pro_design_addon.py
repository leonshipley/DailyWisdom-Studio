import re
import math
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

BASE_DIR = Path(__file__).resolve().parent
FONTS_DIR = BASE_DIR / "assets" / "fonts"

PALETTES: Dict[str, Dict[str, str]] = {
    "Gold Classic": {"bg": "#0B0F1A", "accent": "#FFC800", "text": "#FFFFFF", "alert": "#B3121A", "pill_bg": "#0B0F1ACC"},
    "Midnight Blue": {"bg": "#070B1F", "accent": "#7DD3FC", "text": "#FFFFFF", "alert": "#F59E0B", "pill_bg": "#070B1FCC"},
    "Sunrise": {"bg": "#1A0B0B", "accent": "#FFB347", "text": "#FFFFFF", "alert": "#E63946", "pill_bg": "#1A0B0BCC"},
    "Crimson Glory": {"bg": "#12060A", "accent": "#FFD166", "text": "#FFFFFF", "alert": "#C1121F", "pill_bg": "#12060ACC"},
}

SAFE_X_MIN, SAFE_X_MAX = 60, 900
SAFE_WIDTH = SAFE_X_MAX - SAFE_X_MIN  # 840 px

def hex_to_rgba(h: str, alpha: Optional[int] = None) -> Tuple[int, int, int, int]:
    h = h.lstrip("#")
    if len(h) == 8:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha if alpha is not None else int(h[6:8], 16))
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha if alpha is not None else 255)

def clean_ascii(text: str) -> str:
    if not text:
        return ""
    t = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace("—", " - ").replace("…", "...")
    return re.sub(r"\s+", " ", re.sub(r"[^\x20-\x7E]", "", t)).strip()

def get_font(bold_type: str = "extrabold", size: int = 60) -> ImageFont.FreeTypeFont:
    f_name = "Montserrat-ExtraBold.ttf" if bold_type == "extrabold" else "Montserrat-Bold.ttf"
    p = FONTS_DIR / f_name
    if not p.exists():
        p = BASE_DIR / "bold_font.ttf"
    try:
        return ImageFont.truetype(str(p), max(12, int(size)))
    except Exception:
        return ImageFont.load_default()

def wrap_and_fit(draw: ImageDraw.ImageDraw, text: str, max_w: int = SAFE_WIDTH, max_lines: int = 3, start_sz: int = 128, min_sz: int = 34, stroke: int = 10) -> Tuple[List[str], ImageFont.FreeTypeFont, int]:
    clean = clean_ascii(text)
    words = clean.split()
    if not words:
        return [""], get_font("extrabold", min_sz), min_sz
    for sz in range(start_sz, min_sz - 1, -2):
        f = get_font("extrabold", sz)
        lines, cur, ok = [], [], True
        for w in words:
            wb = draw.textbbox((0, 0), w, font=f, stroke_width=stroke)
            if (wb[2] - wb[0]) > max_w:
                ok = False
                break
            test = " ".join(cur + [w])
            tb = draw.textbbox((0, 0), test, font=f, stroke_width=stroke)
            if (tb[2] - tb[0]) <= max_w or not cur:
                cur.append(w)
            else:
                lines.append(" ".join(cur))
                cur = [w]
        if cur:
            lines.append(" ".join(cur))
        if ok and len(lines) <= max_lines:
            return lines, f, sz
    f = get_font("extrabold", min_sz)
    return [" ".join(words[:4]), " ".join(words[4:8])][:max_lines], f, min_sz

def render_pro_thumbnails(bg_image_path: Path, script: Any, thumb_path: Path, palette_name: str = "Gold Classic") -> Dict[str, Path]:
    """Generates 1080x1920 PNG/JPG, 1280x720 16:9 PNG, and 3 Hook Variant thumbnails using measured bboxes."""
    pal = PALETTES.get(palette_name, PALETTES["Gold Classic"])
    acc_c = hex_to_rgba(pal["accent"])
    txt_c = hex_to_rgba(pal["text"])
    alt_c = hex_to_rgba(pal["alert"], 235)
    pill_c = hex_to_rgba(pal["pill_bg"])

    raw_img = Image.open(bg_image_path).convert("RGB")

    def _build_one(w: int, h: int, hook_str: str, is_vertical: bool = True) -> Image.Image:
        # Aspect-fill resize & center crop
        ir = raw_img.width / raw_img.height
        tr = w / h
        nw, nh = (int(h * ir), h) if ir > tr else (w, int(w / ir))
        im = raw_img.resize((nw, nh), Image.Resampling.LANCZOS)
        im = im.crop(((nw - w) // 2, (nh - h) // 2, (nw - w) // 2 + w, (nh - h) // 2 + h))

        # Ensure first frame / thumbnail brightness >= 40
        luma = float(np.mean(np.asarray(im.convert("L"), dtype=np.float32)))
        if luma < 42.0:
            im = ImageEnhance.Brightness(im).enhance(min(2.0, 48.0 / max(1.0, luma)))
        im = ImageEnhance.Contrast(im).enhance(1.18).convert("RGBA")

        # Top 25% and Bottom 45% dark gradient overlay
        ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        od = ImageDraw.Draw(ov)
        top_lim, bot_start = int(h * 0.25), int(h * 0.55)
        for y in range(h):
            if y <= top_lim:
                a = int(205 * ((1.0 - y / max(1, top_lim)) ** 1.25))
            elif y >= bot_start:
                a = int(230 * (((y - bot_start) / max(1, h - bot_start)) ** 1.15))
            else:
                a = 30
            od.line([(0, y), (w, y)], fill=(6, 9, 18, min(240, a)))
        im = Image.alpha_composite(im, ov)
        draw = ImageDraw.Draw(im)

        # Thin double rounded border inset 40px (24px on 16:9)
        ins = 40 if is_vertical else 24
        draw.rounded_rectangle([ins, ins, w - ins, h - ins], radius=32 if is_vertical else 20, outline=acc_c, width=4)
        draw.rounded_rectangle([ins + 10, ins + 10, w - ins - 10, h - ins - 10], radius=26 if is_vertical else 16, outline=(acc_c[0], acc_c[1], acc_c[2], 120), width=2)

        # Top Badge Pill (Measured from text bbox)
        badge_str = clean_ascii(getattr(script, "topic", "DAILY DEVOTIONAL")).upper()[:26]
        f_badge = get_font("bold", 40 if is_vertical else 28)
        bb = draw.textbbox((0, 0), badge_str, font=f_badge)
        bw, bh = (bb[2] - bb[0]) + 64, (bb[3] - bb[1]) + 32
        bx1 = (w - bw) // 2
        by1 = 220 if is_vertical else 48
        draw.rounded_rectangle([bx1, by1, bx1 + bw, by1 + bh], radius=bh // 2, fill=pill_c, outline=acc_c, width=3)
        draw.text((bx1 + 32 - bb[0], by1 + 16 - bb[1]), badge_str, font=f_badge, fill=acc_c)

        # Main Hook (Max 3 lines, ALL CAPS, 120-140px auto-fitted, key word highlighted in measured box)
        max_tw = (SAFE_WIDTH - 20) if is_vertical else (w - 160)
        lines, f_hk, _ = wrap_and_fit(draw, hook_str.upper(), max_w=max_tw, max_lines=3 if is_vertical else 2, start_sz=132 if is_vertical else 88, min_sz=64 if is_vertical else 44, stroke=10 if is_vertical else 7)
        words_all = [w_tok for w_tok in clean_ascii(hook_str).upper().split() if len(w_tok) >= 4]
        key_w = max(words_all, key=len) if words_all else ""

        cy = 1040 if is_vertical else 185
        stroke_w = 10 if is_vertical else 7
        for ln in lines:
            toks = ln.split()
            sp_w = draw.textbbox((0, 0), " ", font=f_hk)[2]
            metrics = []
            row_w, row_h = 0, 0
            for idx_t, tk in enumerate(toks):
                tb = draw.textbbox((0, 0), tk, font=f_hk, stroke_width=stroke_w)
                tw, th = tb[2] - tb[0], tb[3] - tb[1]
                metrics.append((tk, tw, th, tb))
                row_w += tw + (sp_w if idx_t < len(toks) - 1 else 0)
                row_h = max(row_h, th)

            cur_x = (w - row_w) // 2
            if is_vertical:
                cur_x = max(SAFE_X_MIN, min(cur_x, SAFE_X_MAX - row_w))
            for tk, tw, th, tb in metrics:
                is_hi = (re.sub(r"[^A-Z0-9]", "", tk) == re.sub(r"[^A-Z0-9]", "", key_w)) and bool(key_w)
                if is_hi:
                    # Box sized strictly FROM the measured word bbox so it never clips
                    draw.rounded_rectangle([cur_x - 12, cy - 8, cur_x + tw + 12, cy + th + 8], radius=14, fill=alt_c, outline=acc_c, width=3)
                fill_c = acc_c if is_hi else txt_c
                dx, dy = cur_x - tb[0], cy - tb[1]
                draw.text((dx + 5, dy + 6), tk, font=f_hk, fill=(0, 0, 0, 220), stroke_width=stroke_w, stroke_fill=(0, 0, 0, 220))
                draw.text((dx, dy), tk, font=f_hk, fill=fill_c, stroke_width=stroke_w, stroke_fill=(0, 0, 0, 255))
                cur_x += tw + sp_w
            cy += row_h + (22 if is_vertical else 14)

        # Verse Reference Line (56px, accent color, preserves ':')
        v_ref = clean_ascii(getattr(script, "verse_citation", "Psalm 131:2")).upper()
        f_ref = get_font("extrabold", 56 if is_vertical else 40)
        rb = draw.textbbox((0, 0), v_ref, font=f_ref, stroke_width=6)
        rw = rb[2] - rb[0]
        ry = min(1470 if is_vertical else 530, cy + 20)
        draw.text(((w - rw) // 2 - rb[0], ry - rb[1]), v_ref, font=f_ref, fill=acc_c, stroke_width=6, stroke_fill=(0, 0, 0, 255))

        # CTA Pill at y=1560 (9:16) / y=600 (16:9)
        cta_str = "PRAY THIS NOW"
        f_cta = get_font("extrabold", 44 if is_vertical else 32)
        cb = draw.textbbox((0, 0), cta_str, font=f_cta)
        cw, ch = (cb[2] - cb[0]) + 76, (cb[3] - cb[1]) + 36
        cx1 = (w - cw) // 2
        cy1 = 1560 if is_vertical else 595
        draw.rounded_rectangle([cx1 + 4, cy1 + 6, cx1 + cw + 4, cy1 + ch + 6], radius=ch // 2, fill=(0, 0, 0, 160))
        draw.rounded_rectangle([cx1, cy1, cx1 + cw, cy1 + ch], radius=ch // 2, fill=acc_c, outline=(255, 255, 255, 240), width=3)
        draw.text((cx1 + 38 - cb[0], cy1 + 18 - cb[1]), cta_str, font=f_cta, fill=(10, 12, 20, 255))

        return im.convert("RGB")

    base_hook = getattr(script, "thumbnail_hook", "") or getattr(script, "title", "PEACE IN THE STORM")
    out_dir = thumb_path.parent

    img_9x16 = _build_one(1080, 1920, base_hook, is_vertical=True)
    img_9x16.save(str(thumb_path), "JPEG", quality=95)
    p_png_9x16 = out_dir / "thumbnail_9x16.png"
    img_9x16.save(str(p_png_9x16), "PNG")

    img_16x9 = _build_one(1280, 720, base_hook, is_vertical=False)
    p_png_16x9 = out_dir / "thumbnail_16x9.png"
    img_16x9.save(str(p_png_16x9), "PNG")

    # 3 Hook Variant Thumbnails
    variants = [
        base_hook,
        f"GODS PROMISE FOR {clean_ascii(getattr(script, 'topic', 'YOU')).upper()[:18]}",
        f"HOLD ONTO {clean_ascii(getattr(script, 'verse_citation', 'THIS VERSE')).upper()}",
    ]
    for idx_v, vh_text in enumerate(variants, start=1):
        v_im = _build_one(1080, 1920, vh_text, is_vertical=True)
        v_im.save(str(out_dir / f"thumbnail_9x16_variant_{idx_v}.png"), "PNG")

    return {"jpg": thumb_path, "9x16": p_png_9x16, "16x9": p_png_16x9}
