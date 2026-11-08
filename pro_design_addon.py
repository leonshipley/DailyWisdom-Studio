import re
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Tuple
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

BASE_DIR = Path(__file__).resolve().parent

def clean_ascii(text: str) -> str:
    if not text:
        return ""
    t = (text.replace("’", "'").replace("‘", "'")
             .replace("“", '"').replace("”", '"')
             .replace("—", " - ").replace("…", "..."))
    return re.sub(r"\s+", " ", re.sub(r"[^\x20-\x7E]", "", t)).strip()

def get_black_font(size: int = 60) -> ImageFont.FreeTypeFont:
    """Finds Arial Black or Impact on Windows for ultra-thick thumbnail typography."""
    candidates = [
        Path("C:/Windows/Fonts/ariblk.ttf"),    # Arial Black (Thickest & cleanest)
        Path("C:/Windows/Fonts/impact.ttf"),    # Impact
        Path("C:/Windows/Fonts/segoeuib.ttf"),  # Segoe UI Bold
        Path("C:/Windows/Fonts/arialbd.ttf"),   # Arial Bold
    ]
    for p in candidates:
        if p.exists():
            try:
                return ImageFont.truetype(str(p), max(12, int(size)))
            except Exception:
                continue
    return ImageFont.load_default()

def get_bold_font(size: int = 40) -> ImageFont.FreeTypeFont:
    candidates = [
        Path("C:/Windows/Fonts/segoeuib.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf"),
        Path("C:/Windows/Fonts/arial.ttf")
    ]
    for p in candidates:
        if p.exists():
            try:
                return ImageFont.truetype(str(p), max(12, int(size)))
            except Exception:
                continue
    return ImageFont.load_default()

def split_hook(hook_str: str) -> Tuple[str, str]:
    """Splits headline so Line 1 gets 3D Gold and Line 2 gets White."""
    words = clean_ascii(hook_str).upper().strip().split()
    if not words:
        return ("BREAK", "THE CHAINS")
    if len(words) == 1:
        return (words[0], "")
    if len(words) == 2:
        return (words[0], words[1])
    if len(words) == 3:
        return (words[0], f"{words[1]} {words[2]}")
    # 4+ words: e.g. DON'T / GIVE UP YET, BREAK / EVERY DEBT, PEACE / IN THE STORM
    if words[0] in ("BREAK", "DON'T", "DONT", "STOP", "NEVER", "GOD", "PRAY", "PEACE", "HEAL", "HOLD", "NO"):
        return (words[0], " ".join(words[1:]))
    mid = len(words) // 2
    return (" ".join(words[:mid]), " ".join(words[mid:]))

def render_3d_gold_text(canvas: Image.Image, text: str, font: ImageFont.FreeTypeFont, 
                        cx: int, cy: int, stroke_w: int = 14):
    """Draws true 3D chiseled metallic gold gradient text with multi-layer drop shadows."""
    draw = ImageDraw.Draw(canvas)
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_w)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    tx = cx - tw // 2 - bbox[0]
    ty = cy - th // 2 - bbox[1]

    # 1. Multi-layer Dark 3D Drop Shadow
    for off in range(12, 3, -1):
        alpha = int(180 * (off / 12.0))
        draw.text((tx + off, ty + off + 2), text, font=font, 
                  fill=(0, 0, 0, alpha), stroke_width=stroke_w + 4, stroke_fill=(0, 0, 0, alpha))

    # 2. Thick Pitch-Black Outline
    draw.text((tx, ty), text, font=font, fill=(0, 0, 0, 255), 
              stroke_width=stroke_w, stroke_fill=(0, 0, 0, 255))

    # 3. Create Metallic Gold Gradient (Light Yellow -> Rich Amber Gold -> Deep Bronze)
    grad_pad = 40
    gw, gh = tw + grad_pad * 2, th + grad_pad * 2
    grad_img = Image.new("RGBA", (gw, gh), (0, 0, 0, 0))
    g_draw = ImageDraw.Draw(grad_img)

    c_top = (255, 250, 185)   # Light glowing gold
    c_mid = (235, 185, 55)    # Rich metallic gold
    c_bot = (165, 105, 10)    # Deep bronze gold

    for y in range(gh):
        rat = y / max(1, gh - 1)
        if rat < 0.45:
            sr = rat / 0.45
            cr = int(c_top[0] * (1 - sr) + c_mid[0] * sr)
            cg = int(c_top[1] * (1 - sr) + c_mid[1] * sr)
            cb = int(c_top[2] * (1 - sr) + c_mid[2] * sr)
        else:
            sr = (rat - 0.45) / 0.55
            cr = int(c_mid[0] * (1 - sr) + c_bot[0] * sr)
            cg = int(c_mid[1] * (1 - sr) + c_bot[1] * sr)
            cb = int(c_mid[2] * (1 - sr) + c_bot[2] * sr)
        g_draw.line([(0, y), (gw, y)], fill=(cr, cg, cb, 255))

    # 4. Text Mask to cut out the gold gradient
    mask_img = Image.new("L", (gw, gh), 0)
    m_draw = ImageDraw.Draw(mask_img)
    m_draw.text((grad_pad - bbox[0], grad_pad - bbox[1]), text, font=font, fill=255)

    canvas.paste(grad_img, (tx - grad_pad, ty - grad_pad), mask=mask_img)

