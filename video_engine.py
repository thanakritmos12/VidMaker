import os
import glob
import re
import subprocess
import time
import math
import numpy as np
import imageio_ffmpeg
from PIL import Image, ImageOps, ImageFilter, ImageEnhance, ImageDraw

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WIDTH = 1920
HEIGHT = 1080
FPS = 30

TRANSITION_CATALOG = [
    {
        "id": "crossfade",
        "name": "Crossfade (ละลายภาพนุ่มนวล)",
        "icon": "sparkles",
        "desc": "ค่อยๆ จางซ้อนภาพเก่าเข้าสู่ภาพใหม่อย่างนุ่มนวล",
    },
    {
        "id": "ken_burns",
        "name": "Ken Burns (ซูมช้าๆ + ละลายภาพ)",
        "icon": "zoom-in",
        "desc": "เคลื่อนไหวซูมเข้าภาพอย่างมีมิติพร้อมละลายภาพสไตล์สารคดี",
    },
    {
        "id": "slide_left",
        "name": "Slide Left (เลื่อนภาพไปทางซ้าย)",
        "icon": "arrow-left",
        "desc": "ภาพใหม่เลื่อนเข้ามาจากทางขวา ดันภาพเก่าออกทางซ้าย",
    },
    {
        "id": "slide_right",
        "name": "Slide Right (เลื่อนภาพไปทางขวา)",
        "icon": "arrow-right",
        "desc": "ภาพใหม่เลื่อนเข้ามาจากทางซ้าย ดันภาพเก่าออกทางขวา",
    },
    {
        "id": "slide_up",
        "name": "Slide Up (เลื่อนภาพขึ้นด้านบน)",
        "icon": "arrow-up",
        "desc": "ภาพใหม่เลื่อนขึ้นมาจากด้านล่าง",
    },
    {
        "id": "wipe_left",
        "name": "Linear Wipe (ปาดเปิดภาพแนวนอน)",
        "icon": "columns",
        "desc": "ปาดม่านเปิดภาพใหม่จากซ้ายไปขวา",
    },
    {
        "id": "circle_open",
        "name": "Circle Iris (ขยายวงกลมเปิดภาพ)",
        "icon": "circle",
        "desc": "เปิดภาพใหม่เป็นวงกลมขยายออกจากจุดกึ่งกลางจอ",
    },
    {
        "id": "zoom_in",
        "name": "Dynamic Zoom In (ซูมพุ่งเข้าภาพใหม่)",
        "icon": "maximize-2",
        "desc": "ซูมขยายภาพเก่าพร้อมดึงภาพใหม่เข้ามา",
    },
    {
        "id": "zoom_out",
        "name": "Dynamic Zoom Out (ถอยซูมเผยภาพกว้าง)",
        "icon": "minimize-2",
        "desc": "ย่อถอยออกจากภาพเดิมเข้าสู่ภาพมุมกว้างของภาพถัดไป",
    },
    {
        "id": "fade_black",
        "name": "Dip to Black (เฟดมืดคั่นจังหวะ)",
        "icon": "moon",
        "desc": "เฟดลงสีดำสั้นๆ ก่อนขึ้นภาพใหม่ เหมาะสำหรับคั่นฉาก",
    },
    {
        "id": "flash_white",
        "name": "Camera Flash (แฟลชสว่างชัตเตอร์)",
        "icon": "zap",
        "desc": "สว่างวาบเหมือนแสงแฟลชกล้องถ่ายรูป",
    },
    {
        "id": "cut",
        "name": "Hard Cut (ตัดสลับภาพทันที)",
        "icon": "scissors",
        "desc": "ตัดเปลี่ยนภาพทันทีแบบกระชับ",
    },
]


def smoothstep(t: float) -> float:
    t = max(0.0, min(1.0, float(t)))
    return t * t * (3.0 - 2.0 * t)


