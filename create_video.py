import os
import glob
import re
import subprocess
import time
import imageio_ffmpeg
from PIL import Image, ImageOps, ImageFilter, ImageEnhance, ImageDraw

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AUDIO_PATH = os.path.join(BASE_DIR, "AudioTranscriberAI_เพลงมาร์ช อสม.mp3")
OUTPUT_PATH = os.path.join(BASE_DIR, "วิดีโอ_เพลงมาร์ช_อสม.mp4")

WIDTH = 1920
HEIGHT = 1080
FPS = 30
FADE_SEC = 0.6  # Crossfade duration in seconds

# Intro & Outro banner timing (in seconds)
INTRO_START = 0.40
INTRO_END = 5.80
INTRO_FADE = 0.50

OUTRO_START = 188.00  # 03:08
OUTRO_END = 198.40
OUTRO_FADE = 0.60


def get_audio_duration(ffmpeg_exe, audio_path):
    res = subprocess.run(
        [ffmpeg_exe, "-i", audio_path],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", res.stderr)
    if not match:
        raise RuntimeError(f"Could not parse audio duration from:\n{res.stderr}")
    h, m, s = int(match.group(1)), int(match.group(2)), float(match.group(3))
    return h * 3600 + m * 60 + s


def prepare_frame(img_path, width=WIDTH, height=HEIGHT):
    """Compose image into a 1920x1080 frame with a blurred background backdrop."""
    with Image.open(img_path) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        iw, ih = im.size

        # 1. Create blurred background (cover fit)
        bg_scale = max(width / iw, height / ih)
        bg_w = max(width, int(round(iw * bg_scale)))
        bg_h = max(height, int(round(ih * bg_scale)))
        bg = im.resize((bg_w, bg_h), Image.Resampling.BILINEAR)
        left = (bg_w - width) // 2
        top = (bg_h - height) // 2
        bg = bg.crop((left, top, left + width, top + height))
        bg = bg.filter(ImageFilter.GaussianBlur(radius=32))
        bg = ImageEnhance.Brightness(bg).enhance(0.45)

        # 2. Scale foreground image (contain fit)
        fg_scale = min(width / iw, height / ih)
        fg_w = int(round(iw * fg_scale))
        fg_h = int(round(ih * fg_scale))
        fg = im.resize((fg_w, fg_h), Image.Resampling.LANCZOS)

        # Paste centered on background
        x = (width - fg_w) // 2
        y = (height - fg_h) // 2
        bg.paste(fg, (x, y))
        return bg


def make_card_overlay(width=WIDTH, height=HEIGHT):
    """Create an RGBA overlay with a sleek lower-third rounded banner box."""
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    box = (110, 742, 1810, 1038)
    # Shadow
    shadow_box = (box[0] + 6, box[1] + 8, box[2] + 6, box[3] + 8)
    draw.rounded_rectangle(shadow_box, radius=26, fill=(0, 0, 0, 110))
    # Main dark navy translucent panel
    draw.rounded_rectangle(
        box,
        radius=26,
        fill=(14, 25, 45, 210),
        outline=(255, 200, 70, 230),
        width=3,
    )
    # Inner subtle accent line near top & bottom of card
    draw.line([(220, box[1] + 12), (1700, box[1] + 12)], fill=(255, 215, 100, 120), width=2)
    draw.line([(220, box[3] - 12), (1700, box[3] - 12)], fill=(255, 215, 100, 120), width=2)
    return overlay


def apply_card(img_rgb, card_rgba, alpha=1.0):
    """Composite the card overlay onto an RGB image with given alpha (0..1)."""
    if alpha <= 0.0:
        return img_rgb
    base_with_card = Image.alpha_composite(img_rgb.convert("RGBA"), card_rgba).convert("RGB")
    if alpha >= 0.999:
        return base_with_card
    return Image.blend(img_rgb, base_with_card, alpha)


def smoothstep(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def get_card_alpha(sec):
    """Return card opacity (0.0 to 1.0) at timestamp `sec`."""
    if INTRO_START <= sec <= INTRO_END:
        if sec < INTRO_START + INTRO_FADE:
            return smoothstep((sec - INTRO_START) / INTRO_FADE)
        elif sec > INTRO_END - INTRO_FADE:
            return smoothstep((INTRO_END - sec) / INTRO_FADE)
        return 1.0
    if OUTRO_START <= sec <= OUTRO_END:
        if sec < OUTRO_START + OUTRO_FADE:
            return smoothstep((sec - OUTRO_START) / OUTRO_FADE)
        elif sec > OUTRO_END - OUTRO_FADE:
            return smoothstep((OUTRO_END - sec) / OUTRO_FADE)
        return 1.0
    return 0.0


def main():
    t0 = time.time()
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

    # Collect images in folder order 1..5
    image_paths = []
    for folder in ["1", "2", "3", "4", "5"]:
        folder_path = os.path.join(BASE_DIR, folder)
        imgs = sorted(glob.glob(os.path.join(folder_path, "*.jpg")))
        image_paths.extend(imgs)

    num_images = len(image_paths)
    if num_images == 0:
        raise RuntimeError("No images found in folders 1-5.")

    duration = get_audio_duration(ffmpeg_exe, AUDIO_PATH)
    total_frames = int(round(duration * FPS))
    fade_frames = int(round(FADE_SEC * FPS))

    print(f"Found {num_images} images across folders 1-5.")
    print(f"Audio duration: {duration:.2f}s ({total_frames} frames at {FPS} fps)")
    print(f"Average time per image: {duration / num_images:.2f}s (crossfade: {FADE_SEC}s)")

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
        "-i", AUDIO_PATH,
        "-vf", "ass=lyrics.ass",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        "-movflags", "+faststart",
        OUTPUT_PATH,
    ]

    proc = subprocess.Popen(cmd, cwd=BASE_DIR, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

    boundaries = [int(round(i * total_frames / num_images)) for i in range(num_images + 1)]

    black_img = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
    card_rgba = make_card_overlay(WIDTH, HEIGHT)
    intro_fade_frames = int(round(0.5 * FPS))
    outro_fade_frames = int(round(0.8 * FPS))

    curr_img = prepare_frame(image_paths[0])
    next_img = prepare_frame(image_paths[1]) if num_images > 1 else curr_img

    for i in range(num_images):
        start_f = boundaries[i]
        end_f = boundaries[i + 1]
        curr_bytes = curr_img.tobytes()
        curr_card_bytes = None

        trans_start = end_f - fade_frames if i < num_images - 1 else end_f

        for f in range(start_f, end_f):
            sec = f / FPS
            c_alpha = get_card_alpha(sec)

            # Determine base image before intro/outro fade-to-black
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

            # Compute dynamic frame
            if is_trans:
                t = (f - trans_start + 1) / (fade_frames + 1)
                frame = Image.blend(curr_img, next_img, smoothstep(t))
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

        if (i + 1) % 10 == 0 or i == num_images - 1:
            print(f"Processed {i + 1}/{num_images} images...")

        curr_img = next_img
        if i + 2 < num_images:
            next_img = prepare_frame(image_paths[i + 2])

    proc.stdin.close()
    stderr_out = proc.stderr.read().decode("utf-8", errors="replace")
    ret = proc.wait()
    if ret != 0:
        raise RuntimeError(f"FFmpeg exited with code {ret}:\n{stderr_out}")

    elapsed = time.time() - t0
    size_mb = os.path.getsize(OUTPUT_PATH) / (1024 * 1024)
    print(f"Done in {elapsed:.1f}s! Output: {OUTPUT_PATH} ({size_mb:.2f} MB)")


if __name__ == "__main__":
    main()
