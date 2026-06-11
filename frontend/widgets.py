"""
widgets.py - reusable UI pieces for the ClipperX app.
"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFileDialog, QFrame, QLabel, QVBoxLayout

VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".avi", ".m4v", ".webm")


class DropZone(QFrame):
    """A large drag-and-drop target that also opens a file dialog on click."""

    fileDropped = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setMinimumHeight(260)
        self.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        self.icon = QLabel("⤓")  # downwards arrow to bar
        self.icon.setObjectName("DropIcon")
        self.icon.setAlignment(Qt.AlignCenter)
        self.title = QLabel("Drop a 16:9 video here")
        self.title.setObjectName("DropTitle")
        self.title.setAlignment(Qt.AlignCenter)
        self.sub = QLabel("or click to browse  ·  mp4, mov, mkv…")
        self.sub.setObjectName("DropSub")
        self.sub.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.icon)
        layout.addWidget(self.title)
        layout.addWidget(self.sub)

    def mousePressEvent(self, event):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose a video", "",
            "Videos (*.mp4 *.mov *.mkv *.avi *.m4v *.webm)")
        if path:
            self.fileDropped.emit(path)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and self._is_video(event):
            event.acceptProposedAction()
            self.setProperty("hover", True)
            self._restyle()

    def dragLeaveEvent(self, event):
        self.setProperty("hover", False)
        self._restyle()

    def dropEvent(self, event):
        self.setProperty("hover", False)
        self._restyle()
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(VIDEO_EXTS):
                self.fileDropped.emit(path)
                break

    def _is_video(self, event) -> bool:
        return any(u.toLocalFile().lower().endswith(VIDEO_EXTS)
                   for u in event.mimeData().urls())

    def _restyle(self):
        self.style().unpolish(self)
        self.style().polish(self)
