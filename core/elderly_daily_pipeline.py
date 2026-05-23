"""
银发日常 / 「老头们的快乐生活」类抖音：剧本补强、自动分配不同音色。
"""
from typing import Dict, List

# 老人角色默认音色（每人不同，避免听起来像同一个人）
ELDERLY_MALE_VOICES = [
    "zh-CN-YunzeNeural",   # 沉稳
    "zh-CN-YunjianNeural", # 成熟
    "zh-CN-YunyangNeural", # 播报感
    "zh-CN-YunxiNeural",   # 年轻男（可作提问年轻人）
]
ELDERLY_FEMALE_VOICES = [
    "zh-CN-XiaomoNeural",
    "zh-CN-XiaochenNeural",
    "zh-CN-XiaoyiNeural",
    "zh-CN-XiaohanNeural",
]


def _dialogue_motion_hint(dialogues: List[dict]) -> str:
    parts = []
    for d in dialogues or []:
        if not isinstance(d, dict):
            continue
        name = (d.get("character") or "").strip()
        emo = (d.get("emotion") or "自然").strip()
        line = (d.get("line") or "").strip()[:24]
        if name:
            parts.append(f"{name}{emo}地说「{line}…」时带手势与表情")
    return "；".join(parts) if parts else ""


def assign_elderly_character_voices(script: dict) -> None:
    """为未指定音色的角色自动分配不同 Edge TTS 音色。"""
    chars = script.get("characters") or []
    male_i, female_i = 0, 0
    for ch in chars:
        if not isinstance(ch, dict):
            continue
        name = (ch.get("name") or "").strip()
        if not name:
            continue
        if (ch.get("tts_voice") or "").strip():
            continue
        g = (ch.get("gender") or "male").strip().lower()
        if g == "female":
            ch["tts_voice"] = ELDERLY_FEMALE_VOICES[female_i % len(ELDERLY_FEMALE_VOICES)]
            female_i += 1
        else:
            ch["tts_voice"] = ELDERLY_MALE_VOICES[male_i % len(ELDERLY_MALE_VOICES)]
            male_i += 1


def strengthen_elderly_daily_script(script: dict) -> dict:
    """口播改对白为主；补全 motion_intent；限制镜数感（不合并镜头）。"""
    if not script or not isinstance(script, dict):
        return script

    scenes = script.get("scenes") or []
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        dialogues = [d for d in (scene.get("dialogues") or []) if isinstance(d, dict)]
        has_lines = any((d.get("line") or "").strip() for d in dialogues)
        if has_lines and (scene.get("narration") or "").strip():
            # 有对白时旁白尽量缩短，避免「画外音盖过对话」
            narr = (scene.get("narration") or "").strip()
            if len(narr) > 30:
                scene["narration"] = ""

        motion = (scene.get("motion_intent") or "").strip()
        hint = _dialogue_motion_hint(dialogues)
        if hint:
            lip = "；".join(
                f"{(d.get('character') or '').strip()}说话时嘴型张合、表情配合"
                for d in dialogues
                if (d.get("character") or "").strip()
            )
            if lip and "嘴" not in motion:
                hint = f"{hint}；{lip}"
            if not motion:
                scene["motion_intent"] = hint
            elif hint[:8] not in motion:
                scene["motion_intent"] = f"{motion}；{hint}"

        if not (scene.get("camera_movement") or "").strip():
            scene["camera_movement"] = "固定机位或极轻微横移，纪录片跟拍感，禁止花哨转场描述"

    chars = script.get("characters") or []
    if len(chars) < 3:
        defaults = [
            {
                "name": "王大爷", "gender": "male", "age": 72,
                "description": "72岁中国农村大爷，花白短发，深纹额头，藏青对襟褂，肤色偏深，笑容憨厚，真人纪录片质感",
                "personality": "爱抬杠、一本正经胡说",
            },
            {
                "name": "李大妈", "gender": "female", "age": 68,
                "description": "68岁中国农村大妈，烫卷花白短发，碎花围裙，眼角鱼尾纹明显，嗓门亮，无浓妆",
                "personality": "吐槽担当、反应夸张",
            },
            {
                "name": "张叔", "gender": "male", "age": 70,
                "description": "70岁瘦高农村大叔，草帽，灰色开衫，法令纹深，爱比划，朴素真人相",
                "personality": "慢半拍、常接错话",
            },
        ]
        existing = {(c.get("name") or "").strip() for c in chars if isinstance(c, dict)}
        for d in defaults:
            if d["name"] not in existing and len(chars) < 5:
                chars.append(d)
        script["characters"] = chars

    assign_elderly_character_voices(script)

    # 对白里补上 gender，方便 TTS 选音色
    by_name = {
        (c.get("name") or "").strip(): c
        for c in (script.get("characters") or [])
        if isinstance(c, dict)
    }
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        for d in scene.get("dialogues") or []:
            if not isinstance(d, dict):
                continue
            n = (d.get("character") or "").strip()
            ch = by_name.get(n)
            if ch and not d.get("gender"):
                d["gender"] = ch.get("gender", "male")

    return script
