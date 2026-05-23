"""
FFmpeg 路径解析：系统 PATH、用户配置、imageio-ffmpeg 内置包。
"""
import os
import shutil
from typing import Optional

from logger import get_logger

logger = get_logger("ffmpeg_utils")

_CONFIGURED_PATH: Optional[str] = None


def resolve_ffmpeg_path(config: Optional[dict] = None) -> Optional[str]:
    """按优先级查找可用的 ffmpeg 可执行文件。"""
    if config is None:
        from config import load_config
        config = load_config()

    custom = (config.get("ffmpeg_path") or "").strip()
    if custom:
        custom = os.path.abspath(os.path.expanduser(custom))
        if os.path.isfile(custom):
            return custom

    on_path = shutil.which("ffmpeg")
    if on_path:
        return os.path.abspath(on_path)

    try:
        import imageio_ffmpeg
        bundled = imageio_ffmpeg.get_ffmpeg_exe()
        if bundled and os.path.isfile(bundled):
            return os.path.abspath(bundled)
    except Exception as e:
        logger.debug(f"imageio_ffmpeg 不可用: {e}")

    for candidate in (
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "ffmpeg", "bin", "ffmpeg.exe"),
    ):
        if candidate and os.path.isfile(candidate):
            return os.path.abspath(candidate)

    return None


def get_configured_ffmpeg_path() -> Optional[str]:
    return _CONFIGURED_PATH


def configure_ffmpeg(config: Optional[dict] = None) -> str:
    """
    将 FFmpeg 路径写入环境变量与 MoviePy，应在应用启动时调用一次。

    Returns:
        实际使用的 ffmpeg 路径；找不到则返回空字符串。
    """
    global _CONFIGURED_PATH
    path = resolve_ffmpeg_path(config)
    _CONFIGURED_PATH = path

    if not path:
        logger.warning("未找到 FFmpeg，视频合成与部分配音合并将失败")
        return ""

    os.environ["IMAGEIO_FFMPEG_EXE"] = path
    try:
        from moviepy.config import change_settings
        change_settings({"FFMPEG_BINARY": path})
    except Exception as e:
        logger.warning(f"设置 MoviePy FFMPEG_BINARY 失败: {e}")

    logger.info(f"已配置 FFmpeg: {path}")
    return path
