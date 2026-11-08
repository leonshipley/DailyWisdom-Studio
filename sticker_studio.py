import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

BASE_DIR = Path(__file__).resolve().parent
STICKERS_DIR = BASE_DIR / "custom_media" / "stickers"
STICKERS_DIR.mkdir(parents=True, exist_ok=True)

def ensure_default_stickers():
    """Generates clean high-res transparent stickers & animated GIFs if empty."""
    # 1. Red Subscribe + Bell Badge
    sub_png = STICKERS_DIR / "subscribe_bell_badge.png"
    if not sub_png.exists():
        im = Image.new("RGBA", (360, 80), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle([4, 6, 356, 76], radius=38, fill=(0, 0, 0, 160))
        d.rounded_rectangle([0, 0, 350, 70], radius=35, fill=(220, 38, 38))
        d.text((45, 18), "SUBSCRIBE", fill=(255, 255, 255))
        # Bell icon
        d.polygon([(265, 20), (280, 42), (250, 42)], fill=(255, 255, 255))
        d.ellipse([260, 42, 270, 52], fill=(255, 255, 255))
        im.save(str(sub_png), "PNG")

    # 2. Golden Cross Badge
    cross_png = STICKERS_DIR / "golden_cross_badge.png"
    if not cross_png.exists():
        im = Image.new("RGBA", (140, 140), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle([0, 0, 140, 140], radius=28, fill=(9, 14, 25, 230), outline=(225, 185, 55), width=3)
        # Gold cross
        d.rounded_rectangle([58, 22, 82, 118], radius=6, fill=(235, 185, 55))
        d.rounded_rectangle([32, 45, 108, 69], radius=6, fill=(235, 185, 55))
        im.save(str(cross_png), "PNG")

    # 3. Live Animated Pulsing Subscribe Bell GIF
    live_gif = STICKERS_DIR / "live_subscribe_pulse.gif"
    if not live_gif.exists():
        frames = []
        for i in range(12):
            scale = 1.0 + 0.08 * (1.0 if i < 6 else (11 - i) / 6.0)
            fw, fh = int(320 * scale), int(70 * scale)
            f_im = Image.new("RGBA", (360, 90), (0, 0, 0, 0))
            d = ImageDraw.Draw(f_im)
            bx = (360 - fw) // 2
            by = (90 - fh) // 2
            d.rounded_rectangle([bx, by, bx + fw, by + fh], radius=fh // 2, fill=(220, 38, 38))
            d.text((bx + 40, by + int(16 * scale)), "SUBSCRIBE 🔔", fill=(255, 255, 255))
            frames.append(f_im)
        frames[0].save(
            str(live_gif),
            save_all=True,
            append_images=frames[1:],
            duration=80,
            loop=0,
            transparency=0,
            disposal=2
        )

def get_sticker_inventory() -> dict:
    """Returns a dictionary of label -> Path for all available stickers & GIFs."""
    ensure_default_stickers()
    items = {
        "None (No Sticker)": None
    }
    for f in sorted(STICKERS_DIR.iterdir()):
        if f.is_file() and f.suffix.lower() in (".png", ".webp", ".gif", ".jpg"):
            is_gif = f.suffix.lower() == ".gif"
            lbl = f"{'✨ [LIVE GIF]' if is_gif else '🖼️ [STICKER]'} {f.stem.replace('_', ' ').title()}"
            items[lbl] = f
    return items

def build_ffmpeg_sticker_filter(
    sticker_path: Path,
    video_dur: float,
    position: str = "Bottom Dock (Centered)",
    timing: str = "Throughout Entire Video"
) -> tuple:
    """Builds the FFmpeg input args and overlay filter for static or animated stickers."""
    if not sticker_path or not sticker_path.exists():
        return [], ""

    is_gif = sticker_path.suffix.lower() == ".gif"
    inputs = ["-ignore_loop", "0", "-i", str(sticker_path.absolute())] if is_gif else ["-i", str(sticker_path.absolute())]

    # Coordinate mapping for 1080x1920
    if "Bottom Right" in position:
        x_expr = "W-w-70"
        y_expr = "H-h-160"
        scale_w = 300
    elif "Top Right" in position:
        x_expr = "W-w-70"
        y_expr = "200"
        scale_w = 160
    else:  # Bottom Dock (Centered)
        x_expr = "(W-w)/2"
        y_expr = "H-h-130"
        scale_w = 380

    # Timing filter
    if "Last 6s" in timing:
        enable_expr = f":enable='gte(t,{max(0.0, video_dur - 6.0):.2f})'"
    elif "First 5s" in timing:
        enable_expr = ":enable='lte(t,5.0)'"
    else:
        enable_expr = ""

    filter_str = f"scale={scale_w}:-1[stk_scaled];[vout][stk_scaled]overlay=x={x_expr}:y={y_expr}{enable_expr}[vout_stk]"
    return inputs, filter_str
