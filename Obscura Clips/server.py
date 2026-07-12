#!/usr/bin/env python3
# ============================================================
# server.py — Obscura Clips Web UI Server
# Serves the beautiful UI and streams pipeline progress
# via WebSocket in real-time.
# ============================================================

import asyncio
import os
import re
import sys
import time
import uuid
import webbrowser
import threading
import json
import logging
from pathlib import Path

import uvicorn
from fastapi import FastAPI, WebSocket, UploadFile, File, Query
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("server")

# ─── Paths ──────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "temp" / "uploads"
OUTPUT_DIR = BASE_DIR / "output"
UI_FILE    = BASE_DIR / "ui" / "index.html"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app  = FastAPI(title="Obscura Clips")
jobs: dict = {}   # job_id → {"path": str, "filename": str, "start_time": float}


# ─── Routes ─────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    return UI_FILE.read_text(encoding="utf-8")


@app.post("/upload")
async def upload_video(file: UploadFile = File(...)):
    """Accept a video upload and return a job_id."""
    job_id = str(uuid.uuid4())[:8]
    suffix = Path(file.filename).suffix or ".mp4"
    save_path = UPLOAD_DIR / f"job_{job_id}{suffix}"

    # Stream-write in 4 MB chunks to handle large files
    with open(save_path, "wb") as f:
        while True:
            chunk = await file.read(4 * 1024 * 1024)
            if not chunk:
                break
            f.write(chunk)

    jobs[job_id] = {
        "path":     str(save_path),
        "filename": file.filename,
        "start_time": time.time()
    }
    return {"job_id": job_id, "filename": file.filename}
@app.get("/api/music/tracks")
async def get_music_tracks():
    """Retrieve available local and curated background tracks."""
    from modules.bg_music import list_available_tracks
    try:
        return list_available_tracks()
    except Exception as e:
        logger.error(f"Error listing music tracks: {e}")
        return []


@app.websocket("/ws/{job_id}")
async def run_pipeline_ws(
    websocket: WebSocket,
    job_id:    str,
    model:     str = Query(default="small"),
    max_clips: int = Query(default=10),
    language:  str = Query(default=""),
    music:     str = Query(default="auto")
):
    """
    Run the pipeline as a subprocess and stream every log line
    to the browser via WebSocket as structured JSON events.
    """
    await websocket.accept()

    if job_id not in jobs:
        await websocket.send_json({"type": "error", "message": "Job not found."})
        await websocket.close()
        return

    job        = jobs[job_id]
    video_path = job["path"]
    start_time = job["start_time"]
    if music == "off":
        music = "none"

    # Create job-specific output folder and write metadata
    job_dir = OUTPUT_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "job_id": job_id,
        "filename": job["filename"],
        "created": start_time,
        "model": model,
        "max_clips": max_clips,
        "music": music
    }
    try:
        import json
        with open(job_dir / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Failed to write metadata: {e}")

    # Use the venv Python so all packages are available
    python_exe = str(BASE_DIR / "venv" / "Scripts" / "python.exe")
    if not Path(python_exe).exists():
        python_exe = sys.executable

    cmd = [
        python_exe,
        str(BASE_DIR / "local_clipping_pipeline.py"),
        "--input",     video_path,
        "--output-dir", str(job_dir),
        "--model",     model,
        "--max-clips", str(max_clips),
        "--music",     music,
    ]
    if language.strip():
        cmd += ["--language", language.strip()]

    await websocket.send_json({"type": "start", "filename": job["filename"]})

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(BASE_DIR),
            env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
        )

        jobs[job_id]["process"] = process

        # ── Stream stdout → WebSocket ────────────────────────
        while True:
            line_bytes = await process.stdout.readline()
            if not line_bytes:
                break
            text = line_bytes.decode("utf-8", errors="replace").rstrip()
            if not text.strip():
                continue

            event        = _parse_log_line(text)
            event["raw"] = text

            try:
                await websocket.send_json(event)
            except Exception:
                break

        await process.wait()
        success = process.returncode == 0

        # Only return clips created/modified AFTER this job started, scoped to job_id
        clips = _list_clips(job_id=job_id, newer_than=start_time - 5)

        await websocket.send_json({
            "type":    "done",
            "success": success,
            "clips":   clips
        })

    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass

    finally:
        try:
            await websocket.close()
        except Exception:
            pass


