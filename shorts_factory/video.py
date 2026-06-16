# -*- coding: utf-8 -*-
"""plan.json + 콘티 이미지 → TTS · 자막 · MP4 (9:16 쇼츠)."""

from __future__ import annotations

import asyncio
import os
import re
import textwrap
from pathlib import Path
from typing import Any, Callable

import numpy as np
from PIL import Image, ImageDraw, ImageFont

SHORTS_W, SHORTS_H = 1080, 1920
FPS = 24

LogFn = Callable[[str], None]

_VOICE = {
    "host": "ko-KR-SunHiNeural",
    "customer": "ko-KR-InJoonNeural",
}


def _log_default(msg: str) -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("cp949", errors="replace").decode("cp949"), flush=True)


def _safe_stem(name: str, *, default: str = "shorts") -> str:
    raw = (name or "").strip()
    if not raw:
        return default
    parts: list[str] = []
    for ch in raw:
        if ch.isalnum():
            parts.append(ch)
        elif ch in "-_":
            parts.append(ch)
        elif ch.isspace():
            parts.append("_")
    stem = re.sub(r"_+", "_", "".join(parts)).strip("_")
    return (stem[:48] or default)


def _moviepy():
    try:
        from moviepy import (  # type: ignore
            AudioFileClip,
            ColorClip,
            CompositeVideoClip,
            ImageClip,
            concatenate_videoclips,
        )

        return {
            "AudioFileClip": AudioFileClip,
            "ColorClip": ColorClip,
            "CompositeVideoClip": CompositeVideoClip,
            "ImageClip": ImageClip,
            "concatenate_videoclips": concatenate_videoclips,
        }
    except ImportError:
        from moviepy.editor import (  # type: ignore
            AudioFileClip,
            ColorClip,
            CompositeVideoClip,
            ImageClip,
            concatenate_videoclips,
        )

        return {
            "AudioFileClip": AudioFileClip,
            "ColorClip": ColorClip,
            "CompositeVideoClip": CompositeVideoClip,
            "ImageClip": ImageClip,
            "concatenate_videoclips": concatenate_videoclips,
        }


def _with_duration(clip: Any, duration: float) -> Any:
    if hasattr(clip, "with_duration"):
        return clip.with_duration(duration)
    return clip.set_duration(duration)


def _with_audio(clip: Any, audio: Any) -> Any:
    if hasattr(clip, "with_audio"):
        return clip.with_audio(audio)
    return clip.set_audio(audio)


def _resize(clip: Any, *, width: int | None = None, height: int | None = None) -> Any:
    if height is not None:
        if hasattr(clip, "resized"):
            return clip.resized(height=height)
        return clip.resize(height=height)
    if width is not None:
        if hasattr(clip, "resized"):
            return clip.resized(width=width)
        return clip.resize(width=width)
    return clip


def _position(clip: Any, pos: Any) -> Any:
    if hasattr(clip, "with_position"):
        return clip.with_position(pos)
    return clip.set_position(pos)


async def _tts_async(text: str, path: Path, *, speaker: str = "host") -> Path:
    import edge_tts

    voice = _VOICE.get((speaker or "host").strip().lower(), _VOICE["host"])
    text = (text or "").strip() or "."
    path.parent.mkdir(parents=True, exist_ok=True)
    comm = edge_tts.Communicate(text, voice)
    await comm.save(str(path))
    return path


def _tts(text: str, path: Path, *, speaker: str = "host") -> Path:
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_tts_async(text, path, speaker=speaker))
    finally:
        loop.close()


