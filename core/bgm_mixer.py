"""
成片背景音乐混音：循环 BGM 并压低音量，与配音叠加。
"""
import os

from logger import get_logger

logger = get_logger("bgm_mixer")


def apply_bgm_to_clip(final_clip, bgm_path: str, volume: float = 0.15):
    """
    为已拼接的成片叠加背景音乐。

    Args:
        final_clip: MoviePy VideoClip（可含配音轨）
        bgm_path: 本地音频文件（mp3/wav/m4a 等）
        volume: BGM 相对音量（0~1，推荐 0.1~0.25）

    Returns:
        带 BGM 的 VideoClip（失败时返回原 clip）
    """
    if not bgm_path or not os.path.isfile(bgm_path):
        return final_clip

    try:
        from moviepy.editor import AudioFileClip, CompositeAudioClip, concatenate_audioclips
    except ImportError as e:
        logger.warning(f"MoviePy 不可用，跳过 BGM: {e}")
        return final_clip

    vol = max(0.0, min(1.0, float(volume)))
    target_dur = float(final_clip.duration)

    try:
        bgm = AudioFileClip(bgm_path)
        if bgm.duration <= 0:
            bgm.close()
            raise ValueError("BGM 时长为 0")

        if bgm.duration < target_dur:
            n = int(target_dur / bgm.duration) + 1
            looped = concatenate_audioclips([bgm] * n)
            bgm.close()
            bgm = looped

        bgm = bgm.subclip(0, target_dur).volumex(vol)

        if final_clip.audio is not None:
            return final_clip.set_audio(CompositeAudioClip([final_clip.audio, bgm]))
        return final_clip.set_audio(bgm)
    except Exception as e:
        logger.warning(f"BGM 混音失败，使用原音轨: {e}")
        return final_clip
