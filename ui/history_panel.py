"""
AI短剧生成器 - 历史记录面板
"""
import os
from typing import Optional, Dict, Any, Callable

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QMessageBox, QSizePolicy,
    QGroupBox, QFrame,
)
from PyQt5.QtCore import Qt, pyqtSignal, QSize
from PyQt5.QtGui import QPixmap, QFont, QIcon

from core.history_manager import list_records, delete_record, clear_all, load_script_by_id

THUMB_W, THUMB_H = 60, 80


class HistoryPanel(QWidget):
    """历史记录面板，可嵌入主窗口。"""

    load_requested = pyqtSignal(object)   # 发射加载的 script dict
    detail_requested = pyqtSignal(object)  # 发射选中的 record dict

    def __init__(self, parent=None):
        super().__init__(parent)
        self._records = []
        self._init_ui()
        self.refresh()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.btn_refresh = QPushButton("刷新")
        self.btn_refresh.setObjectName("btnSecondary")
        self.btn_refresh.setFixedHeight(32)
        self.btn_refresh.clicked.connect(self.refresh)
        btn_row.addWidget(self.btn_refresh)

        self.btn_load = QPushButton("加载选中剧本")
        self.btn_load.setFixedHeight(32)
        self.btn_load.clicked.connect(self._on_load)
        btn_row.addWidget(self.btn_load)

        self.btn_delete = QPushButton("删除选中")
        self.btn_delete.setObjectName("btnSecondary")
        self.btn_delete.setFixedHeight(32)
        self.btn_delete.clicked.connect(self._on_delete)
        btn_row.addWidget(self.btn_delete)

        self.btn_clear = QPushButton("清空全部")
        self.btn_clear.setFixedHeight(32)
        self.btn_clear.setStyleSheet(
            "QPushButton { background: #c0392b; color: white; border-radius: 6px; "
            "padding: 6px 10px; font-size: 12px; min-height: 32px; }"
            "QPushButton:hover { background: #e74c3c; }"
        )
        self.btn_clear.clicked.connect(self._on_clear)
        btn_row.addWidget(self.btn_clear)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.list_widget = QListWidget()
        self.list_widget.setIconSize(QSize(THUMB_W, THUMB_H))
        self.list_widget.setSpacing(4)
        self.list_widget.currentRowChanged.connect(self._on_selection_changed)
        self.list_widget.itemDoubleClicked.connect(lambda _: self._on_load())
        layout.addWidget(self.list_widget, 1)

        self.detail_label = QLabel("双击记录可快速加载剧本")
        self.detail_label.setStyleSheet("color: #8892b0; font-size: 12px;")
        self.detail_label.setWordWrap(True)
        layout.addWidget(self.detail_label)

    def refresh(self):
        self._records = list_records()
        self.list_widget.clear()
        if not self._records:
            item = QListWidgetItem("暂无历史记录")
            item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
            self.list_widget.addItem(item)
            self.btn_load.setEnabled(False)
            self.btn_delete.setEnabled(False)
            return

        for rec in self._records:
            title = rec.get("title", "未命名")
            style = rec.get("style", "")
            created = rec.get("created_at", "")
            scenes = rec.get("scene_count", 0)
            chars = ", ".join(rec.get("characters", []))

            line1 = f"{title}"
            line2 = f"  {style} | {scenes}个场景 | {created}"
            if chars:
                line2 += f" | {chars}"

            item = QListWidgetItem()
            item.setText(f"{line1}\n{line2}")
            item.setData(Qt.UserRole, rec)

            thumb_path = rec.get("thumbnail_path", "")
            if thumb_path and os.path.isfile(thumb_path):
                pixmap = QPixmap(thumb_path)
                if not pixmap.isNull():
                    item.setIcon(QIcon(pixmap.scaled(
                        THUMB_W, THUMB_H,
                        Qt.KeepAspectRatio, Qt.SmoothTransformation,
                    )))

            item.setSizeHint(QSize(200, max(THUMB_H + 12, 56)))
            self.list_widget.addItem(item)

        self.btn_load.setEnabled(False)
        self.btn_delete.setEnabled(False)

    def _on_selection_changed(self, row: int):
        has = 0 <= row < len(self._records)
        self.btn_load.setEnabled(has)
        self.btn_delete.setEnabled(has)
        if has:
            rec = self._records[row]
            info = (
                f"标题: {rec.get('title', '')}\n"
                f"风格: {rec.get('style', '')}  |  "
                f"场景数: {rec.get('scene_count', 0)}  |  "
                f"创建: {rec.get('created_at', '')}\n"
                f"角色: {', '.join(rec.get('characters', []))}\n"
                f"视频: {rec.get('video_path', '无')}"
            )
            self.detail_label.setText(info)
            self.detail_requested.emit(rec)
        else:
            self.detail_label.setText("双击记录可快速加载剧本")

    def _get_selected_id(self) -> Optional[str]:
        row = self.list_widget.currentRow()
        if 0 <= row < len(self._records):
            return self._records[row].get("id")
        return None

    def _on_load(self):
        rec_id = self._get_selected_id()
        if not rec_id:
            QMessageBox.information(self, "提示", "请先选择一条历史记录。")
            return
        script = load_script_by_id(rec_id)
        if not script:
            QMessageBox.warning(self, "错误", "无法加载该记录的剧本文件，可能已被删除。")
            self.refresh()
            return
        self.load_requested.emit(script)

    def _on_delete(self):
        rec_id = self._get_selected_id()
        if not rec_id:
            return
        rec = next((r for r in self._records if r.get("id") == rec_id), None)
        title = rec.get("title", "") if rec else ""
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除历史记录「{title}」吗？\n对应的剧本文件也会被删除。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            delete_record(rec_id)
            self.refresh()

    def _on_clear(self):
        if not self._records:
            return
        reply = QMessageBox.question(
            self, "确认清空",
            f"确定要清空全部 {len(self._records)} 条历史记录吗？\n此操作不可撤销。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            count = clear_all()
            QMessageBox.information(self, "完成", f"已清空 {count} 条历史记录。")
            self.refresh()
