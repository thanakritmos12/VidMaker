import os
import re
import time
import uuid
import threading
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from PIL import Image, ImageOps

from video_engine import (
    BASE_DIR,
    DEFAULT_AUDIO,
    TRANSITION_CATALOG,
    DEFAULT_SUBTITLES,
    discover_workspace_images,
    get_audio_duration,
    ai_recommend_transitions,
    render_project_video,
)

app = FastAPI(title="อสม. Smart Video Studio — Easy Friendly Edition")

STATIC_DIR = os.path.join(BASE_DIR, "static")
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")

CURRENT_AUDIO_PATH = DEFAULT_AUDIO

RENDER_STATE: Dict[str, Any] = {
    "status": "idle",
    "current_image": 0,
    "total_images": 0,
    "percent": 0,
    "elapsed": 0.0,
    "message": "พร้อมสร้างวิดีโอ Full HD (1920x1080)",
    "output_url": "/output/วิดีโอ_เพลงมาร์ช_อสม.mp4"
    if os.path.exists(os.path.join(BASE_DIR, "วิดีโอ_เพลงมาร์ช_อสม.mp4"))
    else None,
    "size_mb": round(os.path.getsize(os.path.join(BASE_DIR, "วิดีโอ_เพลงมาร์ช_อสม.mp4")) / (1024 * 1024), 2)
    if os.path.exists(os.path.join(BASE_DIR, "วิดีโอ_เพลงมาร์ช_อสม.mp4"))
    else 0.0,
}

AI_COPY_TEMPLATES = [
    {
        "id": "official_screening",
        "title": "รูปแบบมาตรฐานราชการ / คัดกรองสุขภาพชุมชน (ค่าเริ่มต้น)",
        "intro": {
            "line1": "กิจกรรมคัดกรองสุขภาพประชาชนอายุ 15 ปีขึ้นไปในชุมชน",
            "line2": "หมู่ที่ 5-9 ตำบลปกาสัย",
            "line3": "โดย ทีม อสม. (รพ.สต.บ้านคลองเสียด)",
        },
        "outro": {
            "line1": "ขอขอบคุณทีม อสม. ทุกท่าน ที่ทุ่มเทแรงกายแรงใจด้วยจิตอาสา",
            "line2": "ร่วมดูแลและส่งเสริมสุขภาพที่ดีให้แก่พี่น้องประชาชนในชุมชนอย่างแข็งขัน",
            "line3": "ด้วยความขอบคุณยิ่ง — รพ.สต.บ้านคลองเสียด ต.ปกาสัย",
        },
    },
    {
        "id": "warm_gratitude",
        "title": "รูปแบบอบอุ่นและเชิดชูเกียรติจิตอาสา อสม.",
        "intro": {
            "line1": "รวมพลัง อสม. ลงพื้นที่คัดกรองสุขภาพเชิงรุกในชุมชน",
            "line2": "ดูแลพี่น้องประชาชนอายุ 15 ปีขึ้นไป หมู่ที่ 5-9 ตำบลปกาสัย",
            "line3": "ทีมงานจิตอาสา อสม. รพ.สต.บ้านคลองเสียด",
        },
        "outro": {
            "line1": "ขอขอบพระคุณพี่น้อง อสม. ทุกท่าน ผู้เสียสละเวลาและทุ่มเทด้วยหัวใจจิตอาสา",
            "line2": "เพราะรอยยิ้มและสุขภาพที่ดีของคนในชุมชน คือความภูมิใจของพวกเรา",
            "line3": "ครอบครัว อสม. รพ.สต.บ้านคลองเสียด ตำบลปกาสัย",
        },
    },
    {
        "id": "active_health",
        "title": "รูปแบบกระชับ ทันสมัย สร้างเสริมสุขภาพดีถ้วนหน้า",
        "intro": {
            "line1": "โครงการคัดกรองสุขภาพประชาชนเชิงรุก (อายุ 15 ปีขึ้นไป)",
            "line2": "พื้นที่หมู่ที่ 5 – 9 ตำบลปกาสัย",
            "line3": "ดำเนินการโดย ทีม อสม. รพ.สต.บ้านคลองเสียด",
        },
        "outro": {
            "line1": "ขอบคุณพลังทีม อสม. ทุกท่าน ที่มุ่งมั่นเคียงข้างสุขภาพคนไทยในชุมชน",
            "line2": "ก้าวไปด้วยกัน เพื่อชุมชนปลอดโรค ปลอดภัย สุขภาพดีทั่วกัน",
            "line3": "รพ.สต.บ้านคลองเสียด ตำบลปกาสัย",
        },
    },
]


