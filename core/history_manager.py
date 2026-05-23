"""
AI短剧生成器 - 历史记录管理
"""
import os
import json
import time
import shutil
from typing import List, Dict, Any, Optional
from logger import get_logger
from config import get_output_dir

logger = get_logger("history_manager")

HISTORY_DIR_NAME = "history"
HISTORY_INDEX_FILE = "history_index.json"


def _get_history_dir() -> str:
    return os.path.join(get_output_dir(), HISTORY_DIR_NAME)


def _get_index_path() -> str:
    return os.path.join(_get_history_dir(), HISTORY_INDEX_FILE)


def _ensure_dir():
    os.makedirs(_get_history_dir(), exist_ok=True)


def _load_index() -> List[Dict[str, Any]]:
    path = _get_index_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"加载历史索引失败: {e}")
        return []


def _save_index(records: List[Dict[str, Any]]):
    _ensure_dir()
    path = _get_index_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"保存历史索引失败: {e}")


def find_latest_final_video(output_dir: Optional[str] = None) -> str:
    """在输出目录查找最新成片（short_drama_*.mp4，非分镜片段）。"""
    out = output_dir or get_output_dir()
    if not os.path.isdir(out):
        return ""
    candidates = []
    for fname in os.listdir(out):
        if fname.startswith("short_drama_") and fname.endswith(".mp4"):
            path = os.path.join(out, fname)
            if os.path.isfile(path):
                candidates.append((os.path.getmtime(path), path))
    if not candidates:
        return ""
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def add_record(
    script: Dict[str, Any],
    video_path: Optional[str] = None,
    style: str = "",
    user_input: str = "",
) -> Dict[str, Any]:
    """生成完成后调用，保存一条历史记录并返回该记录。"""
    _ensure_dir()
    record_id = str(int(time.time() * 1000))
    title = script.get("title", "未命名剧本")
    scenes = script.get("scenes", [])
    scene_count = len(scenes)

    thumbnail_path = None
    images_dir = os.path.join(get_output_dir(), "images")
    for scene in scenes:
        img = scene.get("image_path", "")
        if img and os.path.isfile(img):
            thumbnail_path = img
            break
    if not thumbnail_path and os.path.isdir(images_dir):
        for fname in sorted(os.listdir(images_dir)):
            if fname.startswith("scene_") and fname.endswith(".png"):
                thumbnail_path = os.path.join(images_dir, fname)
                break

    script_filename = f"script_{record_id}.json"
    script_path = os.path.join(_get_history_dir(), script_filename)
    try:
        with open(script_path, "w", encoding="utf-8") as f:
            json.dump(script, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"保存历史剧本失败: {e}")
        script_path = None

    characters = script.get("characters", [])
    character_names = []
    for c in characters:
        name = c.get("name", "") if isinstance(c, dict) else str(c)
        if name:
            character_names.append(name)

    record = {
        "id": record_id,
        "title": title,
        "style": style,
        "user_input": user_input,
        "scene_count": scene_count,
        "characters": character_names,
        "video_path": video_path or "",
        "script_path": script_path or "",
        "thumbnail_path": thumbnail_path or "",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "timestamp": time.time(),
    }

    records = _load_index()
    records.insert(0, record)
    _save_index(records)
    logger.info(f"历史记录已保存: {title} (id={record_id})")
    return record


def list_records() -> List[Dict[str, Any]]:
    return _load_index()


def get_record(record_id: str) -> Optional[Dict[str, Any]]:
    for r in _load_index():
        if r.get("id") == record_id:
            return r
    return None


def load_script_by_id(record_id: str) -> Optional[Dict[str, Any]]:
    record = get_record(record_id)
    if not record:
        return None
    script_path = record.get("script_path", "")
    if not script_path or not os.path.isfile(script_path):
        logger.warning(f"历史剧本文件不存在: {script_path}")
        return None
    try:
        with open(script_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"加载历史剧本失败: {e}")
        return None


def delete_record(record_id: str) -> bool:
    records = _load_index()
    target = None
    new_records = []
    for r in records:
        if r.get("id") == record_id:
            target = r
        else:
            new_records.append(r)
    if not target:
        return False

    script_path = target.get("script_path", "")
    if script_path and os.path.isfile(script_path):
        try:
            os.remove(script_path)
        except Exception as e:
            logger.warning(f"删除历史剧本文件失败: {e}")

    _save_index(new_records)
    logger.info(f"历史记录已删除: {target.get('title')} (id={record_id})")
    return True


def clear_all() -> int:
    records = _load_index()
    count = len(records)
    for r in records:
        script_path = r.get("script_path", "")
        if script_path and os.path.isfile(script_path):
            try:
                os.remove(script_path)
            except Exception:
                pass
    _save_index([])
    logger.info(f"已清空全部 {count} 条历史记录")
    return count
