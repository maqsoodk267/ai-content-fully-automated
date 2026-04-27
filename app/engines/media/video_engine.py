"""
VideoEngine — assembles short-form videos using FFmpeg.

Pipeline:
  inputs (images, clips, background_video) + voice WAV + subtitles
  → stitched, vertical MP4 with transitions, motion, and audio sync.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.engines.base import BaseEngine
from app.engines.media.image_engine import STORAGE_ROOT

VIDEO_DIR = STORAGE_ROOT / "videos"
VIDEO_DIR.mkdir(parents=True, exist_ok=True)

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")


def ffmpeg_available() -> bool:
    return FFMPEG is not None


def _probe_duration(path: str) -> float:
    if not FFPROBE or not os.path.exists(path):
        return 0.0
    try:
        out = subprocess.check_output(
            [FFPROBE, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            stderr=subprocess.DEVNULL, timeout=15,
        ).decode().strip()
        return float(out or 0.0)
    except Exception:
        return 0.0


class VideoEngine(BaseEngine):
    name = "video"
    description = "Render vertical videos with FFmpeg, stitching, subtitles, transitions and motion"

    def run(
        self,
        *,
        image_paths: Optional[List[str]] = None,
        clip_paths: Optional[List[str]] = None,
        background_video: Optional[str] = None,
        audio_path: Optional[str] = None,
        subtitle_path: Optional[str] = None,
        duration_per_image: float = 3.0,
        transition_duration: float = 0.6,
        zoom_cuts: bool = True,
        speed_ramp: bool = True,
        width: int = 1080,
        height: int = 1920,
        fps: int = 30,
        text_animations: Optional[List[Dict[str, Any]]] = None,
        glitch_effect: Optional[List[str]] = None,
        glitch_intensity: Optional[float] = None,
        out_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not ffmpeg_available():
            return {"path": None, "error": "ffmpeg is not installed in this environment"}

        image_paths = image_paths or []
        clip_paths = clip_paths or []

        assets: List[Dict[str, Any]] = []
        for image_path in image_paths:
            if os.path.exists(image_path):
                assets.append({"path": image_path, "type": "image", "duration": duration_per_image})
        for clip_path in clip_paths:
            if os.path.exists(clip_path):
                assets.append({"path": clip_path, "type": "clip", "duration": max(1.0, _probe_duration(clip_path))})

        if background_video and os.path.exists(background_video) and not assets:
            assets.append({"path": background_video, "type": "clip", "duration": max(1.0, _probe_duration(background_video)), "loop": True})

        if not assets:
            return {"path": None, "error": "No valid image, clip or background_video source provided"}

        audio_duration = _probe_duration(audio_path) if audio_path and os.path.exists(audio_path) else 0.0
        transition_total = transition_duration * max(0, len(assets) - 1)
        content_duration = sum(item["duration"] for item in assets)
        target_duration = audio_duration or (content_duration - transition_total)
        target_duration = max(2.0, float(target_duration))

        if audio_duration and content_duration > 0:
            ratio = (audio_duration + transition_total) / content_duration
            for item in assets:
                item["duration"] = max(0.5, item["duration"] * ratio)
                item["speed_factor"] = ratio
        else:
            for item in assets:
                item["speed_factor"] = 1.0

        command: List[str] = [FFMPEG, "-y", "-hide_banner"]

        for asset in assets:
            if asset["type"] == "image":
                command += ["-loop", "1", "-t", f"{asset['duration']:.2f}", "-i", asset["path"]]
            else:
                if asset.get("loop"):
                    command += ["-stream_loop", "-1", "-t", f"{target_duration:.2f}", "-i", asset["path"]]
                else:
                    command += ["-i", asset["path"]]

        if audio_path and os.path.exists(audio_path):
            command += ["-i", audio_path]

        text_animations = self._normalize_text_animations(text_animations)
        glitch_effects = self._normalize_glitch_effects(glitch_effect)
        glitch_intensity = max(0.0, min(1.0, glitch_intensity or 0.0))
        text_animation_path: Optional[str] = None

        filter_commands: List[str] = []
        video_labels: List[str] = []
        for index, asset in enumerate(assets):
            input_label = f"[{index}:v]"
            segment_label = f"[seg{index}]"
            if asset["type"] == "image":
                frames = int(round(asset["duration"] * fps))
                zoom = self._build_zoom_expression(frames, zoom_cuts, speed_ramp)
                filter_commands.append(
                    f"{input_label}scale={width}:{height}:force_original_aspect_ratio=increase,"
                    f"crop={width}:{height},format=rgba,zoompan=z='{zoom}':d={frames}:s={width}x{height},"
                    f"fps={fps},format=yuv420p{segment_label}"
                )
            else:
                speed_filter = ""
                if asset.get("speed_factor", 1.0) != 1.0:
                    speed_filter = f"setpts=PTS*{asset['speed_factor']:.8f},"
                filter_commands.append(
                    f"{input_label}{speed_filter}scale={width}:{height}:force_original_aspect_ratio=increase,"
                    f"crop={width}:{height},format=yuv420p,fps={fps}{segment_label}"
                )
            video_labels.append(segment_label)

        if len(video_labels) == 1:
            output_label = video_labels[0]
        else:
            output_label = self._build_transition_chain(video_labels, assets, transition_duration)

        if text_animations:
            text_animation_path = self._render_text_animations_ass(text_animations, target_duration, width, height)
            animation_filter = self._build_subtitle_filter(text_animation_path)
            filter_commands.append(f"{output_label}{animation_filter}[animv]")
            output_label = "[animv]"

        if subtitle_path and os.path.exists(subtitle_path):
            subtitle_filter = self._build_subtitle_filter(subtitle_path)
            filter_commands.append(f"{output_label}{subtitle_filter}[outv]")
            output_label = "[outv]"

        if glitch_effects and glitch_intensity > 0:
            glitch_label = self._build_glitch_filters(output_label, glitch_effects, glitch_intensity, width, height)
            filter_commands.append(glitch_label)
            output_label = "[glitched]"

        filter_complex = ";".join(filter_commands)
        command += ["-filter_complex", filter_complex]
        command += ["-map", output_label]
        if audio_path and os.path.exists(audio_path):
            command += ["-map", f"{len(assets)}:a"]

        command += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", "-threads", "0"]
        if audio_path and os.path.exists(audio_path):
            command += ["-c:a", "aac", "-b:a", "128k", "-shortest"]
        else:
            command += ["-an"]

        if out_path:
            out_path = Path(out_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            out_path = VIDEO_DIR / f"video_{uuid.uuid4().hex[:10]}.mp4"

        command += [str(out_path)]

        try:
            subprocess.run(command, check=True, capture_output=True, timeout=600)
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.decode("utf-8", "ignore")[-1500:]
            return {"path": None, "error": f"ffmpeg failed: {stderr}"}
        except subprocess.TimeoutExpired:
            return {"path": None, "error": "ffmpeg timed out"}
        finally:
            if text_animation_path and os.path.exists(text_animation_path):
                try:
                    os.remove(text_animation_path)
                except OSError:
                    pass

        return {
            "path": str(out_path),
            "url": f"/media/videos/{out_path.name}",
            "duration_s": round(target_duration, 2),
            "size": [width, height],
            "fps": fps,
            "segments": len(assets),
            "transition_duration": transition_duration,
            "zoom_cuts": zoom_cuts,
            "speed_ramp": speed_ramp,
            "text_animations": text_animations,
            "glitch_effect": glitch_effects,
            "glitch_intensity": glitch_intensity,
        }

    # ------------------------------------------------------------------
    @staticmethod
    def _build_zoom_expression(frames: int, zoom_cuts: bool, speed_ramp: bool) -> str:
        if not zoom_cuts or frames < 2:
            return "if(lte(on,1),1.0,zoom+0.0008)"
        mid = max(1, frames // 3)
        if speed_ramp:
            return (
                f"if(lte(on,{mid}),1+on*0.0005,1+{mid}*0.0005+(on-{mid})*0.0012)"
            )
        return "if(lte(on,1),1.0,zoom+0.0008)"

    @staticmethod
    def _build_transition_chain(labels: List[str], assets: List[Dict[str, Any]],
                                transition_duration: float) -> str:
        current_label = labels[0]
        previous_duration = 0.0
        for index in range(1, len(labels)):
            output_label = f"[xf{index}]"
            previous_duration += assets[index - 1]["duration"]
            offset = max(0.0, previous_duration - transition_duration * index)
            current_label = (
                f"{current_label}{labels[index]}xfade=transition=fade:duration={transition_duration:.2f}:"
                f"offset={offset:.2f}{output_label}"
            )
        return current_label

    @staticmethod
    def _build_subtitle_filter(path: str) -> str:
        esc = path.replace("\\", "\\\\").replace(":", "\\:").replace(",", "\\,")
        style = "Fontsize=32,Outline=2,BorderStyle=3,BackColour=&H80000000&,PrimaryColour=&Hffffff&"
        return f"subtitles='{esc}':force_style='{style}'"

    @staticmethod
    def _normalize_glitch_effects(glitch_effect: Optional[List[str]]) -> List[str]:
        if not glitch_effect:
            return []
        if isinstance(glitch_effect, str):
            glitch_effect = [glitch_effect]
        return [str(effect).lower() for effect in glitch_effect if effect]

    @staticmethod
    def _build_glitch_filters(input_label: str, effects: List[str], intensity: float, width: int, height: int) -> str:
        label = input_label
        anodes: List[str] = []
        if "pixelation" in effects:
            pixel = max(2, int(width * (1.0 - intensity) * 0.25))
            anodes.append(f"{label}scale={pixel}:{max(2, int(height * (1.0 - intensity) * 0.25))}:flags=neighbor,scale={width}:{height}:flags=neighbor[px]")
            label = "[px]"
        if "frame_shift" in effects:
            shift = max(1, int(15 * intensity))
            anodes.append(
                f"{label}split=2[base][shifted];"
                f"[shifted]setpts=PTS+0.02/TB,translate={shift}:0[shifted2];"
                f"[base][shifted2]blend=all_mode='lighten':all_opacity={min(1.0, 0.4 + intensity * 0.6)}[fs]"
            )
            label = "[fs]"
        if "rgb_split" in effects:
            split = max(1, int(5 * intensity))
            anodes.append(
                f"{label}split=3[r][g][b];"
                f"[r]lutrgb=r=r:g=0:b=0,translate={split}:0[r2];"
                f"[g]lutrgb=r=0:g=g:b=0,translate=-{split}:0[g2];"
                f"[b]lutrgb=r=0:g=0:b=b,translate=0:{split}[b2];"
                f"[r2][g2]blend=all_mode='lighten'[rg];"
                f"[rg][b2]blend=all_mode='lighten'[rgb]"
            )
            label = "[rgb]"
        if not anodes:
            return ""
        combined = ";".join(anodes)
        return f"{combined}{label}[glitched]"

    @staticmethod
    def _normalize_text_animations(text_animations: Optional[Any]) -> List[Dict[str, Any]]:
        if not text_animations:
            return []
        normalized: List[Dict[str, Any]] = []
        if isinstance(text_animations, dict):
            if all(isinstance(value, str) for value in text_animations.values()):
                for anim_type, text in text_animations.items():
                    normalized.append({"type": anim_type, "text": text})
                return normalized
            if text_animations.get("text") and text_animations.get("type"):
                return [text_animations]
            return []
        if isinstance(text_animations, list):
            for item in text_animations:
                if isinstance(item, dict) and item.get("text"):
                    normalized.append(item)
            return normalized
        return []

    @staticmethod
    def _render_text_animations_ass(animations: List[Dict[str, Any]], duration: float, width: int, height: int) -> str:
        lines = [
            "[Script Info]",
            "Title: Text Animations",
            "ScriptType: v4.00+",
            f"PlayResX: {width}",
            f"PlayResY: {height}",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
            "Style: Default,Arial,64,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,1,2,10,10,10,1",
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        ]

        for animation in animations:
            text = str(animation.get("text", "")).replace("\n", "\\N")
            if not text:
                continue
            anim_type = str(animation.get("type", "fade")).lower()
            start = float(animation.get("start", 0.0))
            duration_sec = float(animation.get("duration", max(0.5, duration - start)))
            end = min(start + duration_sec, duration)
            position = str(animation.get("position", "center")).lower()
            x, y = VideoEngine._ass_position(position, width, height)
            tags: List[str] = [f"\\fs{int(animation.get('font_size', 64))}", "\\bord2", "\\shad1", "\\c&HFFFFFF&"]
            if anim_type == "fade":
                fade_ms = min(500, int(duration_sec * 1000))
                tags.append(f"\\fad({fade_ms},{fade_ms})")
            if anim_type == "bounce":
                tags.append(f"\\t(0,{min(int(duration_sec * 1000), 600)},\\fs{int(animation.get('font_size', 64)) + 24})")
            if anim_type == "slide":
                direction = str(animation.get("direction", "left")).lower()
                start_x = -int(width * 0.2) if direction != "right" else width + int(width * 0.2)
                tags.append(f"\\move({start_x},{y},{x},{y})")
            else:
                tags.append(f"\\pos({x},{y})")
            if anim_type == "typewriter":
                chars = list(text)
                delay = max(4, int(duration_sec * 100 / max(1, len(chars))))
                typewriter_text = "".join(f"\\k{delay}{c}" for c in chars)
                text = typewriter_text
            event_text = "{" + "".join(tags) + "}" + text
            lines.append(
                f"Dialogue: 0,{VideoEngine._format_ass_time(start)},{VideoEngine._format_ass_time(end)},Default,,0,0,0,,{event_text}"
            )

        ass_path = tempfile.NamedTemporaryFile(delete=False, suffix=".ass").name
        with open(ass_path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines))
        return ass_path

    @staticmethod
    def _ass_position(position: str, width: int, height: int) -> tuple[int, int]:
        if position == "top":
            return width // 2, int(height * 0.18)
        if position == "bottom":
            return width // 2, int(height * 0.82)
        if position == "left":
            return int(width * 0.1), height // 2
        if position == "right":
            return int(width * 0.9), height // 2
        return width // 2, height // 2

    @staticmethod
    def _format_ass_time(seconds: float) -> str:
        total_cs = int(round(seconds * 100))
        hours = total_cs // 360000
        minutes = (total_cs % 360000) // 6000
        secs = (total_cs % 6000) / 100.0
        return f"{hours}:{minutes:02d}:{secs:05.2f}"