def resolve_image_abs_path(item: Dict[str, Any]) -> str:
    rel_path = item.get("rel_path", "")
    if rel_path:
        candidate = os.path.join(BASE_DIR, rel_path.replace("/", os.sep))
        if os.path.exists(candidate):
            return candidate
    url = item.get("url", "")
    if url.startswith("/uploads/"):
        fname = os.path.basename(url.split("?")[0])
        candidate = os.path.join(UPLOADS_DIR, fname)
        if os.path.exists(candidate):
            return candidate
    if url.startswith("/media/"):
        parts = url.split("?")[0].split("/")
        if len(parts) >= 4:
            candidate = os.path.join(BASE_DIR, parts[2], parts[3])
            if os.path.exists(candidate):
                return candidate
    raise FileNotFoundError(f"ไม่พบไฟล์รูปภาพ: {item}")


class AIRecommendRequest(BaseModel):
    mode: str = "smart_auto"
    images: List[Dict[str, Any]]


class RenderRequest(BaseModel):
    images: List[Dict[str, Any]]
    fade_duration: float = 0.6
    intro: Dict[str, Any]
    outro: Dict[str, Any]
    subtitles: List[Dict[str, Any]]
    subtitles_enabled: bool = True
    output_filename: str = "วิดีโอ_เพลงมาร์ช_อสม.mp4"


@app.get("/", response_class=HTMLResponse)
def index():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if not os.path.exists(index_path):
        raise HTTPException(status_code=404, detail="UI file not found")
    with open(index_path, "r", encoding="utf-8") as f:
        return f.read()


@app.get("/api/project")
def get_project():
    duration = get_audio_duration(CURRENT_AUDIO_PATH)

    return {
        "title": "ระบบสร้างวิดีโอจากรูปภาพ + AI แนะนำ Transition",
        "audio_url": f"/audio?t={int(time.time())}",
        "audio_name": os.path.basename(CURRENT_AUDIO_PATH),
        "duration": round(duration, 2),
        "fps": 30,
        "resolution": "1920x1080 (Full HD 16:9)",
        "transitions_catalog": TRANSITION_CATALOG,
        "copy_templates": AI_COPY_TEMPLATES,
        "images": [],
        "intro": {
            "enabled": True,
            "start": 0.40,
            "end": 5.80,
            "line1": "กิจกรรมคัดกรองสุขภาพประชาชนอายุ 15 ปีขึ้นไปในชุมชน",
            "line2": "หมู่ที่ 5-9 ตำบลปกาสัย",
            "line3": "โดย ทีม อสม. (รพ.สต.บ้านคลองเสียด)",
        },
        "outro": {
            "enabled": True,
            "start": max(0.0, round(duration - 10.8, 1)),
            "end": round(duration - 0.4, 1),
            "line1": "ขอขอบคุณทีม อสม. ทุกท่าน ที่ทุ่มเทแรงกายแรงใจด้วยจิตอาสา",
            "line2": "ร่วมดูแลและส่งเสริมสุขภาพที่ดีให้แก่พี่น้องประชาชนในชุมชนอย่างแข็งขัน",
            "line3": "ด้วยความขอบคุณยิ่ง — รพ.สต.บ้านคลองเสียด ต.ปกาสัย",
        },
        "subtitles": DEFAULT_SUBTITLES,
        "render_state": RENDER_STATE,
    }


@app.post("/api/upload-images")
async def upload_images(files: List[UploadFile] = File(...)):
    uploaded_items = []
    for f in files:
        if not f.filename:
            continue
        uid = uuid.uuid4().hex[:8]
        safe_orig = re.sub(r"[^a-zA-Z0-9ก-๙._-]", "_", os.path.splitext(f.filename)[0])[:40]
        out_name = f"img_{int(time.time())}_{uid}_{safe_orig}.jpg"
        out_path = os.path.join(UPLOADS_DIR, out_name)

        raw_bytes = await f.read()
        try:
            from io import BytesIO
            with Image.open(BytesIO(raw_bytes)) as im:
                im = ImageOps.exif_transpose(im).convert("RGB")
                im.save(out_path, "JPEG", quality=94)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"ไฟล์ {f.filename} ไม่ใช่รูปภาพที่รองรับ: {e}")

        uploaded_items.append({
            "id": f"up_{uid}",
            "folder": "อัปโหลด",
            "filename": f.filename,
            "rel_path": f"uploads/{out_name}",
            "url": f"/uploads/{out_name}",
            "transition": "crossfade",
            "fade_duration": 0.6,
            "enabled": True,
        })

    return {"ok": True, "uploaded": uploaded_items}


