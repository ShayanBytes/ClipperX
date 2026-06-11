"""
ClipperX - entry point. Launches the desktop app.
"""
import os
import sys

# Run from the project root so temp/ and exports/ resolve consistently, and
# so `backend` / `frontend` import cleanly regardless of launch directory.
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(PROJECT_ROOT)
sys.path.insert(0, PROJECT_ROOT)

from PySide6.QtWidgets import QApplication  # noqa: E402

from frontend.main_window import MainWindow  # noqa: E402


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("ClipperX")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
