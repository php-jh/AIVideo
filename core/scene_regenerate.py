"""
单镜媒体清理：强制重生图片/配音/动效前删除旧文件。
"""
import glob
import os


def clear_scene_images(images_dir: str, scene_number: int) -> None:
    pattern = os.path.join(images_dir, f"scene_{scene_number:02d}_*.png")
    for path in glob.glob(pattern):
        try:
            os.remove(path)
        except OSError:
            pass


def clear_scene_audio(audio_dir: str, scene_number: int) -> None:
    sn = f"{scene_number:02d}"
    patterns = [
        os.path.join(audio_dir, f"audio_scene_{sn}.mp3"),
        os.path.join(audio_dir, f"temp_dialogue_{scene_number}_*.mp3"),
        os.path.join(audio_dir, f"temp_narration_{scene_number}.mp3"),
    ]
    for pattern in patterns:
        for path in glob.glob(pattern):
            try:
                os.remove(path)
            except OSError:
                pass


def clear_scene_videos(videos_dir: str, scene_number: int) -> None:
    pattern = os.path.join(videos_dir, f"scene_{scene_number:02d}_*.mp4")
    for path in glob.glob(pattern):
        try:
            os.remove(path)
        except OSError:
            pass


def clear_scene_media_keys(script_scene: dict, keys=None) -> None:
    """清空剧本中该镜的媒体路径字段。"""
    if keys is None:
        keys = ("image_path", "video_path", "audio_path")
    for key in keys:
        script_scene.pop(key, None)
