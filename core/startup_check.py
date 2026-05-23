"""
启动环境检查：FFmpeg、必填 API Key 等。
"""
from typing import List

from config import load_config
from core.api_routing import has_siliconflow_key, describe_active_apis
from core.ffmpeg_utils import resolve_ffmpeg_path, get_configured_ffmpeg_path


def check_ffmpeg(config=None) -> bool:
    if get_configured_ffmpeg_path():
        return True
    return resolve_ffmpeg_path(config) is not None


def run_startup_checks() -> List[str]:
    """返回需提示用户的问题列表（空列表表示无阻塞项）。"""
    config = load_config()
    issues: List[str] = []

    ffmpeg = get_configured_ffmpeg_path() or resolve_ffmpeg_path(config)
    if not ffmpeg:
        issues.append(
            "未找到 FFmpeg。\n\n"
            "请任选一种方式：\n"
            "1. 安装 FFmpeg 并加入系统 PATH（推荐）\n"
            "   下载：https://www.gyan.dev/ffmpeg/builds/ 解压后将 bin 目录加入 PATH\n"
            "2. 在「设置 → 视频设置」中指定 ffmpeg.exe 完整路径\n"
            "3. 执行：pip install imageio-ffmpeg（使用内置 FFmpeg）"
        )
    elif not __import__("shutil").which("ffmpeg"):
        # 有内置/自定义路径但不在 PATH：仅记录，不弹窗打扰
        pass

    if not (config.get("deepseek_api_key") or "").strip():
        issues.append(
            "未填写 DeepSeek API Key，无法生成剧本。\n"
            "请在菜单「设置 → API设置」中填写。"
        )

    image_api = (config.get("image_api") or "").strip().lower()
    if image_api == "siliconflow" and not has_siliconflow_key(config):
        issues.append(
            "图片 API 选择了 SiliconFlow，但未填写图片 API Key。\n"
            "生图将失败，请填写 Key 或改用 Pollinations。"
        )

    return issues


def startup_status_line() -> str:
    """状态栏附加说明（与 api_routing 组合使用）。"""
    parts = [describe_active_apis()]
    if not check_ffmpeg():
        parts.append("⚠ 未检测到 FFmpeg")
    else:
        import shutil
        if not shutil.which("ffmpeg") and get_configured_ffmpeg_path():
            parts.append("FFmpeg: 内置/自定义路径")
    return " | ".join(parts)
