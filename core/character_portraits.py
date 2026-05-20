"""
全片角色外形一致：为每个角色维护一张「定妆照」，各分镜基于该图做图生图。
"""
import os
import re
import shutil
from typing import Dict, List, Tuple

from core.character_refs import resolve_reference_path, scene_character_names


def safe_char_filename(name: str) -> str:
    s = re.sub(r"[^\w\u4e00-\u9fff]+", "_", (name or "").strip())
    return s or "character"


def pick_portrait_for_scene(scene, registry: Dict[str, str]) -> Tuple[str, str]:
    """
    为本镜选取定妆照路径。
    优先本镜出镜/有台词的角色；否则不用。
    返回 (portrait_path, character_name)。
    """
    if not registry:
        return "", ""
    for name in scene_character_names(scene):
        path = registry.get(name)
        if path and os.path.isfile(path):
            return path, name
    return "", ""


def build_character_bible(script_characters: List[dict], scene_names: set) -> str:
    """把剧本中的固定外貌写入每镜 prompt，减少换脸。"""
    if not script_characters:
        return ""
    lines = []
    for ch in script_characters:
        if not isinstance(ch, dict):
            continue
        name = (ch.get("name") or "").strip()
        if not name:
            continue
        if scene_names and name not in scene_names:
            continue
        desc = (ch.get("description") or "").strip()
        gender = (ch.get("gender") or "").strip()
        extra = ", ".join(x for x in (desc, gender) if x)
        if extra:
            lines.append(f"{name} ({extra})")
        else:
            lines.append(name)
    if not lines:
        return ""
    return (
        "SAME ACTORS IN EVERY SHOT — identical face and hairstyle for each named character, "
        "do not change identity: " + "; ".join(lines)
    )
