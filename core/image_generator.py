"""
AI短剧生成器 - 分镜图片生成模块
根据分镜描述调用 AI 生图 API 生成图片
支持：Pollinations（免费）、DeepSeek 扩写+生图、SiliconFlow 生图、DALL-E

SiliconFlow 文生图接口说明：
https://docs.siliconflow.cn/cn/api-reference/images/images-generations
产品简介与文档索引：https://docs.siliconflow.cn/cn/userguide/introduction · https://docs.siliconflow.cn/llms.txt
"""
import os
import glob
import time
import hashlib
import base64
import requests
from openai import OpenAI
from PIL import Image
from config import load_config
from logger import get_logger
from core.storyboard import StoryboardScene
from core.character_refs import (
    pick_scene_reference_image,
    image_file_to_data_uri,
    scene_character_names,
    resolve_reference_path,
)
from core.character_portraits import (
    safe_char_filename,
    pick_portrait_for_scene,
    build_character_bible,
    enrich_character_for_portrait,
    _is_elderly_character,
)
from core.api_routing import get_effective_image_api, has_siliconflow_key
from core.zhipu_image import generate_glm_image

logger = get_logger("image_generator")

# 扩写后的英文 prompt 末尾追加（Pollinations / 部分后端会用到）
_IMAGE_PROMPT_REALISM_SUFFIX = (
    ", hyperrealistic photograph, shot on Sony A7III with 85mm f/1.4 lens, "
    "natural skin texture with visible pores and fine wrinkles, real human imperfections, "
    "correct human anatomy, exactly five fingers per visible hand, "
    "symmetrical eyes with natural catchlights, coherent jawline, "
    "level horizon, correct linear perspective, single coherent scene, "
    "natural ambient occlusion, objects rest on surfaces with consistent contact shadows, "
    "subsurface skin scattering, realistic hair strands, fabric weave visible, "
    "no beauty filter, no airbrushing, no plastic skin, no CGI look, no anime, no cartoon, "
    "documentary-style candid shot, available light photography, "
    "real human body proportions, natural body shape, realistic posture"
)

# 定妆照专用：比场景后缀更强调证件照/选角照级真人质感
_PORTRAIT_REALISM_SUFFIX = (
    ", ultra photorealistic headshot, real human photographed not illustrated, "
    "Canon EOS R5 85mm f/1.8 portrait lens, shallow depth of field, "
    "individual skin pores visible, fine wrinkles and age lines, natural asymmetry, "
    "real iris detail and moisture in eyes, individual eyebrow hairs, "
    "authentic Chinese face, unretouched RAW photo look, "
    "NO anime, NO cartoon, NO 3D render, NO doll, NO wax figure, NO beauty app filter, "
    "NO plastic skin, NO airbrushed porcelain skin, NO CGI, NO illustration"
)

_IMAGE_PROMPT_ANIME_SUFFIX = (
    ", high quality 2D anime TV key visual, clean lineart, soft cel shading, "
    "consistent character model, on-model face, expressive eyes and mouth for dialogue scenes, "
    "readable simple background, vertical 9:16 composition, studio anime lighting, no 3D CGI doll"
)


