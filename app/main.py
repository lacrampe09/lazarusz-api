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