def _subtitle_rgba(text: str, size: tuple[int, int] = (SHORTS_W, SHORTS_H)) -> np.ndarray:
    w, h = size
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    font_size = 52
    try:
        font = ImageFont.truetype("malgun.ttf", font_size)
    except OSError:
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except OSError:
            font = ImageFont.load_default()

    lines = textwrap.wrap((text or "").strip(), width=16) or [""]
    lines = lines[:2]
    line_h = font_size + 10
    total_h = len(lines) * line_h
    y0 = int(h * 0.72)
    draw.rounded_rectangle(
        [36, y0 - 14, w - 36, y0 - 14 + total_h + 28],
        radius=16,
        fill=(0, 0, 0, 138),
    )
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        x = (w - tw) // 2
        y = y0 + i * line_h
        for dx, dy in [(-2, 0), (2, 0), (0, -2), (0, 2)]:
            draw.text((x + dx, y + dy), line, font=font, fill=(0, 0, 0, 255))
        draw.text((x, y), line, font=font, fill=(255, 230, 0, 255))
    return np.array(canvas)


def _placeholder_jpg(dest: Path, scene: dict, idx: int) -> Path:
    """콘티 이미지 없을 때 — 텍스트 없는 은은한 그라데이션만."""
    palette = [
        ((30, 58, 95), (45, 85, 120)),
        ((45, 85, 120), (55, 70, 110)),
        ((55, 70, 110), (80, 50, 90)),
        ((80, 50, 90), (30, 58, 95)),
    ]
    c0, c1 = palette[idx % len(palette)]
    img = Image.new("RGB", (SHORTS_W, SHORTS_H))
    px = img.load()
    for y in range(SHORTS_H):
        t = y / max(1, SHORTS_H - 1)
        r = int(c0[0] * (1 - t) + c1[0] * t)
        g = int(c0[1] * (1 - t) + c1[1] * t)
        b = int(c0[2] * (1 - t) + c1[2] * t)
        for x in range(SHORTS_W):
            px[x, y] = (r, g, b)
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, quality=92)
    return dest


def _ken_burns_clip(mp: dict[str, Any], image_path: Path, duration: float) -> Any:
    """정지 이미지에 천천히 줌·팬 — 슬라이드쇼 느낌 완화."""
    pil = Image.open(image_path).convert("RGB")
    iw, ih = pil.size
    scale = max(SHORTS_W / iw, SHORTS_H / ih) * 1.18
    canvas = pil.resize((max(1, int(iw * scale)), max(1, int(ih * scale))), Image.Resampling.LANCZOS)
    cw, ch = canvas.size

    def make_frame(t: float) -> np.ndarray:
        progress = min(1.0, max(0.0, t / max(duration, 0.01)))
        crop_w = max(SHORTS_W, int(cw - (cw - SHORTS_W) * 0.85 * progress))
        crop_h = max(SHORTS_H, int(ch - (ch - SHORTS_H) * 0.85 * progress))
        left = int((cw - crop_w) * 0.45 * progress)
        top = int((ch - crop_h) * 0.35 * progress)
        left = min(max(0, left), max(0, cw - crop_w))
        top = min(max(0, top), max(0, ch - crop_h))
        crop = canvas.crop((left, top, left + crop_w, top + crop_h))
        frame = crop.resize((SHORTS_W, SHORTS_H), Image.Resampling.LANCZOS)
        return np.array(frame)

    try:
        from moviepy import VideoClip  # type: ignore

        clip = VideoClip(make_frame, duration=duration).with_fps(FPS)
        return clip
    except ImportError:
        from moviepy.editor import VideoClip  # type: ignore

        clip = VideoClip(make_frame, duration=duration)
        clip = clip.set_fps(FPS)
        return clip


def _fit_image_clip(mp: dict[str, Any], image_path: Path, duration: float) -> Any:
    try:
        return _ken_burns_clip(mp, image_path, duration)
    except Exception:
        ImageClip = mp["ImageClip"]
        clip = ImageClip(str(image_path))
        clip = _resize(clip, height=SHORTS_H)
        if clip.w > SHORTS_W:
            try:
                clip = clip.cropped(x_center=clip.w / 2, width=SHORTS_W, height=SHORTS_H)
            except Exception:
                xc = clip.w / 2
                clip = clip.cropped(x1=xc - SHORTS_W / 2, width=SHORTS_W, height=SHORTS_H)
        clip = _resize(clip, width=SHORTS_W, height=SHORTS_H)
        return _with_duration(clip, duration)


