"""
AI短剧生成器 - 剧本生成模块
调用DeepSeek API生成短剧剧本
"""
import json
import re
from openai import OpenAI
from config import load_config
from logger import get_logger
from prompts.story_prompt import build_story_prompt, is_comedy_style
from core.storyboard import ensure_scene_continuity_fields, strengthen_script_continuity

logger = get_logger("story_generator")


class StoryGenerator:
    """剧本生成器"""

    def __init__(self):
        self.config = load_config()
        self.client = None

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

    def generate(self, user_input: str, style: str = "短剧",
                 on_progress=None) -> dict:
        """
        根据用户输入生成短剧剧本

        Args:
            user_input: 用户输入的故事主题/关键词
            style: 故事风格
            on_progress: 进度回调函数 fn(message: str)

        Returns:
            剧本字典（解析后的JSON）
        """
        logger.info(f"开始生成剧本，主题: {user_input[:50]}..., 风格: {style}")
        
        if on_progress:
            on_progress("正在构思剧本...")

        self.config = load_config()
        visual_style = self.config.get("visual_style", "live_action")
        if style in ("动漫短片",):
            visual_style = "anime_cartoon"
        prompt = build_story_prompt(user_input, style, visual_style=visual_style)
        client = self._get_client()
        temperature = 0.92 if is_comedy_style(style) else 0.88

        if on_progress:
            on_progress("AI正在创作剧本，请稍候...")

        content = ""
        try:
            response = client.chat.completions.create(
                model=self.config.get("deepseek_model", "deepseek-chat"),
                messages=[
                    {"role": "system", "content": "你只输出合法 JSON，不输出 markdown 说明。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=temperature,
                max_tokens=8192,
            )

            # 兼容 openai 1.x / 2.x：content 可能为 None
            raw_content = response.choices[0].message.content
            if raw_content is None:
                raise ValueError("DeepSeek API 返回内容为空，请检查 API Key 是否有效或账户余额是否充足")
            content = raw_content.strip()

            if not content:
                raise ValueError("DeepSeek API 返回了空内容，请重试")

            if on_progress:
                on_progress("正在解析剧本...")

            # 提取JSON内容（处理可能的markdown代码块包裹）
            script = self._parse_json_with_fallback(content)

            # 验证剧本结构
            self._validate_script(script)

            if on_progress:
                on_progress("正在优化分镜连贯性（承上启下）...")

            script = self._refine_continuity_with_llm(script, user_input, style)
            strengthen_script_continuity(script)

            scene_count = len(script.get('scenes', []))
            logger.info(f"剧本生成完成，共 {scene_count} 个场景")
            
            if on_progress:
                on_progress(f"剧本生成完成！共 {scene_count} 个场景")

            return script

        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {e}")
            raise ValueError(f"AI返回的剧本格式有误，无法解析JSON: {e}\n原始内容: {content[:500]}")
        except (ValueError, RuntimeError) as e:
            logger.error(f"剧本生成失败: {e}")
            raise
        except Exception as e:
            logger.error(f"剧本生成异常: {e}")
            raise RuntimeError(f"剧本生成失败: {e}")

    def _extract_json(self, text: str) -> str:
        """从AI返回的文本中提取JSON"""
        # 尝试直接解析
        text = text.strip()

        # 处理 ```json ... ``` 包裹
        if text.startswith("```"):
            # 移除开头的 ```json 或 ```
            text = re.sub(r'^```(?:json)?\s*\n?', '', text)
            # 移除结尾的 ```
            text = re.sub(r'\n?```\s*$', '', text)
            text = text.strip()

        # 查找最外层的 { } 或 [ ]
        if text.startswith('{'):
            # 找到最后一个 }
            last_brace = text.rfind('}')
            if last_brace > 0:
                text = text[:last_brace + 1]
        elif text.startswith('['):
            last_bracket = text.rfind(']')
            if last_bracket > 0:
                text = text[:last_bracket + 1]

        return text

    @staticmethod
    def _fix_json(json_str: str) -> str:
        """
        修复常见的AI返回JSON格式错误：
        - 缺少逗号（如 }后直接跟 {，或 ]后直接跟 ,）
        - 尾部多余逗号（如 [1,2,3,]）
        - 单引号替换为双引号
        - 中文标点替换为英文标点
        - 注释移除
        """
        s = json_str.strip()

        # 移除 JSON 中的 // 和 /* */ 注释（避免干扰内容中的斜杠）
        s = re.sub(r'//[^\n]*', '', s)
        s = re.sub(r'/\*.*?\*/', '', s, flags=re.DOTALL)

        # 中文标点 → 英文标点（仅在 JSON 结构字符处）
        s = s.replace('\uff1a', ':')    # ：→ :
        s = s.replace('\uff0c', ',')    # ，→ ,
        s = s.replace('\u300a', '"')    # 《→ "
        s = s.replace('\u300b', '"')    # 》→ "

        # 修复 "key": "value" 后缺少逗号的情况
        # 在 } 或 ] 后面紧跟 { 或 [ 或 " 时插入逗号
        # 但排除 key: { 和 key: [ 的合法情况
        # 匹配模式：数字/字符串/布尔/null/}/] 结束，紧接着 {/[/"
        s = re.sub(
            r'(?<=[0-9"\]}\w])\s*\n\s*(?=[\[{"])',
            r',\n',
            s
        )
        # 更精确：} 或 ] 后直接跟 { 或 [ 时插入逗号
        s = re.sub(r'(?<=[\]}])\s*(?=[\[{"])', r', ', s)
        # } 或 ] 后直接跟 "（新键名）时插入逗号
        s = re.sub(r'(?<=[\]}\n])\s*\n(\s*")', r',\n\1', s)

        # 移除尾逗号：], 或 },  → ] 或 }
        s = re.sub(r',\s*([}\]])', r'\1', s)

        return s

    def _parse_json_with_fallback(self, content: str) -> dict:
        """
        多级容错的 JSON 解析：
        1. 直接解析
        2. 修复常见错误后解析
        3. 使用正则暴力提取所有字段
        """
        # 第一轮：直接解析
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # 第二轮：提取 JSON 块
        json_str = self._extract_json(content)
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass

        # 第三轮：修复后解析
        fixed = self._fix_json(json_str)
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            pass

        # 第四轮：如果还有错，尝试逐字符修复（处理控制字符等）
        try:
            # 移除所有控制字符（保留换行和制表符）
            cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', fixed)
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            # 最终仍然失败，给出有用错误信息
            # 尝试定位错误位置附近的内容
            err_pos = e.pos if hasattr(e, 'pos') else 0
            context = fixed[max(0, err_pos - 50):err_pos + 50] if fixed else json_str
            raise ValueError(
                f"AI返回的JSON多次修复仍无法解析。\n"
                f"错误位置附近: ...{context}...\n"
                f"原始错误: {e}\n"
                f"原始内容前500字: {content[:500]}"
            )

    def _refine_continuity_with_llm(
        self, script: dict, user_input: str, style: str
    ) -> dict:
        """
        二次调用 DeepSeek：只优化各镜 story_beat / continuity_from_previous / leads_to_next，
        使分镜承上启下、因果清晰。失败则返回原剧本。
        """
        scenes = script.get("scenes") or []
        if len(scenes) < 2:
            return script

        outline = []
        for s in scenes:
            if not isinstance(s, dict):
                continue
            outline.append({
                "scene_number": s.get("scene_number"),
                "location": s.get("location"),
                "story_beat": s.get("story_beat"),
                "continuity_from_previous": s.get("continuity_from_previous"),
                "leads_to_next": s.get("leads_to_next"),
                "narration": (s.get("narration") or "")[:80],
                "dialogues": s.get("dialogues"),
                "visual_description": (s.get("visual_description") or "")[:100],
            })

        prompt = f"""你是短视频分镜连贯性编辑。下面是一部竖屏短剧的分镜大纲（主题：{user_input}，风格：{style}）。

请只优化每一镜的「承上启下」，使观众能清楚看懂因果链，禁止空泛套话。

要求：
1. continuity_from_previous：第1镜写开场；第N镜(N≥2)必须具体写出上一镜结尾发生了什么、本镜如何接上（可引用台词/道具/地点）。
2. leads_to_next：写出本镜结尾状态，下一镜将如何接（最后一镜写收束）。
3. story_beat：本镜在主线中的作用（铺垫/升级/笑点/反转/收束等）。
4. 不要改 scene_number、location、dialogues、visual_description 等其他字段。

分镜大纲：
{json.dumps(outline, ensure_ascii=False, indent=2)}

请输出 JSON，格式：
{{"scenes": [{{"scene_number": 1, "story_beat": "...", "continuity_from_previous": "...", "leads_to_next": "..."}}, ...]}}
只输出 JSON。"""

        try:
            client = self._get_client()
            response = client.chat.completions.create(
                model=self.config.get("deepseek_model", "deepseek-chat"),
                messages=[
                    {"role": "system", "content": "你只输出合法 JSON。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.5,
                max_tokens=4096,
            )
            raw = (response.choices[0].message.content or "").strip()
            if not raw:
                return script
            patch = self._parse_json_with_fallback(raw)
            patched = {int(s.get("scene_number", i + 1)): s for i, s in enumerate(patch.get("scenes") or []) if isinstance(s, dict)}
            for i, scene in enumerate(scenes):
                if not isinstance(scene, dict):
                    continue
                num = int(scene.get("scene_number", i + 1))
                p = patched.get(num)
                if not p:
                    continue
                for key in ("story_beat", "continuity_from_previous", "leads_to_next"):
                    val = (p.get(key) or "").strip()
                    if val:
                        scene[key] = val
        except Exception as e:
            print(f"警告：分镜连贯性二次优化失败，使用原剧本：{e}")
        return script

    def _validate_script(self, script: dict):
        """验证剧本结构完整性"""
        required_fields = ["title", "scenes"]
        for field in required_fields:
            if field not in script:
                raise ValueError(f"剧本缺少必要字段: {field}")

        if not script["scenes"]:
            raise ValueError("剧本没有场景内容")

        ensure_scene_continuity_fields(script)

        for i, scene in enumerate(script["scenes"]):
            if "visual_description" not in scene:
                raise ValueError(f"场景 {i+1} 缺少 visual_description（画面描述）")
            # 默认时长
            if "duration" not in scene:
                scene["duration"] = 4.0
            # 如果场景没旁白没对话，补充默认旁白（不抛异常）
            has_narration = bool(scene.get("narration", "").strip())
            has_dialogue = bool(scene.get("dialogues"))
            if not has_narration and not has_dialogue:
                scene["narration"] = f"[场景 {i+1}]"
                scene["dialogues"] = []

    def regenerate_scene(self, script: dict, scene_index: int,
                         instruction: str, on_progress=None) -> dict:
        """重新生成指定场景"""
        scene = script["scenes"][scene_index]
        prompt = f"""你是一位专业的短剧编剧。请根据以下指令修改指定场景。

原场景：
{json.dumps(scene, ensure_ascii=False, indent=2)}

修改指令：{instruction}

请输出修改后的完整场景JSON，格式保持一致，直接输出JSON不要其他内容。"""

        if on_progress:
            on_progress(f"正在重新生成场景 {scene_index + 1}...")

        client = self._get_client()
        response = client.chat.completions.create(
            model=self.config.get("deepseek_model", "deepseek-chat"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=2048,
        )

        content = response.choices[0].message.content
        if content is None:
            raise ValueError("DeepSeek API 返回内容为空")
        content = content.strip()
        new_scene = self._parse_json_with_fallback(content)
        script["scenes"][scene_index] = new_scene

        return script
