"""
分镜资源路径：写回剧本 JSON、从 output 目录自动找回已生成的图/视频/音频。
"""
import glob
import os
from typing import List, Optional, Tuple

from config import get_output_dir


def sync_storyboard_paths_to_script(storyboard, script: dict) -> None:
    """将 storyboard 场景上的 image/video/audio 路径写入 script['scenes']。"""
    script_scenes = script.get("scenes") or []
    for scene, s in zip(storyboard.scenes, script_scenes):
        if not isinstance(s, dict):
            continue
        ip = getattr(scene, "image_path", None)
        if ip:
            s["image_path"] = ip
        vp = getattr(scene, "video_path", None)
        if vp:
            s["video_path"] = vp
        ap = getattr(scene, "audio_path", None)
        if ap:
            s["audio_path"] = ap


def _latest_match(pattern: str) -> Optional[str]:
    paths = sorted(glob.glob(pattern))
    if not paths:
        return None
    return paths[-1]


def resolve_scene_media_from_disk(scenes, output_base: Optional[str] = None) -> int:
    """
    当剧本里缺少路径或文件已移动时，从 output/images|videos|audio 按场景号匹配文件。
    返回成功补全路径的场景数。
    """
    base = output_base or get_output_dir()
    img_dir = os.path.join(base, "images")
    vid_dir = os.path.join(base, "videos")
    aud_dir = os.path.join(base, "audio")
    fixed = 0

    for scene in scenes:
        n = scene.scene_number
        prefix = f"scene_{n:02d}_"
        changed = False

        ip = getattr(scene, "image_path", None) or ""
        if not ip or not os.path.isfile(ip):
            found = _latest_match(os.path.join(img_dir, prefix + "*.png"))
            if not found:
                found = _latest_match(os.path.join(img_dir, prefix + "*.jpg"))
            if found:
                scene.image_path = found
                changed = True

        vp = getattr(scene, "video_path", None) or ""
        if not vp or not os.path.isfile(vp):
            found = _latest_match(os.path.join(vid_dir, prefix + "*.mp4"))
            if found:
                scene.video_path = found
                changed = True

        ap = getattr(scene, "audio_path", None) or ""
        if not ap or not os.path.isfile(ap):
            found = _latest_match(os.path.join(aud_dir, prefix + "*.mp3"))
            if not found:
                found = _latest_match(os.path.join(aud_dir, prefix + "*.wav"))
            if found:
                scene.audio_path = found
                changed = True

        if changed:
            fixed += 1
    return fixed


def count_scenes_with_visual_media(scenes) -> int:
    """有可用图片或动态视频的分镜数量。"""
    n = 0
    for scene in scenes:
        vp = getattr(scene, "video_path", None) or ""
        ip = getattr(scene, "image_path", None) or ""
        if (vp and os.path.isfile(vp)) or (ip and os.path.isfile(ip)):
            n += 1
    return n


def scenes_missing_visual_media(scenes) -> List[int]:
    """缺少图片与视频的分镜编号列表。"""
    missing = []
    for scene in scenes:
        vp = getattr(scene, "video_path", None) or ""
        ip = getattr(scene, "image_path", None) or ""
        if not ((vp and os.path.isfile(vp)) or (ip and os.path.isfile(ip))):
            missing.append(scene.scene_number)
    return missing
