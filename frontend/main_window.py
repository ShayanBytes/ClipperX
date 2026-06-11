"""
main_window.py - the ClipperX desktop app.

Flow: drop a 16:9 video -> Generate Vertical (runs the reframe pipeline on a
background thread with a live progress bar) -> preview the 9:16 result -> Export.
"""
from __future__ import annotations

import os
import shutil

from PySide6.QtCore import QObject, Qt, QThread, QUrl, Signal, Slot
from PySide6.QtGui import QFont
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QMainWindow, QProgressBar,
    QPushButton, QVBoxLayout, QWidget,
)

from backend.pipeline import probe_meta, reframe
from frontend.widgets import DropZone

STYLESHEET = """
QWidget { background: #0d0e12; color: #e9eaf0; font-family: 'Segoe UI', sans-serif; }
#Title { font-size: 22px; font-weight: 700; }
#Subtitle { color: #8b8e9b; font-size: 13px; }
#DropZone { background: #14161d; border: 2px dashed #2c2f3a; border-radius: 18px; }
#DropZone[hover="true"] { border-color: #6c7bff; background: #181b26; }
#DropIcon { font-size: 46px; color: #6c7bff; }
#DropTitle { font-size: 18px; font-weight: 600; }
#DropSub { color: #8b8e9b; font-size: 13px; }
#Card { background: #14161d; border: 1px solid #23262f; border-radius: 16px; }
#SourceInfo { color: #b9bcc8; font-size: 13px; }
QPushButton { background: #6c7bff; color: white; border: none; border-radius: 12px;
              padding: 12px 22px; font-size: 14px; font-weight: 600; }
QPushButton:hover { background: #7d8bff; }
QPushButton:disabled { background: #2a2d38; color: #6c6f7c; }
QPushButton#Ghost { background: transparent; border: 1px solid #34384a; color: #cdd0db; }
QPushButton#Ghost:hover { background: #1b1e29; }
QProgressBar { background: #1b1e29; border: none; border-radius: 8px; height: 10px; text-align: center; color: transparent; }
QProgressBar::chunk { background: #6c7bff; border-radius: 8px; }
#Stage { color: #9da0ad; font-size: 12px; }
"""


class ReframeWorker(QObject):
    progress = Signal(float, str)
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, input_path: str):
        super().__init__()
        self.input_path = input_path

    @Slot()
    def run(self):
        try:
            out = reframe(self.input_path,
                          progress_cb=lambda p, l: self.progress.emit(p, l))
            self.finished.emit(out)
        except Exception as exc:  # surface any failure to the UI
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ClipperX")
        self.resize(880, 760)
        self.setStyleSheet(STYLESHEET)

        self.input_path: str | None = None
        self.output_path: str | None = None
        self._thread: QThread | None = None
        self._worker: ReframeWorker | None = None

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(18)

        title = QLabel("ClipperX")
        title.setObjectName("Title")
        subtitle = QLabel("Turn 16:9 talking videos into cinematic 9:16 shorts")
        subtitle.setObjectName("Subtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        self.drop = DropZone()
        self.drop.fileDropped.connect(self.on_file)
        layout.addWidget(self.drop)

        self.source_info = QLabel("")
        self.source_info.setObjectName("SourceInfo")
        self.source_info.setVisible(False)
        layout.addWidget(self.source_info)

        # action row
        row = QHBoxLayout()
        self.generate_btn = QPushButton("Generate Vertical")
        self.generate_btn.setEnabled(False)
        self.generate_btn.clicked.connect(self.on_generate)
        row.addWidget(self.generate_btn)
        row.addStretch()
        layout.addLayout(row)

        # progress
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setVisible(False)
        self.stage = QLabel("")
        self.stage.setObjectName("Stage")
        self.stage.setVisible(False)
        layout.addWidget(self.progress)
        layout.addWidget(self.stage)

        # preview
        self.video = QVideoWidget()
        self.video.setMinimumHeight(360)
        self.video.setVisible(False)
        layout.addWidget(self.video, stretch=1)

        self.player = QMediaPlayer()
        self.audio = QAudioOutput()
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video)

        # result row
        self.result_row = QHBoxLayout()
        self.play_btn = QPushButton("Play / Pause")
        self.play_btn.setObjectName("Ghost")
        self.play_btn.clicked.connect(self.toggle_play)
        self.open_btn = QPushButton("Open Folder")
        self.open_btn.setObjectName("Ghost")
        self.open_btn.clicked.connect(self.open_folder)
        self.export_btn = QPushButton("Export…")
        self.export_btn.clicked.connect(self.export_as)
        self.result_row.addWidget(self.play_btn)
        self.result_row.addWidget(self.open_btn)
        self.result_row.addStretch()
        self.result_row.addWidget(self.export_btn)
        self.result_widget = QWidget()
        self.result_widget.setLayout(self.result_row)
        self.result_widget.setVisible(False)
        layout.addWidget(self.result_widget)

    # ---- handlers ----
    def on_file(self, path: str):
        self.input_path = path
        try:
            meta = probe_meta(path)
            info = (f"{os.path.basename(path)}   ·   {meta.width}×{meta.height}   ·   "
                    f"{meta.fps:.0f} fps   ·   {meta.duration:.0f}s")
        except Exception as exc:
            info = f"{os.path.basename(path)}  (could not read: {exc})"
        self.source_info.setText(info)
        self.source_info.setVisible(True)
        self.drop.title.setText("✓ Loaded — drop another to replace")
        self.generate_btn.setEnabled(True)
        self.result_widget.setVisible(False)
        self.video.setVisible(False)

    def on_generate(self):
        if not self.input_path:
            return
        self.generate_btn.setEnabled(False)
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self.stage.setText("Starting…")
        self.stage.setVisible(True)
        self.result_widget.setVisible(False)
        self.video.setVisible(False)
        self.player.setSource(QUrl())  # release any previous file handle

        self._thread = QThread()
        self._worker = ReframeWorker(self.input_path)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self.on_progress)
        self._worker.finished.connect(self.on_finished)
        self._worker.failed.connect(self.on_failed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_thread)
        self._thread.start()

    @Slot(float, str)
    def on_progress(self, pct: float, label: str):
        self.progress.setValue(int(pct * 100))
        self.stage.setText(f"{label}…  {pct*100:.0f}%")

    @Slot(str)
    def on_finished(self, out_path: str):
        self.output_path = out_path
        self.stage.setText(f"Done  ·  {os.path.basename(out_path)}")
        self.progress.setValue(100)
        self.generate_btn.setEnabled(True)
        self.video.setVisible(True)
        self.result_widget.setVisible(True)
        self.player.setSource(QUrl.fromLocalFile(os.path.abspath(out_path)))
        self.player.play()

    @Slot(str)
    def on_failed(self, message: str):
        self.stage.setText(f"Failed: {message}")
        self.generate_btn.setEnabled(True)

    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def open_folder(self):
        if self.output_path:
            folder = os.path.dirname(os.path.abspath(self.output_path))
            try:
                os.startfile(folder)  # Windows
            except AttributeError:
                pass

    def export_as(self):
        if not self.output_path:
            return
        dest, _ = QFileDialog.getSaveFileName(
            self, "Export vertical clip",
            os.path.basename(self.output_path), "MP4 video (*.mp4)")
        if dest:
            shutil.copy(self.output_path, dest)
            self.stage.setText(f"Exported to {dest}")

    def _cleanup_thread(self):
        if self._thread:
            self._thread.deleteLater()
        self._thread = None
        self._worker = None
