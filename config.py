"""
AI短剧生成器 - 配置文件
"""
import os
import json
from typing import Any, Dict, Optional
from logger import get_logger

logger = get_logger("config")

# 配置文件路径
CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".ai-short-drama")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

# 环境变量前缀
ENV_PREFIX = "AI_SHORT_DRAMA_"

# 默认配置
DEFAULT_CONFIG = {
    "deepseek_api_key": "",
    "deepseek_base_url": "https://api.deepseek.com",
    "deepseek_model": "deepseek-chat",
    "image_api": "siliconflow",  # deepseek / siliconflow / pollinations / dall-e / none
    "image_api_key": "",  # SiliconFlow / DALL-E 等生图 Key（选 siliconflow 时填 SiliconFlow）
    # 文生图 POST /v1/images/generations，模型以控制台「to-image」为准（见官方文档）
    # https://docs.siliconflow.cn/cn/api-reference/images/images-generations
    "siliconflow_image_model": "Kwai-Kolors/Kolors",
    # Kolors 竖屏推荐 720x1280；Qwen-Image 等见文档中 image_size 枚举
    "siliconflow_image_size": "720x1280",
    "siliconflow_image_steps": 28,
    "siliconflow_image_guidance": 7.0,
    # 两次 SiliconFlow 生图请求之间的间隔（秒），避免 HTTP 429 / IPM 限流
    "siliconflow_request_interval_sec": 15,
    # 遇到 429 时最多自动重试次数（每次退避等待更久）
    "siliconflow_rate_limit_retries": 8,
    # Pollinations 文生图模型：flux 细节与人体更稳；turbo 更快但易有 AI 感
    "pollinations_model": "flux",
    # 生图后缩放到视频分辨率：letterbox 完整保留画面（推荐，减少裁切错位）；crop 铺满但可能切头切脸
    "image_fit_mode": "letterbox",
    # 角色参考图：blend=参考图+分镜描述 AI 生图（推荐）；direct=直接用参考图作分镜图再图生视频
    "character_ref_image_mode": "blend",
    # 图生视频首帧：scene_keyframe=用分镜图（默认）；reference=直接用角色参考图（更像本人、场景变化小）
    "character_ref_video_first_frame": "scene_keyframe",
    # 全片角色换脸抑制：为每角色生成/锁定定妆照，分镜图生图时复用（推荐 SiliconFlow）
    "character_consistency": True,
    # 分镜图生图时相对定妆照的变化幅度，越小越像同一人（0.15~0.40）
    # 推荐值：0.20-0.25（强锁脸）
    "character_scene_img2img_strength": 0.22,
    "tts_voice_narrator": "zh-CN-YunxiNeural",  # 旁白音色
    "tts_voice_male": "zh-CN-YunxiNeural",  # 男角色音色
    "tts_voice_female": "zh-CN-XiaochenNeural",  # 女角色音色（温柔）
    "video_width": 1080,
    "video_height": 1920,
    "video_fps": 24,
    # 画面风格：live_action 真人纪实（默认）；anime_cartoon 2D 动漫（角色会动、对话镜头）
    "visual_style": "live_action",
    # 合成时无 video_path：auto 时动漫用本地动效 MP4，真人用 Ken Burns
    "scene_clip_fallback": "auto",
    # animated：每镜生成动态短视频（动漫风格下自动视为开启）
    "video_mode": "animated",
    # 动态片段：siliconflow=云端图生视频（举手/说话等更像动画）；zhipu=智谱清影；local=本机轻量动效（无 GPU 可备用）
    "video_animated_backend": "zhipu",
    # SiliconFlow /v1/video/submit 图生视频模型（以控制台为准）
    "siliconflow_video_model": "Wan-AI/Wan2.2-I2V-A14B",
    # 智谱清影配置
    "zhipu_api_key": "",
    "zhipu_video_model": "cogvideox-3",
    "zhipu_video_size": "720x1280",
    "zhipu_video_fps": 30,
    "zhipu_video_duration": 5,
    "transition_duration": 0.5,
    # 背景音乐：合成时与配音混音（需本地音频文件）
    "bgm_enabled": False,
    "bgm_path": "",
    "bgm_volume": 0.18,
    # 可选：ffmpeg.exe 完整路径（未加入 PATH 时填写；留空则自动用 imageio-ffmpeg 内置）
    "ffmpeg_path": "",
    "default_story_style": "短剧",
    "output_dir": "",
}

