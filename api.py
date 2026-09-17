"""TEOS Sovereign Video Engine — Deployment Web API.

Exposes the full sovereign video pipeline over HTTP so the Vercel
frontend can request and download finished MP4s.
"""

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from core import governance
from core.orchestrator import VideoOrchestrator

APP_VERSION = "1.0.0"

APP_DIR = Path(__file__).resolve().parent
ASSETS_DIR = APP_DIR / "assets"
AUDIT_FILE = APP_DIR / "AUDIT_INDEX.md"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

_DEFAULT_ALLOWED_ORIGINS = [
    "https://teos-ai-engine.vercel.app",
    "https://elmahrosa.com",
    "https://www.elmahrosa.com",
    "https://teosegypt.com",
    "https://www.teosegypt.com",
]


def _cors_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS", "").strip()
    if not raw:
        return list(_DEFAULT_ALLOWED_ORIGINS)
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


app = FastAPI(
    title="TEOS Sovereign Video Engine",
    description="Renders fact-checked sovereign short-form video from a single topic.",
    version=APP_VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/media", StaticFiles(directory=ASSETS_DIR), name="media")


class GenerateRequest(BaseModel):
    topic: str = Field(
        ...,
        min_length=2,
        max_length=200,
        description="Topic that the sovereign pipeline turns into a video.",
    )
    voice: str | None = Field(
        default=None,
        max_length=64,
        description="Optional Edge-TTS voice override, e.g. en-US-ChristopherNeural.",
    )


def _to_media_url(path: str | None) -> str:
    if not path:
        return ""
    normalized = Path(path).as_posix()
    prefix = "assets/"
    if normalized.startswith(prefix):
        normalized = normalized[len(prefix):]
    return f"/media/{normalized}"


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "teos-video-engine", "version": APP_VERSION}


@app.post("/api/v1/video/generate")
async def generate_video(request: GenerateRequest) -> dict:
    topic = request.topic.strip()
    if not topic:
        raise HTTPException(status_code=422, detail="topic is required.")

    try:
        result = await VideoOrchestrator(topic=topic, voice=request.voice).generate()
    except Exception as exc:  # noqa: BLE001 — surface pipeline failures to the client
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    result["video_url"] = _to_media_url(result.get("video"))
    result["audio_url"] = _to_media_url(result.get("audio"))
    result["subtitles_url"] = _to_media_url(result.get("subtitles"))
    result["audit"] = governance.recent_audit(limit=25)
    result["service"] = "teos-video-engine"
    result["version"] = APP_VERSION
    return result


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)