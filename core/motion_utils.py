"""
分镜「角色会动」：判断是否生成动态片段，并在合成前补全缺失的 video_path。
"""
import os
from typing import Callable, List, Optional

from config import load_config, get_output_dir


def is_anime_cartoon(config=None) -> bool:
    cfg = config or load_config()
    return (cfg.get("visual_style") or "live_action").strip().lower() == "anime_cartoon"


def effective_video_mode(config=None) -> str:
    """动漫风格下默认强制开启动态分镜。"""
    cfg = config or load_config()
    if is_anime_cartoon(cfg):
        return "animated"
    return (cfg.get("video_mode") or "static").strip().lower()


def should_generate_motion_clips(config=None) -> bool:
    cfg = config or load_config()
    if effective_video_mode(cfg) == "animated":
        return True
    if is_anime_cartoon(cfg):
        fb = (cfg.get("scene_clip_fallback") or "auto").strip().lower()
        return fb in ("auto", "local_motion")
    return False


def build_dialogue_motion_hints(scene) -> str:
    """根据台词与情绪生成图生视频动作描述（举手、说话等）。"""
    hints = []
    gesture_map = {
        "举手": "raises hand, arm lift gesture",
        "挥手": "waves hand",
        "转身": "turns body",
        "走": "walks",
        "跑": "runs",
        "点头": "nods head",
        "摇头": "shakes head",
        "笑": "smiles, cheerful expression",
        "哭": "crying expression",
        "怒": "angry expression",
        "惊": "surprised expression, eyes widen",
        "说": "speaking, mouth moving for dialogue",
        "喊": "shouts with exaggerated mouth open",
    }
    motion = (getattr(scene, "motion_intent", "") or "").strip()
    if motion:
        extra = []
        for zh, en in gesture_map.items():
            if zh in motion:
                extra.append(en)
        if extra:
            hints.append(", ".join(extra))
        hints.append(motion)

    for d in getattr(scene, "dialogues", None) or []:
        char = (d.get("character") or "character").strip()
        emotion = (d.get("emotion") or "neutral").strip()
        line = (d.get("line") or "").strip()
        hints.append(
            f"{char} speaks with {emotion} emotion, anime lip-flap mouth movement, "
            f"expressive eyes and eyebrows, subtle hand gesture while talking"
            + (f", line: {line[:30]}" if line else "")
        )

    if not hints and (getattr(scene, "narration", "") or "").strip():
        hints.append(
            "character listens then reacts with subtle head nod and expression change, "
            "idle body sway like anime dialogue scene"
        )
    return "; ".join(hints)


def ensure_motion_clips_for_storyboard(
    storyboard,
    script: dict,
    output_base: str,
    on_progress: Optional[Callable] = None,
) -> None:
    """
    为缺少 video_path 的分镜生成动态短视频（SiliconFlow 或本地动效）。
    合成前调用，避免成片只有静图 Ken Burns。
    """
    config = load_config()
    if not should_generate_motion_clips(config):
        return

    scenes = storyboard.scenes
    from core.api_routing import scene_video_needs_regeneration

    need = [
        s for s in scenes
        if scene_video_needs_regeneration(s, config)
    ]
    if not need:
        return

    if not all(getattr(s, "image_path", None) and os.path.isfile(s.image_path or "") for s in need):
        return

    video_dir = os.path.join(output_base, "videos")
    if not os.path.isdir(os.path.dirname(video_dir)):
        video_dir = os.path.join(get_output_dir(), "videos")
    os.makedirs(video_dir, exist_ok=True)

    from core.video_generator import VideoGenerator

    def prog(*args):
        if not on_progress:
            return
        if len(args) == 3:
            on_progress(args[0], args[1], args[2])
        elif len(args) == 1:
            on_progress(0, 0, args[0])

    prog(0, 0, "正在生成分镜动态视频（角色会动）…")
    vg = VideoGenerator()
    story_meta = {
        "title": getattr(storyboard, "title", "") or "",
        "theme": getattr(storyboard, "theme", "") or "",
        "genre": getattr(storyboard, "genre", "") or "",
    }
    vg.generate_all_videos(
        scenes,
        video_dir,
        on_progress=prog,
        story_meta=story_meta,
        script_characters=script.get("characters", []),
    )
    for scene, s in zip(scenes, script.get("scenes", [])):
        vp = getattr(scene, "video_path", None)
        if vp:
            s["video_path"] = vp
