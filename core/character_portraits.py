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


def _is_elderly_character(ch: dict) -> bool:
    text = " ".join([
        (ch.get("name") or ""),
        (ch.get("description") or ""),
        (ch.get("personality") or ""),
    ])
    if any(k in text for k in ("大爷", "大妈", "奶奶", "爷爷", "阿姨", "叔", "婆", "姥")):
        return True
    try:
        age = int(ch.get("age", 0))
        return age >= 55
    except (TypeError, ValueError):
        pass
    return False


def enrich_character_for_portrait(ch: dict, elderly_daily: bool = False) -> str:
    """
    为定妆照生图补全更贴近真人的外貌描述（不改变剧本原意，只追加摄影向细节）。
    """
    base = (ch.get("description") or "").strip()
    name = (ch.get("name") or "").strip()
    gender = (ch.get("gender") or "").strip().lower()
    parts = [base] if base else []

    if elderly_daily or _is_elderly_character(ch):
        parts.append(
            "real Chinese senior citizen 65-80 years old, authentic rural or small-town look, "
            "natural gray or white hair, visible forehead wrinkles and crow's feet, "
            "sun-touched skin texture, no beauty retouching, no plastic skin"
        )
    else:
        parts.append(
            "real Chinese adult person, natural skin pores and subtle imperfections, "
            "unretouched documentary photograph, no AI doll face"
        )

    if gender == "female":
        parts.append("natural middle-aged or elderly woman, minimal makeup")
    elif gender == "male":
        parts.append("natural middle-aged or elderly man, weathered friendly face")

    if name:
        parts.append(f"casting photo of character {name}")

    return ", ".join(p for p in parts if p)


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
        "CRITICAL: SAME PERSON IN EVERY SHOT - absolutely identical face shape, eyes, nose, mouth, "
        "eyebrows, jawline, skin tone, hairstyle, hair color for each named character. "
        "Do NOT change any facial feature between scenes. "
        "Face must be exactly the same as previous scenes. "
        "Characters: " + "; ".join(lines)
    )


def sync_portraits_from_disk_to_script(script: dict, output_base: str = "") -> int:
    """
    从 output/images/character_portraits/{safe_name}.png 补全 script 中角色的 portrait_path。
    返回成功匹配的角色数。
    """
    if not script or not isinstance(script, dict):
        return 0
    from config import get_output_dir

    base = output_base or get_output_dir()
    portrait_dir = os.path.join(base, "images", "character_portraits")
    if not os.path.isdir(portrait_dir):
        return 0
    matched = 0
    for ch in script.get("characters") or []:
        if not isinstance(ch, dict):
            continue
        name = (ch.get("name") or "").strip()
        if not name:
            continue
        path = os.path.join(portrait_dir, f"{safe_char_filename(name)}.png")
        if not os.path.isfile(path) or os.path.getsize(path) <= 2000:
            continue
        path = os.path.abspath(path)
        ch["portrait_path"] = path
        ref = (ch.get("reference_image") or "").strip()
        if not ref or not os.path.isfile(ref):
            ch["reference_image"] = path
        matched += 1
    return matched