# 配置验证规则
CONFIG_VALIDATORS = {
    "video_width": lambda x: isinstance(x, int) and x > 0,
    "video_height": lambda x: isinstance(x, int) and x > 0,
    "video_fps": lambda x: isinstance(x, int) and 1 <= x <= 120,
    "siliconflow_image_steps": lambda x: isinstance(x, int) and 1 <= x <= 100,
    "siliconflow_image_guidance": lambda x: isinstance(x, (int, float)) and 0 <= x <= 20,
    "transition_duration": lambda x: isinstance(x, (int, float)) and 0 <= x <= 5,
    "image_fit_mode": lambda x: x in ("letterbox", "crop"),
    "visual_style": lambda x: x in ("live_action", "anime_cartoon"),
    "video_mode": lambda x: x in ("static", "animated"),
    "video_animated_backend": lambda x: x in ("siliconflow", "zhipu", "local"),
    "zhipu_video_model": lambda x: x in ("cogvideox-flash", "cogvideox-3", "cogvideox-2", "vidu2-image", "viduq1-image"),
    "zhipu_video_fps": lambda x: x in (30, 60),
    "zhipu_video_duration": lambda x: x in (5, 10),
    "bgm_volume": lambda x: isinstance(x, (int, float)) and 0 <= x <= 1,
}


def _load_from_env(config: Dict[str, Any]) -> Dict[str, Any]:
    """从环境变量加载配置"""
    for key in config:
        env_key = ENV_PREFIX + key.upper()
        env_value = os.environ.get(env_key)
        if env_value is not None:
            # 根据默认值类型转换环境变量
            default_value = config[key]
            if isinstance(default_value, bool):
                config[key] = env_value.lower() in ("true", "1", "yes")
            elif isinstance(default_value, int):
                try:
                    config[key] = int(env_value)
                except ValueError:
                    logger.warning(f"环境变量 {env_key} 不是有效整数: {env_value}")
            elif isinstance(default_value, float):
                try:
                    config[key] = float(env_value)
                except ValueError:
                    logger.warning(f"环境变量 {env_key} 不是有效浮点数: {env_value}")
            else:
                config[key] = env_value
            logger.debug(f"从环境变量加载配置: {key}")
    return config


def _validate_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """验证配置值"""
    for key, validator in CONFIG_VALIDATORS.items():
        if key in config and not validator(config[key]):
            logger.warning(f"配置项 {key} 值无效: {config[key]}，使用默认值")
            config[key] = DEFAULT_CONFIG[key]
    return config


def load_config() -> Dict[str, Any]:
    """加载配置"""
    try:
        config = DEFAULT_CONFIG.copy()
        
        # 从文件加载
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                file_config = json.load(f)
                config.update(file_config)
                logger.info(f"配置已从 {CONFIG_FILE} 加载")
        
        # 从环境变量加载（优先级更高）
        config = _load_from_env(config)
        
        # 验证配置
        config = _validate_config(config)
        
        return config
    except Exception as e:
        logger.error(f"加载配置失败: {e}")
        return DEFAULT_CONFIG.copy()


def save_config(config: Dict[str, Any]) -> None:
    """保存配置"""
    try:
        # 验证配置
        config = _validate_config(config)
        
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        logger.info(f"配置已保存到 {CONFIG_FILE}")
    except Exception as e:
        logger.error(f"保存配置失败: {e}")
        raise


def get_output_dir() -> str:
    """获取输出目录"""
    config = load_config()
    if config.get("output_dir"):
        return config["output_dir"]
    # 默认输出到项目的output目录
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output")


def get_config_value(key: str, default: Any = None) -> Any:
    """获取单个配置值"""
    config = load_config()
    return config.get(key, default)
