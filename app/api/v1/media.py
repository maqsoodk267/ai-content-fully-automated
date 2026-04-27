"""
Media generation endpoints — voice, subtitles, video, image, asset fetch.
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body
from pydantic import BaseModel, Field

from app.engines import get_engine

router = APIRouter(prefix="/media", tags=["media"])


class VoiceRequest(BaseModel):
    text: str
    language: str = "en"
    voice: Optional[str] = None
    out_path: Optional[str] = None


@router.post("/voice")
async def synthesize_voice(payload: VoiceRequest) -> Dict[str, Any]:
    return get_engine("voice")(text=payload.text, language=payload.language,
                                voice=payload.voice, out_path=payload.out_path)


class SubtitleRequest(BaseModel):
    audio_path: Optional[str] = None
    script: Optional[str] = None
    out_path: Optional[str] = None
    language: str = "en"


@router.post("/subtitles")
async def generate_subtitles(payload: SubtitleRequest) -> Dict[str, Any]:
    return get_engine("subtitle")(audio_path=payload.audio_path,
                                   script=payload.script,
                                   out_path=payload.out_path,
                                   language=payload.language)


class ImageRequest(BaseModel):
    prompt: str
    out_path: Optional[str] = None
    width: int = 1080
    height: int = 1920
    title: Optional[str] = None
    subtitle: Optional[str] = None


@router.post("/image")
async def generate_image(payload: ImageRequest) -> Dict[str, Any]:
    return get_engine("image")(**payload.dict())


@router.post("/thumbnail")
async def generate_thumbnail(payload: ImageRequest) -> Dict[str, Any]:
    d = payload.dict()
    d.setdefault("width", 1280); d.setdefault("height", 720)
    return get_engine("thumbnail")(**d)


class VideoRequest(BaseModel):
    image_paths: List[str] = Field(default_factory=list)
    clip_paths: List[str] = Field(default_factory=list)
    audio_path: Optional[str] = None
    subtitle_path: Optional[str] = None
    background_video: Optional[str] = None
    out_path: Optional[str] = None
    duration_per_image: float = 3.0
    transition_duration: float = 0.6
    zoom_cuts: bool = True
    speed_ramp: bool = True
    width: int = 1080
    height: int = 1920
    fps: int = 30


@router.post("/video")
async def assemble_video(payload: VideoRequest) -> Dict[str, Any]:
    return get_engine("video")(**payload.dict())


class AssetRequest(BaseModel):
    query: str
    asset_type: str = "image"  # image|video
    count: int = 5
    orientation: str = "portrait"


@router.post("/assets/fetch")
async def fetch_assets(payload: AssetRequest) -> Dict[str, Any]:
    return get_engine("asset_fetch")(**payload.dict())
