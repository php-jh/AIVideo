"""
AI短剧生成器 - 动态视频生成模块（改进版）
从静态图片生成动态视频片段，支持：
- 本地 MoviePy 特效（默认，无需额外 API）
- SiliconFlow 图生视频（配置 video_animated_backend=siliconflow + image_api_key）

核心改进（本地模式）：
1. 三层视差（前景/中景/背景分离，不同速度移动）
2. 手持摄像机抖动（模拟真实拍摄）
3. 动画风格色采（增加饱和度、柔化）
4. 动态粒子效果
5. 电影感暗角
"""
import os
import io
import base64
import hashlib
import random
import time
import numpy as np
import requests
from PIL import Image, ImageEnhance, ImageDraw, ImageFilter
from moviepy.editor import VideoClip
from config import load_config
from core.storyboard import StoryboardScene
from core.character_refs import pick_scene_reference_image
from core.motion_utils import build_dialogue_motion_hints, is_anime_cartoon
from core.api_routing import get_effective_video_backend, has_siliconflow_key


class VideoGenerator:
    """
    从静态图生成动态视频：本地特效，或 SiliconFlow 图生视频（见配置 video_animated_backend）。

    本地模式效果包括：
    1. 三层视差效果（前景移动快，背景移动慢）
    2. 手持摄像机抖动
    3. 动画风格色采增强
    4. 动态粒子（光斑/雨/花瓣/火花/雾气）
    5. 电影感暗角呼吸
    """

    # 特效强度配置
    EFFECT_PRESETS = {
        "温馨": {"zoom_range": 0.03, "brightness_var": 0.06, "particle_type": "bokeh", "warm_shift": 0.08, "parallax": 0.02},
        "紧张": {"zoom_range": 0.02, "brightness_var": 0.10, "particle_type": "none", "warm_shift": 0.0, "parallax": 0.015},
        "悲伤": {"zoom_range": 0.02, "brightness_var": 0.04, "particle_type": "rain", "warm_shift": -0.06, "parallax": 0.01},
        "激烈": {"zoom_range": 0.05, "brightness_var": 0.12, "particle_type": "spark", "warm_shift": 0.0, "parallax": 0.03},
        "浪漫": {"zoom_range": 0.03, "brightness_var": 0.05, "particle_type": "petal", "warm_shift": 0.10, "parallax": 0.02},
        "恐怖": {"zoom_range": 0.015, "brightness_var": 0.08, "particle_type": "fog", "warm_shift": -0.10, "parallax": 0.01},
        "欢乐": {"zoom_range": 0.04, "brightness_var": 0.06, "particle_type": "bokeh", "warm_shift": 0.06, "parallax": 0.025},
        "愤怒": {"zoom_range": 0.04, "brightness_var": 0.10, "particle_type": "spark", "warm_shift": -0.04, "parallax": 0.03},
    }

    def __init__(self):
        self.config = load_config()
        self.width = self.config.get("video_width", 1080)
        self.height = self.config.get("video_height", 1920)
        self.fps = self.config.get("video_fps", 24)

    def generate_scene_video(
        self,
        scene: StoryboardScene,
        output_dir: str,
        on_progress=None,
        prev_scene=None,
        next_scene=None,
        story_meta=None,
        force_local: bool = False,
        script_characters=None,
    ) -> str:
        """
        为单个场景从图片生成动态视频（简化版，避免图片被切割）。

        Args:
            prev_scene / next_scene: 相邻分镜，用于 SiliconFlow 提示词与连贯动效推断。
            story_meta: {"title", "theme", "genre"} 等全片元信息。
            force_local: True 时强制使用本地 MoviePy 动效（合成阶段回退用，避免误入 SiliconFlow 排队）。
        """
        self.config = load_config()
        os.makedirs(output_dir, exist_ok=True)

        ref_path = pick_scene_reference_image(scene, script_characters or [])
        if not scene.image_path or not os.path.exists(scene.image_path):
            if ref_path:
                scene.image_path = ref_path
            else:
                raise ValueError(
                    f"场景 {scene.scene_number} 没有图片，请先生成图片或为角色设置参考图"
                )

        backend = get_effective_video_backend(self.config, force_local=force_local)
        ctx_bits = "|".join([
            getattr(scene, "motion_intent", "") or "",
            getattr(scene, "continuity_from_previous", "") or "",
        ])
        hash_extra = "|compose_fallback" if force_local else ""
        tag = "sf" if backend == "siliconflow" else "local"
        content_hash = hashlib.md5(
            f"{scene.image_path}|{backend}|{ctx_bits}{hash_extra}".encode("utf-8")
        ).hexdigest()[:8]
        filename = f"scene_{scene.scene_number:02d}_{tag}_{content_hash}.mp4"
        filepath = os.path.join(output_dir, filename)

        if os.path.exists(filepath) and os.path.getsize(filepath) > 10000:
            if on_progress:
                on_progress(f"场景 {scene.scene_number} 动态视频已存在，跳过")
            scene.video_path = filepath
            return filepath

        # 相同首帧图+动效参数的分镜视频已存在 → 复用，不调图生视频 API
        import glob
        from shutil import copyfile
        for dup in glob.glob(os.path.join(output_dir, f"*_{tag}_{content_hash}.mp4")):
            if os.path.abspath(dup) == os.path.abspath(filepath):
                continue
            if os.path.getsize(dup) > 10000:
                copyfile(dup, filepath)
                scene.video_path = filepath
                if on_progress:
                    on_progress(
                        f"场景 {scene.scene_number} 复用已有动效视频 "
                        f"（{os.path.basename(dup)}，未调用 API）"
                    )
                return filepath

        if on_progress:
            if backend == "siliconflow":
                on_progress(
                    f"场景 {scene.scene_number}：正在调用 SiliconFlow 图生视频 API…"
                )
            elif backend == "zhipu":
                on_progress(
                    f"场景 {scene.scene_number}：正在调用智谱清影图生视频 API…"
                )
            else:
                on_progress(
                    f"场景 {scene.scene_number}：使用本地动效（未走云端 API）…"
                )

        try:
            if backend == "siliconflow":
                self._generate_scene_video_siliconflow(
                    scene, filepath, on_progress,
                    prev_scene=prev_scene, next_scene=next_scene, story_meta=story_meta,
                    script_characters=script_characters,
                )
                return filepath

            if backend == "zhipu":
                self._generate_scene_video_zhipu(
                    scene, filepath, on_progress,
                    prev_scene=prev_scene, next_scene=next_scene, story_meta=story_meta,
                    script_characters=script_characters,
                )
                return filepath

            duration = getattr(scene, "duration", 5.0)
            mood = getattr(scene, "mood", "")
            zoom_trend = self._infer_local_zoom_direction(scene)
            anime_motion = is_anime_cartoon(self.config)

            # 加载图片
            img = Image.open(scene.image_path).convert("RGB")
            
            # 保持宽高比调整图片尺寸
            img_ratio = img.width / img.height
            target_ratio = self.width / self.height
            
            if img_ratio > target_ratio:
                # 图片较宽
                new_width = self.width
                new_height = int(new_width / img_ratio)
            else:
                # 图片较高
                new_height = self.height
                new_width = int(new_height * img_ratio)
            
            img = img.resize((new_width, new_height), Image.LANCZOS)

            # 获取特效预设
            preset = self.EFFECT_PRESETS.get(mood, {
                "zoom_range": 0.03,
                "brightness_var": 0.06,
                "particle_type": "bokeh",
                "warm_shift": 0.04,
            })

            # 预生成粒子
            particles = self._generate_particles(
                preset["particle_type"], duration
            )

            # 使用场景路径作为种子，确保同一场景效果一致
            random.seed(abs(hash(scene.image_path)) % (2**32))

            # 创建动态clip（简化版，不分割图片）
            def make_frame(t):
                progress = t / duration
                return self._apply_simple_effects(
                    img, t, duration, progress, preset, particles, zoom_trend,
                    anime_motion=anime_motion,
                )

            clip = VideoClip(make_frame, duration=duration)

            # 编码保存
            clip.write_videofile(
                filepath,
                fps=self.fps,
                codec="libx264",
                audio=False,
                preset="medium",
                threads=4,
                logger=None,
            )
            clip.close()

            scene.video_path = filepath

            if on_progress:
                on_progress(f"场景 {scene.scene_number} 动态视频生成完成")

            return filepath

        except Exception as e:
            raise RuntimeError(f"场景 {scene.scene_number} 动态视频生成失败: {e}")

    def _infer_local_zoom_direction(self, scene: StoryboardScene) -> int:
        """
        根据分镜文案推断本地伪动效的推拉趋势。
        返回 1=缓推（放大）、-1=缓拉（缩小）、0=原有呼吸缩放。
        """
        text = (
            (getattr(scene, "camera_movement", "") or "")
            + " "
            + (getattr(scene, "motion_intent", "") or "")
        ).lower()
        pull_kw = ("拉远", "pull", "zoom out", "后退", "撤离", "拉开", "渐远")
        push_kw = ("推进", "推近", "zoom in", "靠近", "逼近", "凑近", "压近")
        if any(k in text for k in pull_kw):
            return -1
        if any(k in text for k in push_kw):
            return 1
        return 0

    def _build_siliconflow_video_prompt(
        self,
        scene: StoryboardScene,
        prev_scene=None,
        next_scene=None,
        story_meta=None,
    ) -> str:
        """图生视频：融入全片主题、视觉锚点、镜间衔接与单镜动效。"""
        self.config = load_config()
        anime = (self.config.get("visual_style") or "live_action").strip().lower() == "anime_cartoon"
        parts = []
        sm = story_meta or {}
        head = " / ".join(
            x for x in (
                (sm.get("title") or "").strip(),
                (sm.get("theme") or "").strip(),
            ) if x
        )
        if head:
            parts.append(f"short drama arc: {head}")

        vd = (getattr(scene, "visual_description", "") or "").strip()
        if vd:
            parts.append(vd)

        anchor = (getattr(scene, "visual_anchor", "") or "").strip()
        if anchor:
            parts.append(f"visual anchor: {anchor}")

        bridge = (getattr(scene, "continuity_from_previous", "") or "").strip()
        if bridge:
            parts.append(f"continuity from previous: {bridge}")
        leads = (getattr(scene, "leads_to_next", "") or "").strip()
        if leads:
            parts.append(f"leads to next beat: {leads}")

        motion = (getattr(scene, "motion_intent", "") or "").strip()
        if motion:
            parts.append(f"motion to animate: {motion}")

        dialogue_motion = build_dialogue_motion_hints(scene)
        if dialogue_motion:
            parts.append(f"character acting: {dialogue_motion}")

        cm = (getattr(scene, "camera_movement", "") or "").strip()
        if cm and cm != "静态":
            parts.append(f"camera: {cm}")

        mood = (getattr(scene, "mood", "") or "").strip()
        if mood:
            parts.append(f"mood: {mood}")

        if prev_scene is not None:
            pv = (getattr(prev_scene, "visual_description", "") or "").strip()
            if pv:
                parts.append(f"previous shot context: {pv[:200]}")

        if next_scene is not None:
            nv = (getattr(next_scene, "visual_description", "") or "").strip()
            if nv:
                parts.append(f"lead naturally into next: {nv[:200]}")

        if anime:
            parts.append(
                "2D anime character animation clip, character raises hand, gestures while speaking, "
                "mouth opens and closes for dialogue lip-sync style, blinking eyes, eyebrow motion, "
                "subtle squash-and-stretch, hair and clothes follow body movement, fluid inbetweening, "
                "full-body or upper-body acting, NOT a static slideshow, no live-action morphing, stable lineart"
            )
        else:
            parts.append(
                "smooth coherent motion in one clip, stable character identity, "
                "cinematic lighting, no jump cuts inside the clip"
            )
        text = ", ".join(p for p in parts if p)
        return text[:2200]

    def _image_to_data_uri_for_siliconflow_i2v(self, image_path: str) -> str:
        """裁剪缩放为 720x1280 后以 JPEG data URI 上传，与 image_size 一致并减小体积。"""
        img = Image.open(image_path).convert("RGB")
        tw, th = 720, 1280
        scale = max(tw / img.width, th / img.height)
        nw = max(int(img.width * scale), tw)
        nh = max(int(img.height * scale), th)
        img = img.resize((nw, nh), Image.LANCZOS)
        left = (nw - tw) // 2
        top = (nh - th) // 2
        img = img.crop((left, top, left + tw, top + th))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=88)
        b64 = base64.standard_b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/jpeg;base64,{b64}"

    def _siliconflow_video_submit(self, api_key: str, payload: dict) -> str:
        r = requests.post(
            "https://api.siliconflow.cn/v1/video/submit",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=120,
        )
        try:
            data = r.json()
        except Exception:
            data = {}
        if r.status_code != 200:
            msg = data.get("message") if isinstance(data, dict) else None
            raise RuntimeError(
                f"SiliconFlow video/submit HTTP {r.status_code}: {msg or r.text[:500]}"
            )
        req_id = data.get("requestId") or data.get("request_id")
        if not req_id:
            raise RuntimeError(f"SiliconFlow video/submit 未返回 requestId: {data}")
        return req_id

    def _siliconflow_video_status(self, api_key: str, request_id: str) -> dict:
        r = requests.post(
            "https://api.siliconflow.cn/v1/video/status",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={"requestId": request_id},
            timeout=60,
        )
        try:
            data = r.json()
        except Exception:
            data = {}
        if r.status_code != 200:
            msg = data.get("message") if isinstance(data, dict) else None
            raise RuntimeError(
                f"SiliconFlow video/status HTTP {r.status_code}: {msg or r.text[:500]}"
            )
        return data if isinstance(data, dict) else {}

    def _generate_scene_video_siliconflow(
        self,
        scene: StoryboardScene,
        filepath: str,
        on_progress=None,
        prev_scene=None,
        next_scene=None,
        story_meta=None,
        script_characters=None,
    ) -> None:
        """调用 SiliconFlow /v1/video/submit + /v1/video/status 图生视频并保存为 MP4。"""
        api_key = (self.config.get("image_api_key") or "").strip()
        if not api_key:
            raise RuntimeError(
                "使用 SiliconFlow 图生视频请在设置中填写「图片API Key」（SiliconFlow 密钥，与生图相同）。"
            )
        model = (self.config.get("siliconflow_video_model") or "Wan-AI/Wan2.2-I2V-A14B").strip()
        prompt = self._build_siliconflow_video_prompt(
            scene, prev_scene=prev_scene, next_scene=next_scene, story_meta=story_meta
        )
        ref_path = pick_scene_reference_image(scene, script_characters or [])
        first_frame = (self.config.get("character_ref_video_first_frame") or "scene_keyframe").strip().lower()
        i2v_image = scene.image_path
        if first_frame == "reference" and ref_path:
            i2v_image = ref_path
        image_uri = self._image_to_data_uri_for_siliconflow_i2v(i2v_image)

        anime = (self.config.get("visual_style") or "live_action").strip().lower() == "anime_cartoon"
        neg = (
            "photorealistic, live action, realistic skin, uncanny 3d doll, western sitcom style, "
            "distorted face, melting lineart, extra fingers, identity drift, "
            "static image, frozen pose, no movement, slideshow, still frame, "
            "flicker, watermark, text, jarring jump cut"
            if anime
            else (
                "distorted face, extra fingers, morphing limbs, identity drift, "
                "flicker, watermark, text, jarring jump cut"
            )
        )

        payload = {
            "model": model,
            "prompt": prompt,
            "image_size": "720x1280",
            "image": image_uri,
            "negative_prompt": neg,
        }

        model = payload.get("model", "")
        print(f"[SiliconFlow] POST /v1/video/submit model={model}")
        if on_progress:
            on_progress(f"场景 {scene.scene_number} 已提交 SiliconFlow 图生视频（排队中）…")

        request_id = self._siliconflow_video_submit(api_key, payload)

        poll_interval = max(3, int(self.config.get("siliconflow_video_poll_interval", 5)))
        max_wait = max(120, int(self.config.get("siliconflow_video_poll_timeout_sec", 900)))
        deadline = time.monotonic() + max_wait
        last_status = ""
        poll_i = 0

        while time.monotonic() < deadline:
            data = self._siliconflow_video_status(api_key, request_id)
            status = (data.get("status") or "").strip()
            if status and status != last_status:
                last_status = status
                if on_progress:
                    on_progress(
                        f"场景 {scene.scene_number} SiliconFlow 视频状态: {status}"
                    )

            if status == "Succeed":
                results = data.get("results") or {}
                videos = results.get("videos") or []
                if not videos:
                    raise RuntimeError(f"SiliconFlow 成功但未返回视频地址: {data}")
                url = (videos[0] or {}).get("url")
                if not url:
                    raise RuntimeError(f"SiliconFlow 响应缺少 url: {data}")
                if on_progress:
                    on_progress(f"场景 {scene.scene_number} 正在下载视频…")
                vr = requests.get(url, timeout=300)
                if vr.status_code != 200:
                    raise RuntimeError(f"下载视频失败 HTTP {vr.status_code}")
                with open(filepath, "wb") as f:
                    f.write(vr.content)
                if os.path.getsize(filepath) < 1000:
                    raise RuntimeError("下载的视频文件过小，可能已损坏")
                scene.video_path = filepath
                if on_progress:
                    on_progress(f"场景 {scene.scene_number} 动态视频生成完成")
                return

            if status == "Failed":
                reason = data.get("reason") or data.get("message") or str(data)
                raise RuntimeError(f"SiliconFlow 视频生成失败: {reason}")

            poll_i += 1
            if on_progress and poll_i % 6 == 0:
                on_progress(
                    f"场景 {scene.scene_number} SiliconFlow 排队/生成中（已等待约 "
                    f"{poll_i * poll_interval}s）…"
                )
            time.sleep(poll_interval)

        raise RuntimeError(
            f"SiliconFlow 图生视频超时（>{max_wait}s），请稍后重试或缩短队列。"
        )

    def _image_to_base64_for_zhipu(self, image_path: str) -> str:
        """将图片转为 Base64 编码用于智谱清影 API。"""
        img = Image.open(image_path).convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=88)
        b64 = base64.standard_b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/jpeg;base64,{b64}"

    def _build_zhipu_video_prompt(
        self,
        scene: StoryboardScene,
        prev_scene=None,
        next_scene=None,
        story_meta=None,
    ) -> str:
        """智谱清影图生视频提示词构建。"""
        self.config = load_config()
        anime = (self.config.get("visual_style") or "live_action").strip().lower() == "anime_cartoon"
        parts = []
        sm = story_meta or {}
        head = " / ".join(
            x for x in (
                (sm.get("title") or "").strip(),
                (sm.get("theme") or "").strip(),
            ) if x
        )
        if head:
            parts.append(f"short drama arc: {head}")

        vd = (getattr(scene, "visual_description", "") or "").strip()
        if vd:
            parts.append(vd)

        anchor = (getattr(scene, "visual_anchor", "") or "").strip()
        if anchor:
            parts.append(f"visual anchor: {anchor}")

        motion = (getattr(scene, "motion_intent", "") or "").strip()
        if motion:
            parts.append(f"motion: {motion}")

        dialogue_motion = build_dialogue_motion_hints(scene)
        if dialogue_motion:
            parts.append(f"character acting: {dialogue_motion}")

        cm = (getattr(scene, "camera_movement", "") or "").strip()
        if cm and cm != "静态":
            parts.append(f"camera: {cm}")

        mood = (getattr(scene, "mood", "") or "").strip()
        if mood:
            parts.append(f"mood: {mood}")

        if anime:
            parts.append(
                "2D anime character animation, smooth motion, character gestures while speaking"
            )
        else:
            parts.append(
                "smooth coherent motion, cinematic lighting"
            )
        text = ", ".join(p for p in parts if p)
        return text[:500]

    def _zhipu_generate_video(self, api_key: str, payload: dict) -> str:
        """调用智谱清影视频生成 API。"""
        r = requests.post(
            "https://open.bigmodel.cn/api/paas/v4/videos/generations",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=120,
        )
        try:
            data = r.json()
        except Exception:
            data = {}
        if r.status_code != 200:
            msg = data.get("error", {}).get("message") if isinstance(data, dict) else None
            raise RuntimeError(
                f"智谱清影 videos/generations HTTP {r.status_code}: {msg or r.text[:500]}"
            )
        task_id = data.get("id")
        if not task_id:
            raise RuntimeError(f"智谱清影未返回任务 ID: {data}")
        return task_id

    def _zhipu_query_result(self, api_key: str, task_id: str) -> dict:
        """查询智谱清影异步任务结果。"""
        r = requests.get(
            f"https://open.bigmodel.cn/api/paas/v4/async-result/{task_id}",
            headers={
                "Authorization": f"Bearer {api_key}",
            },
            timeout=60,
        )
        try:
            data = r.json()
        except Exception:
            data = {}
        if r.status_code != 200:
            msg = data.get("error", {}).get("message") if isinstance(data, dict) else None
            raise RuntimeError(
                f"智谱清影 async-result HTTP {r.status_code}: {msg or r.text[:500]}"
            )
        return data if isinstance(data, dict) else {}

    def _generate_scene_video_zhipu(
        self,
        scene: StoryboardScene,
        filepath: str,
        on_progress=None,
        prev_scene=None,
        next_scene=None,
        story_meta=None,
        script_characters=None,
    ) -> None:
        """调用智谱清影图生视频并保存为 MP4。"""
        api_key = (self.config.get("zhipu_api_key") or "").strip()
        if not api_key:
            raise RuntimeError(
                "使用智谱清影图生视频请在设置中填写「智谱 API Key」。"
            )
        model = (self.config.get("zhipu_video_model") or "cogvideox-3").strip()
        prompt = self._build_zhipu_video_prompt(
            scene, prev_scene=prev_scene, next_scene=next_scene, story_meta=story_meta
        )
        ref_path = pick_scene_reference_image(scene, script_characters or [])
        first_frame = (self.config.get("character_ref_video_first_frame") or "scene_keyframe").strip().lower()
        i2v_image = scene.image_path
        if first_frame == "reference" and ref_path:
            i2v_image = ref_path
        image_url = self._image_to_base64_for_zhipu(i2v_image)

        size = (self.config.get("zhipu_video_size") or "1080x1920").strip()
        fps = int(self.config.get("zhipu_video_fps", 30))
        duration = int(self.config.get("zhipu_video_duration", 5))

        payload = {
            "model": model,
            "prompt": prompt,
            "image_url": image_url,
            "size": size,
            "fps": fps,
            "duration": duration,
            "quality": "quality",
        }

        print(f"[智谱清影] POST /paas/v4/videos/generations model={model}")
        if on_progress:
            on_progress(f"场景 {scene.scene_number} 已提交智谱清影图生视频（排队中）…")

        task_id = self._zhipu_generate_video(api_key, payload)

        poll_interval = max(3, int(self.config.get("zhipu_video_poll_interval", 5)))
        max_wait = max(180, int(self.config.get("zhipu_video_poll_timeout_sec", 1800)))
        deadline = time.monotonic() + max_wait
        last_status = ""
        poll_i = 0

        while time.monotonic() < deadline:
            data = self._zhipu_query_result(api_key, task_id)
            status = (data.get("task_status") or "").strip()
            if status and status != last_status:
                last_status = status
                if on_progress:
                    on_progress(
                        f"场景 {scene.scene_number} 智谱清影视频状态: {status}"
                    )

            if status == "SUCCESS":
                video_result = data.get("video_result") or []
                if not video_result:
                    raise RuntimeError(f"智谱清影成功但未返回视频地址: {data}")
                url = (video_result[0] or {}).get("url")
                if not url:
                    raise RuntimeError(f"智谱清影响应缺少 url: {data}")
                if on_progress:
                    on_progress(f"场景 {scene.scene_number} 正在下载视频…")
                vr = requests.get(url, timeout=300)
                if vr.status_code != 200:
                    raise RuntimeError(f"下载视频失败 HTTP {vr.status_code}")
                with open(filepath, "wb") as f:
                    f.write(vr.content)
                if os.path.getsize(filepath) < 1000:
                    raise RuntimeError("下载的视频文件过小，可能已损坏")
                scene.video_path = filepath
                if on_progress:
                    on_progress(f"场景 {scene.scene_number} 动态视频生成完成")
                return

            if status == "FAIL":
                reason = data.get("error", {}).get("message") or str(data)
                raise RuntimeError(f"智谱清影视频生成失败: {reason}")

            poll_i += 1
            if on_progress and poll_i % 6 == 0:
                on_progress(
                    f"场景 {scene.scene_number} 智谱清影排队/生成中（已等待约 "
                    f"{poll_i * poll_interval}s）…"
                )
            time.sleep(poll_interval)

        raise RuntimeError(
            f"智谱清影图生视频超时（>{max_wait}s），请稍后重试。"
        )

    def _build_parallax_layers(self, img_pil):
        """
        将图片分割为三层 PIL Image（背景/中景/前景），
        每层放大 10% 以便在偏移时不会露出黑边。
        
        注意：对于人像图片，不进行分割，保持完整。
        """
        w, h = img_pil.size
        
        # 检测是否为人像图片
        if self._is_portrait_image(img_pil):
            # 人像图片不分割，保持完整
            pad_w = int(w * 0.12)
            pad_h = int(h * 0.12)
            full_resized = img_pil.resize((w + 2 * pad_w, h + 2 * pad_h), Image.LANCZOS)
            
            return {
                "bg": {"img": full_resized, "y_start": 0, "height": h},
                "mg": None,
                "fg": None,
            }
        
        # 风景图片：分割为三层
        pad_w = int(w * 0.12)
        pad_h = int(h * 0.05)

        # 上 1/3：背景（天空、远景）
        bg_crop = img_pil.crop((0, 0, w, h // 3))
        bg_resized = bg_crop.resize((w + 2 * pad_w, h // 3 + 2 * pad_h), Image.LANCZOS)

        # 中 1/3：中景（建筑、角色上半身）
        mg_crop = img_pil.crop((0, h // 3, w, 2 * h // 3))
        mg_resized = mg_crop.resize((w + 2 * pad_w, h // 3 + 2 * pad_h), Image.LANCZOS)

        # 下 1/3：前景（地面、角色下半身）
        fg_crop = img_pil.crop((0, 2 * h // 3, w, h))
        fg_resized = fg_crop.resize((w + 2 * pad_w, h // 3 + 2 * pad_h), Image.LANCZOS)

        return {
            "bg": {"img": bg_resized, "y_start": 0, "height": h // 3},
            "mg": {"img": mg_resized, "y_start": h // 3, "height": h // 3},
            "fg": {"img": fg_resized, "y_start": 2 * h // 3, "height": h - 2 * h // 3},
        }
    
    def _is_portrait_image(self, img_pil):
        """
        简单检测是否为人像图片
        通过检测图片比例和中央区域的颜色对比度来判断
        """
        w, h = img_pil.size
        
        # 检查图片比例是否接近人像（竖版）
        if h / w > 1.2:
            # 在中央区域采样，检测是否有类似人脸的高对比度区域
            center_region = img_pil.crop((w//4, h//4, 3*w//4, 3*h//4))
            center_array = np.array(center_region)
            
            # 计算颜色标准差，人脸区域通常颜色变化较大
            std_dev = np.std(center_array)
            
            # 如果标准差较高，可能是人像
            if std_dev > 30:
                return True
        
        return False

    def _apply_simple_effects(
        self, img_pil, t, duration, progress, preset, particles, zoom_trend=0, anime_motion=False
    ):
        """
        简化版效果应用：不分割图片，保持完整显示
        应用简单的缩放、平移和颜色效果；anime_motion 时加大摇摆模拟「在动」。
        """
        from PIL import Image, ImageEnhance, ImageDraw
        
        w, h = self.width, self.height
        img_w, img_h = img_pil.size
        
        # 创建黑色背景
        canvas = Image.new("RGB", (w, h), (0, 0, 0))
        
        # 计算基础位置（居中）
        base_x = (w - img_w) // 2
        base_y = (h - img_h) // 2
        
        # 摇动 / 动漫式轻微「表演」位移
        shake_x = 2 * np.sin(t * 3.0) + 1 * np.sin(t * 5.0)
        shake_y = 2 * np.cos(t * 2.5) + 1 * np.cos(t * 4.5)
        if anime_motion:
            shake_x += 6 * np.sin(progress * np.pi * 6)
            shake_y += 8 * np.sin(progress * np.pi * 5 + 0.3)
        
        # 轻微的缩放效果（可随分镜文案做缓推/缓拉以增强叙事连贯感）
        zoom_range = preset.get("zoom_range", 0.03)
        if anime_motion:
            zoom_range = max(zoom_range, 0.05)
        if zoom_trend == 1:
            zoom = 1.0 + zoom_range * float(np.clip(progress, 0.0, 1.0))
        elif zoom_trend == -1:
            zoom = 1.0 + zoom_range * float(1.0 - np.clip(progress, 0.0, 1.0))
        else:
            zoom = 1.0 + zoom_range * np.sin(progress * np.pi * 2)
        
        # 应用缩放
        scaled_w = int(img_w * zoom)
        scaled_h = int(img_h * zoom)
        scaled_img = img_pil.resize((scaled_w, scaled_h), Image.LANCZOS)
        
        # 计算偏移后的位置
        offset_x = int(base_x - (scaled_w - img_w) // 2 + shake_x)
        offset_y = int(base_y - (scaled_h - img_h) // 2 + shake_y)
        
        # 确保图片在画布内
        offset_x = max(0, min(offset_x, w - scaled_w))
        offset_y = max(0, min(offset_y, h - scaled_h))
        
        # 粘贴到画布
        canvas.paste(scaled_img, (offset_x, offset_y))
        
        # 颜色增强
        enhancer = ImageEnhance.Color(canvas)
        canvas = enhancer.enhance(1.15)
        
        # 亮度变化
        brightness_var = preset.get("brightness_var", 0.06)
        brightness = 1.0 + brightness_var * np.sin(progress * np.pi * 3)
        enhancer = ImageEnhance.Brightness(canvas)
        canvas = enhancer.enhance(brightness)
        
        # 色温微调
        warm = preset.get("warm_shift", 0.04)
        if abs(warm) > 0.001:
            arr = np.array(canvas, dtype=np.int16)
            r_shift = int(15 * warm * np.sin(progress * np.pi * 2))
            g_shift = int(5 * warm * np.sin(progress * np.pi * 2.5))
            arr[:, :, 0] = np.clip(arr[:, :, 0] + r_shift, 0, 255)
            arr[:, :, 1] = np.clip(arr[:, :, 1] + g_shift, 0, 255)
            canvas = Image.fromarray(arr.astype(np.uint8))
        
        # 粒子特效
        if particles:
            draw = ImageDraw.Draw(canvas, "RGBA")
            for p in particles:
                px = int(p["x"] + p["vx"] * t)
                py = int(p["y"] + p["vy"] * t)
                px = px % w
                py = py % h
                
                alpha = int(p["alpha"] * (0.5 + 0.5 * np.sin(progress * np.pi * 2 + p["phase"])))
                alpha = max(0, min(255, alpha))
                
                ptype = p["type"]
                size = p["size"]
                
                if ptype == "bokeh":
                    for offset in range(size, 0, -2):
                        a = int(alpha * (offset / size) * 0.3)
                        draw.ellipse(
                            [px - offset, py - offset, px + offset, py + offset],
                            fill=(255, 240, 220, a)
                        )
                elif ptype == "rain":
                    length = size
                    draw.line(
                        [(px, py), (px + 2, py + length)],
                        fill=(200, 210, 255, alpha),
                        width=1
                    )
                elif ptype == "petal":
                    draw.ellipse(
                        [px - size, py - size // 2, px + size, py + size // 2],
                        fill=(255, 180, 200, alpha)
                    )
                elif ptype == "spark":
                    draw.ellipse(
                        [px - size, py - size, px + size, py + size],
                        fill=(255, 200, 100, alpha)
                    )
                elif ptype == "fog":
                    draw.ellipse(
                        [px - size, py - size, px + size, py + size],
                        fill=(180, 180, 200, int(alpha * 0.2))
                    )
        
        # 电影感暗角
        vignette_strength = 0.3 + 0.1 * np.sin(progress * np.pi * 2)
        arr = np.array(canvas, dtype=np.float32)
        y_coords, x_coords = np.mgrid[0:h, 0:w]
        cx, cy = w / 2, h / 2
        max_dist = np.sqrt(cx**2 + cy**2)
        dist = np.sqrt((x_coords - cx)**2 + (y_coords - cy)**2) / max_dist
        vignette = 1.0 - vignette_strength * dist**2
        vignette = vignette[:, :, np.newaxis]
        arr = np.clip(arr * vignette, 0, 255).astype(np.uint8)
        
        return arr

    def _apply_effects(
        self, img_array, t, duration, progress, preset, particles
    ):
        """
        对每一帧应用动态特效（旧版本，保留用于兼容）
        """
        h, w = img_array.shape[:2]
        parallax = preset.get("parallax", 0.02)

        # === 1. 三层视差偏移 ===
        # 基础摇镜头运动
        base_x = w * parallax * np.sin(progress * np.pi * 1.5)
        base_y = h * parallax * 0.3 * np.cos(progress * np.pi * 1.2)

        # 手持微震（因为定格帧已吸附到 8fps，这里用 t 的整数部分避免跳变）
        shake_x = 2 * np.sin(t * 3.0) + 1 * np.sin(t * 5.0)
        shake_y = 2 * np.cos(t * 2.5) + 1 * np.cos(t * 4.5)

        # 合成画布
        canvas = Image.new("RGB", (w, h), (0, 0, 0))
        layers = getattr(self, "_layer_imgs", None)

        if layers:
            # 检查是否是人像模式（只有bg层）
            is_portrait = layers.get("mg") is None and layers.get("fg") is None
            
            if is_portrait:
                # 人像模式：整体移动，不分割
                layer = layers["bg"]
                layer_img = layer["img"]
                lw, lh = layer_img.size
                
                ox = int(base_x * 0.5 + shake_x * 0.5)
                oy = int(base_y * 0.5 + shake_y * 0.5)
                
                crop_x = (lw - w) // 2 + ox
                crop_y = (lh - h) // 2 + oy
                crop_x = max(0, min(crop_x, lw - w))
                crop_y = max(0, min(crop_y, lh - h))
                
                cropped = layer_img.crop((
                    crop_x, crop_y,
                    crop_x + w, crop_y + h
                ))
                
                canvas.paste(cropped, (0, 0))
            else:
                # 风景模式：三层视差合成
                speed_factors = {"bg": 0.3, "mg": 0.6, "fg": 1.0}

                for key, layer in layers.items():
                    if layer is None:
                        continue
                    factor = speed_factors[key]
                    ox = int(base_x * factor + shake_x * factor)
                    oy = int(base_y * factor + shake_y * factor)

                    layer_img = layer["img"]
                    lw, lh = layer_img.size

                    # 从放大的图层中裁剪出 w x layer_height 的区域
                    crop_x = (lw - w) // 2 + ox
                    crop_y = (lh - layer["height"]) // 2 + oy
                    crop_x = max(0, min(crop_x, lw - w))
                    crop_y = max(0, min(crop_y, lh - layer["height"]))

                    cropped = layer_img.crop((
                        crop_x, crop_y,
                        crop_x + w, crop_y + layer["height"]
                    ))

                    # 粘贴到画布对应位置
                    canvas.paste(cropped, (0, layer["y_start"]))
        else:
            # 降级：没有图层信息时，整体偏移
            img_fallback = Image.fromarray(img_array)
            ox = int(base_x + shake_x)
            oy = int(base_y + shake_y)
            canvas.paste(img_fallback, (ox, oy))

        img = canvas

        # === 4. 动画风格色采增强 ===
        # 增加饱和度（动画通常色彩更鲜艳）
        enhancer = ImageEnhance.Color(img)
        img = enhancer.enhance(1.15)
        # 轻微增加亮度
        enhancer = ImageEnhance.Brightness(img)
        img = enhancer.enhance(1.05)
        # 轻微锐化（让边缘更清晰，有"绘制感"）
        enhancer = ImageEnhance.Sharpness(img)
        img = enhancer.enhance(1.2)

        # === 5. 环境光流动（亮度微妙变化）===
        brightness_var = preset["brightness_var"]
        brightness = 1.0 + brightness_var * np.sin(progress * np.pi * 3)
        enhancer = ImageEnhance.Brightness(img)
        img = enhancer.enhance(brightness)

        # === 6. 色温微调 ===
        warm = preset["warm_shift"]
        if abs(warm) > 0.001:
            r_shift = int(15 * warm * np.sin(progress * np.pi * 2))
            g_shift = int(5 * warm * np.sin(progress * np.pi * 2.5))
            arr = np.array(img, dtype=np.int16)
            arr[:, :, 0] = np.clip(arr[:, :, 0] + r_shift, 0, 255)
            arr[:, :, 1] = np.clip(arr[:, :, 1] + g_shift, 0, 255)
            img = Image.fromarray(arr.astype(np.uint8))

        # === 7. 粒子特效 ===
        if particles:
            draw = ImageDraw.Draw(img, "RGBA")
            for p in particles:
                px = int(p["x"] + p["vx"] * t)
                py = int(p["y"] + p["vy"] * t)
                px = px % w
                py = py % h

                alpha = int(p["alpha"] * (0.5 + 0.5 * np.sin(progress * np.pi * 2 + p["phase"])))
                alpha = max(0, min(255, alpha))

                ptype = p["type"]
                size = p["size"]

                if ptype == "bokeh":
                    for offset in range(size, 0, -2):
                        a = int(alpha * (offset / size) * 0.3)
                        draw.ellipse(
                            [px - offset, py - offset, px + offset, py + offset],
                            fill=(255, 240, 220, a)
                        )
                elif ptype == "rain":
                    length = size
                    draw.line(
                        [(px, py), (px + 2, py + length)],
                        fill=(200, 210, 255, alpha),
                        width=1
                    )
                elif ptype == "petal":
                    draw.ellipse(
                        [px - size, py - size // 2, px + size, py + size // 2],
                        fill=(255, 180, 200, alpha)
                    )
                elif ptype == "spark":
                    draw.ellipse(
                        [px - size, py - size, px + size, py + size],
                        fill=(255, 200, 100, alpha)
                    )
                elif ptype == "fog":
                    draw.ellipse(
                        [px - size, py - size, px + size, py + size],
                        fill=(180, 180, 200, int(alpha * 0.2))
                    )

        # === 8. 电影感暗角（呼吸） ===
        vignette_strength = 0.3 + 0.1 * np.sin(progress * np.pi * 2)
        arr = np.array(img, dtype=np.float32)
        y_coords, x_coords = np.mgrid[0:h, 0:w]
        cx, cy = w / 2, h / 2
        max_dist = np.sqrt(cx**2 + cy**2)
        dist = np.sqrt((x_coords - cx)**2 + (y_coords - cy)**2) / max_dist
        vignette = 1.0 - vignette_strength * dist**2
        vignette = vignette[:, :, np.newaxis]
        arr = np.clip(arr * vignette, 0, 255).astype(np.uint8)

        return arr

    def _generate_particles(self, particle_type: str, duration: float) -> list:
        """预生成粒子数据"""
        if particle_type == "none":
            return []

        count = {
            "bokeh": 15,
            "rain": 40,
            "petal": 12,
            "spark": 20,
            "fog": 10,
        }.get(particle_type, 10)

        w, h = self.width, self.height
        particles = []

        for _ in range(count):
            p = {
                "type": particle_type,
                "x": random.uniform(0, w),
                "y": random.uniform(-h * 0.3, h),
                "vx": random.uniform(-30, 30),
                "vy": random.uniform(20, 80) if particle_type != "fog" else random.uniform(-5, 5),
                "size": random.randint(3, 15) if particle_type != "fog" else random.randint(40, 120),
                "alpha": random.randint(40, 180),
                "phase": random.uniform(0, np.pi * 2),
            }
            if particle_type == "rain":
                p["vy"] = random.uniform(200, 400)
                p["vx"] = random.uniform(-10, 10)
                p["size"] = random.randint(8, 20)
            if particle_type == "fog":
                p["vy"] = random.uniform(-10, 10)
                p["vx"] = random.uniform(-15, 15)

            particles.append(p)

        return particles

    def generate_all_videos(
        self,
        scenes: list,
        output_dir: str,
        on_progress=None,
        story_meta=None,
        script_characters=None,
    ) -> list:
        """批量生成所有场景的动态视频；story_meta 传 title/theme 等以增强连贯提示。"""
        video_paths = []
        total = len(scenes)
        prev = None

        for i, scene in enumerate(scenes):
            def progress_wrapper(msg):
                if on_progress:
                    on_progress(i + 1, total, msg)

            nxt = scenes[i + 1] if i + 1 < total else None
            filepath = self.generate_scene_video(
                scene,
                output_dir,
                progress_wrapper,
                prev_scene=prev,
                next_scene=nxt,
                story_meta=story_meta,
                script_characters=script_characters,
            )
            video_paths.append(filepath)
            prev = scene

        return video_paths
