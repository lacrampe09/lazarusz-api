# app/main.py
from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, Dict, Any
import os, re, requests

app = FastAPI(title="LAZARUS-Z API", version="0.4")

# CORS permissif pour tes tests (en prod, remplace "*" par ton domaine)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

class YouTubeLink(BaseModel):
    youtubeUrl: str

@app.get("/")
def root():
    return {"message": "Hello, Lazarus-Z API is running!"}

# ========= Upload d'un fichier (MP3/WAV) =========
@app.post("/api/upload")
async def upload_file(file: UploadFile = File(None)):
    if file:
        data = await file.read()
        return {"filename": file.filename, "size_bytes": len(data)}
    return {"error": "No file uploaded"}

# ========= Utils YouTube =========
_YT_ID_RE = re.compile(r"(?:v=|youtu\.be/|shorts/|embed/)([A-Za-z0-9_-]{11})")

def extract_video_id(url: str) -> Optional[str]:
    """
    Prend en charge:
      - https://www.youtube.com/watch?v=XXXXXXXXXXX
      - https://youtu.be/XXXXXXXXXXX
      - https://www.youtube.com/shorts/XXXXXXXXXXX
      - https://www.youtube.com/embed/XXXXXXXXXXX
    Si une playlist est donnée, on prend l'ID vidéo s'il est présent (param v).
    """
    m = _YT_ID_RE.search(url)
    return m.group(1) if m else None

def iso8601_to_seconds(iso: str) -> int:
    """
    Convertit une durée ISO8601 YouTube (ex: PT1H2M3S) en secondes.
    """
    # ex: PT2H10M30S, PT4M20S, PT50S…
    hrs = mins = secs = 0
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if m:
        hrs = int(m.group(1) or 0)
        mins = int(m.group(2) or 0)
        secs = int(m.group(3) or 0)
    return hrs * 3600 + mins * 60 + secs

def fetch_youtube_metadata(video_id: str) -> Dict[str, Any]:
    if not YOUTUBE_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="YOUTUBE_API_KEY manquant. Ajoutez la variable d'environnement sur Render."
        )
    url = (
        "https://www.googleapis.com/youtube/v3/videos"
        f"?part=snippet,contentDetails&id={video_id}&key={YOUTUBE_API_KEY}"
    )
    r = requests.get(url, timeout=15)
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Appel API YouTube échoué: {r.text}")
    data = r.json()
    items = data.get("items", [])
    if not items:
        raise HTTPException(status_code=404, detail="Vidéo introuvable ou privée.")
    item = items[0]
    snippet = item.get("snippet", {})
    content = item.get("contentDetails", {})
    duration_iso = content.get("duration")
    return {
        "id": item.get("id"),
        "title": snippet.get("title"),
        "channel": snippet.get("channelTitle"),
        "publishedAt": snippet.get("publishedAt"),
        "thumbnail": (snippet.get("thumbnails", {}).get("high", {}) or
                      snippet.get("thumbnails", {}).get("default", {})).get("url"),
        "duration_iso8601": duration_iso,
        "duration_seconds": iso8601_to_seconds(duration_iso or "PT0S"),
        "webpage_url": f"https://www.youtube.com/watch?v={item.get('id')}"
    }

# ========= Lien YouTube -> métadonnées via API officielle =========
@app.post("/api/upload-youtube")
async def upload_youtube(link: YouTubeLink):
    vid = extract_video_id(link.youtubeUrl)
    if not vid:
        raise HTTPException(status_code=400, detail="Lien YouTube non reconnu (impossible d'extraire l'ID).")
    meta = fetch_youtube_metadata(vid)
    return {"message": "Métadonnées récupérées", "meta": meta}

# Santé
@app.get("/api/health")
def health():
    return {"status": "ok"}
# --- conversion WAV & fichiers statiques ---
from pathlib import Path
import uuid, subprocess, os
import imageio_ffmpeg

FILES_ROOT = Path(os.getenv("FILES_ROOT", "/opt/render/project/src/files"))
FILES_ROOT.mkdir(parents=True, exist_ok=True)

def ffmpeg_path():
    return imageio_ffmpeg.get_ffmpeg_exe()

def convert_to_wav(src_path: Path, stereo: bool = True, sr: int = 44100) -> Path:
    dst = src_path.with_suffix(".wav")
    ch = "2" if stereo else "1"
    cmd = [
        ffmpeg_path(),
        "-y", "-i", str(src_path),
        "-vn",
        "-ac", ch,
        "-ar", str(sr),
        "-sample_fmt", "s16",
        str(dst),
    ]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        raise HTTPException(status_code=500, detail=f"FFmpeg error: {proc.stderr.decode(errors='ignore')}")
    return dst

@app.post("/api/convert-wav")
async def convert_wav(file: UploadFile = File(...)):
    # 1) sauvegarde dans un dossier de job unique
    job_id = str(uuid.uuid4())
    job_dir = FILES_ROOT / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    src_path = job_dir / file.filename
    data = await file.read()
    src_path.write_bytes(data)

    # 2) conversion
    wav_path = convert_to_wav(src_path, stereo=True, sr=44100)

    # 3) urls de téléchargement
    return {
        "jobId": job_id,
        "original": f"/files/{job_id}/{src_path.name}",
        "wav": f"/files/{job_id}/{wav_path.name}",
        "note": "Clique ces URLs dans ton navigateur pour télécharger.",
    }

# Servir les fichiers générés (téléchargement)
from fastapi.responses import FileResponse
@app.get("/files/{job_id}/{filename}")
def serve_file(job_id: str, filename: str):
    path = FILES_ROOT / job_id / filename
    if not path.exists():
        raise HTTPException(404, "Fichier introuvable")
    return FileResponse(str(path), filename=filename, media_type="application/octet-stream")