def render_pro_thumbnails(bg_image_path: Path, script: Any, thumb_path: Path, palette_name: str = "Gold Classic") -> Dict[str, Path]:
    """Creates thumbnails that match the reference design."""
    raw_img = Image.open(bg_image_path).convert("RGB")

    def _build(w: int, h: int, is_vertical: bool = True) -> Image.Image:
        # Aspect fill and center crop
        ir = raw_img.width / raw_img.height
        tr = w / h
        nw, nh = (int(h * ir), h) if ir > tr else (w, int(w / ir))
        im = raw_img.resize((nw, nh), Image.Resampling.LANCZOS)
        im = im.crop(((nw - w) // 2, (nh - h) // 2, (nw - w) // 2 + w, (nh - h) // 2 + h))

        # Brightness & contrast boost for cinematic punch
        im = ImageEnhance.Contrast(im).enhance(1.15)
        im = ImageEnhance.Color(im).enhance(1.12).convert("RGBA")

        # HEAVY CINEMATIC DARK VIGNETTE (Crucial so text and stickers NEVER wash out!)
        vignette = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        vd = ImageDraw.Draw(vignette)
        top_h = int(h * (0.24 if is_vertical else 0.30))
        bot_start = int(h * (0.46 if is_vertical else 0.42))

        for y in range(h):
            if y <= top_h:
                a = int(225 * ((1.0 - y / max(1, top_h)) ** 1.3))
            elif y >= bot_start:
                # Heavy dark shadow at the bottom for maximum text contrast
                a = int(245 * (((y - bot_start) / max(1, h - bot_start)) ** 1.05))
            else:
                a = 25
            vd.line([(0, y), (w, y)], fill=(5, 8, 16, min(245, a)))
        im = Image.alpha_composite(im, vignette)
        draw = ImageDraw.Draw(im)

        # 1. DOUBLE METALLIC GOLD BORDER WITH CORNER DIAMONDS
        gold_border = (225, 185, 65)
        ins1 = 36 if is_vertical else 20
        ins2 = ins1 + 14
        r1 = 44 if is_vertical else 24
        r2 = r1 - 10

        draw.rounded_rectangle([ins1, ins1, w - ins1, h - ins1], radius=r1, outline=gold_border, width=4)
        draw.rounded_rectangle([ins2, ins2, w - ins2, h - ins2], radius=r2, outline=(gold_border[0], gold_border[1], gold_border[2], 140), width=2)

        # Corner diamond accents
        for cx, cy in [(ins1 + 6, ins1 + 6), (w - ins1 - 6, ins1 + 6), (ins1 + 6, h - ins1 - 6), (w - ins1 - 6, h - ins1 - 6)]:
            draw.polygon([(cx, cy - 6), (cx + 6, cy), (cx, cy + 6), (cx - 6, cy)], fill=gold_border)

        # 2. TOP PILL BADGE (e.g. DEBT & FINANCIAL FREEDOM)
        topic_text = clean_ascii(getattr(script, "topic", "DAILY DEVOTIONAL")).upper()
        f_badge_sz = 34 if len(topic_text) <= 25 else max(24, int(760 / max(1, len(topic_text) * 0.62)))
        f_badge = get_black_font(f_badge_sz if is_vertical else 22)
        bb = draw.textbbox((0, 0), topic_text, font=f_badge)
        bw, bh = (bb[2] - bb[0]) + 70, (bb[3] - bb[1]) + 30
        bx = (w - bw) // 2
        by = 130 if is_vertical else 38

        # Shadow + dark pill + gold outline
        draw.rounded_rectangle([bx + 3, by + 5, bx + bw + 3, by + bh + 5], radius=bh // 2, fill=(0, 0, 0, 190))
        draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=bh // 2, fill=(9, 14, 25, 245), outline=gold_border, width=3)
        draw.text(((w - (bb[2] - bb[0])) // 2 - bb[0], by + (bh - (bb[3] - bb[1])) // 2 - bb[1]), 
                  topic_text, font=f_badge, fill=(255, 245, 185))

        # 3. LOWER-THIRD HOOK
        # Line 1: MASSIVE 3D GOLD GRADIENT
        # Line 2: MASSIVE PURE WHITE WITH DEEP BLACK STROKE
        raw_hook = getattr(script, "thumbnail_hook", "") or getattr(script, "title", "BREAK THE CHAINS")
        line1, line2 = split_hook(raw_hook)

        hook_y_center = int(h * 0.64) if is_vertical else int(h * 0.38)

        # Line 1 size (Arial Black / Impact)
        f_sz1 = 155 if len(line1) <= 6 else max(80, int(860 / (len(line1) * 0.58)))
        if not is_vertical: f_sz1 = int(f_sz1 * 0.60)
        f_line1 = get_black_font(f_sz1)
        render_3d_gold_text(im, line1, f_line1, w // 2, hook_y_center, stroke_w=16 if is_vertical else 9)

        draw = ImageDraw.Draw(im)

        # Line 2 (Pure White)
        if line2:
            f_sz2 = 115 if len(line2) <= 11 else max(62, int(860 / (len(line2) * 0.58)))
            if not is_vertical: f_sz2 = int(f_sz2 * 0.60)
            f_line2 = get_black_font(f_sz2)
            l2_bb = draw.textbbox((0, 0), line2, font=f_line2, stroke_width=14 if is_vertical else 8)
            l2_w, l2_h = l2_bb[2] - l2_bb[0], l2_bb[3] - l2_bb[1]
            l2_x = (w - l2_w) // 2 - l2_bb[0]
            l2_y = hook_y_center + (f_sz1 // 2) + 20 - l2_bb[1]

            # Deep 3D drop shadow
            for off in range(8, 2, -1):
                draw.text((l2_x + off, l2_y + off + 3), line2, font=f_line2, 
                          fill=(0, 0, 0, 180), stroke_width=16, stroke_fill=(0, 0, 0, 180))
            # Text + black stroke
            draw.text((l2_x, l2_y), line2, font=f_line2, fill=(255, 255, 255), 
                      stroke_width=14 if is_vertical else 8, stroke_fill=(0, 0, 0, 255))
            cur_bot_y = l2_y + l2_h + 18
        else:
            cur_bot_y = hook_y_center + (f_sz1 // 2) + 18

        # 4. SCRIPTURE REFERENCE (In Gold with Black Stroke)
        v_ref = clean_ascii(getattr(script, "verse_citation", "PROVERBS 10:22")).upper()
        f_ref_sz = 54 if is_vertical else 34
        f_ref = get_black_font(f_ref_sz)
        rb = draw.textbbox((0, 0), v_ref, font=f_ref, stroke_width=6)
        rw = rb[2] - rb[0]
        ry = min(h - (390 if is_vertical else 180), cur_bot_y + 14)

        # Shadow + text
        draw.text(((w - rw) // 2 - rb[0] + 4, ry - rb[1] + 4), v_ref, font=f_ref, fill=(0, 0, 0, 220), stroke_width=8, stroke_fill=(0, 0, 0, 220))
        draw.text(((w - rw) // 2 - rb[0], ry - rb[1]), v_ref, font=f_ref, fill=(235, 185, 55), stroke_width=5, stroke_fill=(0, 0, 0, 255))

        # 5. 3D GLOSSY METALLIC GOLD 'PRAY THIS NOW' BUTTON
        btn_w, btn_h = (440, 82) if is_vertical else (280, 52)
        bx1 = (w - btn_w) // 2
        by1 = min(h - (280 if is_vertical else 115), ry + 78)

        # Drop shadow
        draw.rounded_rectangle([bx1 + 4, by1 + 6, bx1 + btn_w + 4, by1 + btn_h + 6], radius=btn_h // 2, fill=(0, 0, 0, 200))

        # Gold gradient pill
        btn_img = Image.new("RGBA", (btn_w, btn_h), (0, 0, 0, 0))
        b_draw = ImageDraw.Draw(btn_img)
        for y_i in range(btn_h):
            r_i = y_i / max(1, btn_h - 1)
            cr = int(255 * (1 - r_i) + 215 * r_i)
            cg = int(240 * (1 - r_i) + 165 * r_i)
            cb = int(170 * (1 - r_i) + 40 * r_i)
            b_draw.line([(0, y_i), (btn_w, y_i)], fill=(cr, cg, cb, 255))

        btn_mask = Image.new("L", (btn_w, btn_h), 0)
        ImageDraw.Draw(btn_mask).rounded_rectangle([0, 0, btn_w, btn_h], radius=btn_h // 2, fill=255)
        im.paste(btn_img, (bx1, by1), mask=btn_mask)

        # Outer white/gold highlight border + Black text
        draw = ImageDraw.Draw(im)
        draw.rounded_rectangle([bx1, by1, bx1 + btn_w, by1 + btn_h], radius=btn_h // 2, outline=(255, 255, 255, 220), width=3)
        cta_txt = "PRAY THIS NOW"
        f_cta = get_black_font(42 if is_vertical else 26)
        cb = draw.textbbox((0, 0), cta_txt, font=f_cta)
        cw, ch = cb[2] - cb[0], cb[3] - cb[1]
        draw.text((bx1 + (btn_w - cw) // 2 - cb[0], by1 + (btn_h - ch) // 2 - cb[1]), cta_txt, font=f_cta, fill=(15, 20, 28, 255))

        # 6. BOTTOM FLOATING ENGAGEMENT DOCK (3 STICKERS)
        if is_vertical:
            dock_y = h - 145
            f_stk = get_bold_font(21)

            # Sticker 1: Red SUBSCRIBE Pill
            s1_x, s1_w, s1_h = 75, 230, 48
            draw.rounded_rectangle([s1_x + 2, dock_y + 4, s1_x + s1_w + 2, dock_y + s1_h + 4], radius=s1_h // 2, fill=(0, 0, 0, 180))
            draw.rounded_rectangle([s1_x, dock_y, s1_x + s1_w, dock_y + s1_h], radius=s1_h // 2, fill=(220, 38, 38))
            draw.text((s1_x + 26, dock_y + 12), "SUBSCRIBE", font=f_stk, fill=(255, 255, 255))
            # Bell icon shape
            draw.polygon([(s1_x + 185, dock_y + 16), (s1_x + 195, dock_y + 28), (s1_x + 175, dock_y + 28)], fill=(255, 255, 255))
            draw.ellipse([s1_x + 182, dock_y + 28, s1_x + 188, dock_y + 34], fill=(255, 255, 255))

            # Sticker 2: LIKE IF YOU BELIEVE
            s2_x = s1_x + s1_w + 32
            # Gold thumb shape
            draw.rounded_rectangle([s2_x, dock_y + 16, s2_x + 10, dock_y + 32], radius=3, fill=(235, 185, 55))
            draw.polygon([(s2_x + 10, dock_y + 22), (s2_x + 24, dock_y + 15), (s2_x + 24, dock_y + 32), (s2_x + 10, dock_y + 32)], fill=(235, 185, 55))
            draw.text((s2_x + 32, dock_y + 12), "LIKE IF YOU BELIEVE", font=f_stk, fill=(255, 255, 255), stroke_width=3, stroke_fill=(0, 0, 0, 220))

            # Sticker 3: COMMENT AMEN Glass Pill
            s3_w, s3_h = 215, 48
            s3_x = w - s3_w - 75
            draw.rounded_rectangle([s3_x + 2, dock_y + 4, s3_x + s3_w + 2, dock_y + s3_h + 4], radius=s3_h // 2, fill=(0, 0, 0, 180))
            draw.rounded_rectangle([s3_x, dock_y, s3_x + s3_w, dock_y + s3_h], radius=s3_h // 2, fill=(9, 14, 25, 240), outline=gold_border, width=2)
            draw.text((s3_x + 25, dock_y + 12), "COMMENT AMEN", font=f_stk, fill=(255, 240, 175))

        return im.convert("RGB")

    # Generate 1080x1920 Master Vertical Thumbnail
    img_9x16 = _build(1080, 1920, is_vertical=True)
    img_9x16.save(str(thumb_path), "JPEG", quality=96)
    
    out_dir = thumb_path.parent
    p_png_9x16 = out_dir / "thumbnail_9x16.png"
    img_9x16.save(str(p_png_9x16), "PNG")

    # Generate 1280x720 Landscape Cover
    img_16x9 = _build(1280, 720, is_vertical=False)
    p_png_16x9 = out_dir / "thumbnail_16x9.png"
    img_16x9.save(str(p_png_16x9), "PNG")

    # Generate 3 Hook Variant Covers
    hook_variants = [
        getattr(script, "thumbnail_hook", "BREAK THE CHAINS"),
        f"GOD'S PROMISE FOR {clean_ascii(getattr(script, 'topic', 'YOU')).upper()[:16]}",
        f"HOLD ONTO {clean_ascii(getattr(script, 'verse_citation', 'THIS VERSE')).upper()}"
    ]
    for v_i, v_text in enumerate(hook_variants, start=1):
        orig_hk = getattr(script, "thumbnail_hook", "")
        script.thumbnail_hook = v_text
        var_im = _build(1080, 1920, is_vertical=True)
        var_im.save(str(out_dir / f"thumbnail_9x16_variant_{v_i}.png"), "PNG")
        script.thumbnail_hook = orig_hk

    return {"jpg": thumb_path, "9x16": p_png_9x16, "16x9": p_png_16x9}
