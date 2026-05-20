"""
根据配置与用户填写的 Key，解析实际调用的生图/图生视频后端，避免「以为在用 SiliconFlow 实际走了 Pollinations/本地动效」。
"""
from config import load_config


def has_siliconflow_key(config=None) -> bool:
    cfg = config or load_config()
    return bool((cfg.get("image_api_key") or "").strip())


def get_effective_image_api(config=None) -> str:
    """
    实际生图 API。
    - 选了 siliconflow → SiliconFlow
    - 选了 deepseek 但填了 image_api_key → 自动走 SiliconFlow 生图（Key 即 SiliconFlow）
  - 选了 deepseek 且无 Key → deepseek（内部会走 Pollinations 免费）
    """
    cfg = config or load_config()
    api = (cfg.get("image_api") or "deepseek").strip().lower()
    if api == "siliconflow":
        return "siliconflow"
    if has_siliconflow_key(cfg) and api in ("deepseek", "none", ""):
        return "siliconflow"
    return api


def get_effective_video_backend(config=None, force_local: bool = False) -> str:
    """
    实际分镜动态视频后端：siliconflow | local
    有 Key 且开启动态分镜时，默认走 siliconflow（除非用户强制 local）。
    """
    if force_local:
        return "local"
    cfg = config or load_config()
    backend = (cfg.get("video_animated_backend") or "local").strip().lower()
    from core.motion_utils import effective_video_mode

    if effective_video_mode(cfg) != "animated":
        return "local"

    if backend == "siliconflow":
        if not has_siliconflow_key(cfg):
            return "local"
        return "siliconflow"

    # 配置为 local，但已填 SiliconFlow Key → 自动改用图生视频
    if has_siliconflow_key(cfg):
        return "siliconflow"
    return "local"


def describe_active_apis(config=None) -> str:
    """供界面状态栏显示当前将调用的服务。"""
    cfg = config or load_config()
    img = get_effective_image_api(cfg)
    vid = get_effective_video_backend(cfg)
    key_ok = has_siliconflow_key(cfg)
    lines = [
        f"生图: {img}" + ("（SiliconFlow API）" if img == "siliconflow" else ""),
        f"分镜视频: {vid}" + ("（SiliconFlow 图生视频）" if vid == "siliconflow" else "（本地 MoviePy 动效）"),
    ]
    if not key_ok and (img == "siliconflow" or vid == "siliconflow"):
        lines.append("⚠ 未填写图片 API Key，SiliconFlow 无法调用")
    elif key_ok:
        lines.append("已检测到 SiliconFlow Key")
    return " | ".join(lines)


def scene_video_needs_regeneration(scene, config=None) -> bool:
    """已有 mp4 但是本地动效文件、而当前应走 SiliconFlow 时，需要重新生成。"""
    cfg = config or load_config()
    want = get_effective_video_backend(cfg)
    vp = getattr(scene, "video_path", None) or ""
    if not vp or not __import__("os").path.isfile(vp):
        return True
    base = __import__("os").path.basename(vp).lower()
    if want == "siliconflow" and "_local_" in base:
        return True
    if want == "local" and "_sf_" in base:
        return True
    return False
