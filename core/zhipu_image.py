"""
智谱 GLM-Image 文生图（人物肖像 / 分镜）
文档: https://docs.bigmodel.cn/cn/guide/models/image-generation/glm-image
"""
from typing import Optional

from core.http_client import request_with_retry, zhipu_ssl_hint

ZHIPU_IMAGES_GENERATIONS_URL = "https://open.bigmodel.cn/api/paas/v4/images/generations"


def generate_glm_image(
    api_key: str,
    prompt: str,
    model: str = "glm-image",
    size: str = "1056x1568",
    timeout: int = 180,
) -> bytes:
    """
    调用智谱 images/generations，返回图片二进制。

    Args:
        api_key: 智谱 API Key（与清影视频共用 zhipu_api_key）
        prompt: 中文或英文描述（模型最大约 1000 字符）
        model: 默认 glm-image
        size: 如 1056x1568（竖版人像）、1088x1472（竖屏场景）
    """
    key = (api_key or "").strip()
    if not key:
        raise RuntimeError("未填写智谱 API Key，请在 设置 → 智谱 API Key 中填写。")

    text = (prompt or "").strip()
    if not text:
        raise RuntimeError("生图描述为空")
    if len(text) > 1000:
        text = text[:997] + "…"

    payload = {
        "model": (model or "glm-image").strip(),
        "prompt": text,
        "size": (size or "1056x1568").strip(),
    }

    try:
        r = request_with_retry(
            "POST",
            ZHIPU_IMAGES_GENERATIONS_URL,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout,
            max_attempts=5,
        )
    except Exception as e:
        raise RuntimeError(f"智谱 GLM-Image 网络请求失败: {e} {zhipu_ssl_hint()}") from e

    try:
        data = r.json()
    except Exception:
        data = {}

    if r.status_code != 200:
        msg = _extract_error(data) or r.text[:500]
        raise RuntimeError(f"智谱 GLM-Image HTTP {r.status_code}: {msg}")

    url = _extract_image_url(data)
    if not url:
        raise RuntimeError(f"智谱 GLM-Image 未返回图片 URL: {data}")

    try:
        img = request_with_retry("GET", url, timeout=timeout, max_attempts=5)
    except Exception as e:
        raise RuntimeError(f"下载智谱生成图片失败: {e} {zhipu_ssl_hint()}") from e
    if img.status_code != 200 or len(img.content) < 1000:
        raise RuntimeError(f"下载智谱生成图片失败 HTTP {img.status_code}")
    return img.content


def _extract_error(data: dict) -> str:
    if not isinstance(data, dict):
        return ""
    err = data.get("error")
    if isinstance(err, dict):
        return str(err.get("message") or err.get("code") or "")
    return str(data.get("message") or data.get("msg") or "")


def _extract_image_url(data: dict) -> Optional[str]:
    if not isinstance(data, dict):
        return None
    items = data.get("data")
    if isinstance(items, list) and items:
        first = items[0]
        if isinstance(first, dict):
            return (first.get("url") or "").strip() or None
    # 兼容少数嵌套结构
    images = data.get("images")
    if isinstance(images, list) and images:
        u = images[0]
        if isinstance(u, dict):
            return (u.get("url") or "").strip() or None
        if isinstance(u, str):
            return u.strip()
    return None
