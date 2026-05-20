"""
角色参考图弹窗（大窗口版，与主界面面板共用逻辑）。
"""
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QPushButton, QHBoxLayout, QSizePolicy,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from ui.character_refs_panel import CharacterRefsPanel, THUMB_H_DIALOG, THUMB_H, _BTN_STYLE_PRIMARY, _BTN_STYLE_SECONDARY


class CharacterRefsDialog(QDialog):
    def __init__(self, script: dict, parent=None):
        super().__init__(parent)
        self.script = script
        self.setWindowTitle("角色参考图 — 多人物分别上传")
        # 大窗口：一屏内可舒适编辑多角色
        self.setMinimumSize(1100, 720)
        self.resize(1200, 800)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        scroll_h = max(520, THUMB_H_DIALOG + 240)
        self.panel = CharacterRefsPanel(self, scroll_min_height=scroll_h, large_cards=True)
        self.panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.panel.set_script(script)
        layout.addWidget(self.panel, stretch=1)

        btns = QHBoxLayout()
        btns.setSpacing(16)
        btns.addStretch()
        save_btn = QPushButton("保存并关闭")
        save_btn.setMinimumSize(160, 48)
        save_btn.setStyleSheet(_BTN_STYLE_PRIMARY)
        save_btn.setFont(QFont("Microsoft YaHei", 14))
        save_btn.clicked.connect(self._save_and_close)
        cancel_btn = QPushButton("取消")
        cancel_btn.setMinimumSize(120, 48)
        cancel_btn.setStyleSheet(_BTN_STYLE_SECONDARY)
        cancel_btn.setFont(QFont("Microsoft YaHei", 14))
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(save_btn)
        btns.addWidget(cancel_btn)
        layout.addLayout(btns)

    def _save_and_close(self):
        if self.panel.apply_to_script(self.script):
            self.accept()