def _fit_video_clip(mp: dict[str, Any], video_path: Path, duration: float) -> Any:
    """다운로드한 B-roll 클립을 9:16에 맞춤."""
    try:
        from moviepy import VideoFileClip  # type: ignore
    except ImportError:
        from moviepy.editor import VideoFileClip  # type: ignore

    clip = VideoFileClip(str(video_path))
    clip = _resize(clip, height=SHORTS_H)
    if clip.w > SHORTS_W:
        try:
            clip = clip.cropped(x_center=clip.w / 2, width=SHORTS_W, height=SHORTS_H)
        except Exception:
            xc = clip.w / 2
            clip = clip.cropped(x1=xc - SHORTS_W / 2, width=SHORTS_W, height=SHORTS_H)
    clip = _resize(clip, width=SHORTS_W, height=SHORTS_H)
    if clip.duration and clip.duration > duration + 0.05:
        try:
            clip = clip.subclipped(0, duration)
        except AttributeError:
            clip = clip.subclip(0, duration)
    return _with_duration(clip, duration)


def _scene_image_path(scene: dict, out_dir: Path, idx: int, work: Path, log: LogFn) -> tuple[Path, str]:
    rel = scene.get("image_file")
    if rel:
        p = out_dir / str(rel).replace("\\", "/")
        if p.is_file() and p.stat().st_size > 512:
            src = str(scene.get("image_source") or "storyboard")
            return p, src
    ph = work / f"placeholder_{idx:02d}.jpg"
    if not ph.is_file():
        _placeholder_jpg(ph, scene, idx)
    log(f"   [경고] 장면 {scene.get('scene_no', idx + 1)}: 실사 이미지 없음, 임시 배경 사용")
    return ph, "placeholder"