@app.post("/api/upload-audio")
async def upload_audio(file: UploadFile = File(...)):
    global CURRENT_AUDIO_PATH
    if not file.filename:
        raise HTTPException(status_code=400, detail="ไม่พบไฟล์เสียง")
    ext = os.path.splitext(file.filename)[1].lower() or ".mp3"
    out_name = f"audio_{int(time.time())}{ext}"
    out_path = os.path.join(UPLOADS_DIR, out_name)
    data = await file.read()
    with open(out_path, "wb") as fp:
        fp.write(data)
    CURRENT_AUDIO_PATH = out_path
    dur = get_audio_duration(CURRENT_AUDIO_PATH)
    return {
        "ok": True,
        "audio_name": file.filename,
        "audio_url": f"/audio?t={int(time.time())}",
        "duration": round(dur, 2),
    }


@app.post("/api/ai-recommend")
def api_ai_recommend(req: AIRecommendRequest):
    if not req.images:
        raise HTTPException(status_code=400, detail="กรุณาใส่รูปภาพในช่องอย่างน้อย 1 รูปก่อนให้ AI แนะนำครับ")

    target_images = []
    for item in req.images:
        if not item.get("enabled", True):
            continue
        abs_p = resolve_image_abs_path(item)
        target_images.append({
            "id": item["id"],
            "folder": item.get("folder", "1"),
            "abs_path": abs_p,
        })

    if not target_images:
        raise HTTPException(status_code=400, detail="กรุณาใส่รูปภาพในช่องอย่างน้อย 1 รูปก่อนให้ AI แนะนำครับ")

    duration = get_audio_duration(CURRENT_AUDIO_PATH)
    recs = ai_recommend_transitions(target_images, total_duration=duration, mode=req.mode)

    counts: Dict[str, int] = {}
    for r in recs:
        t = r["transition"]
        counts[t] = counts.get(t, 0) + 1

    return {
        "mode": req.mode,
        "counts": counts,
        "recommendations": recs,
    }


@app.post("/api/render")
def start_render(req: RenderRequest):
    global RENDER_STATE
    if RENDER_STATE.get("status") == "rendering":
        raise HTTPException(status_code=409, detail="กำลังสร้างวิดีโออยู่ กรุณารอสักครู่")

    resolved_images = []
    for item in req.images:
        if not item.get("enabled", True):
            continue
        abs_p = resolve_image_abs_path(item)
        resolved_images.append({
            **item,
            "abs_path": abs_p,
            "enabled": True,
        })

    active_count = len(resolved_images)
    if active_count == 0:
        raise HTTPException(status_code=400, detail="กรุณาใส่รูปภาพในช่องอย่างน้อย 1 รูปก่อนสร้างวิดีโอครับ")

    config = {
        "images": resolved_images,
        "fade_duration": req.fade_duration,
        "intro": req.intro,
        "outro": req.outro,
        "subtitles": req.subtitles if req.subtitles_enabled else [],
        "output_filename": req.output_filename,
        "audio_path": CURRENT_AUDIO_PATH,
    }

    RENDER_STATE = {
        "status": "rendering",
        "current_image": 0,
        "total_images": active_count,
        "percent": 0,
        "elapsed": 0.0,
        "message": "กำลังเริ่มสร้างเฟรมภาพและใส่เอฟเฟกต์...",
        "output_url": RENDER_STATE.get("output_url"),
        "size_mb": RENDER_STATE.get("size_mb", 0.0),
    }

    def update_progress(state_update: dict):
        global RENDER_STATE
        RENDER_STATE.update(state_update)

    def worker():
        global RENDER_STATE
        try:
            render_project_video(config, progress_cb=update_progress)
        except Exception as e:
            RENDER_STATE = {
                "status": "error",
                "current_image": 0,
                "total_images": active_count,
                "percent": 0,
                "elapsed": 0.0,
                "message": f"เกิดข้อผิดพลาด: {str(e)}",
                "output_url": None,
                "size_mb": 0.0,
            }

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    return {"ok": True, "render_state": RENDER_STATE}


@app.get("/api/render-status")
def get_render_status():
    return RENDER_STATE


@app.get("/media/{folder}/{filename}")
def serve_media(folder: str, filename: str):
    if folder not in ["1", "2", "3", "4", "5"]:
        raise HTTPException(status_code=404, detail="Invalid folder")
    safe_name = os.path.basename(filename)
    full_path = os.path.join(BASE_DIR, folder, safe_name)
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(full_path, media_type="image/jpeg")


@app.get("/audio")
def serve_audio():
    if not os.path.exists(CURRENT_AUDIO_PATH):
        raise HTTPException(status_code=404, detail="Audio not found")
    return FileResponse(CURRENT_AUDIO_PATH, media_type="audio/mpeg")


@app.get("/output/{filename}")
def serve_output(filename: str):
    safe_name = os.path.basename(filename)
    full_path = os.path.join(BASE_DIR, safe_name)
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="Output video not found")
    return FileResponse(full_path, media_type="video/mp4", filename=safe_name)


if __name__ == "__main__":
    import uvicorn
    import re
    uvicorn.run(app, host="127.0.0.1", port=8000)
