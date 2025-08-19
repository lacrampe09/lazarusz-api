from fastapi import FastAPI, UploadFile, File
from pydantic import BaseModel

app = FastAPI(title="LAZARUS-Z API", version="0.2")

class YouTubeLink(BaseModel):
    youtubeUrl: str

@app.get("/")
def root():
    return {"message": "Hello, Lazarus-Z API is running!"}

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(None)):
    if file:
        contents = await file.read()
        return {"filename": file.filename, "size_bytes": len(contents)}
    return {"error": "No file uploaded"}

@app.post("/api/upload-youtube")
async def upload_youtube(link: YouTubeLink):
    return {"message": "Lien YouTube reçu", "url": link.youtubeUrl}
