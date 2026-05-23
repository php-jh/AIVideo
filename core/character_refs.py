"""
角色参考图：用户上传的人物照片，用于生图/图生视频时保持外形一致。
"""
import os
import base64
from typing import List, Optional


def character_has_reference(char: dict) -> bool:
    path = (char.get("reference_image") or "").strip()
    return bool(path and os.path.isfile(path))


def resolve_reference_path(char: dict) -> str:
    """返回可用的参考图绝对路径，不存在则返回空字符串。"""
    path = (char.get("reference_image") or "").strip()
    if not path:
        return ""
    path = os.path.abspath(os.path.expanduser(path))
    return path if os.path.isfile(path) else ""


def scene_character_names(scene) -> List[str]:
    """从分镜中收集出现的角色名（去重，台词角色优先）。"""
    ordered: List[str] = []
    seen = set()

    def add(n: str):
        n = (n or "").strip()
        if n and n not in seen:
            seen.add(n)
            ordered.append(n)

    for d in getattr(scene, "dialogues", None) or []:
        add(d.get("character", ""))
    for c in getattr(scene, "characters", None) or []:
        if isinstance(c, dict):
            add(c.get("name", ""))
        else:
            add(str(c))
    return ordered


def pick_scene_reference_image(scene, script_characters: List[dict]) -> str:
    """
    为本镜选择一张角色参考图：优先本镜有台词/出镜的角色，且已配置 reference_image。
    """
    if not script_characters:
        return ""

    name_to_char = {}
    for ch in script_characters:
        if not isinstance(ch, dict):
            continue
        n = (ch.get("name") or "").strip()
        if n:
            name_to_char[n] = ch

    for name in scene_character_names(scene):
        ch = name_to_char.get(name)
        if ch:
            p = resolve_reference_path(ch)
            if p:
                return p

    for ch in script_characters:
        p = resolve_reference_path(ch)
        if p:
            return p

    return ""


def image_file_to_data_uri(image_path: str, max_edge: int = 1280) -> str:
    """将本地图片转为 API 可用的 data URI（可选缩小以减小请求体）。"""
    from PIL import Image
    import io

    img = Image.open(image_path).convert("RGB")
    w, h = img.size
    if max(w, h) > max_edge:
        scale = max_edge / max(w, h)
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    b64 = base64.standard_b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"
