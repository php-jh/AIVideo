"""
AI科普口播：一镜到底剧本归一、合成辅助。
"""
import copy
import re
from typing import Dict, List, Tuple

SINGLE_TAKE_VISUAL = (
    "竖屏9:16固定机位中景，同一办公室场景一镜到底："
    "亚裔男性程序员老韩穿休闲衬衫戴眼镜坐在书桌前对镜头说话，"
    "背后显示器显示模糊代码界面，柔和自然光，全程同一构图不跳场景、不切镜头"
)


def _scene_text_parts(scene: dict) -> List[str]:
    parts: List[str] = []
    n = (scene.get("narration") or "").strip()
    if n:
        parts.append(n)
    for d in scene.get("dialogues") or []:
        if not isinstance(d, dict):
            continue
        line = (d.get("line") or "").strip()
        if not line:
            continue
        ch = (d.get("character") or "").strip()
        parts.append(f"{ch}：{line}" if ch else line)
    return parts


def normalize_tech_explainer_script(script: dict) -> dict:
    """
    将多镜口播稿合并为 1 镜「一镜到底」，旁白串联，画面描述统一为固定口播构图。
    """
    if not script or not isinstance(script, dict):
        return script

    out = copy.deepcopy(script)
    scenes = out.get("scenes") or []
    if not scenes:
        return out

    all_parts: List[str] = []
    for s in scenes:
        if isinstance(s, dict):
            all_parts.extend(_scene_text_parts(s))

    narration = "\n".join(all_parts).strip()
    if not narration and len(scenes) == 1:
        return out

    first = copy.deepcopy(scenes[0]) if isinstance(scenes[0], dict) else {}
    total_dur = 0.0
    for s in scenes:
        if isinstance(s, dict):
            try:
                total_dur += float(s.get("duration") or 5)
            except (TypeError, ValueError):
                total_dur += 5.0
    total_dur = max(total_dur, 45.0)
    # 按字数估算口播时长（约 4 字/秒）
    est = max(45.0, len(narration.replace("\n", "")) / 4.0)
    total_dur = max(total_dur, min(est, 120.0))

    merged = {
        **first,
        "scene_number": 1,
        "narration": narration,
        "dialogues": [],
        "duration": round(total_dur, 1),
        "story_beat": "一镜到底完整口播",
        "continuity_from_previous": "开场：老韩对镜头，固定机位",
        "leads_to_next": "收束：关注引导",
        "visual_description": SINGLE_TAKE_VISUAL,
        "motion_intent": "对镜头口播，轻微手势与点头，无切镜",
        "location": first.get("location") or "程序员办公室",
    }
    out["scenes"] = [merged]
    out["total_duration"] = merged["duration"]
    genre = (out.get("genre") or "").strip()
    if not genre or "口播" not in genre:
        out["genre"] = "AI科技口播"
    return out


def split_narration_for_subtitles(text: str, total_duration: float) -> List[Tuple[str, float]]:
    """按句号等切分旁白，按时长比例分配字幕段。"""
    text = (text or "").strip()
    if not text or total_duration <= 0:
        return []
    parts = [p.strip() for p in re.split(r"(?<=[。！？!?；;])", text) if p.strip()]
    if not parts:
        return [(text, total_duration)]
    if len(parts) == 1:
        return [(text, total_duration)]
    total_chars = sum(len(p) for p in parts) or 1
    segments: List[Tuple[str, float]] = []
    for p in parts:
        dur = max(0.8, total_duration * len(p) / total_chars)
        segments.append((p, dur))
    return segments
