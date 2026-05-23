"""
单镜 AI 改写：输入修改指令，由 DeepSeek 重写该场景 JSON。
"""
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QTextEdit, QDialogButtonBox,
)


class SceneRewriteDialog(QDialog):
    def __init__(self, scene: dict, parent=None):
        super().__init__(parent)
        num = scene.get("scene_number", "")
        self.setWindowTitle(f"AI 改写场景 {num}")
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "描述希望如何修改本镜（剧情、台词、氛围、动作等）：\n"
            "例如：把对话改得更搞笑；加强反转；让主角更生气。"
        ))

        self.input_edit = QTextEdit()
        self.input_edit.setPlaceholderText("请输入修改指令…")
        self.input_edit.setMinimumHeight(120)
        layout.addWidget(self.input_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_instruction(self) -> str:
        return self.input_edit.toPlainText().strip()