# ─── Helpers ────────────────────────────────────────────────

def _parse_log_line(text: str) -> dict:
    """Convert a raw pipeline log line into a structured UI event."""

    # Main stage: "═══ STAGE 2/6 ─ ASR Transcription (CPU INT8) ═══"
    m = re.search(r"STAGE\s+(\d+)/6[^─\-]*[\-─]\s*(.+?)(?:\s*[═=]+\s*$|\s*$)", text)
    if m:
        return {"type": "stage", "stage": int(m.group(1)), "label": m.group(2).strip()}

    # Clip start: "═══ CLIP 1/5 ══"
    m = re.search(r"CLIP\s+(\d+)/(\d+)", text)
    if m:
        return {"type": "clip_start", "clip_num": int(m.group(1)), "total": int(m.group(2))}

    # Sub-stage: "[4/6] Face Tracking"
    m = re.search(r"\[(\d+)/6\]\s+(.+)", text)
    if m:
        return {"type": "substage", "substage": int(m.group(1)), "label": m.group(2).strip()}

    # Clip ready: "✅ Done → output/clip_01_..."
    m = re.search(r"Done.*?(?:→|->)\s*(output[/\\].+?\.mp4)", text, re.IGNORECASE)
    if m:
        return {"type": "clip_ready", "path": m.group(1)}

    # Errors / warnings
    low = text.lower()
    if "error" in low or "failed" in low or "traceback" in low:
        return {"type": "warning"}

    return {"type": "log"}


def _list_clips(job_id: str = None, newer_than: float = 0) -> list:
    clips = []
    target_dir = OUTPUT_DIR
    if job_id:
        target_dir = OUTPUT_DIR / job_id

    if target_dir.exists():
        for f in target_dir.glob("*.mp4"):
            stat = f.stat()
            if stat.st_mtime < newer_than:
                continue
            url_path = f"/output/{job_id}/{f.name}" if job_id else f"/output/{f.name}"
            clips.append({
                "filename": f.name,
                "size_mb":  round(stat.st_size / 1024 / 1024, 1),
                "url":      url_path,
                "modified": stat.st_mtime,
            })
    return sorted(clips, key=lambda c: c["filename"])


# ─── yt-dlp Download Endpoints ─────────────────────────────

@app.post("/prepare-download")
async def prepare_download():
    """Reserve a job_id for an incoming yt-dlp download."""
    job_id = str(uuid.uuid4())[:8]
    return {"job_id": job_id}