def render_plan_video(
    plan: dict,
    out_dir: Path,
    *,
    output_name: str = "shorts.mp4",
    log: LogFn | None = None,
) -> dict[str, Any]:
    """콘티 plan → MP4. plan에 video_file 갱신."""
    log = log or _log_default
    scenes = plan.get("scenes") or []
    if not scenes:
        return {"ok": False, "error": "장면이 없습니다."}

    try:
        mp = _moviepy()
    except ImportError as e:
        return {
            "ok": False,
            "error": "moviepy·edge-tts 필요: pip install moviepy imageio-ffmpeg edge-tts",
            "detail": str(e),
        }

    AudioFileClip = mp["AudioFileClip"]
    CompositeVideoClip = mp["CompositeVideoClip"]
    ImageClip = mp["ImageClip"]
    concatenate_videoclips = mp["concatenate_videoclips"]

    out_dir = Path(out_dir)
    work = out_dir / "render"
    work.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / output_name

    try:
        from shorts_factory.images import ensure_storyboard_images

        plan = ensure_storyboard_images(plan, out_dir, log=log)
        plan_path = out_dir / "plan.json"
        if plan_path.parent.is_dir():
            import json

            plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        log(f"장면 이미지 자동 생성 실패: {e}")

    scenes = plan.get("scenes") or []
    broll_count = 0
    try:
        from shorts_factory.stock_video import load_manifest

        broll_count = len((load_manifest(out_dir.name, out_dir.parent).get("assignments") or {}))
    except Exception:
        pass
    img_ok = sum(1 for sc in scenes if sc.get("image_file"))
    if img_ok == 0 and broll_count == 0:
        return {
            "ok": False,
            "error": "장면 이미지 또는 B-roll 클립이 없습니다. ② 스토리보드 또는 무료 B-roll 다운로드를 실행하세요.",
        }
    log(f"장면 이미지 {img_ok}/{len(scenes)}장 · B-roll {broll_count}장")

    tmp_dir = work / "_moviepy_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    prev_temp = os.environ.get("TEMP")
    prev_tmp = os.environ.get("TMP")
    os.environ["TEMP"] = str(tmp_dir)
    os.environ["TMP"] = str(tmp_dir)

    scene_clips: list[Any] = []
    try:
        log(f"MP4 렌더 시작 - {len(scenes)}장면")
        for idx, scene in enumerate(scenes):
            n = scene.get("scene_no") or (idx + 1)
            log(f"   장면 {n}/{len(scenes)} TTS·합성…")
            narr = (scene.get("narration") or scene.get("subtitle") or "").strip()
            sub = (scene.get("subtitle") or narr)[:40]
            speaker = str(scene.get("speaker") or "host")

            audio_path = work / f"audio_{idx:02d}.mp3"
            _tts(narr, audio_path, speaker=speaker)
            audio_clip = AudioFileClip(str(audio_path))
            duration = max(1.8, float(audio_clip.duration), float(scene.get("duration_sec") or 3.5))
            duration = min(duration, 12.0)

            scene_no = int(scene.get("scene_no") or (idx + 1))
            broll_path = None
            try:
                from shorts_factory.stock_video import broll_path_for_scene_in_dir

                broll_path = broll_path_for_scene_in_dir(out_dir, scene_no)
            except Exception:
                pass

            if broll_path and broll_path.is_file():
                log(f"      B-roll: {broll_path.name}")
                try:
                    bg = _fit_video_clip(mp, broll_path, duration)
                except Exception as e:
                    log(f"      B-roll 실패({e}), 이미지로 대체")
                    img_path, img_src = _scene_image_path(scene, out_dir, idx, work, log)
                    bg = _fit_image_clip(mp, img_path, duration)
            else:
                img_path, img_src = _scene_image_path(scene, out_dir, idx, work, log)
                if img_src != "placeholder":
                    log(f"      배경: {img_path.name} ({img_src})")
                bg = _fit_image_clip(mp, img_path, duration)

            sub_arr = _subtitle_rgba(sub)
            sub_clip = _position(_with_duration(ImageClip(sub_arr), duration), "center")

            video = _with_audio(bg, audio_clip)
            final = CompositeVideoClip([video, sub_clip], size=(SHORTS_W, SHORTS_H))
            scene_clips.append(final)

        log("마스터 인코딩 중… (1~3분)")
        master = concatenate_videoclips(scene_clips, method="compose", padding=-0.08)
        master.write_videofile(
            str(out_path),
            fps=FPS,
            codec="libx264",
            audio_codec="aac",
            preset="medium",
            threads=2,
            logger=None,
        )
        try:
            master.close()
        except Exception:
            pass
        for c in scene_clips:
            try:
                c.close()
            except Exception:
                pass

        rel_video = output_name
        plan["video_file"] = rel_video
        plan["video_ready"] = True
        log(f"MP4 완료: {out_path.name}")
        return {"ok": True, "video_file": rel_video, "video_path": str(out_path), "plan": plan}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        if prev_temp is not None:
            os.environ["TEMP"] = prev_temp
        elif "TEMP" in os.environ:
            del os.environ["TEMP"]
        if prev_tmp is not None:
            os.environ["TMP"] = prev_tmp
        elif "TMP" in os.environ:
            del os.environ["TMP"]


def render_slug_video(slug: str, *, shorts_root: Path | None = None, log: LogFn | None = None) -> dict[str, Any]:
    root = shorts_root or Path(__file__).resolve().parent.parent / "docs" / "shorts"
    out_dir = root / slug
    plan_path = out_dir / "plan.json"
    if not plan_path.is_file():
        return {"ok": False, "error": f"프로젝트 없음: {slug}"}
    import json

    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    r = render_plan_video(plan, out_dir, log=log)
    if r.get("ok"):
        plan = r.get("plan") or plan
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        r["plan"] = plan
        r["slug"] = slug
    return r
