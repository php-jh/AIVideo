"""
成片风格预设：口播科普、短剧等模式的推荐配置与检测。
"""
from typing import Dict, Any

TECH_EXPLAINER_NAMES = frozenset({"AI科普口播", "程序员口播"})
ELDERLY_DAILY_NAMES = frozenset({"银发日常", "老头们的快乐生活", "村里老人"})


def is_tech_explainer_style(style: str) -> bool:
    from prompts.story_prompt import resolve_style_key
    key = resolve_style_key(style or "")
    return key in TECH_EXPLAINER_NAMES or (style or "").strip() in TECH_EXPLAINER_NAMES


def tech_explainer_ui_hints() -> str:
    return (
        "【AI科普口播·一镜到底】成片为单镜头口播：固定机位+全程旁白字幕；"
        "请上传老韩半身照作参考图；设置中保持「关闭分镜动态视频」。"
    )


def is_single_take_mode(config: dict) -> bool:
    return bool(config and config.get("single_take"))


def is_elderly_daily_style(style: str) -> bool:
    from prompts.story_prompt import resolve_style_key
    key = resolve_style_key(style or "")
    return key in ELDERLY_DAILY_NAMES or (style or "").strip() in ELDERLY_DAILY_NAMES


def elderly_daily_ui_hints() -> str:
    return (
        "【老头们的快乐生活】真人定妆照加强；建议上传各角色生活照作参考图（最像真人）。"
        "多人对白、音色自动区分；有 SiliconFlow Key 时锁脸效果更好。"
    )


def elderly_daily_config_overlay() -> Dict[str, Any]:
    return {
        "visual_style": "live_action",
        "video_mode": "animated",
        "video_animated_backend": "local",
        "single_take": False,
        "transition_duration": 0,
        "scene_clip_fallback": "local_motion",
        "character_consistency": True,
        "elderly_daily_mode": True,
        "elderly_lip_sync_local": True,
        "include_narration_in_image_prompt": False,
        "include_dialogues_in_image_prompt": True,
        "pollinations_portrait_enhance": True,
        "portrait_realism_boost": True,
        # 若用户已在设置里配置智谱 Key，可在设置中将 image_api 改为 zhipu
    }


def recommended_config_overlay() -> Dict[str, Any]:
    """生成口播片时建议的配置（仅内存合并，不写盘）。"""
    return {
        "visual_style": "live_action",
        "video_mode": "static",
        "single_take": True,
        "transition_duration": 0,
        "scene_clip_fallback": "ken_burns",
        "character_consistency": True,
        "character_ref_image_mode": "blend",
        "include_narration_in_image_prompt": True,
    }


def merge_config_for_style(config: Dict[str, Any], style: str) -> Dict[str, Any]:
    """按风格返回合并后的配置副本（用于单次生成）。"""
    merged = dict(config)
    if is_tech_explainer_style(style):
        merged.update(recommended_config_overlay())
    elif is_elderly_daily_style(style):
        merged.update(elderly_daily_config_overlay())
    return merged