@app.websocket("/ws-ytdl/{job_id}")
async def download_url_ws(
    websocket: WebSocket,
    job_id:    str,
    url:       str = Query(...)
):
    """
    Download a video from a URL using yt-dlp and stream progress
    to the browser. On completion, registers the job so the
    pipeline WebSocket can use it directly.
    """
    await websocket.accept()

    python_exe = str(BASE_DIR / "venv" / "Scripts" / "python.exe")
    if not Path(python_exe).exists():
        python_exe = sys.executable

    save_path = UPLOAD_DIR / f"job_{job_id}.mp4"

    cmd = [
        python_exe, "-m", "yt_dlp",
        "--format",
        "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "--output",             str(save_path),
        "--newline",            # one progress line per line — easy to parse
        "--no-playlist",
        "--no-part",            # no .part files
        url
    ]

    await websocket.send_json({"type": "ytdl_start", "url": url})

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
        )

        video_title = "downloaded_video"

        while True:
            line_bytes = await process.stdout.readline()
            if not line_bytes:
                break
            text = line_bytes.decode("utf-8", errors="replace").rstrip()
            if not text.strip():
                continue

            # Capture the video title from the destination line
            m = re.search(r"\[download\] Destination: (.+)", text)
            if m:
                video_title = Path(m.group(1)).stem

            # Parse download progress:
            # [download]  45.2% of 234.56MiB at 2.34MiB/s ETA 00:43
            m = re.search(
                r"\[download\]\s+([\d.]+)%\s+of\s+([~\d.]+\w+)\s+at\s+([\d.]+\w+/s)\s+ETA\s+(\S+)",
                text
            )
            if m:
                await websocket.send_json({
                    "type":    "ytdl_progress",
                    "percent": float(m.group(1)),
                    "size":    m.group(2),
                    "speed":   m.group(3),
                    "eta":     m.group(4),
                })
                continue

            # Forward other lines as log
            await websocket.send_json({"type": "ytdl_log", "raw": text})

        await process.wait()

        if process.returncode == 0 and save_path.exists():
            # Register job so the pipeline WS can use it directly
            jobs[job_id] = {
                "path":       str(save_path),
                "filename":   video_title + ".mp4",
                "start_time": time.time(),
            }
            await websocket.send_json({
                "type":     "ytdl_done",
                "job_id":   job_id,
                "filename": video_title + ".mp4",
                "size_mb":  round(save_path.stat().st_size / 1024 / 1024, 1),
            })
        else:
            await websocket.send_json({
                "type":    "error",
                "message": "Download failed. Check the URL or try a different quality."
            })

    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


@app.get("/uploads")
async def list_uploads():
    uploads = []
    if UPLOAD_DIR.exists():
        for f in UPLOAD_DIR.glob("job_*.mp4"):
            m = re.match(r"job_([a-f0-9]{8})\.mp4", f.name)
            if m:
                jid = m.group(1)
                stat = f.stat()
                if jid not in jobs:
                    jobs[jid] = {
                        "path": str(f),
                        "filename": f.name,
                        "start_time": stat.st_mtime
                    }
                uploads.append({
                    "job_id": jid,
                    "filename": jobs[jid]["filename"],
                    "size_mb": round(stat.st_size / 1024 / 1024, 1),
                    "created": stat.st_mtime
                })
    return {"uploads": sorted(uploads, key=lambda x: x["created"], reverse=True)}


@app.get("/clips")
async def list_clips_endpoint():
    return {"clips": _list_clips()}


@app.get("/history")
async def get_history():
    history = []
    if OUTPUT_DIR.exists():
        for d in OUTPUT_DIR.iterdir():
            if d.is_dir() and (d / "metadata.json").exists():
                try:
                    with open(d / "metadata.json", "r", encoding="utf-8") as f:
                        meta = json.load(f)
                    
                    # Double check if there are actual clips in it
                    clips = list(d.glob("*.mp4"))
                    if clips:
                        meta["clip_count"] = len(clips)
                        history.append(meta)
                except Exception as e:
                    logger.error(f"Error reading metadata for {d.name}: {e}")
    return {"history": sorted(history, key=lambda x: x.get("created", 0), reverse=True)}


@app.get("/history/{job_id}/clips")
async def get_history_clips(job_id: str):
    return {"clips": _list_clips(job_id=job_id)}


@app.get("/output/{job_id}/{filename}")
async def serve_job_output(job_id: str, filename: str):
    path = OUTPUT_DIR / job_id / filename
    if not path.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(str(path), media_type="video/mp4")


@app.get("/output/{filename}")
async def serve_output(filename: str):
    path = OUTPUT_DIR / filename
    if not path.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(str(path), media_type="video/mp4")


# ─── Entry Point ─────────────────────────────────────────────

def _open_browser():
    time.sleep(1.5)
    webbrowser.open("http://localhost:7842")


if __name__ == "__main__":
    threading.Thread(target=_open_browser, daemon=True).start()
    print("\n  *  Obscura Clips - UI server starting")
    print("  -> http://localhost:7842")
    print("  -> Press Ctrl+C to stop\n")
    uvicorn.run(app, host="127.0.0.1", port=7842, log_level="warning")