def get_audio_duration(audio_path: Optional[str] = None) -> float:
    if not audio_path or not os.path.exists(audio_path):
        return 60.0
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    res = subprocess.run(
        [ffmpeg_exe, "-i", audio_path],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", res.stderr)
    if not match:
        return 60.0
    h, m, s = int(match.group(1)), int(match.group(2)), float(match.group(3))
    return h * 3600 + m * 60 + s


def analyze_single_image(img_path):
    """Extract computer-vision metrics for AI Transition Director."""
    try:
        with Image.open(img_path) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            w, h = im.size
            aspect = round(w / max(1, h), 2)
            orientation = "landscape" if aspect > 1.15 else ("portrait" if aspect < 0.88 else "square")
            thumb = im.resize((64, 64), Image.Resampling.BILINEAR)
            arr = np.asarray(thumb, dtype=np.float32)
            brightness = float(np.mean(arr))
            contrast = float(np.std(arr))
            warmth = float(np.mean(arr[:, :, 0] - arr[:, :, 2]))
            hist_r, _ = np.histogram(arr[:, :, 0], bins=8, range=(0, 256), density=True)
            hist_g, _ = np.histogram(arr[:, :, 1], bins=8, range=(0, 256), density=True)
            hist_b, _ = np.histogram(arr[:, :, 2], bins=8, range=(0, 256), density=True)
            sig = np.concatenate([hist_r, hist_g, hist_b])
            return {
                "width": w,
                "height": h,
                "aspect": aspect,
                "orientation": orientation,
                "brightness": round(brightness, 1),
                "contrast": round(contrast, 1),
                "warmth": round(warmth, 1),
                "sig": sig,
            }
    except Exception:
        return {
            "width": 1080,
            "height": 1080,
            "aspect": 1.0,
            "orientation": "square",
            "brightness": 128.0,
            "contrast": 50.0,
            "warmth": 10.0,
            "sig": np.zeros(24, dtype=np.float32),
        }


def ai_recommend_transitions(images_list, total_duration=60.0, mode="smart_auto"):
    """
    Analyze all active images to recommend the ideal transition per image.
    """
    n = len(images_list)
    if n == 0:
        return []

    analyses = [analyze_single_image(item["abs_path"]) for item in images_list]
    recommendations = []

    for i in range(n):
        item = images_list[i]
        curr_meta = analyses[i]
        next_meta = analyses[i + 1] if i + 1 < n else curr_meta

        hist_diff = float(np.sum(np.abs(curr_meta["sig"] - next_meta["sig"])))
        orientation_changed = curr_meta["orientation"] != next_meta["orientation"]

        if i == n - 1:
            recommendations.append({
                "index": i,
                "id": item["id"],
                "transition": "crossfade",
                "fade_duration": 0.6,
                "reason": "ภาพสุดท้ายของคลิป — เฟดจบอย่างนุ่มนวล",
                "metrics": {
                    "orientation": curr_meta["orientation"],
                    "brightness": curr_meta["brightness"],
                    "aspect": curr_meta["aspect"],
                },
            })
            continue

        if mode == "dignified":
            if i % 3 == 0:
                t_choice = "ken_burns"
                reason = "โหมดนุ่มนวลสุภาพ — ใช้ Ken Burns ซูมภาพช้าๆ อย่างมีมิติ"
            else:
                t_choice = "crossfade"
                reason = "โหมดนุ่มนวลสุภาพ — ใช้ Crossfade ละลายภาพต่อเนื่อง"
            fade_dur = 0.7

        elif mode == "upbeat_march":
            cycle = ["slide_left", "zoom_in", "wipe_left", "flash_white", "slide_up", "circle_open"]
            t_choice = cycle[i % len(cycle)]
            reason = f"โหมดคึกคัก — ใช้ {t_choice} ให้ภาพเคลื่อนไหวกระชับ"
            fade_dur = 0.5

        elif mode == "documentary":
            if orientation_changed:
                t_choice = "zoom_out" if next_meta["orientation"] == "landscape" else "ken_burns"
                reason = "สัดส่วนภาพเปลี่ยนระหว่างแนวตั้งและแนวนอน — ใช้การซูมปรับสายตาผู้ชม"
            else:
                t_choice = "ken_burns" if i % 2 == 0 else "crossfade"
                reason = "โหมดสารคดี — เล่าเรื่องด้วย Ken Burns ซูมภาพช้าๆ สลับกับ Crossfade"
            fade_dur = 0.65

        elif mode == "variety":
            all_ids = [t["id"] for t in TRANSITION_CATALOG if t["id"] != "cut"]
            t_choice = all_ids[i % len(all_ids)]
            reason = f"โหมดวาไรตี้ — สลับเอฟเฟกต์ {t_choice} ให้หลากหลายไม่ซ้ำกัน"
            fade_dur = 0.6

        else:
            # Default: "smart_auto" (Computer Vision analysis)
            if hist_diff > 0.72:
                t_choice = "fade_black" if i % 2 == 0 else "circle_open"
                reason = "AI พบว่าโทนสีและฉากของภาพเปลี่ยนไปชัดเจน — ใช้เอฟเฟกต์เปิดฉากใหม่"
                fade_dur = 0.65
            elif hist_diff < 0.34:
                t_choice = "slide_left" if i % 2 == 0 else "wipe_left"
                reason = "AI พบว่าภาพคู่นี้มีโทนสีใกล้เคียงกัน — แนะนำการสไลด์ภาพเพื่อให้เห็นการเปลี่ยนรูปชัดเจน"
                fade_dur = 0.55
            elif orientation_changed:
                t_choice = "zoom_out" if next_meta["orientation"] == "landscape" else "zoom_in"
                reason = "สัดส่วนภาพเปลี่ยน (แนวตั้ง ↔ แนวนอน) — AI แนะนำการซูมเพื่อรับกับมุมภาพใหม่"
                fade_dur = 0.6
            elif abs(curr_meta["brightness"] - next_meta["brightness"]) > 45:
                t_choice = "crossfade" if next_meta["brightness"] < curr_meta["brightness"] else "flash_white"
                reason = "ความสว่างของภาพเปลี่ยนชัดเจน — AI ปรับเอฟเฟกต์แสงให้กลมกลืน"
                fade_dur = 0.6
            else:
                opts = ["crossfade", "ken_burns", "slide_left", "circle_open", "slide_right"]
                t_choice = opts[i % len(opts)]
                reason = "AI วิเคราะห์องค์ประกอบภาพและเลือกเอฟเฟกต์ที่สมดุลต่อเนื่อง"
                fade_dur = 0.6

        recommendations.append({
            "index": i,
            "id": item["id"],
            "transition": t_choice,
            "fade_duration": fade_dur,
            "reason": reason,
            "metrics": {
                "orientation": curr_meta["orientation"],
                "brightness": curr_meta["brightness"],
                "aspect": curr_meta["aspect"],
                "hist_diff": round(hist_diff, 2),
            },
        })

    return recommendations


def prepare_frame(img_path, width=WIDTH, height=HEIGHT):
    """Compose image into a 1920x1080 frame with a blurred background backdrop."""
    with Image.open(img_path) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        iw, ih = im.size

        bg_scale = max(width / iw, height / ih)
        bg_w = max(width, int(round(iw * bg_scale)))
        bg_h = max(height, int(round(ih * bg_scale)))
        bg = im.resize((bg_w, bg_h), Image.Resampling.BILINEAR)
        left = (bg_w - width) // 2
        top = (bg_h - height) // 2
        bg = bg.crop((left, top, left + width, top + height))
        bg = bg.filter(ImageFilter.GaussianBlur(radius=32))
        bg = ImageEnhance.Brightness(bg).enhance(0.45)

        fg_scale = min(width / iw, height / ih)
        fg_w = int(round(iw * fg_scale))
        fg_h = int(round(ih * fg_scale))
        fg = im.resize((fg_w, fg_h), Image.Resampling.LANCZOS)

        x = (width - fg_w) // 2
        y = (height - fg_h) // 2
        bg.paste(fg, (x, y))
        return bg


def zoom_image(img: Image.Image, scale: float) -> Image.Image:
    if abs(scale - 1.0) < 1e-3:
        return img
    w, h = img.size
    crop_w = int(round(w / scale))
    crop_h = int(round(h / scale))
    left = (w - crop_w) // 2
    top = (h - crop_h) // 2
    cropped = img.crop((left, top, left + crop_w, top + crop_h))
    return cropped.resize((w, h), Image.Resampling.BILINEAR)


_CIRCLE_GRID = None


def _get_circle_grid(width=WIDTH, height=HEIGHT):
    global _CIRCLE_GRID
    if _CIRCLE_GRID is None or _CIRCLE_GRID.shape != (height, width):
        yy, xx = np.ogrid[:height, :width]
        cx, cy = width / 2.0, height / 2.0
        max_r = math.hypot(cx, cy)
        _CIRCLE_GRID = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / max_r
    return _CIRCLE_GRID


def render_transition_frame(
    img_a: Image.Image,
    img_b: Image.Image,
    progress: float,
    transition_type: str = "crossfade",
    black_img: Image.Image = None,
    white_img: Image.Image = None,
) -> Image.Image:
    p = smoothstep(progress)
    w, h = img_a.size

    if transition_type == "cut":
        return img_b if progress >= 0.5 else img_a
    if transition_type == "crossfade":
        return Image.blend(img_a, img_b, p)
    if transition_type == "ken_burns":
        zoomed_a = zoom_image(img_a, 1.0 + 0.08 * p)
        zoomed_b = zoom_image(img_b, 1.06 - 0.06 * p)
        return Image.blend(zoomed_a, zoomed_b, p)
    if transition_type == "slide_left":
        offset = int(round(w * p))
        canvas = Image.new("RGB", (w, h))
        canvas.paste(img_a, (-offset, 0))
        canvas.paste(img_b, (w - offset, 0))
        return canvas
    if transition_type == "slide_right":
        offset = int(round(w * p))
        canvas = Image.new("RGB", (w, h))
        canvas.paste(img_a, (offset, 0))
        canvas.paste(img_b, (offset - w, 0))
        return canvas
    if transition_type == "slide_up":
        offset = int(round(h * p))
        canvas = Image.new("RGB", (w, h))
        canvas.paste(img_a, (0, -offset))
        canvas.paste(img_b, (0, h - offset))
        return canvas
    if transition_type == "wipe_left":
        split_x = int(round(w * p))
        if split_x <= 0:
            return img_a
        if split_x >= w:
            return img_b
        canvas = img_a.copy()
        region = img_b.crop((0, 0, split_x, h))
        canvas.paste(region, (0, 0))
        return canvas
    if transition_type == "circle_open":
        grid = _get_circle_grid(w, h)
        mask_arr = np.clip((p * 1.04 - grid) / 0.04, 0.0, 1.0)
        mask = Image.fromarray((mask_arr * 255).astype(np.uint8), mode="L")
        return Image.composite(img_b, img_a, mask)
    if transition_type == "zoom_in":
        zoomed_a = zoom_image(img_a, 1.0 + 0.25 * p)
        return Image.blend(zoomed_a, img_b, p)
    if transition_type == "zoom_out":
        zoomed_b = zoom_image(img_b, 1.0 + 0.25 * (1.0 - p))
        return Image.blend(img_a, zoomed_b, p)
    if transition_type == "fade_black":
        if black_img is None:
            black_img = Image.new("RGB", (w, h), (0, 0, 0))
        if p < 0.5:
            return Image.blend(img_a, black_img, p * 2.0)
        else:
            return Image.blend(black_img, img_b, (p - 0.5) * 2.0)
    if transition_type == "flash_white":
        if white_img is None:
            white_img = Image.new("RGB", (w, h), (255, 255, 255))
        if p < 0.5:
            return Image.blend(img_a, white_img, p * 2.0)
        else:
            return Image.blend(white_img, img_b, (p - 0.5) * 2.0)

    return Image.blend(img_a, img_b, p)


def make_card_overlay(width=WIDTH, height=HEIGHT):
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    box = (110, 742, 1810, 1038)
    shadow_box = (box[0] + 6, box[1] + 8, box[2] + 6, box[3] + 8)
    draw.rounded_rectangle(shadow_box, radius=26, fill=(0, 0, 0, 110))
    draw.rounded_rectangle(
        box,
        radius=26,
        fill=(14, 25, 45, 210),
        outline=(255, 200, 70, 230),
        width=3,
    )
    return overlay


def apply_card(img_rgb, card_rgba, alpha=1.0):
    if alpha <= 0.0:
        return img_rgb
    base_with_card = Image.alpha_composite(img_rgb.convert("RGBA"), card_rgba).convert("RGB")
    if alpha >= 0.999:
        return base_with_card
    return Image.blend(img_rgb, base_with_card, alpha)


def format_ass_time(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def write_ass_file(ass_path: str, config: dict):
    """Generate an ASS subtitle file from user's custom subtitle/text items."""
    subtitles = config.get("subtitles", [])

    lines = [
        "[Script Info]",
        "Title: VidMaker Subtitles",
        "ScriptType: v4.00+",
        f"PlayResX: {WIDTH}",
        f"PlayResY: {HEIGHT}",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Subtitle,Leelawadee UI,60,&H00FFFFFF,&H0000FFFF,&H00141414,&H80000000,-1,0,0,0,100,100,0,0,1,4.5,2.5,2,60,60,55,1",
        "Style: Banner,Leelawadee UI,50,&H00FFFFFF,&H0000FFFF,&H00101010,&H80000000,-1,0,0,0,100,100,0,0,1,3.5,2.0,5,80,80,40,1",
        "Style: Center,Leelawadee UI,68,&H0046C8FF,&H0000FFFF,&H00101010,&H80000000,-1,0,0,0,100,100,0,0,1,5.0,3.0,5,80,80,40,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    for sub in subtitles:
        raw_text = (sub.get("text") or "").strip()
        if not raw_text:
            continue
        st = format_ass_time(float(sub.get("start", 0.0)))
        et = format_ass_time(float(sub.get("end", 3.0)))
        style_mode = sub.get("style", "subtitle")
        text_lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
        joined_text = "\\N".join(text_lines)

        if style_mode == "banner":
            lines.append(
                f"Dialogue: 1,{st},{et},Banner,,0,0,0,,{{\\fad(350,350)\\pos(960,885)}}{joined_text}"
            )
        elif style_mode == "center":
            lines.append(
                f"Dialogue: 1,{st},{et},Center,,0,0,0,,{{\\fad(350,350)\\pos(960,540)}}{joined_text}"
            )
        else:
            lines.append(
                f"Dialogue: 0,{st},{et},Subtitle,,0,0,0,,{{\\fad(180,180)}}{joined_text}"
            )

    with open(ass_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def render_project_video(config: dict, progress_cb=None):
    """Render Full HD 1080p MP4 video from user's selected photos, audio, and custom subtitles."""
    t0 = time.time()
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    audio_path = config.get("audio_path")
    has_audio = bool(audio_path and os.path.exists(audio_path))
    output_filename = config.get("output_filename", "vidmaker_output.mp4")
    output_path = os.path.join(BASE_DIR, output_filename)

    active_images = [img for img in config.get("images", []) if img.get("enabled", True)]
    num_images = len(active_images)
    if num_images == 0:
        raise RuntimeError("กรุณาเลือกรูปภาพอย่างน้อย 1 รูป")

    duration = float(config.get("duration") or (get_audio_duration(audio_path) if has_audio else num_images * 3.0))
    total_frames = max(30, int(round(duration * FPS)))
    default_fade_sec = float(config.get("fade_duration", 0.6))

    subtitles = config.get("subtitles", [])
    banner_intervals = [
        (float(s.get("start", 0)), float(s.get("end", 0)))
        for s in subtitles
        if s.get("style") == "banner" and (s.get("text") or "").strip()
    ]

    ass_filename = "custom_subtitles.ass"
    ass_path = os.path.join(BASE_DIR, ass_filename)
    write_ass_file(ass_path, config)

    def get_card_alpha(sec: float) -> float:
        for st, et in banner_intervals:
            if st <= sec <= et:
                fade = min(0.4, (et - st) * 0.25)
                if fade > 0 and sec < st + fade:
                    return smoothstep((sec - st) / fade)
                if fade > 0 and sec > et - fade:
                    return smoothstep((et - sec) / fade)
                return 1.0
        return 0.0

    cmd = [
        ffmpeg_exe,
        "-y",
        "-loglevel", "error",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-pix_fmt", "rgb24",
        "-s", f"{WIDTH}x{HEIGHT}",
        "-r", str(FPS),
        "-i", "-",
    ]
    if has_audio:
        cmd.extend(["-i", audio_path])

    cmd.extend([
        "-vf", f"ass={ass_filename}",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
    ])
    if has_audio:
        cmd.extend(["-c:a", "aac", "-b:a", "192k", "-shortest"])
    cmd.extend(["-movflags", "+faststart", output_path])

    proc = subprocess.Popen(cmd, cwd=BASE_DIR, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    boundaries = [int(round(i * total_frames / num_images)) for i in range(num_images + 1)]

    black_img = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
    white_img = Image.new("RGB", (WIDTH, HEIGHT), (255, 255, 255))
    card_rgba = make_card_overlay(WIDTH, HEIGHT)
    intro_fade_frames = int(round(0.4 * FPS))
    outro_fade_frames = int(round(0.6 * FPS))

    curr_img = prepare_frame(active_images[0]["abs_path"])
    next_img = prepare_frame(active_images[1]["abs_path"]) if num_images > 1 else curr_img

    for i in range(num_images):
        start_f = boundaries[i]
        end_f = boundaries[i + 1]
        trans_type = active_images[i].get("transition", "crossfade")
        fade_sec = float(active_images[i].get("fade_duration", default_fade_sec))
        fade_frames = max(2, int(round(fade_sec * FPS)))

        curr_bytes = curr_img.tobytes()
        curr_card_bytes = None
        trans_start = max(start_f, end_f - fade_frames) if i < num_images - 1 else end_f

        for f in range(start_f, end_f):
            sec = f / FPS
            c_alpha = get_card_alpha(sec)
            is_trans = (f >= trans_start and i < num_images - 1)
            is_intro_black = (f < intro_fade_frames)
            is_outro_black = (f >= total_frames - outro_fade_frames)

            if not is_trans and not is_intro_black and not is_outro_black:
                if c_alpha <= 0.0:
                    proc.stdin.write(curr_bytes)
                    continue
                elif c_alpha >= 0.999:
                    if curr_card_bytes is None:
                        curr_card_bytes = apply_card(curr_img, card_rgba, 1.0).tobytes()
                    proc.stdin.write(curr_card_bytes)
                    continue

            if is_trans:
                t = (f - trans_start + 1) / max(1, (end_f - trans_start + 1))
                frame = render_transition_frame(
                    curr_img,
                    next_img,
                    t,
                    transition_type=trans_type,
                    black_img=black_img,
                    white_img=white_img,
                )
            else:
                frame = curr_img

            if c_alpha > 0.0:
                frame = apply_card(frame, card_rgba, c_alpha)

            if is_intro_black:
                alpha = smoothstep((f + 1) / intro_fade_frames)
                frame = Image.blend(black_img, frame, alpha)
            elif is_outro_black:
                rem = total_frames - 1 - f
                alpha = smoothstep(max(0.0, rem / outro_fade_frames))
                frame = Image.blend(black_img, frame, alpha)

            proc.stdin.write(frame.tobytes())

        if progress_cb:
            pct = int(round(((i + 1) / num_images) * 100))
            progress_cb({
                "status": "rendering",
                "current_image": i + 1,
                "total_images": num_images,
                "percent": pct,
                "elapsed": round(time.time() - t0, 1),
                "message": f"กำลังเรนเดอร์ภาพที่ {i + 1}/{num_images} ({pct}%) — เอฟเฟกต์ {trans_type}",
            })

        curr_img = next_img
        if i + 2 < num_images:
            next_img = prepare_frame(active_images[i + 2]["abs_path"])

    proc.stdin.close()
    stderr_out = proc.stderr.read().decode("utf-8", errors="replace")
    ret = proc.wait()
    if ret != 0:
        raise RuntimeError(f"FFmpeg exited with code {ret}:\n{stderr_out}")

    elapsed = round(time.time() - t0, 1)
    size_mb = round(os.path.getsize(output_path) / (1024 * 1024), 2)
    result = {
        "status": "completed",
        "current_image": num_images,
        "total_images": num_images,
        "percent": 100,
        "elapsed": elapsed,
        "output_path": output_path,
        "output_url": f"/output/{output_filename}?t={int(time.time())}",
        "size_mb": size_mb,
        "message": f"เรนเดอร์สำเร็จใน {elapsed} วินาที! ({size_mb} MB)",
    }
    if progress_cb:
        progress_cb(result)
    return result
