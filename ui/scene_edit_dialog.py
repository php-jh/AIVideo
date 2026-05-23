"""
分镜就地编辑：旁白、台词、时长、画面描述等。
"""
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QTextEdit, QDoubleSpinBox,
    QDialogButtonBox, QLabel, QMessageBox,
)
from PyQt5.QtGui import QFont


def _dialogues_to_text(dialogues: list) -> str:
    lines = []
    for d in dialogues or []:
        if not isinstance(d, dict):
            continue
        char = (d.get("character") or "").strip()
        line = (d.get("line") or "").strip()
        emo = (d.get("emotion") or "").strip()
        if char and line:
            lines.append(f"{char}: {line}" + (f" [{emo}]" if emo else ""))
        elif line:
            lines.append(line)
    return "\n".join(lines)


def _text_to_dialogues(text: str, old_dialogues: list = None) -> list:
    gender_map = {}
    for d in old_dialogues or []:
        if isinstance(d, dict) and d.get("character"):
            gender_map[d["character"]] = d.get("gender", "male")
    dialogues = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        emotion = ""
        if line.endswith("]") and " [" in line:
            body, _, tail = line.rpartition(" [")
            if tail.endswith("]"):
                emotion = tail[:-1].strip()
                line = body.strip()
        if ":" in line:
            char, _, content = line.partition(":")
            char, content = char.strip(), content.strip()
            if char and content:
                entry = {
                    "character": char,
                    "line": content,
                    "gender": gender_map.get(char, "male"),
                }
                if emotion:
                    entry["emotion"] = emotion
                dialogues.append(entry)
        else:
            dialogues.append({"character": "旁白", "line": line, "gender": "male"})
    return dialogues


class SceneEditDialog(QDialog):
    """编辑单个分镜字段。"""

    def __init__(self, scene: dict, parent=None):
        super().__init__(parent)
        self.scene = scene
        self.setWindowTitle(f"编辑场景 {scene.get('scene_number', '')}")
        self.setMinimumWidth(520)
        self.setMinimumHeight(480)
        layout = QVBoxLayout(self)

        hint = QLabel(
            "对话每行格式：角色名: 台词内容\n"
            "可选情绪：角色名: 台词 [开心]"
        )
        hint.setStyleSheet("color: #8892b0; font-size: 12px;")
        layout.addWidget(hint)

        form = QFormLayout()
        self.duration_spin = QDoubleSpinBox()
        self.duration_spin.setRange(1.0, 30.0)
        self.duration_spin.setSingleStep(0.5)
        self.duration_spin.setValue(float(scene.get("duration") or 4.0))
        form.addRow("时长(秒):", self.duration_spin)

        self.narration_edit = QTextEdit()
        self.narration_edit.setPlainText(scene.get("narration", "") or "")
        self.narration_edit.setMaximumHeight(80)
        form.addRow("旁白:", self.narration_edit)

        self.dialogues_edit = QTextEdit()
        self.dialogues_edit.setPlainText(_dialogues_to_text(scene.get("dialogues", [])))
        self.dialogues_edit.setFont(QFont("Microsoft YaHei", 10))
        form.addRow("对话:", self.dialogues_edit)

        self.visual_edit = QTextEdit()
        self.visual_edit.setPlainText(scene.get("visual_description", "") or "")
        form.addRow("画面描述:", self.visual_edit)

        self.motion_edit = QTextEdit()
        self.motion_edit.setPlainText(scene.get("motion_intent", "") or "")
        self.motion_edit.setMaximumHeight(60)
        form.addRow("动作意图:", self.motion_edit)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_accept(self):
        if not self.narration_edit.toPlainText().strip() and not self.dialogues_edit.toPlainText().strip():
            QMessageBox.warning(self, "提示", "旁白与对话不能同时为空。")
            return
        self.accept()

    def apply_to_scene(self) -> dict:
        """将编辑结果写回 scene 字典。"""
        self.scene["duration"] = float(self.duration_spin.value())
        self.scene["narration"] = self.narration_edit.toPlainText().strip()
        self.scene["dialogues"] = _text_to_dialogues(
            self.dialogues_edit.toPlainText(),
            self.scene.get("dialogues"),
        )
        self.scene["visual_description"] = self.visual_edit.toPlainText().strip()
        self.scene["motion_intent"] = self.motion_edit.toPlainText().strip()
        for key in ("image_path", "video_path", "audio_path"):
            self.scene.pop(key, None)
        return self.scene
