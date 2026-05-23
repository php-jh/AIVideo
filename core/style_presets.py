"""
成片风格预设：口播科普、短剧等模式的推荐配置与检测。
"""
from typing import Dict, Any

TECH_EXPLAINER_NAMES = frozenset({"AI科普口播", "程序员口播"})


def is_tech_explainer_style(style: str) -> bool:
    from prompts.story_prompt import resolve_style_key
    key = resolve_style_key(style or "")
    return key in TECH_EXPLAINER_NAMES or (style or "").strip() in TECH_EXPLAINER_NAMES


def tech_explainer_ui_hints() -> str:
    return (
        "【AI科普口播模式】推荐：设置→真人纪实、关闭分镜动态视频；"
        "主讲可在「角色参考图」绑定音色；成片以旁白+字幕为主。"
    )


def recommended_config_overlay() -> Dict[str, Any]:
    """生成口播片时建议的配置（仅内存合并，不写盘）。"""
    return {
        "visual_style": "live_action",
        "video_mode": "static",
        "scene_clip_fallback": "ken_burns",
        "character_consistency": True,
    }


def merge_config_for_style(config: Dict[str, Any], style: str) -> Dict[str, Any]:
    """按风格返回合并后的配置副本（用于单次生成）。"""
    merged = dict(config)
    if is_tech_explainer_style(style):
        merged.update(recommended_config_overlay())
    return merged
