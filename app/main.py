from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from typing import Any, Dict, Optional

import yt_dlp  # pour extraire les métadonnées YouTube (sans télécharger)

app = FastAPI(title="LAZARUS-Z API", version="0.3")

# CORS – simple et permissif pour tester (en prod: remplace "*" par ton domaine)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

class YouTubeLink(BaseModel):
    youtubeUrl: str

@app.get("/")
def root():
    return {"message": "Hello, Lazarus-Z API is running!"}

# ====== Upload FICHIER (MP3/WAV) ======
@app.post("/api/upload")
async def upload_file(file: UploadFile = File(None)):
    if file:
        data = await file.read()
        return {"filename": file.filename, "size_bytes": len(data)}
    return {"error": "No file uploaded"}

# ====== Métadonnées YouTube (sans téléchargement) ======
def _pick_best_audio_format(info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    best = None
    for f in (info.get("formats") or []):
        # audio-only (pas de vidéo) et codec audio présent
        if f.get("acodec") != "none" and not f.get("video_ext"):
            if (best is None) or (f.get("abr", 0) > best.get("abr", 0)):
                best = f
    return best

def _normalize_info(info: Dict[str, Any], original_url: str) -> Dict[str, Any]:
    # Si c'est une playlist, prendre la première entrée
    if "entries" in info and isinstance(info["entries"], list) and info["entries"]:
        info = info["entries"][0]

    best_audio = _pick_best_audio_format(info)
    return {
        "id": info.get("id"),
        "title": info.get("title"),
        "uploader": info.get("uploader"),
        "channel": info.get("channel"),
        "duration_sec": info.get("duration"),
        "thumbnail": info.get("thumbnail"),
        "webpage_url": info.get("webpage_url") or original_url,
        "best_audio_url": best_audio.get("url") if best_audio else None,
        "best_audio_ext": best_audio.get("ext") if best_audio else None,
        "best_audio_abr": best_audio.get("abr") if best_audio else None,
    }

def extract_youtube_info(url: str) -> Dict[str, Any]:
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "nocheckcertificate": True,
        "extract_flat": False,
        "retries": 2,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return _normalize_info(info, url)

@app.post("/api/upload-youtube")
async def upload_youtube(link: YouTubeLink):
    try:
        meta = extract_youtube_info(link.youtubeUrl)
        return {"message": "Métadonnées récupérées", "meta": meta}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Extraction impossible: {e}")


# (Optionnel) endpoint santé simple
@app.get("/api/health")
def health():
    return {"status": "ok"}