class ImageGenerator:
    """分镜图片生成器"""

    def __init__(self, config=None):
        self.config = config or load_config()
        self.client = None
        self._last_sf_request_ts = 0.0
        # 画面内容 hash -> 已生成图片路径（同批分镜去重，避免重复调 API）
        self._content_hash_cache: dict = {}

    @staticmethod
    def _compute_scene_content_hash(
        scene: StoryboardScene,
        ref_path: str = "",
        portrait_char: str = "",
        config: dict = None,
    ) -> str:
        cfg = config or load_config()
        hash_src = "|".join([
            scene.visual_description or "",
            getattr(scene, "visual_anchor", "") or "",
            getattr(scene, "continuity_from_previous", "") or "",
            getattr(scene, "leads_to_next", "") or "",
            getattr(scene, "motion_intent", "") or "",
            cfg.get("visual_style", "") or "",
            ref_path or "",
            portrait_char or "",
        ])
        return hashlib.md5(hash_src.encode("utf-8")).hexdigest()[:8]

    @staticmethod
    def _is_valid_image_file(path: str, min_bytes: int = 2000) -> bool:
        return bool(path) and os.path.isfile(path) and os.path.getsize(path) >= min_bytes

    def _index_images_in_dir(self, output_dir: str) -> dict:
        """扫描 output/images 下已有分镜图，按内容 hash 建立索引。"""
        cache: dict = {}
        if not os.path.isdir(output_dir):
            return cache
        for p in glob.glob(os.path.join(output_dir, "scene_*_*.png")):
            base = os.path.basename(p)
            if not base.endswith(".png"):
                continue
            h = base.rsplit("_", 1)[-1].replace(".png", "")
            if len(h) != 8:
                continue
            if not self._is_valid_image_file(p):
                continue
            prev = cache.get(h)
            if not prev or os.path.getsize(p) > os.path.getsize(prev):
                cache[h] = p
        return cache

    def _find_image_by_content_hash(self, output_dir: str, content_hash: str) -> str:
        cached = self._content_hash_cache.get(content_hash)
        if self._is_valid_image_file(cached):
            return cached
        for p in glob.glob(os.path.join(output_dir, f"*_{content_hash}.png")):
            if self._is_valid_image_file(p):
                self._content_hash_cache[content_hash] = p
                return p
        return ""

    def _reuse_scene_image(
        self,
        source: str,
        dest: str,
        scene: StoryboardScene,
        content_hash: str,
        on_progress=None,
        reuse_label: str = "相同画面",
    ) -> str:
        """复用已有图片：复制到当前场景文件名（不调用生图 API）。"""
        from shutil import copyfile

        os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
        if os.path.abspath(source) != os.path.abspath(dest):
            copyfile(source, dest)
        scene.image_path = dest
        self._content_hash_cache[content_hash] = source
        if on_progress:
            src_scene = os.path.basename(source)
            on_progress(
                f"场景 {scene.scene_number} {reuse_label}，复用 {src_scene}（未调用生图 API）"
            )
        return dest

    def _sf_request_interval(self) -> float:
        try:
            return max(0.0, float(self.config.get("siliconflow_request_interval_sec", 15)))
        except (TypeError, ValueError):
            return 15.0

    def _sf_rate_limit_retries(self) -> int:
        try:
            return max(1, int(self.config.get("siliconflow_rate_limit_retries", 8)))
        except (TypeError, ValueError):
            return 8

    def _throttle_siliconflow(self, on_progress=None) -> None:
        """相邻 SiliconFlow 请求之间强制间隔，降低 IPM 限流概率。"""
        interval = self._sf_request_interval()
        if interval <= 0:
            return
        elapsed = time.time() - self._last_sf_request_ts
        if elapsed < interval:
            wait = interval - elapsed
            msg = f"SiliconFlow 限流保护：等待 {wait:.0f} 秒后继续…"
            if on_progress:
                on_progress(msg)
            else:
                print(f"[SiliconFlow] {msg}")
            time.sleep(wait)

    def _mark_sf_request(self) -> None:
        self._last_sf_request_ts = time.time()

    @staticmethod
    def _is_sf_rate_limit(response: requests.Response, data: dict = None) -> bool:
        if response is not None and response.status_code == 429:
            return True
        if not isinstance(data, dict):
            return False
        code = data.get("code")
        msg = str(data.get("message") or "").lower()
        if code in (50604, 429):
            return True
        return "rate limit" in msg or "ipm limit" in msg

    def _get_client(self):
        """获取OpenAI兼容客户端"""
        if self.client is None:
            api_key = self.config.get("deepseek_api_key", "")
            base_url = self.config.get("deepseek_base_url", "https://api.deepseek.com")
            if not api_key:
                raise ValueError("请先在设置中配置 DeepSeek API Key")
            self.client = OpenAI(
                api_key=api_key,
                base_url=base_url,
            )
        return self.client

    def _visual_style_anime(self) -> bool:
        return (self.config.get("visual_style") or "live_action").strip().lower() == "anime_cartoon"

    def generate_scene_image(self, scene: StoryboardScene,
                             output_dir: str,
                             on_progress=None,
                             script_characters=None,
                             portrait_registry=None,
                             force_regenerate: bool = False) -> str:
        """
        为单个场景生成图片

        Args:
            scene: 分镜场景
            output_dir: 输出目录
            on_progress: 进度回调
            force_regenerate: 跳过磁盘旧图 hash 匹配，强制调用 API

        Returns:
            生成的图片文件路径
        """
        self.config = load_config()
        os.makedirs(output_dir, exist_ok=True)

        script_chars = script_characters or []
        use_consistency = bool(self.config.get("character_consistency", True))
        registry = portrait_registry or {}

        portrait_path, portrait_char = "", ""
        if use_consistency and registry:
            portrait_path, portrait_char = pick_portrait_for_scene(scene, registry)

        ref_path = portrait_path or pick_scene_reference_image(scene, script_chars)

        content_hash = self._compute_scene_content_hash(
            scene, ref_path, portrait_char, self.config
        )
        filename = f"scene_{scene.scene_number:02d}_{content_hash}.png"
        filepath = os.path.join(output_dir, filename)

        if not force_regenerate:
            # 1) 当前场景文件已存在
            if self._is_valid_image_file(filepath):
                if on_progress:
                    on_progress(f"场景 {scene.scene_number} 图片已存在，跳过")
                scene.image_path = filepath
                self._content_hash_cache[content_hash] = filepath
                return filepath

            # 2) 同内容 hash 的其他场景已生成 → 复用，不调 API
            duplicate_src = self._find_image_by_content_hash(output_dir, content_hash)
            if duplicate_src:
                return self._reuse_scene_image(
                    duplicate_src, filepath, scene, content_hash, on_progress,
                    reuse_label="与已有分镜画面相同",
                )

            # 3) 剧本里已记录且文件有效的 image_path（同 hash 优先）
            existing_ip = getattr(scene, "image_path", None) or ""
            if self._is_valid_image_file(existing_ip):
                existing_base = os.path.basename(existing_ip)
                if existing_base.endswith(f"_{content_hash}.png"):
                    return self._reuse_scene_image(
                        existing_ip, filepath, scene, content_hash, on_progress,
                        reuse_label="使用已保存分镜图",
                    )

        if on_progress:
            if ref_path:
                on_progress(f"正在生成场景 {scene.scene_number} 的图片（含角色参考图）...")
            else:
                on_progress(f"正在生成场景 {scene.scene_number} 的图片...")

        ref_mode = (self.config.get("character_ref_image_mode") or "blend").strip().lower()
        if ref_path and ref_mode == "direct":
            from shutil import copyfile
            copyfile(ref_path, filepath)
            self._resize_to_vertical(filepath)
            scene.image_path = filepath
            self._content_hash_cache[content_hash] = filepath
            if on_progress:
                on_progress(f"场景 {scene.scene_number} 已使用角色参考图作为分镜画面")
            return filepath

        base_prompt = self._build_image_prompt(scene, script_characters=script_chars)
        if ref_path:
            who = portrait_char or "the character"
            base_prompt = (
                f"EXACT SAME PERSON as reference portrait ({who}), "
                f"identical face shape, identical eyes, identical nose, identical mouth, "
                f"identical eyebrows, identical jawline, identical skin tone, "
                f"identical hairstyle and hair color as reference, "
                f"only change pose, clothing and background: "
                + base_prompt
            )
        image_api = get_effective_image_api(self.config)
        deepseek_key = (self.config.get("deepseek_api_key") or "").strip()
        if on_progress and image_api == "siliconflow":
            on_progress(f"场景 {scene.scene_number}：正在调用 SiliconFlow 文生图 API…")
        elif on_progress and image_api == "zhipu":
            on_progress(f"场景 {scene.scene_number}：正在调用智谱 GLM-Image…")
        anime = self._visual_style_anime()
        prompt_suffix = _IMAGE_PROMPT_ANIME_SUFFIX if anime else _IMAGE_PROMPT_REALISM_SUFFIX

        # deepseek：仅基础 prompt，扩写与后缀在 _generate_with_deepseek 内完成
        # siliconflow：若配置了 DeepSeek，则先扩写英文再送 SiliconFlow；否则基础 prompt + 后缀
        # 其他：直接基础 prompt + 后缀
        if image_api == "deepseek":
            prompt = base_prompt
        else:
            prompt = base_prompt.rstrip(".,; ") + prompt_suffix

        try:
            if ref_path and image_api not in ("siliconflow",):
                if on_progress:
                    hint = (
                        "智谱 GLM-Image 为纯文生图，无法图生图锁脸；"
                        if image_api == "zhipu"
                        else ""
                    )
                    on_progress(
                        f"场景 {scene.scene_number}：{hint}"
                        "已用定妆照文字+参考约束；上传参考图作定妆照最像真人"
                    )
            if image_api == "deepseek":
                image_data = self._generate_with_deepseek(base_prompt)
            elif image_api == "siliconflow":
                sf_key = (self.config.get("image_api_key") or "").strip()
                if not sf_key:
                    raise RuntimeError(
                        "使用 SiliconFlow 生图请在设置中填写「图片API Key」（SiliconFlow 平台申请的 API Key）。"
                    )
                if deepseek_key:
                    try:
                        sf_prompt = self._expand_to_english_image_prompt(base_prompt)
                    except Exception:
                        sf_prompt = base_prompt.rstrip(".,; ") + prompt_suffix
                else:
                    sf_prompt = prompt
                img2img_strength = None
                if ref_path and use_consistency:
                    try:
                        img2img_strength = float(
                            self.config.get("character_scene_img2img_strength", 0.4)
                        )
                    except (TypeError, ValueError):
                        img2img_strength = 0.4
                self._throttle_siliconflow(on_progress)
                image_data = self._generate_with_siliconflow(
                    sf_prompt,
                    sf_key,
                    reference_image_path=ref_path,
                    img2img_strength=img2img_strength,
                    on_progress=on_progress,
                )
            elif image_api == "zhipu":
                zh_prompt = self._build_scene_prompt_zh(scene, script_characters=script_chars)
                if ref_path:
                    who = portrait_char or "角色"
                    zh_prompt = (
                        f"与定妆照为同一人（{who}），五官脸型一致，仅改变姿势与场景。"
                        + zh_prompt
                    )
                image_data = self._generate_with_zhipu_image(
                    zh_prompt, portrait=False, on_progress=on_progress
                )
            elif image_api == "dall-e":
                image_data = self._generate_with_dalle(prompt)
            elif image_api == "pollinations":
                image_data = self._generate_with_pollinations(prompt)
            elif image_api == "none" or image_api == "":
                # none 也走 Pollinations（免费无需key）
                image_data = self._generate_with_pollinations(prompt)
            else:
                # 未知API，fallback到Pollinations
                image_data = self._generate_with_pollinations(prompt)

            # 保存图片
            with open(filepath, "wb") as f:
                f.write(image_data)

            # 调整为竖屏尺寸
            self._resize_to_vertical(filepath)

            scene.image_path = filepath
            self._content_hash_cache[content_hash] = filepath

            if on_progress:
                on_progress(f"场景 {scene.scene_number} 图片生成完成")

            return filepath

        except Exception as e:
            raise RuntimeError(f"场景 {scene.scene_number} 图片生成失败: {e}")

    def generate_all_images(self, scenes: list, output_dir: str,
                            on_progress=None, script_characters=None,
                            force_regenerate: bool = True) -> list:
        """
        批量生成所有场景图片

        Args:
            scenes: 分镜场景列表
            output_dir: 输出目录
            on_progress: 进度回调 fn(current, total, message)
            force_regenerate: True 时跳过磁盘旧图缓存，强制调用 API

        Returns:
            图片路径列表
        """
        image_paths = []
        total = len(scenes)
        os.makedirs(output_dir, exist_ok=True)

        # 批量重生成时仍建索引（供同批内去重用），但不再复用外部旧图
        self._content_hash_cache = self._index_images_in_dir(output_dir)
        if force_regenerate:
            self._content_hash_cache.clear()

        portrait_registry = {}
        if self.config.get("character_consistency", True) and script_characters:
            portrait_dir = os.path.join(output_dir, "character_portraits")
            portrait_registry = self.ensure_character_portraits(
                script_characters, portrait_dir, on_progress=on_progress
            )

        master_path = None
        for i, scene in enumerate(scenes):
            def progress_wrapper(msg):
                if on_progress:
                    on_progress(i + 1, total, msg)

            if self.config.get("single_take") and master_path and os.path.isfile(master_path):
                from shutil import copyfile
                content_hash = self._compute_scene_content_hash(
                    scene, master_path, "", self.config
                )
                filename = f"scene_{scene.scene_number:02d}_{content_hash}.png"
                filepath = os.path.join(output_dir, filename)
                copyfile(master_path, filepath)
                scene.image_path = filepath
                image_paths.append(filepath)
                continue

            filepath = self.generate_scene_image(
                scene,
                output_dir,
                progress_wrapper,
                script_characters=script_characters,
                portrait_registry=portrait_registry,
                force_regenerate=force_regenerate,
            )
            if self.config.get("single_take") and not master_path:
                master_path = filepath
            image_paths.append(filepath)

        return image_paths

    def ensure_character_portraits(
        self,
        script_characters: list,
        portrait_dir: str,
        on_progress=None,
    ) -> dict:
        """
        为剧本中每个角色准备定妆照（用户上传图或 AI 生成一张标准肖像）。
        返回 {角色名: 图片路径}。
        """
        os.makedirs(portrait_dir, exist_ok=True)
        registry = {}
        chars = [c for c in (script_characters or []) if isinstance(c, dict)]
        total = len(chars)

        for i, ch in enumerate(chars):
            name = (ch.get("name") or "").strip()
            if not name:
                continue
            safe = safe_char_filename(name)
            path = os.path.join(portrait_dir, f"{safe}.png")

            user_ref = resolve_reference_path(ch)
            if user_ref:
                if on_progress:
                    on_progress(0, 0, f"角色「{name}」使用上传参考图作为定妆照…")
                from shutil import copyfile
                copyfile(user_ref, path)
                registry[name] = path
                continue

            if os.path.isfile(path) and os.path.getsize(path) > 2000:
                registry[name] = path
                continue

            if on_progress:
                on_progress(
                    i + 1, max(total, 1),
                    f"正在为角色「{name}」生成定妆照 ({i + 1}/{total})…",
                )

            image_api = get_effective_image_api(self.config)
            if image_api == "zhipu":
                prompt = self._build_portrait_prompt_zh(ch)
            else:
                prompt = self._build_portrait_prompt(ch)
            user_ref_for_i2i = user_ref if user_ref and os.path.isfile(user_ref) else ""
            try:
                if image_api == "zhipu":
                    data = self._generate_with_zhipu_image(
                        prompt, portrait=True, on_progress=on_progress
                    )
                elif image_api == "siliconflow":
                    sf_key = (self.config.get("image_api_key") or "").strip()
                    if not sf_key:
                        raise RuntimeError("SiliconFlow Key 未配置")
                    deepseek_key = (self.config.get("deepseek_api_key") or "").strip()
                    if deepseek_key:
                        try:
                            prompt = self._expand_to_english_image_prompt(prompt)
                        except Exception:
                            pass
                    self._throttle_siliconflow(on_progress)
                    ref_i2i = user_ref_for_i2i
                    strength = None
                    if ref_i2i:
                        try:
                            strength = float(
                                self.config.get("portrait_img2img_strength", 0.35)
                            )
                        except (TypeError, ValueError):
                            strength = 0.35
                    data = self._generate_with_siliconflow(
                        prompt,
                        sf_key,
                        reference_image_path=ref_i2i or "",
                        img2img_strength=strength,
                        on_progress=on_progress,
                    )
                elif image_api == "deepseek":
                    data = self._generate_with_deepseek(prompt)
                else:
                    if self._visual_style_anime():
                        suf = _IMAGE_PROMPT_ANIME_SUFFIX
                        data = self._generate_with_pollinations(
                            prompt.rstrip(".,; ") + suf, portrait=False
                        )
                    else:
                        data = self._generate_portrait_pollinations(prompt)
            except Exception as e:
                print(f"警告：角色「{name}」定妆照生成失败: {e}")
                continue

            with open(path, "wb") as f:
                f.write(data)
            self._resize_to_vertical(path)
            registry[name] = path

        return registry

    def _build_portrait_prompt(self, ch: dict) -> str:
        name = (ch.get("name") or "").strip()
        gender = (ch.get("gender") or "").strip()
        elderly = bool(self.config.get("elderly_daily_mode"))
        extra = enrich_character_for_portrait(ch, elderly_daily=elderly)
        if gender and gender not in extra:
            extra = f"{extra}, {gender}" if extra else gender

        if self._visual_style_anime():
            return (
                f"2D anime character design portrait, head and shoulders, front view, "
                f"character {name}, {extra}, clean lineart, neutral simple background, "
                f"character reference sheet, single person, identity lock for entire series"
            )

        if elderly or _is_elderly_character(ch):
            scene_ctx = (
                "documentary casting photo of Chinese village elder, "
                "warm natural daylight from window, simple indoor wall background, "
                "wearing everyday cotton jacket or apron, honest relaxed expression, "
            )
        else:
            scene_ctx = (
                "professional casting headshot of real Chinese actor, "
                "soft natural window light, neutral indoor background, "
                "relaxed authentic expression, "
            )

        return (
            f"{scene_ctx}"
            f"single person only, head and shoulders, facing camera, sharp focus on eyes, "
            f"character name {name}, {extra}, "
            f"photographed with full-frame camera, 85mm portrait lens, "
            f"real photograph not digital art"
        )

    def _build_portrait_prompt_zh(self, ch: dict) -> str:
        """智谱 GLM-Image 用中文描述（模型对中文人像更友好）。"""
        name = (ch.get("name") or "").strip()
        elderly = bool(self.config.get("elderly_daily_mode"))
        extra = enrich_character_for_portrait(ch, elderly_daily=elderly)
        gender = (ch.get("gender") or "").strip()
        if gender == "male":
            extra += "，中国男性"
        elif gender == "female":
            extra += "，中国女性"

        if elderly or _is_elderly_character(ch):
            style = (
                "竖屏纪实人物肖像摄影，头肩构图，正对镜头，单人，"
                "中国农村老人真实相貌，自然窗光，朴素背景，"
                "皮肤皱纹与毛孔清晰可见，无美颜磨皮，无动漫插画，"
                "高清真实照片，纪录片选角照风格"
            )
        else:
            style = (
                "竖屏高清人物肖像摄影，头肩构图，正对镜头，单人，"
                "真实中国普通人，自然光线，无网红滤镜，"
                "皮肤质感真实，证件照级清晰度，真实照片非插画"
            )
        return f"{style}。角色：{name}。{extra}"

    def _build_scene_prompt_zh(
        self, scene: StoryboardScene, script_characters=None
    ) -> str:
        """分镜画面中文 prompt（GLM-Image）。"""
        parts = []
        vd = (getattr(scene, "visual_description", None) or "").strip()
        if vd:
            parts.append(vd)
        mi = (getattr(scene, "motion_intent", None) or "").strip()
        if mi:
            parts.append(f"动作：{mi}")
        for d in getattr(scene, "dialogues", None) or []:
            if isinstance(d, dict) and (d.get("line") or "").strip():
                ch = (d.get("character") or "").strip()
                parts.append(f"{ch}说：{d.get('line', '')[:60]}")
        names = scene_character_names(scene)
        if script_characters and names:
            bible = build_character_bible(script_characters, set(names))
            if bible:
                parts.append(bible[:200])
        body = "，".join(parts) if parts else "竖屏生活场景"
        prefix = (
            "竖屏9:16纪实摄影，真实中国人物与环境，自然光，"
            "高清照片，无动漫无插画，透视正常，"
        )
        if self.config.get("elderly_daily_mode"):
            prefix += "农村小院或饭桌日常，"
        return prefix + body

    def _generate_with_zhipu_image(
        self, prompt: str, portrait: bool = False, on_progress=None
    ) -> bytes:
        api_key = (self.config.get("zhipu_api_key") or "").strip()
        model = (self.config.get("zhipu_image_model") or "glm-image").strip()
        if portrait:
            size = (self.config.get("zhipu_image_size_portrait") or "1056x1568").strip()
        else:
            size = (self.config.get("zhipu_image_size") or "1088x1472").strip()
        if on_progress:
            on_progress(
                f"正在调用智谱 GLM-Image（{model}，{size}）…"
            )
        return generate_glm_image(api_key, prompt, model=model, size=size)

    def _generate_portrait_pollinations(self, base_prompt: str) -> bytes:
        """定妆照：竖版人像比例 + 增强负面词 + 可选 enhance。"""
        full = base_prompt.rstrip(".,; ") + _PORTRAIT_REALISM_SUFFIX
        return self._generate_with_pollinations(
            full,
            portrait=True,
            negative_extra=self._build_portrait_negative_prompt(),
        )

    def _build_image_prompt(self, scene: StoryboardScene, script_characters=None) -> str:
        if self._visual_style_anime():
            return self._build_image_prompt_anime(scene, script_characters=script_characters)
        return self._build_image_prompt_live(scene, script_characters=script_characters)

    def _scene_char_name_set(self, scene: StoryboardScene) -> set:
        names = set(scene_character_names(scene))
        return {n for n in names if n}

    def _build_image_prompt_live(self, scene: StoryboardScene, script_characters=None) -> str:
        """真人纪实风生图 prompt。"""
        prompt_parts = []

        prompt_parts.append(
            "hyperrealistic photograph of real human beings, shot on full-frame mirrorless camera with 85mm f/1.4 prime lens, "
            "shallow depth of field with creamy bokeh, natural color science, "
            "available light only, no artificial lighting setup, golden hour or overcast soft light, "
            "moderate contrast, lifted shadows, natural film-like color grading, "
            "ABSOLUTELY NO anime, NO cartoon, NO illustration, NO CGI, NO 3D render"
        )

        prompt_parts.append(
            "real human with natural skin texture, visible pores, subtle skin imperfections, "
            "natural undereye circles, real eyebrows with individual hair strands visible, "
            "realistic eyes with detailed iris and natural catchlights, "
            "correct human anatomy, exactly five fingers on each visible hand, natural hand poses, "
            "asymmetrical natural expression, genuine micro-expressions, no forced smile, "
            "real human body proportions, natural body shape, realistic posture and weight distribution"
        )

        prompt_parts.append(
            "single vanishing point, level horizon, real location with natural depth, "
            "environmental context visible in background, medium shot composition, "
            "natural lens compression, realistic perspective, "
            "ambient occlusion and contact shadows, subsurface skin scattering, "
            "clothing with realistic fabric texture and wrinkles"
        )

        characters = getattr(scene, "characters", []) or []
        dialogues = getattr(scene, "dialogues", []) or []

        char_names = set()
        if characters:
            for c in characters:
                if isinstance(c, dict):
                    char_names.add(c.get("name", ""))
                elif isinstance(c, str):
                    char_names.add(c)
        if dialogues:
            for d in dialogues:
                char_names.add(d.get("character", ""))

        char_names = {n for n in char_names if n and n.strip()}

        bible = build_character_bible(script_characters or [], char_names)
        if bible:
            prompt_parts.append(bible)

        if char_names:
            char_desc = ", ".join(sorted(char_names))
            prompt_parts.append(
                f"real Chinese actors portraying {char_desc}, "
                "natural East Asian facial features, minimal everyday makeup, "
                "IDENTICAL FACE in every single shot - same eyes, same nose, same mouth, same jawline, "
                "same skin tone, same hairstyle, same hair color, no face change ever, "
                "real skin texture, natural lip color, no heavy foundation, "
                "natural human body proportions, realistic body shape"
            )

        if scene.visual_description:
            prompt_parts.append(scene.visual_description)

        if self.config.get("include_narration_in_image_prompt") or self.config.get("single_take"):
            narration = (getattr(scene, "narration", None) or "").strip()
            if narration:
                snippet = narration.replace("\n", " ").strip()[:200]
                prompt_parts.append(
                    "presenter speaking to camera about this exact topic, "
                    f"visual must match spoken content: {snippet}"
                )

        if self.config.get("portrait_realism_boost") or self.config.get("elderly_daily_mode"):
            prompt_parts.append(
                "authentic unretouched Chinese people, documentary photograph not illustration, "
                "natural wrinkles and skin texture, real fabric clothing"
            )

        if self.config.get("include_dialogues_in_image_prompt") or self.config.get("elderly_daily_mode"):
            if dialogues:
                for d in dialogues:
                    if not isinstance(d, dict):
                        continue
                    ch = (d.get("character") or "").strip()
                    line = (d.get("line") or "").strip()
                    emo = (d.get("emotion") or "").strip()
                    if ch and line:
                        prompt_parts.append(
                            f"{ch} speaking with {emo or 'natural'} expression, "
                            f"mouth open mid-sentence, gesture while saying: {line[:80]}"
                        )
                prompt_parts.append(
                    "group of elderly Chinese villagers in courtyard or kitchen, "
                    "candid documentary photo, warm daylight, each person visibly acting"
                )

        anchor = (getattr(scene, "visual_anchor", None) or "").strip()
        if anchor:
            prompt_parts.append(f"same character and wardrobe continuity across shots: {anchor}")

        bridge = (getattr(scene, "continuity_from_previous", None) or "").strip()
        if bridge:
            prompt_parts.append(f"sequential story continuity from previous shot: {bridge}")
        leads = (getattr(scene, "leads_to_next", None) or "").strip()
        if leads:
            prompt_parts.append(f"narrative leads to next moment: {leads}")

        motion = (getattr(scene, "motion_intent", None) or "").strip()
        if motion:
            prompt_parts.append(f"single-take micro-motion arc in this frame: {motion}")

        if scene.mood:
            mood_styles = {
                "紧张": "tense suspenseful atmosphere, dramatic side lighting, deep shadows",
                "温馨": "warm cozy atmosphere, soft golden hour lighting, intimate setting",
                "悲伤": "melancholic mood, soft diffused light, muted colors, gentle rain",
                "激烈": "intense emotional scene, dramatic contrast lighting, intense expressions",
                "浪漫": "romantic mood, gentle warm light, natural bokeh in background, soft colors",
                "恐怖": "dark eerie atmosphere, low key lighting, shadows and mystery",
                "欢乐": "cheerful bright scene, natural daylight, vibrant colors, smiling faces",
                "愤怒": "intense anger, sharp lighting, red undertones, dramatic shadows",
            }
            mood_style = mood_styles.get(scene.mood, f"{scene.mood} mood atmosphere")
            prompt_parts.append(mood_style)

        prompt_parts.append(
            "vertical 9:16 frame, straight upright camera, no dutch angle, no fisheye distortion"
        )

        if not char_names:
            prompt_parts.append(
                "featuring realistic Asian people in everyday clothing, natural relaxed poses, real location"
            )

        return ", ".join(prompt_parts)

    def _build_image_prompt_anime(self, scene: StoryboardScene, script_characters=None) -> str:
        """2D 动漫短片风：便于后续图生视频做「会动的一镜」。"""
        prompt_parts = [
            "high quality 2D anime illustration, TV anime production still, clean outlines, soft cel shading",
            "vivid readable colors, simple layered background, vertical 9:16 portrait frame",
            "expressive face, eyes and mouth clearly drawn, suitable for dialogue performance",
            "medium shot or medium close-up, character centered, dynamic but stable composition",
            "consistent costume and hair design across shots, on-model character",
        ]

        characters = getattr(scene, "characters", []) or []
        dialogues = getattr(scene, "dialogues", []) or []
        char_names = set()
        if characters:
            for c in characters:
                if isinstance(c, dict):
                    char_names.add(c.get("name", ""))
                elif isinstance(c, str):
                    char_names.add(c)
        if dialogues:
            for d in dialogues:
                char_names.add(d.get("character", ""))
        char_names = {n for n in char_names if n and n.strip()}

        bible = build_character_bible(script_characters or [], char_names)
        if bible:
            prompt_parts.append(bible)

        if char_names:
            char_desc = ", ".join(sorted(char_names))
            prompt_parts.append(
                f"anime characters named {char_desc}, East Asian anime facial style, "
                "IDENTICAL character design in every shot - same eyes, same face shape, "
                "same hair style, same hair color, same proportions, "
                "matching reference design, on-model face every shot, "
                "consistent costume and hair design across all scenes"
            )

        if scene.visual_description:
            prompt_parts.append(scene.visual_description)

        anchor = (getattr(scene, "visual_anchor", None) or "").strip()
        if anchor:
            prompt_parts.append(f"strict character design continuity: {anchor}")

        bridge = (getattr(scene, "continuity_from_previous", None) or "").strip()
        if bridge:
            prompt_parts.append(f"storyboard continuity from previous cut: {bridge}")
        leads = (getattr(scene, "leads_to_next", None) or "").strip()
        if leads:
            prompt_parts.append(f"story beat leading to next scene: {leads}")

        motion = (getattr(scene, "motion_intent", None) or "").strip()
        if motion:
            prompt_parts.append(f"animation key pose suggesting motion: {motion}")

        if scene.mood:
            mood_styles = {
                "紧张": "dramatic shadows, cool rim light, tense atmosphere",
                "温馨": "warm soft light, cozy palette",
                "悲伤": "muted cool tones, gentle lighting",
                "激烈": "high contrast, speed lines hint in background only",
                "浪漫": "soft bloom, warm highlights",
                "恐怖": "low key, desaturated, mystery fog",
                "欢乐": "bright high-key, upbeat saturation",
                "愤怒": "sharp contrast, red accents",
            }
            prompt_parts.append(mood_styles.get(scene.mood, f"{scene.mood} anime mood"))

        if not char_names:
            prompt_parts.append("one or two anime characters in casual outfits, approachable designs")

        return ", ".join(prompt_parts)

    def _build_portrait_negative_prompt(self) -> str:
        """定妆照专用负面词（比场景更狠，压 AI 脸/网红脸）。"""
        base = self._build_negative_prompt(anime=False)
        extra = (
            "young model face, influencer face, k-pop idol makeup, porcelain doll, "
            "symmetrical perfect face, uncanny valley, synthetic skin, "
            "overprocessed HDR portrait, glamour retouch, studio glamour lighting, "
            "anime eyes, big sparkly eyes, illustration, vector portrait"
        )
        return f"{base}, {extra}"

    def _build_negative_prompt(self, anime: bool = False) -> str:
        """负面 prompt：真人/动漫分支。"""
        if anime:
            anime_neg = [
                "photorealistic, live action, photograph, realistic skin pores",
                "3d render, uncanny valley doll, UE5 screenshot, western sitcom cartoon",
                "deformed face, melted eyes, asymmetrical face, extra limbs",
                "different character design, face swap, inconsistent face between frames",
                "extra fingers, mangled hands",
                "watermark, text, logo, subtitle, speech bubble",
                "blurry, low resolution, jpeg artifacts",
                "busy cluttered background, unreadable silhouette",
            ]
            return ", ".join(anime_neg)

        negative_parts = [
            "AI generated, artificial, fake, CGI, 3D render, doll, wax figure, uncanny valley, stock photo",
            "cartoon, anime, manga, illustration, painting, sketch, vector art, game screenshot, digital art, drawing",
            "distorted face, melted face, asymmetrical eyes, misaligned eyes, tiny eyes, blurry eyes, cross-eyed",
            "deformed jaw, crooked mouth, duplicate limbs, extra arms, extra legs, twisted torso",
            "extra fingers, six fingers, fused fingers, mangled hands, wrong number of fingers",
            "floating objects, object merged with body, impossible physics, intersecting geometry",
            "tilted horizon, skewed walls, bent doorframes, mismatched floor tiles, duplicated furniture",
            "misaligned windows, asymmetric room layout, mirror reflection errors, duplicate faces",
            "oversmoothed skin, plastic skin, porcelain skin, airbrushed, waxy skin, beauty filter glow",
            "different person, face swap, changed identity, another actor, inconsistent face, face drift",
            "blurry, pixelated, low resolution, jpeg artifacts, watermark, text, signature, logo",
            "cropped head, cut off feet, disembodied limbs, surreal anatomy, collage, double exposure",
            "over-sharpened, harsh HDR, neon oversaturation, bloom halos, lens flare abuse",
            "dutch angle, fisheye, ultra wide distortion, anamorphic stretch",
            "heavy makeup, contouring, false eyelashes, lip filler, botox look, plastic surgery look",
            "studio lighting setup, ring light, softbox visible, professional photography backdrop",
            "posed portrait, stiff expression, forced smile, passport photo style",
            "face change, identity change, different actor, different person between scenes",
            "facial feature change, eye color change, nose shape change, lip shape change",
            "anime style, cartoon style, 2D animation, cel shading, lineart, comic style",
            "unrealistic body proportions, exaggerated features, stylized art",
        ]
        return ", ".join(negative_parts)

    def _generate_with_pollinations(
        self,
        prompt: str,
        portrait: bool = False,
        negative_extra: str = "",
    ) -> bytes:
        """
        使用 Pollinations AI 生成图片（完全免费，无需API Key）

        API: https://image.pollinations.ai/prompt/{prompt}
        支持参数: width, height, nologo, seed, model, negative, enhance
        """
        import urllib.parse
        encoded_prompt = urllib.parse.quote(prompt)

        negative_prompt = self._build_negative_prompt(self._visual_style_anime())
        if negative_extra:
            negative_prompt = f"{negative_prompt}, {negative_extra}"
        encoded_negative = urllib.parse.quote(negative_prompt)

        if portrait:
            width, height = 768, 1152
        else:
            width = 1024
            height = 1792

        model = (self.config.get("pollinations_model") or "flux").strip()
        if portrait and self.config.get("pollinations_portrait_model"):
            model = (self.config.get("pollinations_portrait_model") or model).strip()
        if model.lower() in ("", "default"):
            model = "flux"

        enhance = "true" if (
            portrait and self.config.get("pollinations_portrait_enhance", True)
        ) else "false"

        url = (
            f"https://image.pollinations.ai/prompt/{encoded_prompt}"
            f"?width={width}&height={height}"
            f"&nologo=true&seed={hashlib.md5(prompt.encode()).hexdigest()[:8]}"
            f"&negative={encoded_negative}"
            f"&model={urllib.parse.quote(model)}"
            f"&enhance={enhance}"
        )

        # 下载图片，带重试
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = requests.get(url, timeout=120)
                if response.status_code == 200:
                    # 检查返回的是否是图片
                    content_type = response.headers.get("Content-Type", "")
                    if "image" in content_type or len(response.content) > 10000:
                        return response.content
                    # 如果返回的不是图片（可能是错误页面），重试
                    raise RuntimeError(f"返回内容不是图片 (Content-Type: {content_type}, size: {len(response.content)})")
                else:
                    raise RuntimeError(f"HTTP {response.status_code}: {response.text[:200]}")
            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    continue
                raise RuntimeError(f"Pollinations AI 超时（已重试{max_retries}次），请检查网络连接")
            except RuntimeError:
                if attempt < max_retries - 1:
                    continue
                raise

        raise RuntimeError("Pollinations AI 生图失败，请稍后重试")

    def _expand_to_english_image_prompt(self, base_prompt: str) -> str:
        """
        用 DeepSeek 将完整生图描述压缩为一行英文 prompt，并追加风格后缀。
        需要已配置 deepseek_api_key。
        """
        client = self._get_client()
        anime = self._visual_style_anime()

        if anime:
            expand_instruction = (
                "请根据下列「完整生图描述」输出**仅一行**英文文生图 prompt，不要引号、不要解释。\n"
                "风格：高质量 2D 日系/国漫 TV 动画 Key Visual，干净线稿、赛璐璐上色、可读背景。\n"
                "角色：五官清晰、表情适合「对白表演」，发际与服装色块在多镜中一致。\n"
                "构图：竖屏 9:16，景深简单，避免写实照片用词。\n"
                "若描述含 continuity / character design，译文中保留。\n\n"
                f"{base_prompt}"
            )
            prefix_needle = ("anime", "2d", "cel", "illustration")
            default_prefix = "high quality 2D anime key visual, "
        else:
            expand_instruction = (
                "请根据下列「完整生图描述」输出**仅一行**英文文生图 prompt，不要引号、不要解释。\n"
                "风格：超写实摄影/纪录片感，自然光、真实皮肤纹理与毛孔、零磨皮；\n"
                "避免任何「电影感 HDR」、过度美化、影棚灯光用词。\n"
                "要求：皮肤有自然瑕疵（毛孔、细纹、黑眼圈）；头发丝清晰可见；\n"
                "几何：水平地平线、透视一致、物体落地有阴影、单一场景无拼贴错位。\n"
                "人体：每只可见的手恰好五根手指；五官对称但有自然不对称；眼神自然有神。\n"
                "竖屏 9:16，相机端正无荷兰角，浅景深虚化背景。\n"
                "若描述含 continuity / wardrobe continuity，译文中保留衔接关系。\n\n"
                f"{base_prompt}"
            )
            default_prefix = "hyperrealistic candid photograph, "

        response = client.chat.completions.create(
            model=self.config.get("deepseek_model", "deepseek-chat"),
            messages=[{"role": "user", "content": expand_instruction}],
            temperature=0.55,
            max_tokens=500,
        )
        content = response.choices[0].message.content
        if not content:
            english_prompt = base_prompt
        else:
            english_prompt = content.strip()
        for ch in ('"', "'", "「", "」"):
            if english_prompt.startswith(ch) and english_prompt.endswith(ch) and len(english_prompt) > 2:
                english_prompt = english_prompt[1:-1].strip()
        head = english_prompt.lower()[:160]
        if anime:
            if not any(x in head for x in prefix_needle):
                english_prompt = default_prefix + english_prompt
            suffix = _IMAGE_PROMPT_ANIME_SUFFIX
        else:
            if "photoreal" not in head and "documentary" not in head:
                english_prompt = default_prefix + english_prompt
            suffix = _IMAGE_PROMPT_REALISM_SUFFIX

        return english_prompt.rstrip(".,; ") + suffix

    def _generate_with_deepseek(self, base_prompt: str) -> bytes:
        """DeepSeek 扩写英文 prompt，再按 image_api_key 选择 SiliconFlow 或 Pollinations。"""
        image_api_key = (self.config.get("image_api_key") or "").strip()
        suf = _IMAGE_PROMPT_ANIME_SUFFIX if self._visual_style_anime() else _IMAGE_PROMPT_REALISM_SUFFIX

        try:
            english_prompt = self._expand_to_english_image_prompt(base_prompt)

            if image_api_key:
                return self._generate_with_siliconflow(english_prompt, image_api_key)

            return self._generate_with_pollinations(english_prompt)

        except Exception:
            fallback = base_prompt.rstrip(".,; ") + suf
            return self._generate_with_pollinations(fallback)

    def _generate_with_dalle(self, prompt: str) -> bytes:
        """使用DALL-E生成图片"""
        api_key = self.config.get("image_api_key", "")
        if not api_key:
            api_key = self.config.get("deepseek_api_key", "")

        client = OpenAI(api_key=api_key, base_url="https://api.openai.com/v1")
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1792",  # 竖屏
            quality="hd",
            n=1,
        )
        image_url = response.data[0].url
        image_response = requests.get(image_url)
        return image_response.content

    def _build_siliconflow_images_json(
        self,
        prompt: str,
        reference_image_path: str = "",
        img2img_strength: float = None,
    ) -> dict:
        """组装 /v1/images/generations 请求体（不同模型支持的字段略有差异，见官方文档）。"""
        model = (self.config.get("siliconflow_image_model") or "Kwai-Kolors/Kolors").strip()
        image_size = (self.config.get("siliconflow_image_size") or "720x1280").strip()
        try:
            steps = int(self.config.get("siliconflow_image_steps", 28))
        except (TypeError, ValueError):
            steps = 28
        steps = max(1, min(100, steps))

        payload: dict = {
            "model": model,
            "prompt": prompt,
            "batch_size": 1,
        }
        # Qwen-Image-Edit 等部分模型不支持 image_size；纯文生图一般需带尺寸
        model_l = model.lower()
        if "qwen-image-edit" in model_l:
            pass  # 由用户按文档自行配置尺寸与其它字段
        else:
            payload["image_size"] = image_size

        if reference_image_path and os.path.isfile(reference_image_path):
            payload["image"] = image_file_to_data_uri(reference_image_path)
            if img2img_strength is not None:
                strength = max(0.15, min(0.85, float(img2img_strength)))
                payload["strength"] = strength
                payload["denoising_strength"] = strength

        if "kolors" in model_l:
            payload["num_inference_steps"] = steps
            try:
                payload["guidance_scale"] = float(self.config.get("siliconflow_image_guidance", 7.0))
            except (TypeError, ValueError):
                payload["guidance_scale"] = 7.0
            neg = self._build_negative_prompt(self._visual_style_anime())
            if neg:
                payload["negative_prompt"] = neg[:1200]
        else:
            payload["num_inference_steps"] = steps
            try:
                gs = self.config.get("siliconflow_image_guidance")
                if gs is not None and gs != "":
                    payload["guidance_scale"] = float(gs)
            except (TypeError, ValueError):
                pass

        return payload

    @staticmethod
    def _siliconflow_images_error_message(response: requests.Response) -> str:
        """解析 SiliconFlow 文生图错误响应（含 HTTP 非 200 与 JSON body 内 code）。"""
        text = response.text[:800] if response.text else ""
        try:
            data = response.json()
        except Exception:
            return f"HTTP {response.status_code}: {text}"

        if isinstance(data, dict):
            code = data.get("code")
            msg = data.get("message") or text
            extra = ""
            if code == 30003 or (isinstance(msg, str) and "disabled" in msg.lower()):
                extra = (
                    " 该模型已在平台停用或未对当前账号开放，请到 "
                    "https://cloud.siliconflow.cn 模型广场筛选 to-image，"
                    "将「SiliconFlow 生图模型」改为文档列出的可用模型 ID。"
                )
            elif response.status_code == 429 or code == 50604 or "rate limit" in str(msg).lower():
                extra = (
                    " 已触发 SiliconFlow 每分钟请求上限(IPM)。程序会自动等待并重试；"
                    "也可在配置中增大 siliconflow_request_interval_sec（默认 15 秒），"
                    "或稍后再生成剩余场景。"
                )
            return f"HTTP {response.status_code}, code={code}: {msg}.{extra}" if code is not None else f"HTTP {response.status_code}: {msg}"
        return f"HTTP {response.status_code}: {text}"

    def _generate_with_siliconflow(
        self,
        prompt: str,
        api_key: str,
        reference_image_path: str = "",
        img2img_strength: float = None,
        on_progress=None,
    ) -> bytes:
        """使用 SiliconFlow OpenAPI 文生图（https://api.siliconflow.cn/v1/images/generations）"""
        if not (api_key or "").strip():
            raise RuntimeError(
                "未填写 SiliconFlow API Key。请在 设置 → API设置 → 图片API Key 中填写。"
            )
        payload = self._build_siliconflow_images_json(
            prompt,
            reference_image_path=reference_image_path,
            img2img_strength=img2img_strength,
        )
        model = payload.get("model", "")
        max_retries = self._sf_rate_limit_retries()
        last_err = ""

        for attempt in range(max_retries):
            try:
                print(
                    f"[SiliconFlow] POST /v1/images/generations model={model} "
                    f"(attempt {attempt + 1}/{max_retries})"
                )
                self._mark_sf_request()
                response = requests.post(
                    "https://api.siliconflow.cn/v1/images/generations",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=120,
                )

                try:
                    data = response.json()
                except Exception:
                    data = {}

                if self._is_sf_rate_limit(response, data):
                    wait = min(90.0, 8.0 * (2 ** attempt))
                    last_err = self._siliconflow_images_error_message(response)
                    msg = f"SiliconFlow 限流(429)，{wait:.0f}s 后自动重试 ({attempt + 1}/{max_retries})…"
                    if on_progress:
                        on_progress(msg)
                    else:
                        print(f"[SiliconFlow] {msg}")
                    time.sleep(wait)
                    self._throttle_siliconflow(on_progress)
                    continue

                err_code = isinstance(data, dict) and data.get("code")
                err_msg = isinstance(data, dict) and data.get("message")
                if response.status_code != 200 or (
                    err_code is not None and err_code != 200 and err_msg
                ):
                    raise RuntimeError(self._siliconflow_images_error_message(response))

                if isinstance(data, dict) and data.get("images"):
                    image_url = data["images"][0].get("url", "")
                    if image_url:
                        img_response = requests.get(image_url, timeout=120)
                        if img_response.status_code == 200:
                            return img_response.content
                        raise RuntimeError(
                            f"下载生成图片失败 HTTP {img_response.status_code}"
                        )

                raise RuntimeError(self._siliconflow_images_error_message(response))
            except RuntimeError as e:
                last_err = str(e)
                if "429" in last_err or "50604" in last_err or "rate limit" in last_err.lower():
                    if attempt + 1 < max_retries:
                        wait = min(90.0, 8.0 * (2 ** attempt))
                        msg = f"SiliconFlow 限流，{wait:.0f}s 后重试…"
                        if on_progress:
                            on_progress(msg)
                        time.sleep(wait)
                        self._throttle_siliconflow(on_progress)
                        continue
                raise
            except Exception as e:
                raise RuntimeError(f"Silicon Flow生图失败: {e}") from e

        raise RuntimeError(last_err or "SiliconFlow 生图失败：请求过于频繁，请稍后再试。")

    def _resize_to_vertical(self, filepath: str):
        """
        将图片缩放到与视频一致的竖屏分辨率。

        - letterbox（默认）：等比缩放后上下或左右留边，不裁切主体，减少「裁切错位」感。
        - crop：铺满画布，居中裁切（旧行为），可能切掉头/脚。
        """
        img = Image.open(filepath).convert("RGB")
        target_w, target_h = 1080, 1920
        mode = (self.config.get("image_fit_mode") or "letterbox").strip().lower()

        if img.size == (target_w, target_h):
            return

        img_ratio = img.width / img.height
        target_ratio = target_w / target_h

        if mode == "crop":
            if img_ratio > target_ratio:
                new_w = int(img.height * target_ratio)
                left = (img.width - new_w) // 2
                img = img.crop((left, 0, left + new_w, img.height))
            else:
                new_h = int(img.width / target_ratio)
                top = (img.height - new_h) // 2
                img = img.crop((0, top, img.width, top + new_h))
            img = img.resize((target_w, target_h), Image.LANCZOS)
        else:
            if img_ratio > target_ratio:
                new_w = target_w
                new_h = max(1, int(round(target_w / img_ratio)))
            else:
                new_h = target_h
                new_w = max(1, int(round(target_h * img_ratio)))
            img = img.resize((new_w, new_h), Image.LANCZOS)
            canvas = Image.new("RGB", (target_w, target_h), (10, 10, 12))
            ox = (target_w - new_w) // 2
            oy = (target_h - new_h) // 2
            canvas.paste(img, (ox, oy))
            img = canvas

        img.save(filepath, "PNG")
