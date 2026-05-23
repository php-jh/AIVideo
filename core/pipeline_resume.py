"""
一键生成断点续跑：根据剧本与 output 目录判断已完成步骤。
"""
import os
from dataclasses import dataclass
from typing import Dict, List, Optional

from config import get_output_dir, load_config
from core.motion_utils import effective_video_mode


def _valid_file(path: str, min_bytes: int = 100) -> bool:
    return bool(path) and os.path.isfile(path) and os.path.getsize(path) >= min_bytes


def _scene_has_image(scene: dict, images_dir: str) -> bool:
    ip = scene.get("image_path", "")
    if _valid_file(ip, 2000):
        return True
    num = scene.get("scene_number", 0)
    if images_dir and os.path.isdir(images_dir):
        import glob
        hits = glob.glob(os.path.join(images_dir, f"scene_{num:02d}_*.png"))
        return any(_valid_file(p, 2000) for p in hits)
    return False


def _scene_has_audio(scene: dict, audio_dir: str) -> bool:
    ap = scene.get("audio_path", "")
    if _valid_file(ap, 100):
        return True
    num = scene.get("scene_number", 0)
    p = os.path.join(audio_dir, f"audio_scene_{num:02d}.mp3")
    return _valid_file(p, 100)


def _scene_has_video(scene: dict, videos_dir: str) -> bool:
    vp = scene.get("video_path", "")
    if _valid_file(vp, 1000):
        return True
    num = scene.get("scene_number", 0)
    if videos_dir and os.path.isdir(videos_dir):
        import glob
        hits = glob.glob(os.path.join(videos_dir, f"scene_{num:02d}_*.mp4"))
        return any(_valid_file(p, 1000) for p in hits)
    return False


@dataclass
class PipelineStatus:
    total_scenes: int
    images_done: int
    videos_done: int
    audio_done: int
    need_videos: bool
    next_step: str  # images | videos | audio | compose | done
    output_dir: str

    def summary_lines(self) -> List[str]:
        lines = [
            f"分镜共 {self.total_scenes} 镜",
            f"图片 {self.images_done}/{self.total_scenes}",
        ]
        if self.need_videos:
            lines.append(f"动效 {self.videos_done}/{self.total_scenes}")
        lines.append(f"配音 {self.audio_done}/{self.total_scenes}")
        return lines

    def next_step_label(self) -> str:
        labels = {
            "images": "生成缺失分镜图片",
            "videos": "生成缺失分镜动效",
            "audio": "生成缺失配音",
            "compose": "合成最终视频",
            "done": "媒体已齐，仅合成成片",
        }
        return labels.get(self.next_step, self.next_step)


def analyze_pipeline(script: dict, output_dir: Optional[str] = None, config=None) -> PipelineStatus:
    """分析当前进度，决定续跑从哪一步开始。"""
    cfg = config or load_config()
    out = output_dir or get_output_dir()
    scenes = script.get("scenes") or []
    total = len(scenes)
    images_dir = os.path.join(out, "images")
    audio_dir = os.path.join(out, "audio")
    videos_dir = os.path.join(out, "videos")
    need_videos = effective_video_mode(cfg) == "animated"

    img_done = sum(1 for s in scenes if isinstance(s, dict) and _scene_has_image(s, images_dir))
    aud_done = sum(1 for s in scenes if isinstance(s, dict) and _scene_has_audio(s, audio_dir))
    vid_done = (
        sum(1 for s in scenes if isinstance(s, dict) and _scene_has_video(s, videos_dir))
        if need_videos else total
    )

    if total == 0:
        next_step = "images"
    elif img_done < total:
        next_step = "images"
    elif need_videos and vid_done < total:
        next_step = "videos"
    elif aud_done < total:
        next_step = "audio"
    else:
        next_step = "compose"

    return PipelineStatus(
        total_scenes=total,
        images_done=img_done,
        videos_done=vid_done,
        audio_done=aud_done,
        need_videos=need_videos,
        next_step=next_step,
        output_dir=out,
    )
